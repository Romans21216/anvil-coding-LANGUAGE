"""The -texture modifier maps a BMP onto a cube (8.13, C backend)."""

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

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)


def write_texture(path: pathlib.Path) -> None:
    """4x4 BMP: four 2x2 quadrants, red/green on top, blue/white below."""
    rows = [
        [RED, RED, GREEN, GREEN],
        [RED, RED, GREEN, GREEN],
        [BLUE, BLUE, WHITE, WHITE],
        [BLUE, BLUE, WHITE, WHITE],
    ]
    stride = (4 * 3 + 3) & ~3
    data = bytearray()
    for row in reversed(rows):
        line = bytearray()
        for r, g, b in row:
            line += bytes((b, g, r))
        line += b"\x00" * (stride - len(line))
        data += line
    header = b"BM" + struct.pack("<IHHI", 54 + len(data), 0, 0, 54)
    info = struct.pack(
        "<IiiHHIIiiII", 40, 4, 4, 1, 24, 0, len(data), 2835, 2835, 0, 0
    )
    path.write_bytes(header + info + bytes(data))


PROGRAM = "\n".join(
    (
        "scene 3d",
        "camera perspective 0 0 6",
        "clear rgba(0, 0, 0, 255)",
        'set var(t) = image_load("tex.bmp")',
        "",
        "fn(main)",
        "  say image_width(var(t))",
        "end",
        "",
        "fn(draw)",
        "  display cube(0, 0, 0, 2) -texture(var(t))",
        "end",
        "call fn(main)",
        "",
    )
)


def close_to(actual: tuple[int, int, int], expected: tuple[int, int, int],
             tolerance: int = 60) -> bool:
    return all(abs(a - b) <= tolerance for a, b in zip(actual, expected))


@unittest.skipUnless(os.name == "nt", "window capture uses Win32")
class CubeTextureTests(unittest.TestCase):
    def test_texture_quadrants_land_on_the_cube_face(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_texture(root / "tex.bmp")
            source = root / "textured.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "textured.exe"
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
                time.sleep(1.0)
                width, height, raw = reader.grab(0, 0, 960, 600)
            finally:
                process.kill()
                process.wait()

            def pixel(x: int, y: int) -> tuple[int, int, int]:
                at = (y * width + x) * 4
                return (raw[at + 2], raw[at + 1], raw[at])

            # The cube covers roughly 400..560 horizontally and 190..410 vertically;
            # sample the middle of each texture quadrant.
            def dominant(pixel_value: tuple[int, int, int]) -> str:
                r, g, b = pixel_value
                if max(r, g, b) < 80:
                    return "dark"
                if r > 1.6 * max(g, b):
                    return "red"
                if g > 1.6 * max(r, b):
                    return "green"
                if b > 1.6 * max(r, g):
                    return "blue"
                if min(r, g, b) > 0.75 * max(r, g, b):
                    return "white"
                return f"mixed{pixel_value}"

            samples = {
                "red": pixel(430, 230),
                "green": pixel(530, 230),
                "blue": pixel(430, 370),
                "white": pixel(530, 370),
            }
            for name, value in samples.items():
                self.assertEqual(dominant(value), name, f"{name} quadrant sampled {value}")

    def test_the_modifier_is_refused_in_wasm(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_texture(root / "tex.bmp")
            source = root / "textured.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            build = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "-o",
                    str(root / "textured.wasm"),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertNotEqual(build.returncode, 0)
            self.assertIn("-texture", build.stderr)
            self.assertIn("wasm", build.stderr)


if __name__ == "__main__":
    unittest.main()
