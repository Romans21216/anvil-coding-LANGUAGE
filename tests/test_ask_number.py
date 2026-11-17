"""Numeric `ask`: reading numbers from the console (C backend)."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.common import CompileError  # noqa: E402
from compiler.parser import parse  # noqa: E402
from tests.test_ask import run_c  # noqa: E402
from tests.test_native_x64 import NativeRunMixin  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402


class NumericAskCRuntimeTests(unittest.TestCase):
    def test_whole_number_answer(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(age) = 0\n  ask "Age? ", var(age)\n'
                '  say "Age: ", var(age)\nend\ncall fn(main)\n',
                "42\n",
            ),
            "Age? Age: 42\n",
        )

    def test_decimal_answer(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(price) = 0\n  ask "Price? ", var(price)\n'
                '  say var(price) & " total"\nend\ncall fn(main)\n',
                "3.5\n",
            ),
            "Price? 3.5 total\n",
        )

    def test_arithmetic_on_the_answer(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(a) = 0\n  set var(b) = 0\n'
                '  ask var(a)\n  ask var(b)\n  say var(a) + var(b)\nend\ncall fn(main)\n',
                "2\n3\n",
            ),
            "5\n",
        )

    def test_garbage_answer_becomes_zero(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(n) = 0\n  ask var(n)\n  say var(n)\nend\ncall fn(main)\n',
                "not a number\n",
            ),
            "0\n",
        )


class NumericAskNativeTests(NativeRunMixin, unittest.TestCase):
    """Native numeric ask: whole numbers, negatives, decimals, arithmetic."""

    def _run_with_input(self, text: str, stdin_text: str) -> str:
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
                [str(executable)],
                capture_output=True,
                text=True,
                input=stdin_text,
                timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_native_numeric_ask_whole_number(self) -> None:
        self.assertEqual(
            self._run_with_input(
                'fn(main)\n  set var(age) = 0\n  ask "Age? ", var(age)\n'
                '  say "Age: ", var(age)\nend\ncall fn(main)\n',
                "42\n",
            ),
            "Age? Age: 42\n",
        )


if __name__ == "__main__":
    unittest.main()
