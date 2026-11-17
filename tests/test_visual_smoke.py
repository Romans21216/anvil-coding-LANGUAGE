"""The visual smoke run must produce a real, non-blank frame (8.15)."""

from __future__ import annotations

import json
import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "visual_smoke.py"


@unittest.skipUnless(os.name == "nt", "window capture uses Win32")
class VisualSmokeTests(unittest.TestCase):
    def test_the_sprite_demo_draws_something_reviewable(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            shots = pathlib.Path(temp)
            report = shots / "report.json"
            run = subprocess.run(
                [
                    sys.executable,
                    str(TOOL),
                    "--only",
                    "sprite_transform",
                    "--out",
                    str(shots),
                    "--json",
                    str(report),
                    "--check",
                ],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=ROOT,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            result = json.loads(report.read_text(encoding="utf-8"))["results"][0]
            self.assertEqual((result["width"], result["height"]), (960, 600))
            self.assertGreaterEqual(result["distinct_colours"], 20)
            self.assertGreater(result["non_background"], 0.05)
            image = shots / "sprite_transform.png"
            data = image.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", data[16:24])
            self.assertEqual((width, height), (960, 600))


if __name__ == "__main__":
    unittest.main()
