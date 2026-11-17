"""WASM build profiles have budgets for lightweight and asset import cases."""

from __future__ import annotations

import pathlib
import json
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import bench_build_profiles  # noqa: E402


class BuildProfileBudgetTests(unittest.TestCase):
    def test_published_profile_budgets_cover_all_representative_cases(self) -> None:
        section = json.loads(
            bench_build_profiles.BUDGETS.read_text(encoding="utf-8")
        )["build_profiles"]
        self.assertEqual(set(section["cases"]), set(bench_build_profiles.SOURCES))
        for values in section["cases"].values():
            for key in (
                "budget_total_ms",
                "budget_asset_import_ms",
                "budget_toolchain_link_ms",
                "budget_peak_bytes",
                "budget_peak_working_set_bytes",
                "budget_child_peak_working_set_bytes",
                "budget_toolchain_process_tree_peak_working_set_bytes",
            ):
                self.assertGreater(values[key], 0)

    def test_profile_measurements_stay_inside_published_budgets(self) -> None:
        self.assertEqual(bench_build_profiles.check(), [])

    def test_windows_build_profile_budgets_measure_clang_working_set(self) -> None:
        if sys.platform != "win32":
            self.skipTest("child process working-set counters are Windows-specific")
        values = bench_build_profiles.measure("tiny", repeats=1)
        self.assertGreater(values["child_peak_working_set_bytes"], 0)
        self.assertGreater(values["toolchain_process_tree_peak_working_set_bytes"], 0)
        self.assertGreater(
            values["toolchain_process_tree_peak_working_set_bytes"],
            values["child_peak_working_set_bytes"],
            "the combined sample should include clang's active linker descendant",
        )


if __name__ == "__main__":
    unittest.main()
