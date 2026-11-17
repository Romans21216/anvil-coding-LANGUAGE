"""Comparisons printed straight from say/write are numbers, on both backends."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from tests.test_native_x64 import NativeRunMixin  # noqa: E402

PROGRAM = (
    'fn(main)\n  say "a" < "ab"\n  say "ab" > "a"\n  say "a" = "a"\n'
    '  say "a" != "b"\n  say 2 < 3\n'
    '  write "cmp: "\n  write "a" < "b"\n  say ""\nend\ncall fn(main)\n'
)
EXPECTED = "1\n1\n1\n1\n1\ncmp: 1\n"

ZERO_PROGRAM = "fn(main)\n  say -5 % 5\n  say 0 % 5\n  say 7 % 3\nend\ncall fn(main)\n"
ZERO_EXPECTED = "0\n0\n1\n"


def run_c(text: str) -> str:
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
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


class SayExpressionCRuntimeTests(unittest.TestCase):
    def test_comparisons_print_as_numbers(self) -> None:
        self.assertEqual(run_c(PROGRAM), EXPECTED)

    def test_negative_zero_prints_as_zero(self) -> None:
        self.assertEqual(run_c(ZERO_PROGRAM), ZERO_EXPECTED)


class SayExpressionNativeTests(NativeRunMixin, unittest.TestCase):
    def _run(self, text: str) -> str:
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
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.replace("\r\n", "\n")

    def test_native_comparisons_print_as_numbers(self) -> None:
        self.assertEqual(self._run(PROGRAM), EXPECTED)

    def test_native_negative_zero_prints_as_zero(self) -> None:
        self.assertEqual(self._run(ZERO_PROGRAM), ZERO_EXPECTED)


if __name__ == "__main__":
    unittest.main()
