"""Resource accounting builtins: images, audio, video and total (8.15)."""

from __future__ import annotations

import math
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def write_bmp(path: pathlib.Path, width: int, height: int) -> None:
    row = bytes((30, 60, 200)) * width
    padding = b"\x00" * ((4 - (width * 3) % 4) % 4)
    data = (row + padding) * height
    header = b"BM" + struct.pack("<IHHI", 54 + len(data), 0, 0, 54)
    info = struct.pack(
        "<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(data), 2835, 2835, 0, 0
    )
    path.write_bytes(header + info + data)


def write_wave(path: pathlib.Path, frames: int = 100, rate: int = 8000) -> None:
    samples = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * index / rate)))
        for index in range(frames)
    )
    header = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE"
    chunk = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    path.write_bytes(header + chunk + b"data" + struct.pack("<I", len(samples)) + samples)


PROGRAM = "\n".join(
    (
        "fn(main)",
        "  say memory_images()",
        '  set var(a) = image_load("a.bmp")',
        "  say memory_images()",
        '  set var(b) = image_load("b.bmp")',
        "  say memory_images()",
        "  say image_destroy(var(a))",
        "  say memory_images()",
        "  say image_destroy(var(b))",
        "  say memory_images()",
        "  say memory_video()",
        "  say memory_gpu()",
        "  say memory_total()",
        "  say memory_audio()",
        '  set var(s) = sound_load("tone.wav")',
        "  say memory_audio()",
        "  say sound_destroy(var(s))",
        "  say memory_audio()",
        "end",
        "call fn(main)",
        "",
    )
)


class MemoryBuiltinTests(unittest.TestCase):
    def test_resource_counters_track_loads_and_destroys(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_bmp(root / "a.bmp", 8, 8)
            write_bmp(root / "b.bmp", 4, 4)
            write_wave(root / "tone.wav")
            source = root / "memory.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "memory.exe"
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                [str(executable)], cwd=root, capture_output=True, text=True, timeout=60
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(
                run.stdout.splitlines(),
                [
                    "0",
                    "256",
                    "320",
                    "1",
                    "64",
                    "1",
                    "0",
                    # Two 32-bit backbuffers plus the double-precision depth
                    # buffer: 960*600*4*2 + 960*600*8.
                    "9216000",
                    # The compositor-visible subset: the two DIB sections.
                    "4608000",
                    "9216000",
                    "0",
                    "2400",
                    "1",
                    "0",
                ],
            )


if __name__ == "__main__":
    unittest.main()
