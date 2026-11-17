"""--timings prints honest phase numbers for the C backend and --check."""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()