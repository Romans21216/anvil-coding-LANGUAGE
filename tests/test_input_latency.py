"""Input-latency budget for a real window (Part 8, 8.15).

Interactive: opens a window, posts key messages and measures the delay until
the program's frame observes ``pressed(A)``. Kept to a few presses so it adds
seconds, not minutes, to the interactive run.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "bench_input.py"
BUDGETS = ROOT / "tools" / "input_budgets.json"


@unittest.skipUnless(sys.platform == "win32", "posting window messages needs Win32")
class InputLatencyTests(unittest.TestCase):
    def test_latency_is_measured_and_within_budget(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            report = pathlib.Path(temp) / "latency.json"
            run = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--samples",
                    "8",
                    "--runs",
                    "1",
                    "--json",
                    str(report),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            document = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(document["samples"], 8)
            self.assertGreater(document["p50_ms"], 0.0)
            self.assertLess(document["max_ms"], 500.0)
            self.assertGreaterEqual(document["p95_ms"], document["p50_ms"])

    def test_budget_gate_passes(self) -> None:
        run = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--check",
                "--samples",
                "8",
                "--runs",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("input latency budgets hold", run.stdout)

    def test_budget_file_is_ordered(self) -> None:
        budgets = json.loads(BUDGETS.read_text(encoding="utf-8"))
        self.assertGreater(budgets["p50_ms"], 10.0)
        self.assertGreaterEqual(budgets["p95_ms"], budgets["p50_ms"])
        self.assertGreaterEqual(budgets["max_ms"], budgets["p95_ms"])


if __name__ == "__main__":
    unittest.main()
