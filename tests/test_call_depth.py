"""Runaway recursion is bounded by an explicit stack budget, not the OS.

Part 8 requires recursion to be bounded and reported with a location. Before
this guard a deep recursion died with STATUS_STACK_OVERFLOW (0xC00000FD), no
message, no line, no call stack.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

RECURSION = """\
fn(down, n)
  if var(n) <= 0
    output 0
  end
  output call fn(down, var(n) - 1)
end
fn(main)
  output call fn(down, {depth})
end
"""


def run_source(source: str, *arguments: str):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        path = pathlib.Path(temporary) / "probe.ANVL"
        path.write_text(source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(COMPILER), str(path), *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )


class CallDepthTests(unittest.TestCase):
    def test_runaway_recursion_is_a_controlled_error(self):
        result = run_source(RECURSION.format(depth=100000), "--run")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("call depth exceeded the 512 KiB stack budget", result.stderr)
        self.assertIn("probe.ANVL:1", result.stderr)
        self.assertIn("fn(down)", result.stderr)
        self.assertIn("call stack (innermost first)", result.stderr)
        # The report must be short: the frame table holds 64 entries, not 100k.
        self.assertLess(len(result.stderr), 8000)

    def test_moderate_recursion_still_runs(self):
        result = run_source(RECURSION.format(depth=1000), "--run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("0", result.stdout)

    def test_a_huge_local_array_is_rejected_before_it_can_blow_the_stack(self):
        source = (
            "fn(deep, n)\n"
            "  array big(2000)\n"
            "  set array(big, 0) = var(n)\n"
            "  if var(n) <= 0\n"
            "    output 0\n"
            "  end\n"
            "  output call fn(deep, var(n) - 1)\n"
            "end\n"
            "fn(main)\n"
            "  output call fn(deep, 100000)\n"
            "end\n"
        )
        result = run_source(source, "--run")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("active local arrays exceed", result.stderr)


if __name__ == "__main__":
    unittest.main()
