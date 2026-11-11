"""`number(text)` parses a text value into a number, both backends."""

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


class NumberParseTests(unittest.TestCase):
    def test_number_rejects_a_number_argument(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = "fn(main)\n  set var(n) = number(42)\nend\n"
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
            with self.assertRaises(CompileError) as caught:
                emit_c(path, functions, top, variables, arrays)
        self.assertIn("expected a string", str(caught.exception))

    def test_number_assigns_a_numeric_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  set var(raw) = "12"\n  set var(n) = number(var(raw))\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
        for node in functions["main"].body:
            if node.kind == "set" and node.name == "n":
                self.assertFalse(node.string)
                break
        else:
            self.fail("n assignment not found")


class NumberCRuntimeTests(unittest.TestCase):
    def _expect(self, text: str, want: str) -> None:
        self.assertEqual(run_c(text), want)

    def test_whole_decimal_negative(self) -> None:
        self._expect(
            'fn(main)\n  say number("42")\n  say number("3.5")\n'
            '  say number("-7")\nend\ncall fn(main)\n',
            "42\n3.5\n-7\n",
        )

    def test_garbage_is_zero(self) -> None:
        self._expect('fn(main)\n  say number("junk")\nend\ncall fn(main)\n', "0\n")

    def test_arithmetic_on_the_result(self) -> None:
        self._expect(
            'fn(main)\n  set var(raw) = "12"\n  say number(var(raw)) + 1\n'
            "end\ncall fn(main)\n",
            "13\n",
        )

    def test_store_into_a_variable(self) -> None:
        self._expect(
            'fn(main)\n  set var(n) = number("42")\n  say var(n)\nend\ncall fn(main)\n',
            "42\n",
        )


class NumberDecimalOnlyTests(unittest.TestCase):
    """`number()` reads decimal text only; hex, inf and nan read as 0."""

    def test_hex_and_inf_read_as_zero(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  say number("0x10")\n  say number("inf")\n'
                '  say number("nan")\n  say number("1_000")\n'
                '  say number("12abc")\nend\ncall fn(main)\n'
            ),
            "0\n0\n0\n1\n12\n",
        )

    def test_exponent_and_signs(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  say number("1e3")\n  say number("+5")\n'
                '  say number("2.5e-2")\n  say number("-3.5")\n'
                '  say number("  7 ")\nend\ncall fn(main)\n'
            ),
            "1000\n5\n0.025\n-3.5\n7\n",
        )


class NumberNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_whole_decimal_negative(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  say number("42")\n  say number("3.5")\n'
                '  say number("-7")\nend\ncall fn(main)\n'
            ),
            "42\n3.5\n-7\n",
        )

    def test_native_garbage_is_zero(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say number("junk")\nend\ncall fn(main)\n'),
            "0\n",
        )

    def test_native_arithmetic_on_the_result(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(raw) = "12"\n  say number(var(raw)) + 1\n'
                "end\ncall fn(main)\n"
            ),
            "13\n",
        )

    def test_native_store_into_a_variable(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(n) = number("42")\n  say var(n)\nend\ncall fn(main)\n'
            ),
            "42\n",
        )

    def test_native_negative_fraction_keeps_its_sign(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  say number("-3.5")\n  say number("-0.5")\n'
                '  say number("-12")\nend\ncall fn(main)\n'
            ),
            "-3.5\n-0.5\n-12\n",
        )

    def test_native_leading_whitespace_is_skipped(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  say number("  7 ")\n  say number(" -2.25 ")\n'
                '  say number("  ")\nend\ncall fn(main)\n'
            ),
            "7\n-2.25\n0\n",
        )

    def test_native_exponent_and_plus_signs(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  say number("1e3")\n  say number("+5")\n'
                '  say number("1E2")\n  say number("2.5e-2")\n'
                '  say number("-1.5e2")\n  say number("1e0")\n'
                '  say number("1e")\n  say number("1x")\nend\ncall fn(main)\n'
            ),
            "1000\n5\n100\n0.025\n-150\n1\n1\n1\n",
        )

    def test_native_roundtrip_with_chr(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  say chr(72) & number("0")\nend\ncall fn(main)\n'
            ),
            "H0\n",
        )


if __name__ == "__main__":
    unittest.main()
