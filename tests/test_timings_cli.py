"""--timings prints honest phase numbers for the C backend and --check."""

from __future__ import annotations

import pathlib
import json
import re
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

PROGRAM = 'fn(main)' + chr(10) + '  say "timed"' + chr(10) + 'end' + chr(10) + 'call fn(main)' + chr(10)

BUILD_LINE = re.compile(
    r"^timings: read \d+ ms, parse \d+ ms, generate \d+ ms, build \d+ ms, total \d+ ms$"
)
CHECK_LINE = re.compile(r"^timings: read \d+ ms, parse \d+ ms, generate \d+ ms, total \d+ ms$")


def run(arguments: list[str]):
    return subprocess.run(
        [sys.executable, str(COMPILER), *arguments],
        capture_output=True,
        text=True,
        timeout=180,
    )


class TimingsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.source = self.root / "timed.ANVL"
        self.source.write_text(PROGRAM, encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_a_build_reports_four_phases(self) -> None:
        result = run([str(self.source), "-o", str(self.root / "timed.exe"), "--timings"])
        if result.returncode != 0 and "No C compiler found" in result.stderr:
            self.skipTest("MSVC is not available")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line for line in result.stderr.splitlines() if line.startswith("timings:")]
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertRegex(lines[0], BUILD_LINE)

    def test_a_normal_build_stays_quiet(self) -> None:
        result = run([str(self.source), "-o", str(self.root / "quiet.exe")])
        if result.returncode != 0 and "No C compiler found" in result.stderr:
            self.skipTest("MSVC is not available")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("timings:", result.stderr)

    def test_check_reports_no_build_phase(self) -> None:
        result = run([str(self.source), "--check", "--timings"])
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = [line for line in result.stderr.splitlines() if line.startswith("timings:")]
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertRegex(lines[0], CHECK_LINE)

    def test_profile_json_records_phases_and_artifact_sizes_without_text_timings(self) -> None:
        profile = self.root / "profile.json"
        result = run(
            [str(self.source), "--check", "--profile-json", str(profile)]
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("timings:", result.stderr)
        report = json.loads(profile.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], "anvil.build-profile")
        self.assertEqual(report["version"], 1)
        self.assertEqual(report["artifacts"]["backend"], "c")
        self.assertEqual(report["artifacts"]["source_bytes"], self.source.stat().st_size)
        self.assertGreater(report["artifacts"]["generated_bytes"], 0)
        self.assertEqual(report["artifacts"]["generated_kind"], "c_source")
        self.assertEqual(report["artifacts"]["output_bytes"], 0)
        self.assertEqual(report["artifacts"]["build_state"], "not_built")
        self.assertEqual(
            [phase["name"] for phase in report["phases"]],
            ["read", "parse", "generate"],
        )

    def test_profile_json_distinguishes_cold_compile_and_warm_cache_hit(self) -> None:
        output = self.root / "cached.exe"
        cold_profile = self.root / "cold.json"
        warm_profile = self.root / "warm.json"
        cold = run(
            [str(self.source), "-o", str(output), "--profile-json", str(cold_profile)]
        )
        if cold.returncode != 0 and "No C compiler found" in cold.stderr:
            self.skipTest("MSVC is not available")
        self.assertEqual(cold.returncode, 0, cold.stdout + cold.stderr)
        warm = run(
            [str(self.source), "-o", str(output), "--profile-json", str(warm_profile)]
        )
        self.assertEqual(warm.returncode, 0, warm.stdout + warm.stderr)
        cold_report = json.loads(cold_profile.read_text(encoding="utf-8"))
        warm_report = json.loads(warm_profile.read_text(encoding="utf-8"))
        self.assertEqual(cold_report["artifacts"]["build_state"], "cold_compile")
        self.assertEqual(warm_report["artifacts"]["build_state"], "warm_cache_hit")
        self.assertGreater(cold_report["artifacts"]["output_bytes"], 0)
        self.assertGreater(warm_report["artifacts"]["output_bytes"], 0)
        for report in (cold_report, warm_report):
            self.assertEqual(
                [phase["name"] for phase in report["phases"]],
                ["read", "parse", "generate", "build"],
            )

    def test_wasm_asset_import_timing_does_not_leak_into_following_c_profile(self) -> None:
        from compiler import cli, wasm

        wasm_profile = self.root / "wasm.json"
        c_profile = self.root / "c.json"

        def fake_wasm_build(*_args, **_kwargs):
            wasm._timed_asset_import(lambda: time.sleep(0.02))()

        with mock.patch.object(wasm, "build", side_effect=fake_wasm_build):
            with mock.patch.object(
                sys, "argv",
                [str(COMPILER), str(self.source), "--backend", "wasm", "-o",
                 str(self.root / "out.wasm"), "--profile-json", str(wasm_profile)],
            ):
                self.assertEqual(cli.main(), 0)
            wasm_report = json.loads(wasm_profile.read_text(encoding="utf-8"))
            self.assertGreater(wasm_report["asset_import"]["value"], 0)

            with mock.patch.object(
                sys, "argv",
                [str(COMPILER), str(self.source), "--check", "--profile-json", str(c_profile)],
            ):
                self.assertEqual(cli.main(), 0)
        c_report = json.loads(c_profile.read_text(encoding="utf-8"))
        self.assertEqual(c_report["asset_import"]["value"], 0)


if __name__ == "__main__":
    unittest.main()
