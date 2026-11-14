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
        statement, terminator = dead[0]
        self.assertEqual(statement.kind, "say")
        self.assertEqual(statement.line, 3)
        self.assertEqual(terminator, "output")

    def test_code_after_stop_is_unreachable_too(self) -> None:
        source = (
            "fn(main)\n"
            '  say "before"\n'
            "  stop\n"
            '  say "after"\n'
            "end\ncall fn(main)\n"
        )
        path, functions, top = parse_source(source, self.base)
        dead = unreachable(functions)
        self.assertEqual([(statement.kind, terminator) for statement, terminator in dead],
                         [("say", "stop")])
        messages = [m for m, _ in report(functions, top, path)]
        self.assertIn("unreachable statement after stop", messages)

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


    def test_an_unused_function_in_the_entry_file_is_reported(self) -> None:
        source = (
            "fn(spare, a)\n  output var(a)\nend\n"
            "fn(main)\n  say 1\nend\ncall fn(main)\n"
        )
        path, functions, top = parse_source(source, self.base)
        messages = [message for message, _ in report(functions, top, path)]
        self.assertIn("function 'spare' is never called", messages)

    def test_an_unused_function_in_an_included_file_is_not_reported(self) -> None:
        library = self.base / "lib.ANVL"
        library.write_text(
            "fn(helper, a)\n  output var(a)\nend\n", encoding="utf-8"
        )
        source = (
            'include "lib.ANVL"\n\nfn(main)\n  say 1\nend\ncall fn(main)\n'
        )
        path, functions, top = parse_source(source, self.base)
        messages = [message for message, _ in report(functions, top, path)]
        self.assertEqual(messages, [])

    def test_an_unused_parameter_is_reported(self) -> None:
        source = (
            "fn(f, a, b)\n  output var(a)\nend\n"
            "fn(main)\n  say call fn(f, 1, 2)\nend\ncall fn(main)\n"
        )
        path, functions, top = parse_source(source, self.base)
        messages = [message for message, _ in report(functions, top, path)]
        self.assertIn("parameter 'b' of 'f' is never used", messages)


    def test_a_for_loop_that_can_never_run_is_reported(self) -> None:
        cases = {
            "step 0": "  for local(i) = 0 to 3 step 0\n",
            "wrong direction": "  for local(i) = 5 to 1\n",
        }
        for label, loop in cases.items():
            with self.subTest(case=label):
                source = (
                    "fn(main)\n"
                    "  set local(total) = 0\n"
                    + loop
                    + "    set local(total) = local(total) + 1\n"
                    "  end\n  say local(total)\nend\ncall fn(main)\n"
                )
                path, functions, top = parse_source(source, self.base)
                messages = [m for m, _ in report(functions, top, path)]
                self.assertTrue(
                    any(m.startswith("for loop never runs") for m in messages), messages
                )

    def test_a_countdown_with_a_negative_step_is_fine(self) -> None:
        source = (
            "fn(main)\n  set local(total) = 0\n"
            "  for local(i) = 5 to 1 step -1\n"
            "    set local(total) = local(total) + local(i)\n"
            "  end\n  say local(total)\nend\ncall fn(main)\n"
        )
        path, functions, top = parse_source(source, self.base)
        self.assertEqual(report(functions, top, path), [])

    def test_a_loop_with_variable_bounds_is_not_guessed_at(self) -> None:
        source = (
            "fn(main)\n  set local(n) = 3\n"
            "  for local(i) = 0 to local(n)\n    say local(i)\n  end\n"
            "end\ncall fn(main)\n"
        )
        path, functions, top = parse_source(source, self.base)
        self.assertEqual(report(functions, top, path), [])


    def test_number_of_a_non_numeric_literal_is_reported(self) -> None:
        source = (
            "fn(main)\n"
            '  say number("abc")\n'
            '  say number("42")\n'
            '  set var(t) = "7"\n'
            "  say number(var(t))\n"
            "end\ncall fn(main)\n"
        )
        path, functions, top = parse_source(source, self.base)
        messages = [m for m, _ in report(functions, top, path)]
        self.assertEqual(
            [m for m in messages if m.startswith("number(")],
            ['number("abc") is not a number, so it evaluates to 0'],
        )


    def test_a_global_that_is_written_and_never_read_is_reported(self) -> None:
        source = (
            "set var(dead) = 1\n\n"
            "fn(main)\n  set var(live) = 2\n  say var(live)\nend\ncall fn(main)\n"
        )
        path, functions, top = parse_source(source, self.base)
        messages = [m for m, _ in report(functions, top, path)]
        self.assertIn("global 'dead' is never read", messages)
        self.assertNotIn("global 'live' is never read", messages)

    def test_a_discarded_call_result_is_not_reported(self) -> None:
        # `set var(x) = some_call()` is how a value-less call is written.
        source = (
            "fn(main)\n  set var(ignored) = image_width()\n  say 1\nend\ncall fn(main)\n"
        )
        path, functions, top = parse_source(source, self.base)
        messages = [m for m, _ in report(functions, top, path)]
        self.assertEqual([m for m in messages if m.startswith("global")], [])


if __name__ == "__main__":
    unittest.main()
