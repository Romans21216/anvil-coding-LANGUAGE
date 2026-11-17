"""Structured diagnostics for editors: one JSON object per line."""

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def structured(source, *arguments):
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        path = pathlib.Path(temporary) / "probe.ANVL"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(path), "--json-diagnostics", *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    lines = [line for line in result.stderr.splitlines() if line.strip()]
    return result, [json.loads(line) for line in lines]


class JsonDiagnosticsTests(unittest.TestCase):
    def test_error_is_one_json_object_with_a_source_span(self):
        result, records = structured("fn(main)\n output unknown\nend\n")
        self.assertEqual(result.returncode, 1)
        self.assertGreaterEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["severity"], "error")
        self.assertTrue(record["file"].endswith("probe.ANVL"))
        self.assertEqual(record["line"], 2)
        self.assertEqual(record["column"], 9)
        self.assertIn("unknown name", record["message"])
        self.assertIn("var(name)", record["help"])

    def test_warning_is_reported_with_the_same_shape(self):
        result, records = structured(
            "fn(main)\n display rect(0,0,10,10)\n output 0\nend\n", "--check"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        warning = next(record for record in records if record["severity"] == "warning")
        self.assertEqual(warning["line"], 2)
        self.assertIn("has no effect", warning["message"])
        self.assertIn("scene 2d", warning["help"])


if __name__ == "__main__":
    unittest.main()
