"""The published backend capability matrix must match measured behaviour."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "capability_matrix.py"

sys.path.insert(0, str(ROOT))

from compiler.build import find_compiler  # noqa: E402


class CapabilityMatrixTests(unittest.TestCase):
    def test_committed_matrix_matches_the_current_backends(self) -> None:
        if find_compiler(None) is None:
            raise unittest.SkipTest("MSVC is not available")
        result = subprocess.run(
            [sys.executable, str(TOOL), "--check"],
            capture_output=True,
            text=True,
            timeout=900,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("is current", result.stdout)


if __name__ == "__main__":
    unittest.main()
