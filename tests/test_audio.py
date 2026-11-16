"""sound_load/sound_play: bounded WAV playback and its diagnostics."""

from __future__ import annotations

import math
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402

DEVICE_MISSING = "the audio device is unavailable"


def wav_bytes(
    seconds: float = 0.2,
    rate: int = 44100,
    channels: int = 1,
    bits: int = 16,
) -> bytes:
    """A mono sine WAV in the requested shape, written through the wave module."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        path = pathlib.Path(temp) / "tone.wav"
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(channels)
            handle.setsampwidth(bits // 8)
            handle.setframerate(rate)
            frames = bytearray()
            count = int(rate * seconds)
            for i in range(count):
                value = math.sin(2.0 * math.pi * 440.0 * i / rate)
                if bits == 16:
                    sample = int(12000.0 * value)
                    for _ in range(channels):
                        frames += struct.pack("<h", sample)
                elif bits == 8:
                    sample = int(128.0 + 100.0 * value)
                    frames += bytes([sample]) * channels
                else:
                    sample = int(12000.0 * value)
                    for _ in range(channels):
                        frames += struct.pack("<i", sample)[:3]
            handle.writeframes(bytes(frames))
        return path.read_bytes()


def run_c(source: str, files: dict[str, bytes] | None = None) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        temp_path = pathlib.Path(temp)
        for name, payload in (files or {}).items():
            (temp_path / name).write_bytes(payload)
        path = temp_path / "sound.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        c_file = temp_path / "sound.c"
        c_file.write_text(
            emit_c(path, functions, top, variables, arrays), encoding="utf-8"
        )
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        executable = temp_path / "sound.exe"
        build_c(compiler[1], c_file, executable, release=True)
        return subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=60,
            cwd=temp_path,
        )


def lines_of(result: subprocess.CompletedProcess) -> list[str]:
    return result.stdout.replace("\r\n", "\n").splitlines()


class AudioLoadErrorTests(unittest.TestCase):
    def test_a_missing_file_reports_why(self) -> None:
        source = (
            "fn(main)\n"
            '  say sound_load("missing.wav")\n'
            "  say sound_error()\n"
            '  say sound_load("")\n'
            "  say sound_error()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            lines_of(result),
            ["0", "cannot open the file", "0", "the path is empty"],
        )

    def test_a_non_wav_file_is_rejected(self) -> None:
        source = (
            "fn(main)\n"
            '  say sound_load("noise.bin")\n'
            "  say sound_error()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"noise.bin": b"this is not a wav file"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines_of(result), ["0", "the file is not a readable WAV"])

    def test_24_bit_audio_is_rejected(self) -> None:
        source = (
            "fn(main)\n"
            '  say sound_load("wide.wav")\n'
            "  say sound_error()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"wide.wav": wav_bytes(bits=24)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines_of(result), ["0", "only 8- or 16-bit WAV is supported"])

    def test_three_channels_are_rejected(self) -> None:
        source = (
            "fn(main)\n"
            '  say sound_load("three.wav")\n'
            "  say sound_error()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"three.wav": wav_bytes(channels=3)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines_of(result), ["0", "only mono or stereo WAV is supported"])

    def test_a_low_sample_rate_is_rejected(self) -> None:
        source = (
            "fn(main)\n"
            '  say sound_load("slow.wav")\n'
            "  say sound_error()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"slow.wav": wav_bytes(rate=4000)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines_of(result), ["0", "the sample rate is outside 8000..192000 Hz"])

    def test_a_sound_over_the_per_sound_budget_is_rejected(self) -> None:
        # 8 MiB decoded is 2,097,152 stereo frames at 48 kHz, about 43.7 s.
        source = (
            "fn(main)\n"
            '  say sound_load("long.wav")\n'
            "  say sound_error()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"long.wav": wav_bytes(seconds=48.0, rate=48000)})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        self.assertEqual(lines[0], "0")
        self.assertIn("per-sound limit", lines[1])


class AudioPlaybackTests(unittest.TestCase):
    def test_play_controls_and_stop(self) -> None:
        source = (
            "fn(main)\n"
            '  set var(s) = sound_load("tone.wav")\n'
            "  say var(s)\n"
            "  set var(v) = sound_play(var(s))\n"
            "  say var(v)\n"
            "  say sound_active()\n"
            "  say sound_volume(var(v), 0.5)\n"
            "  say sound_pan(var(v), -2)\n"
            "  say sound_pitch(var(v), 9)\n"
            "  say sound_stop(var(v))\n"
            "  say sound_active()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"tone.wav": wav_bytes()})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        if DEVICE_MISSING in lines:
            self.skipTest("no audio device on this machine")
        self.assertEqual(
            lines,
            ["1", "1", "1", "0.5", "-1", "4", "1", "0"],
        )

    def test_voices_are_bounded(self) -> None:
        source = (
            "fn(main)\n"
            '  set var(s) = sound_load("tone.wav")\n'
            "  set var(n) = 0\n"
            "  set var(i) = 0\n"
            "  while var(i) < 8\n"
            "    set var(v) = sound_play(var(s))\n"
            "    if var(v) > 0\n"
            "      add var(n) 1\n"
            "    end\n"
            "    add var(i) 1\n"
            "  end\n"
            "  say var(n)\n"
            "  set var(extra) = sound_play(var(s))\n"
            "  say var(extra)\n"
            "  say sound_active()\n"
            "  say sound_stop_all()\n"
            "  say sound_active()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"tone.wav": wav_bytes()})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        if DEVICE_MISSING in lines:
            self.skipTest("no audio device on this machine")
        self.assertEqual(lines, ["8", "0", "8", "8", "0"])

    def test_a_looping_voice_survives_its_sound_length(self) -> None:
        source = (
            "fn(main)\n"
            '  set var(s) = sound_load("tone.wav")\n'
            "  set var(v) = sound_play_loop(var(s))\n"
            "  say var(v)\n"
            "  wait 0.4\n"
            "  say sound_active()\n"
            "  set var(stopped) = sound_stop(var(v))\n"
            "  say sound_active()\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"tone.wav": wav_bytes(seconds=0.1)})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        if DEVICE_MISSING in lines:
            self.skipTest("no audio device on this machine")
        self.assertEqual(lines, ["1", "1", "0"])

    def test_destroy_stops_voices_and_frees_the_slot(self) -> None:
        source = (
            "fn(main)\n"
            '  set var(s) = sound_load("tone.wav")\n'
            "  set var(v) = sound_play(var(s))\n"
            "  say sound_destroy(var(s))\n"
            "  say sound_active()\n"
            "  set var(again) = sound_load(\"tone.wav\")\n"
            "  say var(again)\n"
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"tone.wav": wav_bytes()})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        if DEVICE_MISSING in lines:
            self.skipTest("no audio device on this machine")
        self.assertEqual(lines, ["1", "0", "1"])


if __name__ == "__main__":
    unittest.main()
