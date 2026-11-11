"""Incremental builds: a repeated build reuses the cached executable."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

PROGRAM = 'fn(main)\n  say "cached"\nend\ncall fn(main)\n'


def build(source: pathlib.Path, out: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(out)],
        capture_output=True,
        text=True,
        timeout=180,
    )


class BuildCacheTests(unittest.TestCase):
    def test_second_build_reuses_the_cached_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "prog.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            out = temp_path / "prog.exe"

            first = build(source, out)
            if first.returncode != 0:
                if "No C compiler found" in first.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(first.stderr)
            self.assertIn("Built", first.stdout)
            self.assertTrue(out.exists())
            first_bytes = out.read_bytes()

            second = build(source, out)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("cache", second.stdout.lower())
            self.assertEqual(out.read_bytes(), first_bytes)

    def test_changed_source_misses_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "prog.ANVL"
            out = temp_path / "prog.exe"
            source.write_text(PROGRAM, encoding="utf-8")

            first = build(source, out)
            if first.returncode != 0:
                if "No C compiler found" in first.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(first.stderr)
            cached_bytes = out.read_bytes()

            source.write_text(
                'fn(main)\n  say "cached"\n  say "again"\nend\ncall fn(main)\n',
                encoding="utf-8",
            )
            second = build(source, out)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("Built", second.stdout)
            self.assertNotIn("cache", second.stdout.lower())
            self.assertNotEqual(out.read_bytes(), cached_bytes)

    def test_run_output_survives_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "prog.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            out = temp_path / "prog.exe"

            first = build(source, out)
            if first.returncode != 0:
                if "No C compiler found" in first.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(first.stderr)
            build(source, out)
            result = subprocess.run(
                [str(out)], capture_output=True, text=True, timeout=30
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.replace("\r\n", "\n"), "cached\n")


if __name__ == "__main__":
    unittest.main()
