"""Part 8.10: bound the source file before reading it into memory."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
LIMIT = 4 * 1024 * 1024


class SourceLimitTests(unittest.TestCase):
    def test_oversized_source_is_rejected_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = root / "big.ANVL"
            source.write_text(
                'fn(main)\n  say "ok"\nend\ncall fn(main)\n', encoding="utf-8"
            )
            with source.open("a", encoding="utf-8") as handle:
                handle.write("a" * (LIMIT + 1))
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "--check"],
                capture_output=True,
                text=True,
                timeout=180,
            )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("4 MiB budget", result.stderr)
        self.assertNotIn("unsupported statement", result.stderr)


if __name__ == "__main__":
    unittest.main()
