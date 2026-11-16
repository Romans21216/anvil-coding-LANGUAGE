"""Incremental builds: a repeated build reuses the cached executable."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

sys.path.insert(0, str(ROOT))

from compiler.cli import _cache_key  # noqa: E402

PROGRAM = 'fn(main)\n  say "cached"\nend\ncall fn(main)\n'


def build(
    source: pathlib.Path, out: pathlib.Path, *extra: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(out), *extra],
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

    def test_no_cache_forces_a_rebuild_but_keeps_the_old_entry(self) -> None:
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
            second = build(source, out)
            self.assertIn("cache", second.stdout.lower())

            bypass = build(source, out, "--no-cache")
            self.assertEqual(bypass.returncode, 0, bypass.stderr)
            self.assertIn("Built", bypass.stdout)
            self.assertNotIn("cache", bypass.stdout.lower())

            again = build(source, out)
            self.assertIn("cache", again.stdout.lower())


class CacheKeyInputTests(unittest.TestCase):
    """C8-6: the key must cover every transitive build input."""

    def _runtime_dir(self, root: pathlib.Path) -> pathlib.Path:
        runtime = root / "runtime"
        runtime.mkdir()
        for name in ("anvil_runtime.c", "anvil_runtime.h", "anvil_projection.h"):
            (runtime / name).write_text(f"/* {name} */\n", encoding="utf-8")
        return runtime

    def _compiler(self, root: pathlib.Path) -> pathlib.Path:
        compiler = root / "cl.exe"
        compiler.write_bytes(b"fake compiler one")
        return compiler

    def test_projection_header_edit_changes_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            runtime = self._runtime_dir(root)
            compiler = self._compiler(root)
            before = _cache_key("int main(void){}", str(compiler), True, runtime)
            (runtime / "anvil_projection.h").write_text(
                "/* changed projection */\n", encoding="utf-8"
            )
            after = _cache_key("int main(void){}", str(compiler), True, runtime)
        self.assertNotEqual(before, after)

    def test_replacing_the_compiler_at_the_same_path_changes_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            runtime = self._runtime_dir(root)
            compiler = self._compiler(root)
            before = _cache_key("int main(void){}", str(compiler), True, runtime)
            compiler.write_bytes(b"fake compiler two, a different binary")
            after = _cache_key("int main(void){}", str(compiler), True, runtime)
        self.assertNotEqual(before, after)

    def test_unchanged_inputs_keep_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            runtime = self._runtime_dir(root)
            compiler = self._compiler(root)
            first = _cache_key("int main(void){}", str(compiler), True, runtime)
            second = _cache_key("int main(void){}", str(compiler), True, runtime)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
