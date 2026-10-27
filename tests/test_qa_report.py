import pathlib
import re
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "QA_REPORT.md"
VALIDATOR = ROOT / "scripts" / "validate_qa_report.py"


class QaReportValidationTests(unittest.TestCase):
    def _run_validator(self, report_path):
        return subprocess.run(
            [sys.executable, str(VALIDATOR), "--report", str(report_path)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_accepts_valid_rubric_with_zero_point_criterion(self):
        report = REPORT.read_text(encoding="utf-8")
        start = report.find("| # | Criterion | Score | Evidence, deduction, and status |")
        end = report.find("### Deduction details and follow-up", start)
        self.assertGreaterEqual(start, 0)
        self.assertGreater(end, start)
        score_rows = re.findall(
            r"^\| (\d+) \| [^\n]*? \| ([012]) \|",
            report[start:end],
            re.MULTILINE,
        )
        criterion, old_score = next(
            (int(number), int(score))
            for number, score in score_rows
            if int(score) == 2
        )
        row = re.compile(rf"^(\| {criterion} \| [^|\n]* \| )2( \|)", re.MULTILINE)
        report, count = row.subn(r"\g<1>0\g<2>", report, count=1)
        self.assertEqual(count, 1)

        category_names = [
            "Requirement fulfillment",
            "Functionality and reliability",
            "Code quality and architecture",
            "Testing and verification",
            "Developer experience and delivery",
        ]
        category_index = (criterion - 1) // 10
        category = category_names[category_index]
        category_row = re.compile(
            rf"^(\| \| \*\*{re.escape(category)}\*\* \| \*\*)(\d+)(/20\*\* \|.*)$",
            re.MULTILINE,
        )
        report, count = category_row.subn(
            lambda match: f"{match.group(1)}{int(match.group(2)) - old_score}{match.group(3)}",
            report,
            count=1,
        )
        self.assertEqual(count, 1)

        total_row = re.compile(r"^(\| \| \*\*Total\*\* \| \*\*)(\d+)(/100\*\* \|.*)$", re.MULTILINE)
        report, count = total_row.subn(
            lambda match: f"{match.group(1)}{int(match.group(2)) - old_score}{match.group(3)}",
            report,
            count=1,
        )
        self.assertEqual(count, 1)
        latest_score = re.compile(r"^(\*\*Latest independent evaluation:\*\* \*\*)(\d+)(/100.*)$", re.MULTILINE)
        report, count = latest_score.subn(
            lambda match: f"{match.group(1)}{int(match.group(2)) - old_score}{match.group(3)}",
            report,
            count=1,
        )
        self.assertEqual(count, 1)
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = pathlib.Path(temp_dir) / "QA_REPORT.md"
            report_path.write_text(report, encoding="utf-8")
            result = self._run_validator(report_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected_total = sum(int(score) for _, score in score_rows) - old_score
        self.assertIn(f"50 criteria = {expected_total}/100", result.stdout)

    def test_rejects_mismatched_category_subtotal(self):
        report = REPORT.read_text(encoding="utf-8")
        row = re.compile(
            r"^(\| \| \*\*Requirement fulfillment\*\* \| \*\*)(\d+)(/20\*\* \|.*)$",
            re.MULTILINE,
        )
        report, count = row.subn(
            lambda match: f"{match.group(1)}{int(match.group(2)) - 1}{match.group(3)}",
            report,
            count=1,
        )
        self.assertEqual(count, 1)
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = pathlib.Path(temp_dir) / "QA_REPORT.md"
            report_path.write_text(report, encoding="utf-8")
            result = self._run_validator(report_path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("criterion rows sum", result.stderr)


if __name__ == "__main__":
    unittest.main()
