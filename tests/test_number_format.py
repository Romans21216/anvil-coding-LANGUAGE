"""Both backends print numbers the same way: six fractional digits, trimmed."""

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
    "fn(main)\n  say 1 / 3\n  say \"third=\" & 1 / 3\n  say 0.000001\n"
    "  say 10000000000\n  say 123456789.5\n  say -5 % 5\n  say 2\n  say 2.5\n"
    "end\ncall fn(main)\n"
)
EXPECTED = (
    "0.333333\nthird=0.333333\n0.000001\n10000000000\n123456789.5\n0\n2\n2.5\n"
)


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


NEGATIVE_ZERO_PROGRAM = (
    "fn(main)\n  say 0 * -1\n  say -0.0000001\n  say \"x=\" & (0 * -1)\n"
    "  say -0.5\n  say -0.0000006\nend\ncall fn(main)\n"
)
NEGATIVE_ZERO_EXPECTED = "0\n0\nx=0\n-0.5\n-0.000001\n"

# An implicit entry (no `call fn(main)`) must follow the same rules as an
# explicit one: no stray "0" after a say-only main, and main's return value is
# formatted like `say` rather than with printf("%.15g").
IMPLICIT_SAY_PROGRAM = "set var(x) = 5\n\nfn(main)\n  say var(x) * 2\nend\n"
IMPLICIT_SAY_EXPECTED = "10\n"
MAIN_RETURN_PROGRAM = "fn(main)\n  output 1 / 3\nend\n"
MAIN_RETURN_EXPECTED = "0.333333\n"


class NumberFormatCRuntimeTests(unittest.TestCase):
    def test_c_formatting_matches_the_policy(self) -> None:
        self.assertEqual(run_c(PROGRAM), EXPECTED)

    def test_c_drops_the_minus_from_values_that_round_to_zero(self) -> None:
        self.assertEqual(run_c(NEGATIVE_ZERO_PROGRAM), NEGATIVE_ZERO_EXPECTED)

    def test_c_implicit_main_has_no_stray_zero(self) -> None:
        self.assertEqual(run_c(IMPLICIT_SAY_PROGRAM), IMPLICIT_SAY_EXPECTED)

    def test_c_implicit_main_return_is_formatted_like_say(self) -> None:
        self.assertEqual(run_c(MAIN_RETURN_PROGRAM), MAIN_RETURN_EXPECTED)


class NumberFormatNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_formatting_matches_the_policy(self) -> None:
        self.assertEqual(self._run(PROGRAM), EXPECTED)

    def test_native_drops_the_minus_from_values_that_round_to_zero(self) -> None:
        self.assertEqual(self._run(NEGATIVE_ZERO_PROGRAM), NEGATIVE_ZERO_EXPECTED)

    def test_native_implicit_main_has_no_stray_zero(self) -> None:
        self.assertEqual(self._run(IMPLICIT_SAY_PROGRAM), IMPLICIT_SAY_EXPECTED)

    def test_native_implicit_main_return_is_formatted_like_say(self) -> None:
        self.assertEqual(self._run(MAIN_RETURN_PROGRAM), MAIN_RETURN_EXPECTED)


if __name__ == "__main__":
    unittest.main()
