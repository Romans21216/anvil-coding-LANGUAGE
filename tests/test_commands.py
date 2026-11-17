"""Part 8.14: the stable lifecycle commands new/clean/doctor/run."""

from __future__ import annotations

import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

PROGRAM = 'fn(main)\n  say "hi"\nend\ncall fn(main)\n'


def run_compiler(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(COMPILER), *args],
        capture_output=True,
        text=True,
        timeout=180,
    )


class DoctorTests(unittest.TestCase):
    def test_doctor_reports_the_toolchain_without_a_source(self) -> None:
        result = run_compiler("--doctor")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Anvil doctor", result.stdout)
        self.assertIn("native backend: ready", result.stdout)
        self.assertIn("runtime/anvil_runtime.c: ok", result.stdout)


class NewProjectTests(unittest.TestCase):
    def test_new_scaffolds_a_runnable_project(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            target = pathlib.Path(temp) / "game"
            result = run_compiler("--new", str(target))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "main.ANVL").is_file())
            self.assertTrue((target / "game.ANVLproj").is_file())
            self.assertTrue((target / "README.md").is_file())

    def test_new_refuses_a_non_empty_directory(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            target = pathlib.Path(temp) / "game"
            target.mkdir()
            (target / "keep.txt").write_text("x", encoding="utf-8")
            result = run_compiler("--new", str(target))
            self.assertEqual(result.returncode, 1)
            self.assertIn("not empty", result.stderr)
            self.assertTrue((target / "keep.txt").is_file())


class RunCommandTests(unittest.TestCase):
    def test_run_builds_and_returns_the_program_exit_code(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            source = pathlib.Path(temp) / "ok.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            result = run_compiler(str(source), "--backend", "native", "--run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("hi", result.stdout)

    def test_run_propagates_a_failing_program(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            source = pathlib.Path(temp) / "bad.ANVL"
            source.write_text(
                "fn(main)\n  say 1 / 0\nend\ncall fn(main)\n", encoding="utf-8"
            )
            result = run_compiler(str(source), "--backend", "native", "--run")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("division by zero", result.stderr)

    def test_run_rejects_incompatible_flags(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            source = pathlib.Path(temp) / "ok.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            result = run_compiler(str(source), "--check", "--run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("--run builds and runs", result.stderr)

    def test_run_resolves_relative_assets_from_source_folder(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            project = root / "project"
            caller = root / "caller"
            project.mkdir()
            caller.mkdir()
            header = bytearray(54)
            header[:2] = b"BM"
            struct.pack_into("<I", header, 2, 58)
            struct.pack_into("<I", header, 10, 54)
            struct.pack_into("<I", header, 14, 40)
            struct.pack_into("<iiHHI", header, 18, 1, 1, 1, 24, 0)
            struct.pack_into("<I", header, 34, 4)
            (project / "pixel.bmp").write_bytes(bytes(header) + b"\0\0\xff\0")
            source = project / "main.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            command = [
                sys.executable, str(COMPILER), str(source), "--backend", "native",
                "--run", "-o", "build/native.exe",
            ]
            native = subprocess.run(command, cwd=caller, capture_output=True, text=True, timeout=180)
            self.assertEqual(native.returncode, 0, native.stdout + native.stderr)
            self.assertIn("hi", native.stdout)

            source.write_text(
                "fn(main)\n"
                '  set var(image) = image_load("pixel.bmp")\n'
                "  say image_width(var(image))\n"
                "  say image_error()\n"
                "end\ncall fn(main)\n",
                encoding="utf-8",
            )
            command = [
                sys.executable, str(COMPILER), str(source), "--backend", "c",
                "--run", "-o", "build/c.exe",
            ]
            c_backend = subprocess.run(command, cwd=caller, capture_output=True, text=True, timeout=300)
            if c_backend.returncode != 0 and "No C compiler found" in c_backend.stderr:
                raise unittest.SkipTest("MSVC is not available")
            self.assertEqual(c_backend.returncode, 0, c_backend.stdout + c_backend.stderr)
            c_output = c_backend.stdout.replace("\r\n", "\n")
            self.assertIn("1\n\nBuilt ", c_output)
            self.assertNotIn("cannot open the file", c_output)

            source_dir = project / "src"
            source_dir.mkdir()
            project_entry = source_dir / "main.ANVL"
            project_entry.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            manifest = project / "game.ANVLproj"
            manifest.write_text('name = "Asset test"\nentry = "src/main.ANVL"\n', encoding="utf-8")
            project_command = [
                sys.executable, str(COMPILER), str(manifest), "--backend", "c",
                "--run", "-o", "build/project.exe",
            ]
            project_run = subprocess.run(
                project_command, cwd=caller, capture_output=True, text=True, timeout=300
            )
            self.assertEqual(project_run.returncode, 0, project_run.stdout + project_run.stderr)
            project_output = project_run.stdout.replace("\r\n", "\n")
            self.assertIn("1\n\nBuilt ", project_output)
            self.assertNotIn("cannot open the file", project_output)


class CleanTests(unittest.TestCase):
    def test_clean_removes_generated_artifacts_but_keeps_sources(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "prog.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            build = run_compiler(str(source), "-o", str(root / "prog.exe"))
            if build.returncode != 0:
                if "No C compiler found" in build.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(build.stderr)
            self.assertTrue((root / "prog.generated.c").is_file())
            self.assertTrue((root / "prog_obj").is_dir())

            result = run_compiler(str(source), "--clean")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((root / "prog.generated.c").exists())
            self.assertFalse((root / "prog_obj").exists())
            self.assertFalse((root / ".anvil-cache").exists())
            self.assertTrue(source.is_file())
            self.assertTrue((root / "prog.exe").is_file())


class ProjectTestCommandTests(unittest.TestCase):
    def _project(self, root: pathlib.Path) -> pathlib.Path:
        (root / "tests").mkdir(parents=True)
        (root / "main.ANVL").write_text(PROGRAM, encoding="utf-8")
        (root / "tests/ok.ANVL").write_text(PROGRAM, encoding="utf-8")
        manifest = root / "game.ANVLproj"
        manifest.write_text('name = "T"\nentry = "main.ANVL"\n', encoding="utf-8")
        return manifest

    def test_passing_cases_report_pass_and_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            manifest = self._project(pathlib.Path(temp))
            result = run_compiler(str(manifest), "--backend", "native", "--test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS ok.ANVL", result.stdout)
        self.assertIn("1 passed, 0 failed", result.stdout)

    def test_a_failing_case_fails_the_run(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            manifest = self._project(root)
            (root / "tests/bad.ANVL").write_text(
                "fn(main)\n  say 1 / 0\nend\ncall fn(main)\n", encoding="utf-8"
            )
            result = run_compiler(str(manifest), "--backend", "native", "--test")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL bad.ANVL", result.stdout)
        self.assertIn("1 passed, 1 failed", result.stdout)

    def test_a_project_without_tests_says_so(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            (root / "main.ANVL").write_text(PROGRAM, encoding="utf-8")
            manifest = root / "game.ANVLproj"
            manifest.write_text('name = "T"\nentry = "main.ANVL"\n', encoding="utf-8")
            result = run_compiler(str(manifest), "--test")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no tests folder", result.stderr)


if __name__ == "__main__":
    unittest.main()
