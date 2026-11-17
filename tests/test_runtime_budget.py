"""The runtime frame-time budgets in tools/bench_budgets.json are enforced."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "bench_runtime.py"
sys.path.insert(0, str(ROOT / "tools"))
from bench_runtime import SCENES  # noqa: E402  (the single list of scenes)


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

    def test_runtime_profile_json_is_versioned_and_describes_sampling(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            output = pathlib.Path(temporary) / "profile.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--scene",
                    "idle_2d",
                    "--runs",
                    "1",
                    "--json",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], "anvil.runtime-profile")
            self.assertEqual(report["version"], 1)
            self.assertEqual(report["sampling"]["warmup_frames_per_run"], 30)
            self.assertEqual(report["sampling"]["sample_frames_per_run"], 120)
            self.assertEqual(report["sampling"]["runs"], 1)
            self.assertIn("platform", report["environment"])
            self.assertIn("idle_2d", report["scenes"])
            metric = report["scenes"]["idle_2d"]["measurements"]["work_p50_ms"]
            self.assertEqual(metric["unit"], "ms")
            self.assertGreaterEqual(metric["value"], 0)
            memory = report["scenes"]["idle_2d"]["measurements"]["peak_working_set_bytes"]
            self.assertEqual(memory["unit"], "bytes")
            if sys.platform == "win32":
                self.assertGreater(memory["value"], 0)


if __name__ == "__main__":
    unittest.main()
