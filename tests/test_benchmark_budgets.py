"""Keep the Part 8 regression budgets honest without running a build.

GATE 6 asks for agreed thresholds that fail when a metric regresses beyond
noise. The comparison logic is pure, so it is tested on synthetic measurement
dicts; the checked-in budget file is checked for shape and coverage so it cannot
silently drift away from the backends it is supposed to guard.
"""

import copy
import importlib.util
import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUDGETS = ROOT / "tools" / "benchmarks" / "budgets.json"


def _benchmark_module():
    path = ROOT / "tools" / "benchmark.py"
    spec = importlib.util.spec_from_file_location("benchmark", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _results(backends: dict) -> dict:
    """Build a ``measure``-shaped result from ``{backend: {metric: value}}``."""
    shaped = {}
    for backend, metrics in backends.items():
        shaped[backend] = {
            metric: (
                {"median": value, "min": value, "max": value, "samples": [value]}
                if metric.endswith("_seconds")
                else value
            )
            for metric, value in metrics.items()
        }
    return {"machine": {"platform": "test"}, "runs": 1, "backends": shaped}


class BudgetComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _benchmark_module()
        cls.budget = cls.module.load_budgets(BUDGETS)

    def _base(self, backend="c"):
        return dict(self.budget["backends"][backend])

    def _spec(self, metric):
        return self.budget["metrics"][metric]

    def test_measured_at_budget_passes(self):
        base = self._base()
        rows, missing = self.module.compare_budget(_results({"c": base}), self.budget)
        self.assertEqual(missing, [])
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["ok"] for row in rows), rows)

    def test_measured_inside_tolerance_passes(self):
        base = self._base()
        spec = self._spec("build_seconds")
        # Just under the allowed ceiling: base * tolerance + slack.
        allowed = base["build_seconds"] * spec["tolerance"] + spec["slack"]
        base["build_seconds"] = allowed * 0.99
        rows, _ = self.module.compare_budget(_results({"c": base}), self.budget)
        build = next(row for row in rows if row["metric"] == "build_seconds")
        self.assertTrue(build["ok"], build)
        self.assertAlmostEqual(build["allowed"], allowed)

    def test_measured_past_tolerance_fails(self):
        base = self._base()
        spec = self._spec("run_seconds")
        allowed = base["run_seconds"] * spec["tolerance"] + spec["slack"]
        base["run_seconds"] = allowed * 1.05
        rows, _ = self.module.compare_budget(_results({"c": base}), self.budget)
        run = next(row for row in rows if row["metric"] == "run_seconds")
        self.assertFalse(run["ok"], run)
        self.assertGreater(run["actual"], run["allowed"])

    def test_byte_size_uses_tight_ratio(self):
        base = self._base()
        spec = self._spec("exe_bytes")
        self.assertLessEqual(spec["tolerance"], 1.05)
        self.assertEqual(spec["slack"], 0.0)
        base["exe_bytes"] = base["exe_bytes"] * 1.10
        rows, _ = self.module.compare_budget(_results({"c": base}), self.budget)
        size = next(row for row in rows if row["metric"] == "exe_bytes")
        self.assertFalse(size["ok"], size)

    def test_unrecorded_backend_is_reported(self):
        base = self._base()
        rows, missing = self.module.compare_budget(
            _results({"c": base, "mystery": base}), self.budget
        )
        self.assertEqual(missing, ["mystery"])
        self.assertEqual(len(rows), 4)

    def test_checksum_drift_is_reported(self):
        results = _results({"c": self._base()})
        results["backends"]["c"]["checksum"] = "00000000"
        mismatches = self.module.check_checksums(results, self.budget)
        self.assertEqual(len(mismatches), 1)
        self.assertIn("c", mismatches[0])

    def test_matching_checksum_is_silent(self):
        results = _results({"c": self._base()})
        results["backends"]["c"]["checksum"] = self.budget["checksums"]["c"]
        self.assertEqual(self.module.check_checksums(results, self.budget), [])

    def test_allowed_value_matches_formula(self):
        spec = {"tolerance": 1.5, "slack": 0.01}
        self.assertAlmostEqual(self.module.allowed_value(2.0, spec), 3.01)
        self.assertAlmostEqual(self.module.allowed_value(0.0, spec), 0.01)


class BudgetFileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = _benchmark_module()
        cls.budget = json.loads(BUDGETS.read_text(encoding="utf-8"))
        cls.results = {
            "machine": {"platform": "test"},
            "runs": 1,
            "backends": {
                backend: {
                    "build_seconds": {"median": 1.0, "min": 1.0, "max": 1.0, "samples": [1.0]},
                    "run_seconds": {"median": 0.01, "min": 0.01, "max": 0.01, "samples": [0.01]},
                    "startup_seconds": {"median": 0.01, "min": 0.01, "max": 0.01, "samples": [0.01]},
                    "exe_bytes": 1024,
                    "checksum": "1234",
                }
                for backend in cls.module.BACKENDS
            },
        }

    def test_budget_covers_every_backend(self):
        self.assertEqual(set(self.budget["backends"]), set(self.module.BACKENDS))

    def test_budget_records_every_metric(self):
        for backend, metrics in self.budget["backends"].items():
            with self.subTest(backend=backend):
                self.assertEqual(set(metrics), set(self.module.METRICS))

    def test_budget_declares_every_metric_spec(self):
        self.assertEqual(set(self.budget["metrics"]), set(self.module.METRICS))
        for metric, spec in self.budget["metrics"].items():
            with self.subTest(metric=metric):
                self.assertIn("tolerance", spec)
                self.assertIn("slack", spec)
                self.assertGreater(spec["tolerance"], 1.0)

    def test_checksums_agree_across_backends(self):
        checksums = set(self.budget["checksums"].values())
        self.assertEqual(len(checksums), 1, "both backends must print one checksum")
        self.assertEqual(set(self.budget["checksums"]), set(self.module.BACKENDS))

    def test_budget_has_no_unknown_backend(self):
        self.assertTrue(set(self.budget["backends"]) <= set(self.module.BACKENDS))

    def test_write_budget_round_trips(self):
        """--write-budget output must load back and compare cleanly."""
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "budgets.json"
            written = self.module.write_budget(self.results, path)
            reloaded = self.module.load_budgets(path)
            self.assertEqual(reloaded["backends"], written["backends"])
            self.assertEqual(set(reloaded["backends"]), set(self.module.BACKENDS))
            self.assertEqual(
                reloaded["checksums"],
                {backend: "1234" for backend in self.module.BACKENDS},
                "a re-recorded budget must keep the checksum guard",
            )
            rows, missing = self.module.compare_budget(self.results, reloaded)
            self.assertEqual(missing, [])
            self.assertTrue(all(row["ok"] for row in rows), rows)

    def test_render_budget_lists_every_metric(self):
        results = {
            "machine": {"platform": "test"},
            "runs": 1,
            "backends": copy.deepcopy(self.results["backends"]),
        }
        results["backends"]["ghost"] = copy.deepcopy(self.results["backends"]["c"])
        rows, missing = self.module.compare_budget(results, self.budget)
        text = self.module.render_budget(rows, missing, self.budget)
        self.assertIn("## Regression budgets", text)
        for metric in self.module.METRICS:
            self.assertIn(metric, text)
        self.assertIn("no budget recorded", text)
        self.assertIn("ghost", text)

    def test_published_benchmarks_show_the_budget_section(self):
        """docs/BENCHMARKS.md must document the budgets it is checked against."""
        published = (ROOT / "docs" / "BENCHMARKS.md").read_text(encoding="utf-8")
        self.assertIn("## Regression budgets", published)
        for metric in self.budget["metrics"]:
            self.assertIn(metric, published)
        for backend in self.budget["backends"]:
            self.assertIn(f"| {backend} |", published)

    def test_render_budget_reports_checksum_regression(self):
        results = {
            "machine": {"platform": "test"},
            "runs": 1,
            "backends": copy.deepcopy(self.results["backends"]),
        }
        results["backends"]["c"]["checksum"] = "deadbeef"
        rows, missing = self.module.compare_budget(results, self.budget)
        text = self.module.render_budget(
            rows, missing, self.budget, self.module.check_checksums(results, self.budget)
        )
        self.assertIn("Checksum regression", text)


class BudgetCliTests(unittest.TestCase):
    """The gate only matters if the CLI turns a regression into a non-zero exit."""

    @classmethod
    def setUpClass(cls):
        cls.module = _benchmark_module()
        cls.budget = json.loads(BUDGETS.read_text(encoding="utf-8"))

    def _results(self, build_seconds=1.32):
        return {
            "machine": {
                "platform": "test",
                "processor": "test",
                "python": "3.13",
                "c_compiler": "test",
            },
            "runs": 1,
            "backends": {
                "c": {
                    "build_seconds": {
                        "median": build_seconds,
                        "min": build_seconds,
                        "max": build_seconds,
                        "samples": [build_seconds],
                    },
                    "run_seconds": {"median": 0.013, "min": 0.013, "max": 0.013, "samples": [0.013]},
                    "startup_seconds": {"median": 0.006, "min": 0.006, "max": 0.006, "samples": [0.006]},
                    "exe_bytes": 288768,
                    "checksum": "36886024",
                },
                "native": {
                    "build_seconds": {"median": 0.092, "min": 0.092, "max": 0.092, "samples": [0.092]},
                    "run_seconds": {"median": 0.005, "min": 0.005, "max": 0.005, "samples": [0.005]},
                    "startup_seconds": {"median": 0.003, "min": 0.003, "max": 0.003, "samples": [0.003]},
                    "exe_bytes": 70144,
                    "checksum": "36886024",
                },
            },
        }

    def _run_main(self, results, budget_path):
        import contextlib
        import io
        import sys
        import tempfile

        original_measure = self.module.measure
        original_argv = sys.argv
        self.module.measure = lambda runs: results
        out, err = io.StringIO(), io.StringIO()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                report = pathlib.Path(temporary) / "BENCHMARKS.md"
                sys.argv = [
                    "benchmark.py",
                    "--check-budget",
                    "--budget",
                    str(budget_path),
                    "--write",
                    str(report),
                ]
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = self.module.main()
        finally:
            self.module.measure = original_measure
            sys.argv = original_argv
        return code, out.getvalue(), err.getvalue()

    def test_cli_exits_zero_when_within_budget(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "budgets.json"
            path.write_text(json.dumps(self.budget), encoding="utf-8")
            code, out, err = self._run_main(self._results(), path)
        self.assertEqual(code, 0, err)
        self.assertIn("benchmark budget ok", out)

    def test_cli_exits_one_when_a_metric_regresses(self):
        import tempfile

        budget = json.loads(json.dumps(self.budget))
        budget["backends"]["c"]["build_seconds"] = 0.5
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "budgets.json"
            path.write_text(json.dumps(budget), encoding="utf-8")
            code, out, err = self._run_main(self._results(build_seconds=1.35), path)
        self.assertEqual(code, 1, err)
        self.assertIn("OVER BUDGET", out)
        self.assertIn("benchmark budget failed", err)

    def test_cli_exits_one_when_checksum_drifts(self):
        import tempfile

        results = self._results()
        results["backends"]["native"]["checksum"] = "00000000"
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "budgets.json"
            path.write_text(json.dumps(self.budget), encoding="utf-8")
            code, out, err = self._run_main(results, path)
        self.assertEqual(code, 1, err)
        self.assertIn("checksum regression", err)

    def test_cli_exits_two_without_a_budget_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            missing = pathlib.Path(temporary) / "absent.json"
            code, _out, err = self._run_main(self._results(), missing)
        self.assertEqual(code, 2, err)
        self.assertIn("--write-budget", err)


if __name__ == "__main__":
    unittest.main()
