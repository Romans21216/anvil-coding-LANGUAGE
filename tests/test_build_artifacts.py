"""A failed build must never destroy the last good executable."""

import pathlib
import subprocess
import sys
import tempfile
import unittest

from compiler.build import build_c

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def run_cli(source_path, *arguments):
    return subprocess.run(
        [sys.executable, str(COMPILER), str(source_path), *arguments],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


class BuildArtifactTests(unittest.TestCase):
    def test_a_failed_toolchain_run_keeps_the_previous_executable(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder = pathlib.Path(temporary)
            generated = folder / "program.c"
            generated.write_text("/* generated */\nint main(void){return 0;}\n", encoding="utf-8")
            output = folder / "app.exe"
            output.write_bytes(b"LAST GOOD BUILD")
            with self.assertRaises(Exception):
                build_c("anvil-no-such-compiler", generated, output, False)
            self.assertEqual(output.read_bytes(), b"LAST GOOD BUILD")
            self.assertEqual(sorted(p.name for p in folder.iterdir()),
                             ["app.exe", "program.c"])

    def test_a_successful_c_build_replaces_the_executable_without_leftovers(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder = pathlib.Path(temporary)
            source = folder / "app.ANVL"
            source.write_text('fn(main)\n  print "built"\nend\n', encoding="utf-8")
            output = folder / "app.exe"
            output.write_bytes(b"STALE")
            result = run_cli(source, "-o", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater(output.stat().st_size, len(b"STALE"))
            self.assertNotIn("STALE", output.read_bytes()[:16].decode("latin-1"))
            self.assertEqual([p for p in folder.iterdir() if ".partial" in p.name], [])

    def test_a_native_build_writes_through_a_staging_file(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder = pathlib.Path(temporary)
            source = folder / "app.ANVL"
            source.write_text("fn(main)\n  print \"native\"\nend\n", encoding="utf-8")
            output = folder / "app.exe"
            result = run_cli(source, "--backend", "native", "-o", str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.is_file())
            self.assertEqual([p for p in folder.iterdir() if ".partial" in p.name], [])

    def test_a_rejected_program_leaves_the_previous_executable_alone(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            folder = pathlib.Path(temporary)
            source = folder / "app.ANVL"
            source.write_text("fn(main)\n  print \"ok\"\nend\n", encoding="utf-8")
            output = folder / "app.exe"
            self.assertEqual(run_cli(source, "-o", str(output)).returncode, 0)
            good = output.read_bytes()
            source.write_text(
                "fn(main)\n  set var(x) = nosuchfn(3)\nend\n", encoding="utf-8"
            )
            broken = run_cli(source, "-o", str(output))
            self.assertEqual(broken.returncode, 1)
            self.assertEqual(output.read_bytes(), good)


if __name__ == "__main__":
    unittest.main()
