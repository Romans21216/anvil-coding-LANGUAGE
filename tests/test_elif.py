"""`elif` chains: one decision list instead of nested if blocks."""

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

CHAIN = """fn(main)
  set var(n) = 2
  if var(n) = 1
    say "one"
  elif var(n) = 2
    say "two"
  elif var(n) = 3
    say "three"
  else
    say "many"
  end
end
call fn(main)
"""


def parse_source(text: str):
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "sample.ANVL"
        path.write_text(text, encoding="utf-8")
        return parse(path, text)


class ElifParseTests(unittest.TestCase):
    def test_elif_compiles_to_nested_else_if(self) -> None:
        functions, _, _, _ = parse_source(CHAIN)
        body = functions["main"].body
        self.assertEqual([node.kind for node in body], ["set", "if"])
        first = body[1]
        self.assertEqual(first.value, "var(n) = 1")
        self.assertEqual([node.kind for node in first.otherwise], ["if"])
        second = first.otherwise[0]
        self.assertEqual(second.value, "var(n) = 2")
        self.assertEqual([node.kind for node in second.otherwise], ["if"])
        third = second.otherwise[0]
        self.assertEqual(third.value, "var(n) = 3")
        self.assertEqual(
            [(node.kind, node.value) for node in third.otherwise], [("say", '"many"')]
        )

    def test_elif_works_without_else(self) -> None:
        functions, _, _, _ = parse_source(
            'fn(main)\n  set var(n) = 2\n  if var(n) = 1\n    say "a"\n  elif var(n) = 2\n    say "b"\n  end\nend\ncall fn(main)\n'
        )
        first = functions["main"].body[1]
        self.assertEqual(first.value, "var(n) = 1")
        self.assertEqual(first.otherwise[0].value, "var(n) = 2")
        self.assertEqual(first.otherwise[0].otherwise, [])

    def test_elif_after_else_is_rejected(self) -> None:
        with self.assertRaises(CompileError) as caught:
            parse_source(
                'fn(main)\n  if var(n) = 1\n    say "a"\n  else\n    say "b"\n  elif var(n) = 2\n    say "c"\n  end\nend\ncall fn(main)\n'
            )
        self.assertIn("'elif' must directly follow an 'if' body", str(caught.exception))

    def test_elif_outside_if_is_rejected(self) -> None:
        with self.assertRaises(CompileError) as caught:
            parse_source('fn(main)\n  elif var(n) = 1\nend\n')
        self.assertIn("'elif' must directly follow an 'if' body", str(caught.exception))


class ElifCRuntimeTests(unittest.TestCase):
    def test_chain_selects_the_matching_branch(self) -> None:
        self.assertEqual(compile_and_run(CHAIN), "two\n")

    def test_final_else_catches_the_remainder(self) -> None:
        source = CHAIN.replace("set var(n) = 2", "set var(n) = 9")
        self.assertEqual(compile_and_run(source), "many\n")

    def test_elif_without_else_prints_nothing_on_miss(self) -> None:
        source = (
            'fn(main)\n  set var(n) = 5\n  if var(n) = 1\n    say "a"\n  elif var(n) = 2\n    say "b"\n  end\n  say "done"\nend\ncall fn(main)\n'
        )
        self.assertEqual(compile_and_run(source), "done\n")


class ElifNativeRuntimeTests(NativeRunMixin, unittest.TestCase):
    def test_chain_selects_the_matching_branch(self) -> None:
        self.assertEqual(self._run_source(CHAIN), "two\n")

    def test_final_else_catches_the_remainder(self) -> None:
        self.assertEqual(
            self._run_source(CHAIN.replace("set var(n) = 2", "set var(n) = 9")),
            "many\n",
        )


if __name__ == "__main__":
    unittest.main()
