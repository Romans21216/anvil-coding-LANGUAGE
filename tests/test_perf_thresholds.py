"""8.15: published compile-time and executable-size budgets are enforced.

The budgets live in tools/bench_budgets.json and are measured medians times a
multiplier (see tools/bench_anvil.py --write-budgets). This test fails when a
change makes a build slower or larger than the published number, which is what
"thresholds are enforced" means for the roadmap.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools import bench_anvil  # noqa: E402


class PerformanceBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if bench_anvil.find_compiler(None) is None:
            raise unittest.SkipTest("MSVC is not available")
        cls.budgets = bench_anvil.load_budgets()

    def test_the_budget_file_covers_every_case(self) -> None:
        names = {name for name, _ in bench_anvil.CASES}
        program_budgets = {
            key: value for key, value in self.budgets.items() if key != "runtime"
        }
        self.assertEqual(set(program_budgets), names)
        for name, entry in program_budgets.items():
            self.assertIn("native", entry, name)
            self.assertGreater(entry["native"]["seconds"], 0.0, name)
            self.assertGreater(entry["native"]["bytes"], 0, name)
            self.assertIn("c", entry, name)
            self.assertGreater(entry["c"]["seconds"], 0.0, name)
            self.assertGreater(entry["c"]["bytes"], 0, name)
        # Runtime frame budgets share the file but have their own schema.
        self.assertIn("scenes", self.budgets.get("runtime", {}))

    def test_measured_builds_stay_inside_the_published_budgets(self) -> None:
        problems = bench_anvil.violations(
            bench_anvil.CASES, self.budgets, c_repeats=1, native_repeats=2
        )
        self.assertEqual(problems, [])

    def test_a_tighter_budget_would_fail(self) -> None:
        """The checker is not vacuous: an impossible budget must be reported."""
        impossible = {
            "tiny": {
                "native": {"seconds": 0.0, "bytes": 1},
                "c": {"seconds": 0.0, "bytes": 1},
            }
        }
        problems = bench_anvil.violations(
            bench_anvil.CASES[:1], impossible, c_repeats=1, native_repeats=1
        )
        self.assertTrue(problems)
        self.assertTrue(any("exceeds" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
