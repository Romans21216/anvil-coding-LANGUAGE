"""Prefix `not`: negating conditions without comparing against zero by hand."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.common import CompileError  # noqa: E402
from compiler.parser import parse  # noqa: E402
from tests.test_say import compile_and_run  # noqa: E402
from tests.test_native_x64 import NativeRunMixin  # noqa: E402

PROGRAM = """fn(main)
  set var(alive) = 1
  say not 0
  say not var(alive)
  say not var(alive) = 1
  say not 3.5
  say not 0 and 1
  say not 0 or 0
end
call fn(main)
"""


def parse_source(text: str):
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "sample.ANVL"
        path.write_text(text, encoding="utf-8")
        return parse(path, text)


class NotParseTests(unittest.TestCase):
    def test_not_binds_looser_than_comparison(self) -> None:
        functions, _, _, _ = parse_source(
            'fn(main)\n  set var(a) = 0\n  if not var(a) = 1\n  end\nend\n'
        )
        self.assertEqual(functions["main"].body[1].value, "not var(a) = 1")

    def test_bare_not_is_rejected(self) -> None:
        # Statement lowering happens at codegen; exercise the expression layer.
        from compiler.expressions import expr

        with self.assertRaises(CompileError) as caught:
            expr(pathlib.Path("sample.ANVL"), 1, "not")
        self.assertIn("expected an expression", str(caught.exception))

    def test_double_not_negates_twice(self) -> None:
        self.assertEqual(compile_and_run("fn(main)\n  say not not 0\nend\ncall fn(main)\n"), "0\n")


class NotCRuntimeTests(unittest.TestCase):
    def test_truth_table(self) -> None:
        self.assertEqual(
            compile_and_run(PROGRAM),
            "1\n0\n0\n0\n1\n1\n",
        )


class NotNativeRuntimeTests(NativeRunMixin, unittest.TestCase):
    def test_truth_table(self) -> None:
        self.assertEqual(
            self._run_source(PROGRAM),
            "1\n0\n0\n0\n1\n1\n",
        )

    def test_not_inside_if_condition(self) -> None:
        source = (
            'fn(main)\n  set var(dead) = 0\n  if not var(dead)\n    say "alive"\n  end\nend\ncall fn(main)\n'
        )
        self.assertEqual(self._run_source(source), "alive\n")


if __name__ == "__main__":
    unittest.main()
