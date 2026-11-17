"""--timings reports compiler phases without disturbing the pipeline."""

from __future__ import annotations

import io
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.timing import Timings  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
