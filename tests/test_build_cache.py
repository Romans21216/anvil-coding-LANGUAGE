"""Incremental builds: a repeated build reuses the cached executable."""

from __future__ import annotations

import os
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

sys.path.insert(0, str(ROOT))

from compiler.cli import (  # noqa: E402
    _cache_key,
    _dependency_digest,
    _key_with_dependencies,
    _sdk_fingerprint,
)

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

    def test_same_size_same_time_compiler_replacement_changes_the_key(self) -> None:
        """C8-9: stat metadata alone can collide after an in-place replacement."""
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            runtime = self._runtime_dir(root)
            compiler = self._compiler(root)
            before = _cache_key("int main(void){}", str(compiler), True, runtime)
            original = compiler.stat()
            compiler.write_bytes(b"Y" * original.st_size)
            os.utime(compiler, ns=(original.st_atime_ns, original.st_mtime_ns))
            after = _cache_key("int main(void){}", str(compiler), True, runtime)
        self.assertNotEqual(before, after)

    def test_a_changed_linker_beside_the_compiler_changes_the_key(self) -> None:
        """C8-10: cl.exe invokes link.exe, which decides the executable bytes."""
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            runtime = self._runtime_dir(root)
            compiler = self._compiler(root)
            linker = root / "link.exe"
            linker.write_bytes(b"linker one")
            before = _cache_key("int main(void){}", str(compiler), True, runtime)
            original = linker.stat()
            linker.write_bytes(b"LINKER TWO")
            os.utime(linker, ns=(original.st_atime_ns, original.st_mtime_ns))
            after = _cache_key("int main(void){}", str(compiler), True, runtime)
        self.assertNotEqual(before, after)

    def test_an_unchanged_linker_keeps_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            runtime = self._runtime_dir(root)
            compiler = self._compiler(root)
            (root / "link.exe").write_bytes(b"linker one")
            first = _cache_key("int main(void){}", str(compiler), True, runtime)
            second = _cache_key("int main(void){}", str(compiler), True, runtime)
        self.assertEqual(first, second)

    def test_unchanged_inputs_keep_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            runtime = self._runtime_dir(root)
            compiler = self._compiler(root)
            first = _cache_key("int main(void){}", str(compiler), True, runtime)
            second = _cache_key("int main(void){}", str(compiler), True, runtime)
        self.assertEqual(first, second)


class SdkFingerprintTests(unittest.TestCase):
    """C8-11: SDK contents, not just version-directory names, decide the key."""

    VERSION = "10.0.26100.0"

    def _sdk(self, root: pathlib.Path) -> pathlib.Path:
        include = root / "Include" / self.VERSION / "um"
        include.mkdir(parents=True)
        library = root / "Lib" / self.VERSION / "um" / "x64"
        library.mkdir(parents=True)
        (include / "windows.h").write_text("header one", encoding="utf-8")
        (library / "kernel32.lib").write_text("library one", encoding="utf-8")
        return root

    def test_a_header_changed_in_place_changes_the_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self._sdk(pathlib.Path(temp))
            before = _sdk_fingerprint(root)
            (root / "Include" / self.VERSION / "um" / "windows.h").write_text(
                "header two, longer", encoding="utf-8"
            )
            after = _sdk_fingerprint(root)
        self.assertNotEqual(before, after)

    def test_a_library_changed_in_place_changes_the_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self._sdk(pathlib.Path(temp))
            before = _sdk_fingerprint(root)
            (root / "Lib" / self.VERSION / "um" / "x64" / "kernel32.lib").write_text(
                "library two, longer", encoding="utf-8"
            )
            after = _sdk_fingerprint(root)
        self.assertNotEqual(before, after)

    def test_an_unchanged_sdk_keeps_the_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self._sdk(pathlib.Path(temp))
            self.assertEqual(_sdk_fingerprint(root), _sdk_fingerprint(root))

    def test_a_newer_version_directory_is_the_selected_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self._sdk(pathlib.Path(temp))
            before = _sdk_fingerprint(root)
            newer = root / "Include" / "10.0.27000.0" / "um"
            newer.mkdir(parents=True)
            (newer / "windows.h").write_text("newer sdk", encoding="utf-8")
            (root / "Lib" / "10.0.27000.0" / "um" / "x64").mkdir(parents=True)
            after = _sdk_fingerprint(root)
        self.assertNotEqual(before, after)

    def test_a_missing_sdk_is_marked_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(_sdk_fingerprint(pathlib.Path(temp) / "absent"), b"missing")


class DependencyListTests(unittest.TestCase):
    """C8-11: the bytes of consumed headers, not their metadata, decide the key."""

    def _sidecar(self, root: pathlib.Path, headers: list[pathlib.Path]) -> pathlib.Path:
        root.mkdir(parents=True, exist_ok=True)
        sidecar = root / "base.deps.json"
        sidecar.write_text(
            json.dumps(
                {
                    "Version": "1.2",
                    "Data": {"Includes": [str(header) for header in headers]},
                }
            ),
            encoding="utf-8",
        )
        return sidecar

    def test_same_size_same_mtime_header_replacement_changes_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            header = root / "windows.h"
            header.write_text("AAAA", encoding="utf-8")
            st = header.stat()
            sidecar = self._sidecar(root, [header])
            before = _key_with_dependencies("base-key", sidecar)

            header.write_text("BBBB", encoding="utf-8")
            os.utime(header, ns=(st.st_atime_ns, st.st_mtime_ns))
            self.assertEqual(header.stat().st_size, 4)
            after = _key_with_dependencies("base-key", sidecar)

        self.assertNotEqual(before, after)

    def test_an_unchanged_dependency_keeps_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            header = root / "windows.h"
            header.write_text("AAAA", encoding="utf-8")
            sidecar = self._sidecar(root, [header])
            self.assertEqual(
                _key_with_dependencies("base-key", sidecar),
                _key_with_dependencies("base-key", sidecar),
            )

    def test_a_missing_sidecar_falls_back_to_the_base_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            absent = pathlib.Path(temp) / "absent.deps.json"
            self.assertEqual(_key_with_dependencies("base-key", absent), "base-key")
            self.assertEqual(_dependency_digest(absent), b"")

    def test_an_unreadable_sidecar_falls_back_to_the_base_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sidecar = pathlib.Path(temp) / "broken.deps.json"
            sidecar.write_text("not json", encoding="utf-8")
            self.assertEqual(_key_with_dependencies("base-key", sidecar), "base-key")

    def test_a_deleted_dependency_changes_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            header = root / "windows.h"
            header.write_text("AAAA", encoding="utf-8")
            sidecar = self._sidecar(root, [header])
            before = _key_with_dependencies("base-key", sidecar)
            header.unlink()
            after = _key_with_dependencies("base-key", sidecar)
        self.assertNotEqual(before, after)

    def test_a_multi_source_document_is_read(self) -> None:
        """MSVC emits a list of Data records when several sources compile."""
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            first = root / "windows.h"
            second = root / "stdio.h"
            first.write_text("AAAA", encoding="utf-8")
            second.write_text("BBBB", encoding="utf-8")
            sidecar = root / "multi.deps.json"
            sidecar.write_text(
                json.dumps(
                    {
                        "Version": "1.2",
                        "Data": [
                            {"Source": "a.c", "Includes": [str(first)]},
                            {"Source": "b.c", "Includes": [str(second)]},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            before = _key_with_dependencies("base-key", sidecar)
            self.assertNotEqual(before, "base-key")
            st = second.stat()
            second.write_text("CCCC", encoding="utf-8")
            os.utime(second, ns=(st.st_atime_ns, st.st_mtime_ns))
            after = _key_with_dependencies("base-key", sidecar)
        self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
