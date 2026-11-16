"""Part 8's project commands: ``--doctor``, ``--new``, ``--clean``, ``--package``."""

import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def run_cli(*arguments):
    return subprocess.run(
        [sys.executable, str(COMPILER), *arguments],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT),
    )


class DoctorCommandTests(unittest.TestCase):
    def test_doctor_reports_every_backend_and_exits_zero(self):
        result = run_cli("--doctor")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Anvil toolchain", result.stdout)
        self.assertIn("Python", result.stdout)
        self.assertIn("Native backend", result.stdout)
        self.assertIn("No blocking problems", result.stdout)

    def test_doctor_does_not_need_a_source_file(self):
        result = run_cli("--doctor")
        self.assertNotIn("a source file or project manifest is required", result.stderr)


class NewCommandTests(unittest.TestCase):
    def test_new_writes_a_manifest_and_a_program_that_builds_on_both_backends(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            target = pathlib.Path(temporary) / "demo"
            result = run_cli("--new", str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "main.ANVL").is_file())
            self.assertTrue((target / "demo.ANVLproj").is_file())
            self.assertTrue((target / "assets").is_dir())
            for backend in ("c", "native"):
                checked = run_cli(
                    str(target / "main.ANVL"), "--check", "--backend", backend
                )
                self.assertEqual(
                    checked.returncode, 0, f"{backend}: {checked.stdout}{checked.stderr}"
                )
                self.assertIn("no errors", checked.stdout)

    def test_new_refuses_to_overwrite_a_non_empty_folder(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            target = pathlib.Path(temporary) / "busy"
            target.mkdir()
            (target / "keep.txt").write_text("keep", encoding="utf-8")
            result = run_cli("--new", str(target))
            self.assertEqual(result.returncode, 1)
            self.assertIn("not empty", result.stderr)
            self.assertTrue((target / "keep.txt").is_file())


class CleanCommandTests(unittest.TestCase):
    def test_clean_removes_the_executable_and_keeps_the_source(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = pathlib.Path(temporary) / "probe.ANVL"
            source.write_text("fn(main)\n  output 0\nend\n", encoding="utf-8")
            built = run_cli(str(source))
            self.assertEqual(built.returncode, 0, built.stderr)
            executable = source.with_suffix(".exe")
            self.assertTrue(executable.is_file())
            cleaned = run_cli(str(source), "--clean")
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
            self.assertIn("Removed", cleaned.stdout)
            self.assertFalse(executable.exists())
            self.assertTrue(source.is_file())

    def test_clean_reports_nothing_to_do_when_the_build_is_already_gone(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = pathlib.Path(temporary) / "probe.ANVL"
            source.write_text("fn(main)\n  output 0\nend\n", encoding="utf-8")
            result = run_cli(str(source), "--clean")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("nothing to clean", result.stdout)

    def test_clean_needs_a_source_or_manifest(self):
        result = run_cli("--clean")
        self.assertEqual(result.returncode, 1)
        self.assertIn("--clean needs a source file or project manifest", result.stderr)


class PackageCommandTests(unittest.TestCase):
    def test_package_builds_a_runnable_folder_with_a_hashed_manifest(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = pathlib.Path(temporary) / "console.ANVL"
            source.write_text("fn(main)\n  output 42\nend\n", encoding="utf-8")
            result = run_cli(str(source), "--package")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            dist = pathlib.Path(temporary) / "dist" / "console"
            executable = dist / "console.exe"
            self.assertTrue(executable.is_file())
            manifest = json.loads((dist / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["name"], "console")
            self.assertEqual(manifest["target"], "windows-x64")
            self.assertEqual(manifest["compiler"]["backend"], "c")
            self.assertEqual(manifest["entry"], "console.ANVL")
            self.assertIn("console", manifest["features"])
            self.assertEqual(manifest["dependencies"], [])

            for entry in manifest["files"]:
                packaged = dist / entry["path"]
                self.assertTrue(packaged.is_file(), entry["path"])
                digest = hashlib.sha256(packaged.read_bytes()).hexdigest()
                self.assertEqual(entry["sha256"], digest)
                self.assertEqual(entry["bytes"], packaged.stat().st_size)
                self.assertEqual(manifest["checksums"][entry["path"]], f"sha256:{digest}")

            ran = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0)
            self.assertEqual(ran.stdout.strip(), "42")

    def test_package_dry_run_prints_the_plan_and_writes_nothing(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = pathlib.Path(temporary) / "dryrun.ANVL"
            source.write_text("fn(main)\n  output 0\nend\n", encoding="utf-8")
            result = run_cli(str(source), "--package", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Package dryrun", result.stdout)
            self.assertIn("windows-x64 (c backend)", result.stdout)
            self.assertIn("Dry run: nothing written", result.stdout)
            self.assertFalse((pathlib.Path(temporary) / "dist").exists())

    def test_package_refuses_a_missing_image_load_asset(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = pathlib.Path(temporary) / "missing.ANVL"
            source.write_text(
                'scene 2d\n'
                'clear rgba(0,0,0,255)\n'
                'set var(s) = image_load("assets/nope.bmp")\n'
                'fn(update)\nend\nfn(draw)\nend\n',
                encoding="utf-8",
            )
            result = run_cli(str(source), "--package")
            self.assertEqual(result.returncode, 1)
            self.assertIn("assets/nope.bmp", result.stderr)
            self.assertIn("missing asset(s)", result.stderr)
            self.assertFalse((pathlib.Path(temporary) / "dist").exists())

    def test_dry_run_without_package_is_rejected(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            source = pathlib.Path(temporary) / "plain.ANVL"
            source.write_text("fn(main)\n  output 0\nend\n", encoding="utf-8")
            result = run_cli(str(source), "--dry-run")
            self.assertEqual(result.returncode, 1)
            self.assertIn("--dry-run only makes sense with --package", result.stderr)


if __name__ == "__main__":
    unittest.main()
