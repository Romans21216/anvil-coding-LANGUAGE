"""Memory budgets for compile and runtime working sets (Part 8, 8.15)."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "bench_memory.py"
BUDGETS = ROOT / "tools" / "mem_budgets.json"


class MemoryBudgetTests(unittest.TestCase):
    def test_one_scene_reports_compile_and_run_memory(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            report = pathlib.Path(temp) / "memory.json"
            run = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--scene",
                    "idle_2d",
                    "--json",
                    str(report),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            document = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(len(document["results"]), 1)
            result = document["results"][0]
            self.assertEqual(result["scene"], "idle_2d")
            self.assertGreaterEqual(result["compile_peak_mb"], 20.0)
            self.assertGreater(result["generated_bytes"], 1000)
            self.assertGreater(result["exe_bytes"], 50000)
            self.assertGreaterEqual(result["run_peak_mb"], 5.0)

    def test_budgets_hold_for_one_scene(self) -> None:
        run = subprocess.run(
            [
                sys.executable,
                str(TOOL),
                "--check",
                "--scene",
                "idle_2d",
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("memory budgets hold", run.stdout)

    def test_the_budget_file_covers_every_scene(self) -> None:
        budgets = json.loads(BUDGETS.read_text(encoding="utf-8"))
        self.assertGreater(budgets["compile_peak_mb"], 100.0)
        scenes = budgets["run_peak_mb"]
        for name in ("idle_2d", "overdraw_2d", "text_ui", "particles_2d", "cubes_3d"):
            self.assertIn(name, scenes)
            self.assertGreater(scenes[name], 10.0)


if __name__ == "__main__":
    unittest.main()
