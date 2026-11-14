"""Lints for dead code and locals nobody reads."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.lints import report, unreachable, unused_locals  # noqa: E402
from compiler.parser import parse  # noqa: E402

ANVIL = ROOT / "compiler" / "anvil.py"


def parse_source(source: str, directory: pathlib.Path):
    path = directory / "program.ANVL"
    path.write_text(source, encoding="utf-8")
    functions, top, variables, arrays = parse(path, source)
    return path, functions, top


class LintTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_code_after_output_is_unreachable(self) -> None:
        source = (
            "fn(f, a)\n"
            "  output var(a)\n"
            '  say "dead"\n'
            "end\n"
            "fn(main)\n  say call fn(f, 1)\nend\ncall fn(main)\n"
        )
        _, functions, _ = parse_source(source, self.base)
        dead = unreachable(functions)
        self.assertEqual(len(dead), 1)
        self.assertEqual(dead[0].kind, "say")
        self.assertEqual(dead[0].line, 3)

    def test_output_at_the_end_is_not_a_warning(self) -> None:
        source = (
            "fn(f, a)\n  output var(a)\nend\n"
            "fn(main)\n  say call fn(f, 1)\nend\ncall fn(main)\n"
        )
        _, functions, _ = parse_source(source, self.base)
        self.assertEqual(unreachable(functions), [])

    def test_output_inside_an_if_only_ends_that_branch(self) -> None:
        source = (
            "fn(f, a)\n"
            "  if var(a) > 0\n"
            "    output 1\n"
            "  end\n"
            "  output 2\n"
            "end\n"
            "fn(main)\n  say call fn(f, 1)\nend\ncall fn(main)\n"
        )
        _, functions, _ = parse_source(source, self.base)
        self.assertEqual(unreachable(functions), [])

    def test_a_local_nobody_reads_is_reported(self) -> None:
        source = (
            "fn(f, a)\n"
            "  set local(spare) = 1\n"
            "  set local(used) = var(a) + local(used)\n"
            "  output local(used)\n"
            "end\n"
            "fn(main)\n  say call fn(f, 1)\nend\ncall fn(main)\n"
        )
        _, functions, _ = parse_source(source, self.base)
        names = [name for _, name in unused_locals(functions)]
        self.assertEqual(names, ["spare"])

    def test_loop_counters_are_not_reported(self) -> None:
        source = (
            "fn(main)\n"
            "  set local(total) = 0\n"
            "  for local(i) = 0 to 3\n"
            "    set local(total) = local(total) + 1\n"
            "  end\n"
            "  say local(total)\n"
            "end\ncall fn(main)\n"
        )
        _, functions, _ = parse_source(source, self.base)
        self.assertEqual(unused_locals(functions), [])

    def test_the_cli_warns_with_a_caret_and_builds(self) -> None:
        path, _, _ = parse_source(
            "fn(main)\n  set local(spare) = 1\n  say 2\nend\ncall fn(main)\n", self.base
        )
        result = subprocess.run(
            [sys.executable, str(ANVIL), str(path), "--check"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning: unused local 'spare'", result.stderr)
        self.assertIn("^", result.stderr)

    def test_deny_warnings_turns_lints_into_failures(self) -> None:
        path, _, _ = parse_source(
            "fn(main)\n  set local(spare) = 1\n  say 2\nend\ncall fn(main)\n", self.base
        )
        result = subprocess.run(
            [sys.executable, str(ANVIL), str(path), "--check", "--deny-warnings"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("1 warning(s) treated as errors", result.stderr)


    def test_a_value_call_to_a_function_without_output_is_reported(self) -> None:
        source = (
            "fn(f, a)\n  say var(a)\nend\n"
            "fn(main)\n  say call fn(f, 7)\nend\ncall fn(main)\n"
        )
        _, functions, top = parse_source(source, self.base)
        messages = [message for message, _ in report(functions, top)]
        self.assertIn("function 'f' has no output, so this call yields 0", messages)

    def test_a_statement_call_to_a_function_without_output_is_fine(self) -> None:
        source = (
            "fn(show, a)\n  say var(a)\nend\n"
            "fn(main)\n  call fn(show, 7)\n  say 1\nend\ncall fn(main)\n"
        )
        _, functions, top = parse_source(source, self.base)
        self.assertEqual(report(functions, top), [])

    def test_output_anywhere_in_the_body_counts(self) -> None:
        source = (
            "fn(f, a)\n  if var(a) > 0\n    output 1\n  end\n  output 0\nend\n"
            "fn(main)\n  say call fn(f, 7)\nend\ncall fn(main)\n"
        )
        _, functions, top = parse_source(source, self.base)
        self.assertEqual(report(functions, top), [])


if __name__ == "__main__":
    unittest.main()
