"""Part 8.14: the stable `format` command normalises without changing meaning."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

sys.path.insert(0, str(ROOT))

from compiler.formatting import format_source  # noqa: E402

MESSY = 'fn(main)\n      say "hi"   \n\n\n\n  if 1\n  say "yes"\n     end\nend\ncall fn(main)\n'
CLEAN = 'fn(main)\n  say "hi"\n\n  if 1\n    say "yes"\n  end\nend\ncall fn(main)\n'


class FormatSourceTests(unittest.TestCase):
    def test_normalises_indentation_whitespace_and_blank_runs(self) -> None:
        self.assertEqual(format_source(MESSY), CLEAN)

    def test_is_idempotent(self) -> None:
        self.assertEqual(format_source(format_source(MESSY)), format_source(MESSY))

    def test_else_dedents_and_reindents(self) -> None:
        source = "fn(main)\nif 1\nsay 1\nelse\nsay 2\nend\nend\n"
        self.assertEqual(
            format_source(source),
            "fn(main)\n  if 1\n    say 1\n  else\n    say 2\n  end\nend\n",
        )

    def test_windows_line_endings_are_normalised(self) -> None:
        self.assertEqual(format_source("fn(main)\r\n  say 1\r\nend\r\n"), "fn(main)\n  say 1\nend\n")


class FormatCommandTests(unittest.TestCase):
    def _compiler(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(COMPILER), *args],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_check_then_format_then_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "prog.ANVL"
            source.write_text(MESSY, encoding="utf-8")

            check = self._compiler(str(source), "--format-check")
            self.assertEqual(check.returncode, 1, check.stdout + check.stderr)
            self.assertIn("would be reformatted", check.stderr)

            formatted = self._compiler(str(source), "--format")
            self.assertEqual(formatted.returncode, 0, formatted.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"), CLEAN)

            again = self._compiler(str(source), "--format-check")
            self.assertEqual(again.returncode, 0, again.stderr)

    def test_a_formatted_example_still_checks_cleanly(self) -> None:
        example = ROOT / "examples" / "first_world.ANVL"
        with tempfile.TemporaryDirectory() as temp:
            copy = pathlib.Path(temp) / "first_world.ANVL"
            copy.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            formatted = self._compiler(str(copy), "--format")
            self.assertEqual(formatted.returncode, 0, formatted.stderr)
            checked = self._compiler(str(copy), "--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertIn("ok", checked.stdout)


if __name__ == "__main__":
    unittest.main()
