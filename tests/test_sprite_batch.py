"""Sprite batching and depth sorting (8.14)."""

from __future__ import annotations

import os
import pathlib
import struct
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
BLUE = (40, 80, 220)


def solid_bmp(path: pathlib.Path, size: int, colour: tuple[int, int, int]) -> None:
    stride = (size * 3 + 3) & ~3
    line = bytes((colour[2], colour[1], colour[0])) * size
    line += b"\x00" * (stride - size * 3)
    data = line * size
    header = b"BM" + struct.pack("<IHHI", 54 + len(data), 0, 0, 54)
    info = struct.pack(
        "<IiiHHIIiiII", 40, size, size, 1, 24, 0, len(data), 2835, 2835, 0, 0
    )
    path.write_bytes(header + info + data)


def program(batch: int, depths: tuple[int, int] | None) -> str:
    lines = [
        "scene 2d",
        "clear rgba(10, 10, 10, 255)",
        'set var(red) = image_load("red.bmp")',
        'set var(blue) = image_load("blue.bmp")',
        f"set var(b) = sprite_batch({batch})",
        "",
        "fn(draw)",
    ]
    if depths is None:
        lines += [
            "  set var(n) = image_draw(var(blue), 380, 200)",
            "  set var(m) = image_draw(var(red), 380, 200)",
        ]
    else:
        lines += [
            f"  set var(d) = sprite_depth({depths[0]})",
            "  set var(n) = image_draw(var(blue), 380, 200)",
            f"  set var(d2) = sprite_depth({depths[1]})",
            "  set var(m) = image_draw(var(red), 420, 220)",
        ]
    lines += ["end", ""]
    return "\n".join(lines)


@unittest.skipUnless(os.name == "nt", "window capture uses Win32")
class SpriteBatchTests(unittest.TestCase):
    def _frame(self, root: pathlib.Path, text: str) -> tuple[int, int, bytes]:
        solid_bmp(root / "red.bmp", 200, RED)
        solid_bmp(root / "blue.bmp", 200, BLUE)
        source = root / "batch.ANVL"
        source.write_text(text, encoding="utf-8")
        executable = root / "batch.exe"
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        process = subprocess.Popen([str(executable)], cwd=root, stdout=subprocess.DEVNULL)
        try:
            reader = WindowReader(process.pid)
            reader.find(time.monotonic() + 10.0)
            time.sleep(1.0)
            return reader.grab(0, 0, 960, 600)
        finally:
            process.kill()
            process.wait()

    @staticmethod
    def _pixel(frame: tuple[int, int, bytes], x: int, y: int) -> tuple[int, int, int]:
        width, _height, raw = frame
        at = (y * width + x) * 4
        return (raw[at + 2], raw[at + 1], raw[at])

    def test_a_higher_depth_wins_regardless_of_submission_order(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            frame = self._frame(pathlib.Path(temp), program(1, (30, 10)))
            # blue was submitted first but has the higher depth, so it is on top
            self.assertEqual(self._pixel(frame, 500, 300), BLUE)
            self.assertEqual(self._pixel(frame, 390, 210), BLUE)
            self.assertEqual(self._pixel(frame, 600, 400), RED)

    def test_equal_depths_keep_submission_order_with_batching_on(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            batched = self._frame(pathlib.Path(temp), program(1, None))
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            immediate = self._frame(pathlib.Path(temp), program(0, None))
        # red is submitted second, so it covers blue at the shared position
        self.assertEqual(self._pixel(batched, 480, 300), RED)
        self.assertEqual(self._pixel(immediate, 480, 300), RED)
        self.assertEqual(self._pixel(batched, 480, 300), self._pixel(immediate, 480, 300))


if __name__ == "__main__":
    unittest.main()
