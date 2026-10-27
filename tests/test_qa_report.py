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
        report = report.replace(
            "| 1 | Explicit requirements identified | 2 |",
            "| 1 | Explicit requirements identified | 0 |",
            1,
        )
        report = re.sub(
            r"(\| \| \*\*Requirement fulfillment\*\* \| \*\*)16(?=/20)",
            r"\g<1>14",
            report,
            count=1,
        )
        report = re.sub(
            r"(\| \| \*\*Total\*\* \| \*\*)89(?=/100)",
            r"\g<1>87",
            report,
            count=1,
        )
        report = re.sub(
            r"(\*\*Latest independent evaluation:\*\* \*\*)89(?=/100)",
            r"\g<1>87",
            report,
            count=1,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = pathlib.Path(temp_dir) / "QA_REPORT.md"
            report_path.write_text(report, encoding="utf-8")
            result = self._run_validator(report_path)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("50 criteria = 87/100", result.stdout)

    def test_rejects_mismatched_category_subtotal(self):
        report = REPORT.read_text(encoding="utf-8")
        report = report.replace("**Requirement fulfillment** | **16/20**", "**Requirement fulfillment** | **15/20**", 1)
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = pathlib.Path(temp_dir) / "QA_REPORT.md"
            report_path.write_text(report, encoding="utf-8")
            result = self._run_validator(report_path)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("criterion rows sum", result.stderr)


if __name__ == "__main__":
    unittest.main()
