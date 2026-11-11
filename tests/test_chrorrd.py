"""`chr(n)` / `ord(text)`: number-to-character and character-to-number."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.common import CompileError  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from tests.test_native_x64 import NativeRunMixin  # noqa: E402

PROGRAM = (
    'fn(main)\n'
    '  say chr(65)\n'
    '  say chr(97)\n'
    '  say ord("A")\n'
    '  set var(name) = "abc"\n'
    '  say ord(var(name))\n'
    '  say "glyph: " & chr(66)\n'
    '  say chr(ord("Z"))\n'
    'end\n'
    'call fn(main)\n'
)
WANT = "A\na\n65\n97\nglyph: B\nZ\n"


class CaseParseTests(unittest.TestCase):
    def test_ord_rejects_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = "fn(main)\n  set var(n) = ord(65)\nend\n"
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
            with self.assertRaises(CompileError) as caught:
                emit_c(path, functions, top, variables, arrays)
        self.assertIn("expected a string", str(caught.exception))


class ChrOrdCRuntimeTests(unittest.TestCase):
    def _run(self, text: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "sample.ANVL"
            source.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(source, text)
            c_file = temp_path / "sample.c"
            c_file.write_text(
                emit_c(source, functions, top, variables, arrays), encoding="utf-8"
            )
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            executable = temp_path / "sample.exe"
            build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        return result.returncode, result.stdout

    def test_full_program(self) -> None:
        code, out = self._run(PROGRAM)
        self.assertEqual(code, 0)
        self.assertEqual(out, WANT)

    def test_space_and_high_values(self) -> None:
        code, out = self._run(
            'fn(main)\n  say ord(" ")\n  say chr(126)\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "32\n~\n")

    def test_chr_out_of_range_stops_with_error(self) -> None:
        code, out = self._run('fn(main)\n  say chr(300)\nend\ncall fn(main)\n')
        self.assertEqual(code, 1)
        self.assertEqual(out, "")


class ChrOrdNativeTests(NativeRunMixin, unittest.TestCase):
    def _run(self, text: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "sample.ANVL"
            source.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(source, text)
            executable = temp_path / "sample.exe"
            executable.write_bytes(
                NativeCodegen(source, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        return result.returncode, result.stdout + result.stderr

    def test_native_full_program(self) -> None:
        code, out = self._run(PROGRAM)
        self.assertEqual(code, 0)
        self.assertEqual(out, WANT)

    def test_native_space_and_high_values(self) -> None:
        code, out = self._run(
            'fn(main)\n  say ord(" ")\n  say chr(126)\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "32\n~\n")

    def test_native_chr_out_of_range_stops_with_error(self) -> None:
        code, out = self._run('fn(main)\n  say chr(300)\nend\ncall fn(main)\n')
        self.assertEqual(code, 1)
        self.assertIn("chr out of range", out)

    def test_native_chr_negative_stops_with_error(self) -> None:
        code, out = self._run('fn(main)\n  say chr(-1)\nend\ncall fn(main)\n')
        self.assertEqual(code, 1)
        self.assertIn("chr out of range", out)

    def test_native_ord_of_empty_text_is_zero(self) -> None:
        code, out = self._run(
            'fn(main)\n  set var(name) = ""\n  say ord(var(name))\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "0\n")


if __name__ == "__main__":
    unittest.main()
