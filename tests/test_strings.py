"""Text variables and `&` joining: strings a beginner can hold and combine."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.common import CompileError  # noqa: E402
from compiler.parser import parse  # noqa: E402
from tests.test_press_enter import compile_binary, run_with_input  # noqa: E402
from tests.test_native_x64 import NativeRunMixin  # noqa: E402


def run_c(text: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        executable = compile_binary(text, "c", pathlib.Path(temp))
        result = run_with_input(executable, "")
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout


def parse_source(text: str):
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "sample.ANVL"
        path.write_text(text, encoding="utf-8")
        return parse(path, text)


class StringRuntimeTests(unittest.TestCase):
    def test_len_of_a_join_and_long_builtin_joins(self) -> None:
        # `len(<join>)` used to be misread as text, and a six-way join of text
        # builtins wrapped the four rotating text buffers.
        self.assertEqual(
            run_c(
                'fn(main)\n  say len("a" & "b")\n'
                '  say upper("a") & upper("b") & upper("c") & upper("d")'
                ' & upper("e") & upper("f")\n'
                '  say len(upper("a") & upper("b"))\n'
                "end\ncall fn(main)\n"
            ),
            "2\nABCDEF\n2\n",
        )

    def test_text_variable_and_join(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  set var(name) = "Ada"\n  say "Hello, " & var(name)\nend\ncall fn(main)\n'),
            "Hello, Ada\n",
        )

    def test_numbers_join_as_text(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(name) = "Ada"\n  set var(lives) = 3\n'
                '  say var(name) & " has " & var(lives) & " lives"\nend\ncall fn(main)\n'
            ),
            "Ada has 3 lives\n",
        )

    def test_joined_text_builtins_and_pure_number_joins(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(a) = "Hello"\n  set var(b) = "World"\n'
                '  set var(s) = upper(var(a)) & lower(var(b))\n  say var(s)\n'
                "  set var(n) = 1 & 2\n  say var(n)\nend\ncall fn(main)\n"
            ),
            "HELLOworld\n12\n",
        )

    def test_joined_text_can_be_stored_then_printed(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(name) = "Ada"\n  set var(msg) = var(name) & "!"\n  say var(msg)\nend\ncall fn(main)\n'
            ),
            "Ada!\n",
        )

    def test_literal_number_join(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  say "Half: " & 0.5\nend\ncall fn(main)\n'),
            "Half: 0.5\n",
        )

    def test_text_survives_updates(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(name) = "Ada"\n  say var(name)\n  set var(name) = "Bo"\n  say var(name)\nend\ncall fn(main)\n'
            ),
            "Ada\nBo\n",
        )

    def test_long_chains_keep_every_value(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  say "1" & "2" & "3" & "4" & "5" & "6"\nend\ncall fn(main)\n'
            ),
            "123456\n",
        )


class StringErrorTests(unittest.TestCase):
    def test_variable_cannot_switch_kind(self) -> None:
        with self.assertRaises(CompileError) as caught:
            parse_source(
                'fn(main)\n  set var(x) = 5\n  set var(x) = "text"\nend\n'
            )
        self.assertIn("cannot mix text and numbers", str(caught.exception))

    def test_text_in_numeric_context_is_rejected(self) -> None:
        # Lowering happens during code generation, not at parse time.
        with self.assertRaises(CompileError) as caught:
            run_c('fn(main)\n  set var(name) = "Ada"\n  output var(name)\nend\ncall fn(main)\n')
        self.assertIn("expected number", str(caught.exception))

class NativeStringRuntimeTests(NativeRunMixin, unittest.TestCase):
    def test_len_of_a_join_and_long_builtin_joins(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  say len("a" & "b")\n'
                '  say upper("a") & upper("b") & upper("c") & upper("d")'
                ' & upper("e") & upper("f")\n'
                '  say len(upper("a") & upper("b"))\n'
                "end\ncall fn(main)\n"
            ),
            "2\nABCDEF\n2\n",
        )

    def test_joined_text_builtins_and_pure_number_joins(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  set var(a) = "Hello"\n  set var(b) = "World"\n'
                '  set var(s) = upper(var(a)) & lower(var(b))\n  say var(s)\n'
                "  set var(n) = 1 & 2\n  say var(n)\nend\ncall fn(main)\n"
            ),
            "HELLOworld\n12\n",
        )

    def test_text_variable_and_join(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  set var(name) = "Ada"\n  say "Hello, " & var(name)\nend\ncall fn(main)\n'
            ),
            "Hello, Ada\n",
        )

    def test_numbers_join_as_text(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  set var(name) = "Ada"\n  set var(lives) = 3\n'
                '  say var(name) & " has " & var(lives) & " lives"\nend\ncall fn(main)\n'
            ),
            "Ada has 3 lives\n",
        )

    def test_joined_text_can_be_stored_then_printed(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  set var(name) = "Ada"\n  set var(msg) = var(name) & "!"\n  say var(msg)\nend\ncall fn(main)\n'
            ),
            "Ada!\n",
        )

    def test_text_survives_updates(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  set var(name) = "Ada"\n  say var(name)\n  set var(name) = "Bo"\n  say var(name)\nend\ncall fn(main)\n'
            ),
            "Ada\nBo\n",
        )

    def test_long_chains_keep_every_value(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  say "1" & "2" & "3" & "4" & "5" & "6"\nend\ncall fn(main)\n'
            ),
            "123456\n",
        )


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()



if __name__ == "__main__":
    unittest.main()
