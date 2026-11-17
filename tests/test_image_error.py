"""image_error() explains why image_load() returned 0."""

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
from compiler.common import CompileError  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

PROGRAM = (
    "fn(main)\n"
    '  say image_load("missing.bmp")\n'
    "  say image_error()\n"
    '  say image_load("")\n'
    "  say image_error()\n"
    "end\ncall fn(main)\n"
)


def one_pixel_bmp() -> bytes:
    """A 1x1, 24-bit, bottom-up BMP with one padding byte per row."""
    header = bytearray(54)
    header[0:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + 4)      # file size
    struct.pack_into("<I", header, 10, 54)          # pixel data offset
    struct.pack_into("<I", header, 14, 40)          # DIB header size
    struct.pack_into("<i", header, 18, 1)           # width
    struct.pack_into("<i", header, 22, 1)           # height
    struct.pack_into("<H", header, 26, 1)           # planes
    struct.pack_into("<H", header, 28, 24)          # bits per pixel
    struct.pack_into("<I", header, 34, 4)           # image size
    pixel = bytes((0, 0, 255, 0))                    # blue + padding
    return bytes(header) + pixel


def run_c(source: str, files: dict[str, bytes] | None = None) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        for name, payload in (files or {}).items():
            (temp_path / name).write_bytes(payload)
        path = temp_path / "img.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        c_file = temp_path / "img.c"
        c_file.write_text(
            emit_c(path, functions, top, variables, arrays), encoding="utf-8"
        )
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        executable = temp_path / "img.exe"
        build_c(compiler[1], c_file, executable, release=True)
        return subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=30, cwd=temp_path
        )


class ImageErrorTests(unittest.TestCase):
    def test_a_missing_file_reports_why(self) -> None:
        result = run_c(PROGRAM)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.replace("\r\n", "\n"),
            "0\ncannot open the file\n0\nthe path is empty\n",
        )

    def test_a_loaded_image_clears_the_message(self) -> None:
        source = (
            "fn(main)\n"
            '  say image_load("pixel.bmp")\n'
            '  say "[" & image_error() & "]"\n'
            "end\ncall fn(main)\n"
        )
        result = run_c(source, {"pixel.bmp": one_pixel_bmp()})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.replace("\r\n", "\n").splitlines()
        self.assertNotEqual(lines[0], "0")
        self.assertEqual(lines[1], "[]")

    def test_native_names_the_limitation(self) -> None:
        source = "fn(main)\n  say image_error()\nend\ncall fn(main)\n"
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "img.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            with self.assertRaises(CompileError) as caught:
                NativeCodegen(path, functions, top, variables, arrays).generate()
        self.assertIn("native x64 backend", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
