"""The runtime frame-time budgets in tools/bench_budgets.json are enforced."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "bench_runtime.py"
SCENES = ("idle_2d", "overdraw_2d", "text_ui", "particles_2d", "cubes_3d")


class RuntimeBudgetTests(unittest.TestCase):
    def test_frame_time_budgets_hold(self) -> None:
        result = subprocess.run(
            [sys.executable, str(TOOL), "--check", "--runs", "1"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(
            result.returncode,
            0,
            f"bench_runtime --check failed:\n{result.stdout}\n{result.stderr}",
        )
        for scene in SCENES:
            self.assertIn(scene, result.stdout)
        self.assertIn("runtime budgets: ok", result.stdout)

    def test_scene_list_matches_the_budgets_file(self) -> None:
        import json

        budgets = json.loads((ROOT / "tools" / "bench_budgets.json").read_text(encoding="utf-8"))
        recorded = set(budgets.get("runtime", {}).get("scenes", {}))
        self.assertEqual(recorded, set(SCENES))

    def test_budgets_split_scene_work_from_present(self) -> None:
        """Present cost is platform noise; scene work must have its own budget."""
        import json

        scenes = json.loads(
            (ROOT / "tools" / "bench_budgets.json").read_text(encoding="utf-8")
        )["runtime"]["scenes"]
        for name, entry in scenes.items():
            for key in ("work_p50_ms", "work_p95_ms", "present_p95_ms"):
                self.assertIn(key, entry, f"{name} has no {key} budget")
                self.assertGreater(entry[key], 0.0, f"{name} {key} is not positive")


if __name__ == "__main__":
    unittest.main()
