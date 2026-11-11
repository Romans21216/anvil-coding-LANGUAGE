"""`round(x)` rounds to the nearest whole number, halves away from zero."""

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
    return result.stdout


class RoundCRuntimeTests(unittest.TestCase):
    def _case(self, value: str, want: str) -> None:
        self.assertEqual(
            run_c(f'fn(main)\n  say round({value})\nend\ncall fn(main)\n'),
            want + "\n",
        )

    def test_positive_halves_round_away(self) -> None:
        self._case("2.5", "3")

    def test_negative_halves_round_away(self) -> None:
        self._case("-2.5", "-3")

    def test_fraction_below_half_rounds_down(self) -> None:
        self._case("2.3", "2")

    def test_fraction_above_half_rounds_up(self) -> None:
        self._case("2.7", "3")

    def test_negative_fractions(self) -> None:
        self._case("-2.3", "-2")
        self._case("-2.7", "-3")

    def test_whole_numbers_stay(self) -> None:
        self._case("3", "3")
        self._case("-3", "-3")


class RoundNativeTests(NativeRunMixin, unittest.TestCase):
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
        return result.stdout

    def test_native_positive_halves(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say round(2.5)\nend\ncall fn(main)\n'), "3\n"
        )

    def test_native_negative_halves(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say round(-2.5)\nend\ncall fn(main)\n'), "-3\n"
        )

    def test_native_fractions(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n'
                '  say round(2.3)\n'
                '  say round(2.7)\n'
                '  say round(-2.3)\n'
                '  say round(-2.7)\n'
                'end\ncall fn(main)\n'
            ),
            "2\n3\n-2\n-3\n",
        )

    def test_native_small_values_and_integrals(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n'
                '  say round(0.5)\n'
                '  say round(-0.5)\n'
                '  say round(0.125)\n'
                '  say round(3)\n'
                '  say round(100.25)\n'
                'end\ncall fn(main)\n'
            ),
            "1\n-1\n0\n3\n100\n",
        )

    def test_native_round_in_arithmetic(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(v) = round(2.6) * 10\n'
                '  say var(v)\nend\ncall fn(main)\n'
            ),
            "30\n",
        )


if __name__ == "__main__":
    unittest.main()
