"""`--run` builds the program, runs it, and returns the program's exit code."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def run_cli(source, *arguments):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        path = pathlib.Path(temporary) / "probe.ANVL"
        path.write_text(source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(COMPILER), str(path), *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )


class RunCommandTests(unittest.TestCase):
    def test_run_builds_then_runs_and_returns_the_program_exit_code(self):
        result = run_cli('fn(main)\n print "hello"\n output 0\nend\n', "--run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("hello", result.stdout)
        self.assertIn("Built ", result.stdout)

    def test_run_propagates_a_runtime_failure(self):
        result = run_cli("fn(main)\n output 1 / 0\nend\n", "--run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("division by zero", result.stderr)

    def test_run_cannot_be_combined_with_check_or_emit_c(self):
        result = run_cli("fn(main)\n output 0\nend\n", "--run", "--check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--run builds and runs", result.stderr)


if __name__ == "__main__":
    unittest.main()
