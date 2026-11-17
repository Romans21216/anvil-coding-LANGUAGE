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

    def test_asset_scene_reports_resource_bytes(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            report = pathlib.Path(temp) / "assets.json"
            run = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--scene",
                    "assets",
                    "--json",
                    str(report),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(report.read_text(encoding="utf-8"))["results"][0]
            self.assertEqual(result["scene"], "assets")
            self.assertEqual(result["image_bytes"], 8 * 64 * 64 * 4)
            self.assertEqual(result["video_bytes"], 960 * 600 * 16)  # 2 buffers + depth
            self.assertGreater(result["audio_bytes"], 0)
            self.assertEqual(result["image_bytes_after_destroy"], 7 * 64 * 64 * 4)
            self.assertGreater(result["audio_bytes"], result["audio_bytes_after_destroy"])

    def test_the_audio_scene_reports_decoded_samples(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            report = pathlib.Path(temp) / "audio.json"
            run = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--scene",
                    "audio",
                    "--json",
                    str(report),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(report.read_text(encoding="utf-8"))["results"][0]
        self.assertEqual(result["scene"], "audio")
        # Four 1.5 s mono sources decoded to 48 kHz stereo 16-bit.
        self.assertEqual(result["audio_bytes"], 4 * 72000 * 4)
        self.assertEqual(result["voices_active"], 3)
        self.assertEqual(result["audio_bytes_after_play"], 4 * 72000 * 4)
        self.assertGreaterEqual(result["run_peak_mb"], 1.0)

    def test_the_network_scene_runs_with_a_peer(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            report = pathlib.Path(temp) / "network.json"
            run = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--scene",
                    "network",
                    "--json",
                    str(report),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(report.read_text(encoding="utf-8"))["results"][0]
        self.assertEqual(result["scene"], "network")
        # The socket lives in the kernel, so the process figure stays small;
        # what matters is that the transport ran at all and is measured.
        self.assertGreaterEqual(result["run_peak_mb"], 1.0)
        self.assertGreater(result["run_ms"], 0.0)
        self.assertEqual(result["scene"], "network")
        self.assertNotIn("stdout", result)

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
        for name in ("idle_2d", "overdraw_2d", "text_ui", "particles_2d", "cubes_3d", "audio", "network"):
            self.assertIn(name, scenes)
            self.assertGreater(scenes[name], 10.0)


if __name__ == "__main__":
    unittest.main()
