"""`expect` and `expect_text` assert inside a program and name the failing line."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def run_source(source: str, *arguments: str):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        path = pathlib.Path(temporary) / "probe.ANVL"
        path.write_text(source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(COMPILER), str(path), *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )


class ExpectTests(unittest.TestCase):
    def test_passing_expectations_continue_the_program(self):
        result = run_source(
            'fn(main)\n  expect(2 + 2, 4)\n  expect(round(2.5), 3)\n'
            '  expect_text(upper("ok"), "OK")\n  print "done"\nend\n',
            "--run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("done", result.stdout)

    def test_a_failed_number_expectation_names_the_line_and_exits_one(self):
        result = run_source('fn(main)\n  expect(2 + 2, 5)\nend\n', "--run")
        self.assertEqual(result.returncode, 1)
        self.assertIn("probe.ANVL:2: expect failed: expected 5, got 4", result.stderr)
        self.assertIn("in fn(main)", result.stderr)

    def test_a_failed_text_expectation_reports_both_values(self):
        result = run_source(
            'fn(main)\n  expect_text(lower("NO"), "yes")\nend\n', "--run"
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn('expected "yes", got "no"', result.stderr)

    def test_expect_can_stand_at_the_top_level_of_a_program(self):
        result = run_source(
            'expect(1 + 1, 2)\nfn(main)\n  print "ok"\nend\n', "--run"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
