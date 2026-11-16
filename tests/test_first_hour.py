"""The documented first-hour workflow works end to end on a fresh project.

This is the closest automated stand-in for the Part 8 new-user trial: scaffold a
project, check it, build and run it, format it, package it, and ask the doctor
and the error explainer for help — exactly the commands the docs tell a new
programmer to type, in order.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def run(*arguments: str, cwd=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(COMPILER), *arguments],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=cwd,
    )


class FirstHourTests(unittest.TestCase):
    def test_new_project_builds_runs_formats_and_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = pathlib.Path(temp) / "my-game"

            created = run("--new", str(project))
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertTrue((project / "main.ANVL").is_file())
            self.assertTrue((project / "game.ANVLproj").is_file())
            self.assertIn("--run", created.stdout)

            checked = run(str(project / "main.ANVL"), "--check")
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertIn(": ok", checked.stdout)

            program = project / "build" / "main.exe"
            built = run(
                str(project / "main.ANVL"), "-o", str(program), "--timings"
            )
            if built.returncode != 0 and "No C compiler found" in built.stderr:
                self.skipTest("MSVC is not available")
            self.assertEqual(built.returncode, 0, built.stderr)
            self.assertTrue(program.is_file())
            self.assertIn("timings:", built.stderr)

            ran = subprocess.run(
                [str(program)], capture_output=True, text=True, timeout=60
            )
            self.assertEqual(ran.returncode, 0, ran.stderr)

            formatted = run(str(project / "main.ANVL"), "--format")
            self.assertEqual(formatted.returncode, 0, formatted.stderr)

            dry_run = run(str(project / "game.ANVLproj"), "--package-dry-run")
            self.assertEqual(dry_run.returncode, 0, dry_run.stderr)

            packaged = run(
                str(project / "game.ANVLproj"),
                "--package",
                str(project / "dist"),
            )
            self.assertEqual(packaged.returncode, 0, packaged.stderr)
            self.assertTrue((project / "dist" / "anvil-package.json").is_file())

            doctor = run("--doctor")
            self.assertEqual(doctor.returncode, 0, doctor.stderr)

            explained = run("--explain", "ANV102")
            self.assertEqual(explained.returncode, 0, explained.stderr)
            self.assertIn("error[ANV102]", explained.stdout)


if __name__ == "__main__":
    unittest.main()
