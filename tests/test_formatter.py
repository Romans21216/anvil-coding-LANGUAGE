"""Formatter tests: canonical indentation, idempotence, and semantics."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

from compiler.formatter import format_source

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

MESSY = """fn(main)
      set var(x) = 1
 if var(x) > 0
         print "positive"
    else
 print "other"
          end
   end
"""

FORMATTED = """fn(main)
  set var(x) = 1
  if var(x) > 0
    print "positive"
  else
    print "other"
  end
end
"""


class FormatterTests(unittest.TestCase):
    def test_nested_blocks_get_two_space_indentation(self):
        self.assertEqual(format_source(MESSY), FORMATTED)

    def test_formatting_is_idempotent(self):
        once = format_source(MESSY)
        self.assertEqual(format_source(once), once)

    def test_else_if_chain_keeps_one_indentation_level(self):
        source = (
            "fn(main)\n"
            " if 1 = 1\n"
            "  print \"one\"\n"
            " else if 2 = 2\n"
            "  print \"two\"\n"
            " else\n"
            "  print \"other\"\n"
            " end\n"
            "end\n"
        )
        expected = (
            "fn(main)\n"
            "  if 1 = 1\n"
            "    print \"one\"\n"
            "  else if 2 = 2\n"
            "    print \"two\"\n"
            "  else\n"
            "    print \"other\"\n"
            "  end\n"
            "end\n"
        )
        self.assertEqual(format_source(source), expected)

    def test_formatted_source_still_compiles(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            path = pathlib.Path(temporary) / "messy.ANVL"
            path.write_text(MESSY, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(path), "--format"],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            check = subprocess.run(
                [sys.executable, str(COMPILER), str(path), "--check"],
                capture_output=True, text=True,
            )
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("no errors", check.stdout)

    def test_format_check_reports_unformatted_then_formatted(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            path = pathlib.Path(temporary) / "messy.ANVL"
            path.write_text(MESSY, encoding="utf-8")
            unformatted = subprocess.run(
                [sys.executable, str(COMPILER), str(path), "--format-check"],
                capture_output=True, text=True,
            )
            self.assertEqual(unformatted.returncode, 1)
            self.assertIn("needs formatting", unformatted.stderr)
            subprocess.run(
                [sys.executable, str(COMPILER), str(path), "--format"],
                capture_output=True, text=True, check=True,
            )
            formatted = subprocess.run(
                [sys.executable, str(COMPILER), str(path), "--format-check"],
                capture_output=True, text=True,
            )
            self.assertEqual(formatted.returncode, 0)
            self.assertIn("formatted", formatted.stdout)


if __name__ == "__main__":
    unittest.main()
