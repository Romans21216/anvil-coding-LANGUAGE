"""frame_capture() turns the drawn frame into a reusable image (8.14)."""

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

RED = (220, 40, 40)
BACKGROUND = (10, 10, 10)

PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(10, 10, 10, 255)",
        "set var(n) = 0",
        "set var(cap) = 0",
        "",
        "fn(draw)",
        "  set var(n) = compute(var(n) + 1)",
        "  if var(n) == 2",
        "    display rect(100, 100, 200, 200) -rgb(220, 40, 40)",
        "    set var(cap) = frame_capture()",
        "  end",
        "  if var(n) > 2",
        "    # the snapshot is a full-screen image; pasting it at 300,300 moves",
        "    # the square that was drawn at 100,100 to 400,400",
        "    set var(d) = image_draw(var(cap), 300, 300)",
        "  end",
        "end",
        "",
    )
)


@unittest.skipUnless(os.name == "nt", "window capture uses Win32")
class FrameCaptureTests(unittest.TestCase):
    def test_a_captured_frame_can_be_drawn_as_an_image(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "capture.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "capture.exe"
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
                time.sleep(1.2)
                width, height, raw = reader.grab(0, 0, 960, 600)
            finally:
                process.kill()
                process.wait()

            def pixel(x: int, y: int) -> tuple[int, int, int]:
                at = (y * width + x) * 4
                return (raw[at + 2], raw[at + 1], raw[at])

            self.assertEqual(pixel(400, 400), RED)
            self.assertEqual(pixel(700, 500), BACKGROUND)

    def test_the_capture_is_refused_in_wasm(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "capture.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            build = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "-o",
                    str(root / "capture.wasm"),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertNotEqual(build.returncode, 0)
            self.assertIn("frame_capture", build.stderr)
            self.assertIn("wasm", build.stderr)


if __name__ == "__main__":
    unittest.main()
