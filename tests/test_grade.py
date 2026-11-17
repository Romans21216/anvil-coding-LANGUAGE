"""The published grade must hold: the rubric runs and scores at least 8/10."""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from grade_anvil import RUBRIC, main as grade_main  # noqa: E402


class GradeTests(unittest.TestCase):
    def test_rubric_weights_add_up(self) -> None:
        self.assertEqual(sum(weight for _, weight, *_ in RUBRIC), 100)

    def test_language_scores_at_least_eight(self) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = grade_main()
        report = buffer.getvalue()
        match = re.search(r"Score: (\d+)/100\s+->\s+([\d.]+)/10", report)
        self.assertIsNotNone(match, report)
        score = float(match.group(1))
        self.assertEqual(code, 0, report)
        self.assertGreaterEqual(score, 80.0, report)


if __name__ == "__main__":
    unittest.main()
