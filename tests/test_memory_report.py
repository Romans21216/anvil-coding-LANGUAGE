"""memory_report(): name every live allocation with its source line (8.15).

The report is the diagnostic half of resource accounting: memory_total() says
how many bytes are in use, but a leak needs the line that allocated them. The
compiler passes the Anvil file and line to image_load()/sound_load(), the
runtime records them per slot, and memory_report() prints one row per live
resource.
"""

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


# Line numbers matter: the report must name line 3 for the image and line 4 for
# the sound. Keep this program's shape if the assertions are edited.
PROGRAM = "\n".join(
    (
        "fn(main)",
        '  say "start"',
        '  set var(a) = image_load("a.bmp")',
        '  set var(s) = sound_load("tone.wav")',
        "  say memory_report()",
        "  say image_destroy(var(a))",
        "  say memory_report()",
        "end",
        "call fn(main)",
        "",
    )
)


class MemoryReportTests(unittest.TestCase):
    def build_and_run(self, root: pathlib.Path) -> subprocess.CompletedProcess[str]:
        write_bmp(root / "a.bmp", 8, 8)
        write_wave(root / "tone.wav")
        source = root / "report.ANVL"
        source.write_text(PROGRAM, encoding="utf-8")
        executable = root / "report.exe"
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        return subprocess.run(
            [str(executable)], cwd=root, capture_output=True, text=True, timeout=60
        )

    def test_report_names_the_allocating_line(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            run = self.build_and_run(pathlib.Path(temp))
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.splitlines()
            self.assertEqual(lines[0], "start")
            self.assertEqual(lines[1], "Anvil memory report")
            image = lines[2]
            self.assertIn("image 0", image)
            self.assertIn("8x8", image)
            self.assertIn("256 bytes", image)
            self.assertIn("report.ANVL:3", image)
            self.assertTrue(image.endswith("a.bmp"), image)
            sound = lines[3]
            self.assertIn("sound 0", sound)
            self.assertIn("600 frames", sound)
            self.assertIn("2400 bytes", sound)
            self.assertIn("report.ANVL:4", sound)
            self.assertTrue(sound.endswith("tone.wav"), sound)
            self.assertEqual(lines[4], "  live allocations: 2  (256 image bytes, 2400 audio bytes)")
            self.assertEqual(lines[5], "2")
            # image_destroy removes the image from the report but not the sound.
            self.assertEqual(lines[6], "1")
            self.assertEqual(lines[7], "Anvil memory report")
            self.assertIn("sound 0", lines[8])
            self.assertEqual(lines[9], "  live allocations: 1  (0 image bytes, 2400 audio bytes)")

    def test_wasm_refuses_the_report(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "refuse.ANVL"
            source.write_text("\n".join((
                "scene 2d",
                "clear rgba(10, 12, 18, 255)",
                "set var(live) = memory_report()",
                "fn(draw)",
                "  display rect(10, 10, 40, 40) -rgb(255, 0, 0)",
                "end",
                "",
            )), encoding="utf-8")
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "--backend", "wasm",
                 "-o", str(root / "refuse.wasm")],
                capture_output=True, text=True, timeout=180,
            )
            self.assertNotEqual(build.returncode, 0)
            combined = build.stdout + build.stderr
            self.assertIn("'memory_report' is not available in the wasm backend yet", combined)
            self.assertIn(":3:", combined)


if __name__ == "__main__":
    unittest.main()
