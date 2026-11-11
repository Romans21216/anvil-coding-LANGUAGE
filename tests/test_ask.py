"""`ask` reads one console line into a text variable, both backends."""

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
from tests.test_native_x64 import NativeRunMixin  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402

PROGRAM = """fn(main)
  ask "Name? ", var(name)
  say "Hello, " & var(name)
end
call fn(main)
"""

NUMERIC_PROGRAM = """fn(main)
  set var(age) = 0
  ask "Age? ", var(age)
  say "Age: ", var(age)
end
call fn(main)
"""


def run_c(text: str, stdin_text: str) -> str:
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
            [str(executable)],
            capture_output=True,
            text=True,
            input=stdin_text,
            timeout=15,
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout


class AskParseTests(unittest.TestCase):
    def test_ask_splits_prompt_and_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  ask "Name? ", var(name)\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
        ask = functions["main"].body[0]
        self.assertEqual(ask.kind, "ask")
        self.assertEqual(ask.value, '"Name? "')
        self.assertEqual(ask.params, ["name"])
        self.assertIn("name", variables)

    def test_ask_without_a_variable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  ask "Name?"\nend\n'
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, text)
        self.assertIn("needs a variable", str(caught.exception))

    def test_ask_target_follows_the_variable_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  set var(age) = 9\n  ask "Age? ", var(age)\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
        ask = functions["main"].body[1]
        self.assertEqual(ask.string, False)  # numeric ask for a numeric variable


class AskCRuntimeTests(unittest.TestCase):
    def test_prompt_answer_and_join(self) -> None:
        self.assertEqual(
            run_c(PROGRAM, "Ada\n"),
            "Name? Hello, Ada\n",
        )

    def test_ask_without_prompt(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  ask var(nick)\n  say "Hey " & var(nick)\nend\ncall fn(main)\n', "Bo\n"),
            "Hey Bo\n",
        )

    def test_empty_answer_still_joins(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  ask "Name? ", var(name)\n  say "Hi " & var(name) & "!"\nend\ncall fn(main)\n', "\n"),
            "Name? Hi !\n",
        )


class AskNativeRuntimeTests(NativeRunMixin, unittest.TestCase):
    def _run_with_input(self, source: str, stdin_text: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
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

    def test_prompt_answer_and_join(self) -> None:
        self.assertEqual(self._run_with_input(PROGRAM, "Ada\n"), "Name? Hello, Ada\n")

    def test_ask_without_prompt(self) -> None:
        self.assertEqual(
            self._run_with_input(
                'fn(main)\n  ask var(nick)\n  say "Hey " & var(nick)\nend\ncall fn(main)\n',
                "Bo\n",
            ),
            "Hey Bo\n",
        )

    def test_ask_only_main_prints_no_stray_zero(self) -> None:
        self.assertEqual(
            self._run_with_input(
                'fn(main)\n  ask "Name? ", var(name)\nend\ncall fn(main)\n',
                "Ada\n",
            ),
            "Name? ",
        )

    def test_two_text_asks_keep_both_lines(self) -> None:
        source = (
            'fn(main)\n  set var(first) = ""\n  set var(last) = ""\n'
            '  ask "first? ", var(first)\n  ask "last? ", var(last)\n'
            '  say var(last) & ", " & var(first)\nend\ncall fn(main)\n'
        )
        self.assertEqual(
            self._run_with_input(source, "Ada\nLovelace\n"),
            "first? last? Lovelace, Ada\n",
        )

    def test_three_numeric_asks_sum(self) -> None:
        source = (
            "fn(main)\n  set var(a) = 0\n  set var(b) = 0\n  set var(c) = 0\n"
            '  ask "1? ", var(a)\n  ask "2? ", var(b)\n  ask "3? ", var(c)\n'
            "  say var(a) + var(b) + var(c)\nend\ncall fn(main)\n"
        )
        self.assertEqual(self._run_with_input(source, "1\n2\n3\n"), "1? 2? 3? 6\n")

    def test_empty_first_answer_keeps_the_second(self) -> None:
        source = (
            "fn(main)\n  set var(a) = 0\n  set var(b) = 4\n"
            '  ask "a? ", var(a)\n  ask "b? ", var(b)\n'
            "  say var(a) + var(b)\nend\ncall fn(main)\n"
        )
        self.assertEqual(self._run_with_input(source, "\n4\n"), "a? b? 4\n")

    def test_crlf_input_is_stripped(self) -> None:
        source = (
            "fn(main)\n  set var(a) = 0\n  set var(b) = 0\n"
            '  ask "a? ", var(a)\n  ask "b? ", var(b)\n'
            "  say var(a) + var(b)\nend\ncall fn(main)\n"
        )
        self.assertEqual(
            self._run_with_input(source, "3" + chr(13) + chr(10) + "4" + chr(13) + chr(10)),
            "a? b? 7\n",
        )


class NativeNumericAskTests(NativeRunMixin, unittest.TestCase):
    """Numeric `ask` on the native x64 backend: prompt, parse, arithmetic."""

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

    def test_numeric_ask_whole_number(self) -> None:
        self.assertEqual(
            self._run_with_input(NUMERIC_PROGRAM, "42\n"),
            "Age? Age: 42\n",
        )

    def test_numeric_ask_negative(self) -> None:
        self.assertEqual(
            self._run_with_input(NUMERIC_PROGRAM, "-5\n"),
            "Age? Age: -5\n",
        )

    def test_numeric_ask_decimal(self) -> None:
        self.assertEqual(
            self._run_with_input(NUMERIC_PROGRAM, "3.5\n"),
            "Age? Age: 3.5\n",
        )

    def test_numeric_ask_fraction_only(self) -> None:
        self.assertEqual(
            self._run_with_input(NUMERIC_PROGRAM, "0.125\n"),
            "Age? Age: 0.125\n",
        )

    def test_numeric_ask_arithmetic(self) -> None:
        self.assertEqual(
            self._run_with_input(
                'fn(main)\n'
                '  set var(a) = 0\n'
                '  ask var(a)\n'
                '  say "Twice: ", var(a) * 2 + 1\n'
                'end\ncall fn(main)\n',
                "7\n",
            ),
            "Twice: 15\n",
        )

    def test_numeric_ask_garbage_is_zero(self) -> None:
        self.assertEqual(
            self._run_with_input(NUMERIC_PROGRAM, "junk\n"),
            "Age? Age: 0\n",
        )




if __name__ == "__main__":
    unittest.main()
