"""image_error() names the exact limit that rejected an oversized BMP."""

from __future__ import annotations

import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402

PROGRAM = (
    "fn(main)\n"
    '  say image_load("probe.bmp")\n'
    "  say image_error()\n"
    "end\ncall fn(main)\n"
)


def bmp_header(width: int, height: int, bits: int = 24) -> bytes:
    """A valid BMP header with no pixel data.

    The loader validates dimensions, pixel count and the memory budget from
    the header before it reads pixels, so a header alone is enough to prove a
    rejection.
    """
    row_stride = (width * (bits // 8) + 3) & ~3
    image_bytes = row_stride * abs(height)
    header = bytearray(54)
    header[0:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + image_bytes)
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<i", header, 18, width)
    struct.pack_into("<i", header, 22, height)
    struct.pack_into("<H", header, 26, 1)
    struct.pack_into("<H", header, 28, bits)
    struct.pack_into("<I", header, 34, image_bytes)
    return bytes(header)


def run_c(files: dict[str, bytes]) -> subprocess.CompletedProcess:
    compiler = find_compiler(None)
    if compiler is None:
        raise unittest.SkipTest("MSVC is not available")
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        for name, payload in files.items():
            (temp_path / name).write_bytes(payload)
        source = temp_path / "img.ANVL"
        source.write_text(PROGRAM, encoding="utf-8")
        functions, top, variables, arrays = parse(source, PROGRAM)
        c_file = temp_path / "img.c"
        c_file.write_text(
            emit_c(source, functions, top, variables, arrays), encoding="utf-8"
        )
        executable = temp_path / "img.exe"
        build_c(compiler[1], c_file, executable, release=True)
        return subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=30, cwd=temp_path
        )


class ImageLimitTests(unittest.TestCase):
    def lines(self, payload: bytes) -> list[str]:
        result = run_c({"probe.bmp": payload})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.replace("\r\n", "\n").splitlines()

    def test_a_width_over_the_limit_names_the_number(self) -> None:
        lines = self.lines(bmp_header(8193, 1))
        self.assertEqual(lines[0], "0")
        self.assertEqual(lines[1], "the image is 8193 pixels wide; the limit is 8192")

    def test_a_height_over_the_limit_names_the_number(self) -> None:
        lines = self.lines(bmp_header(1, 8193))
        self.assertEqual(lines[0], "0")
        self.assertEqual(lines[1], "the image is 8193 pixels tall; the limit is 8192")

    def test_a_pixel_count_over_the_limit_names_the_numbers(self) -> None:
        lines = self.lines(bmp_header(4097, 4097))
        self.assertEqual(lines[0], "0")
        self.assertEqual(
            lines[1], "the image has 16785409 pixels; the limit is 16777216"
        )

    def test_a_truncated_file_names_the_shortfall(self) -> None:
        # Within every limit, but the header promises rows that are not there.
        lines = self.lines(bmp_header(4, 4))
        self.assertEqual(lines[0], "0")
        self.assertEqual(lines[1], "the file is too short for the declared image size")

    def test_the_largest_allowed_width_still_loads(self) -> None:
        row_stride = 8192 * 3
        payload = bmp_header(8192, 1) + bytes(row_stride)
        lines = self.lines(payload)
        self.assertNotEqual(lines[0], "0", lines)
        self.assertEqual(lines[1], "")


if __name__ == "__main__":
    unittest.main()
