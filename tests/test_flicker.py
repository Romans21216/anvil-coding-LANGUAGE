"""The window must never show the black paint background (flicker regression)."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

sys.path.insert(0, str(ROOT / "tests"))
from test_sprite_draw import WindowReader  # noqa: E402

CONTENT = (200, 40, 40)

PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(30, 60, 90, 255)",
        "",
        "fn(draw)",
        f"  display rect(0, 0, 960, 600) -rgb({CONTENT[0]}, {CONTENT[1]}, {CONTENT[2]})",
        "end",
        "",
    )
)


@unittest.skipUnless(os.name == "nt", "window capture uses Win32")
class FlickerTests(unittest.TestCase):
    def test_a_static_frame_never_flashes_the_background(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "steady.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "steady.exe"
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            process = subprocess.Popen(
                [str(executable)], cwd=root, stdout=subprocess.DEVNULL
            )
            try:
                reader = WindowReader(process.pid)
                reader.find(time.monotonic() + 10.0)
                time.sleep(0.6)
                frames = []
                for _ in range(20):
                    frames.append(reader.grab(0, 0, 960, 600))
                    time.sleep(0.012)
            finally:
                process.kill()
                process.wait()

            worst = 1.0
            for index, (width, height, raw) in enumerate(frames):
                total = width * height
                matching = 0
                black = 0
                for at in range(0, len(raw), 4):
                    pixel = (raw[at + 2], raw[at + 1], raw[at])
                    if pixel == CONTENT:
                        matching += 1
                    if pixel == (0, 0, 0):
                        black += 1
                coverage = matching / total
                worst = min(worst, coverage)
                self.assertLess(
                    black / total,
                    0.02,
                    f"frame {index} is {black / total:.1%} black — the paint "
                    "background flashed through",
                )
                self.assertGreater(
                    coverage,
                    0.9,
                    f"frame {index} shows the solid rectangle on only "
                    f"{coverage:.1%} of the window",
                )
            self.assertGreater(worst, 0.9)


if __name__ == "__main__":
    unittest.main()
