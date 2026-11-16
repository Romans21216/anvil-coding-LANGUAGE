"""PCM WAV loading, inspection and playback entry points."""

import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def make_wav(rate=8000, samples=400):
    """Build a mono 16-bit PCM WAV so tests do not depend on binary fixtures."""
    data = struct.pack("<" + "h" * samples, *([1000] * samples))
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    chunks = (
        b"fmt " + struct.pack("<I", len(fmt)) + fmt
        + b"data" + struct.pack("<I", len(data)) + data
    )
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def run_program(folder: pathlib.Path, source: str, *arguments: str):
    path = folder / "probe.ANVL"
    path.write_text(source, encoding="utf-8")
    build = subprocess.run(
        [sys.executable, str(COMPILER), str(path), "--run", *arguments],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(folder),
    )
    return build


class AudioTests(unittest.TestCase):
    def test_load_rejects_missing_and_malformed_files(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder = pathlib.Path(temporary)
            (folder / "tone.wav").write_bytes(make_wav())
            (folder / "bad.wav").write_bytes(b"not a wave file")
            result = run_program(
                folder,
                'fn(main)\n'
                '  set var(a) = sound_load("missing.wav")\n'
                '  set var(b) = sound_load("bad.wav")\n'
                '  set var(c) = sound_load("tone.wav")\n'
                '  print "abc=" + var(a) + var(b) + var(c)\n'
                'end\n',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("abc=001", result.stdout)

    def test_a_loaded_file_reports_its_rate_and_byte_length(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder = pathlib.Path(temporary)
            wav = make_wav(rate=11025, samples=256)
            (folder / "tone.wav").write_bytes(wav)
            result = run_program(
                folder,
                'fn(main)\n'
                '  set var(s) = sound_load("tone.wav")\n'
                '  print "rate=" + sound_rate(var(s)) + " bytes=" + sound_length(var(s))\n'
                'end\n',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"rate=11025 bytes={len(wav)}", result.stdout)

    def test_invalid_handles_never_play_or_stop_anything(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder = pathlib.Path(temporary)
            result = run_program(
                folder,
                'fn(main)\n'
                '  print "play=" + sound_play(99) + " stop=" + sound_stop()\n'
                '  print "rate=" + sound_rate(99) + " len=" + sound_length(99)\n'
                'end\n',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("play=0 stop=0", result.stdout)
            self.assertIn("rate=0 len=0", result.stdout)

    def test_the_native_backend_rejects_sound_calls_with_a_location(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder = pathlib.Path(temporary)
            path = folder / "probe.ANVL"
            path.write_text(
                'fn(main)\n  set var(s) = sound_load("tone.wav")\nend\n',
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(path), "--backend", "native", "--check"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                cwd=str(folder),
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("sound_load", result.stderr)
            self.assertIn("probe.ANVL:2", result.stderr)


if __name__ == "__main__":
    unittest.main()
