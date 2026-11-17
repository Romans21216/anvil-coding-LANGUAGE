"""--timings reports compiler phases without disturbing the pipeline."""

from __future__ import annotations

import io
import json
import pathlib
import re
import sys
import tempfile
import time
import tracemalloc
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.timing import Timings  # noqa: E402
from compiler import gltf  # noqa: E402

LINE = re.compile(r"^timings: (?P<phases>.+)$")


def parse_line(text: str) -> list[tuple[str, int]]:
    match = LINE.match(text.strip())
    if not match:
        raise AssertionError(f"not a timings line: {text!r}")
    entries = []
    for part in match.group("phases").split(", "):
        name, value, unit = part.split(" ")
        if unit != "ms":
            raise AssertionError(f"unexpected unit in {part!r}")
        entries.append((name, int(value)))
    return entries


class TimingTests(unittest.TestCase):
    def test_disabled_prints_nothing(self) -> None:
        timings = Timings(False)
        timings.mark("parse")
        out = io.StringIO()
        timings.report(out)
        self.assertEqual(out.getvalue(), "")

    def test_phases_keep_their_order_with_a_total(self) -> None:
        timings = Timings(True)
        timings.mark("read")
        timings.mark("parse")
        timings.mark("generate")
        out = io.StringIO()
        timings.report(out)
        entries = parse_line(out.getvalue())
        self.assertEqual([name for name, _ in entries], ["read", "parse", "generate", "total"])
        total = entries[-1][1]
        self.assertEqual(total, sum(value for _, value in entries[:-1]))

    def test_values_are_not_negative(self) -> None:
        timings = Timings(True)
        timings.mark("parse")
        out = io.StringIO()
        timings.report(out)
        self.assertTrue(all(value >= 0 for _, value in parse_line(out.getvalue())))

    def test_report_without_marks_is_silent(self) -> None:
        timings = Timings(True)
        out = io.StringIO()
        timings.report(out)
        self.assertEqual(out.getvalue(), "")

    def test_a_slow_phase_is_recorded_in_milliseconds(self) -> None:
        timings = Timings(True)
        start = timings._started  # noqa: SLF001 - the test measures the same clock
        timings._started = start - 0.25  # noqa: SLF001
        timings.mark("build")
        out = io.StringIO()
        timings.report(out)
        entries = dict(parse_line(out.getvalue()))
        self.assertGreaterEqual(entries["build"], 240)

    def test_json_profile_is_versioned_and_keeps_phase_units(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "profile.json"
            timings = Timings(False, path)
            timings.set_metadata(backend="c", source_bytes=23)
            timings._started -= 0.01  # noqa: SLF001 - deterministic phase in this test
            timings.mark("read")
            timings._started -= 0.02  # noqa: SLF001
            timings.mark("parse")
            timings.report()
            report = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(report["schema"], "anvil.build-profile")
        self.assertEqual(report["version"], 1)
        self.assertEqual([phase["name"] for phase in report["phases"]], ["read", "parse"])
        self.assertTrue(all(phase["unit"] == "ms" for phase in report["phases"]))
        self.assertEqual(report["artifacts"], {"backend": "c", "source_bytes": 23})
        self.assertGreater(report["memory"]["peak_bytes"], 0)
        if sys.platform == "win32":
            self.assertGreater(report["memory"]["peak_working_set_bytes"], 0)
        self.assertEqual(
            report["memory"]["measurement"], "Python allocations traced by tracemalloc"
        )
        self.assertEqual(report["asset_import"]["unit"], "ms")

    def test_json_profile_uses_invocation_peak_when_tracing_is_already_active(self) -> None:
        if tracemalloc.is_tracing():
            self.skipTest("test requires ownership of the process tracing session")
        tracemalloc.start()
        try:
            old_peak = bytearray(2_000_000)
            del old_peak
            with tempfile.TemporaryDirectory() as temporary:
                path = pathlib.Path(temporary) / "profile.json"
                timings = Timings(False, path)
                invocation_allocation = bytearray(32_000)
                del invocation_allocation
                timings.mark("build")
                timings.report()
                report = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(tracemalloc.is_tracing())
            self.assertGreater(report["memory"]["peak_bytes"], 0)
            self.assertLess(report["memory"]["peak_bytes"], 1_000_000)
        finally:
            tracemalloc.stop()

    def test_asset_import_time_is_captured_only_when_enabled(self) -> None:
        gltf.reset_import_time()
        gltf.measure_import_time(False)
        with mock.patch.object(gltf, "_ensure_model", side_effect=lambda *_: time.sleep(0.01)):
            gltf.ensure_model("unused.gltf", pathlib.Path("."))
            self.assertEqual(gltf.import_time_seconds(), 0.0)
            gltf.measure_import_time(True)
            gltf.ensure_model("unused.gltf", pathlib.Path("."))
        gltf.measure_import_time(False)
        self.assertGreater(gltf.import_time_seconds(), 0.0)

    def test_disabled_timing_without_json_does_not_start_a_clock(self) -> None:
        with mock.patch("compiler.timing.tracemalloc.start", side_effect=AssertionError):
            timings = Timings(False)
        self.assertEqual(timings._started, 0.0)  # noqa: SLF001
        self.assertFalse(timings.capture_enabled)
        self.assertFalse(timings._owns_trace)  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
