"""The captured Visual Studio environment is parsed and cached correctly."""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler import toolchain_env  # noqa: E402
from compiler.toolchain_env import (  # noqa: E402
    CACHE_ENV_VAR,
    cache_path,
    load,
    parse_environment,
    store,
)

NL = chr(10)


class ParseEnvironmentTests(unittest.TestCase):
    def test_banner_lines_and_drive_entries_are_skipped(self) -> None:
        text = NL.join(
            (
                "** Visual Studio 2026 Developer Command Prompt **",
                "INCLUDE=C:" + chr(92) + "inc",
                "=C:=C:" + chr(92) + "work",
                "",
            )
        )
        environment = parse_environment(text)
        self.assertEqual(environment, {"INCLUDE": "C:" + chr(92) + "inc"})

    def test_keys_are_upper_cased_and_values_keep_equals_signs(self) -> None:
        environment = parse_environment("lib=c:" + chr(92) + "lib;x=1" + NL)
        self.assertEqual(environment["LIB"], "c:" + chr(92) + "lib;x=1")

    def test_a_value_may_be_empty(self) -> None:
        environment = parse_environment("WINDOWSDK=" + NL)
        self.assertEqual(environment["WINDOWSDK"], "")


class CacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.devcmd = self.root / "VsDevCmd.bat"
        self.devcmd.write_text("@echo off" + NL, encoding="utf-8")
        self.patch = mock.patch.dict(os.environ, {CACHE_ENV_VAR: str(self.root / "cache")})
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def test_the_cache_directory_follows_the_override(self) -> None:
        self.assertEqual(toolchain_env.cache_directory(), self.root / "cache")

    def test_store_then_load_round_trips(self) -> None:
        environment = {"INCLUDE": "x", "LIB": "y"}
        store(environment, self.devcmd)
        self.assertTrue(cache_path(self.devcmd).exists())
        self.assertEqual(load(self.devcmd), environment)

    def test_a_truncated_cache_file_is_ignored(self) -> None:
        store({"INCLUDE": "x"}, self.devcmd)
        cache_path(self.devcmd).write_text("{not json", encoding="utf-8")
        self.assertIsNone(load(self.devcmd))

    def test_a_cache_without_include_is_ignored(self) -> None:
        path = cache_path(self.devcmd)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"PATH": "x"}), encoding="utf-8")
        self.assertIsNone(load(self.devcmd))

    def test_changing_the_toolset_changes_the_cache_key(self) -> None:
        before = cache_path(self.devcmd)
        self.devcmd.write_text("@echo off" + NL + "rem changed" + NL, encoding="utf-8")
        self.assertNotEqual(before, cache_path(self.devcmd))

    def test_a_missing_toolset_returns_none_instead_of_raising(self) -> None:
        missing = self.root / "nope" / "VsDevCmd.bat"
        self.assertIsNone(load(missing))
        self.assertIsNone(toolchain_env.ensure(missing))


class ContentKeyTests(unittest.TestCase):
    """C8-12: the cache name follows batch-file contents, not metadata."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.patch = mock.patch.dict(os.environ, {CACHE_ENV_VAR: str(self.root / "cache")})
        self.patch.start()

    def tearDown(self) -> None:
        self.patch.stop()
        self.tmp.cleanup()

    def _script(self, body: bytes) -> pathlib.Path:
        path = self.root / "VsDevCmd.bat"
        path.write_bytes(body)
        return path

    def test_same_size_content_with_restored_time_changes_the_key(self) -> None:
        script = self._script(b"@echo off" + bytes([10]) + b"rem one" + bytes([10]))
        stat = script.stat()
        before = cache_path(script)
        script.write_bytes(b"@echo off" + bytes([10]) + b"rem TWO" + bytes([10]))
        os.utime(script, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(len(script.read_bytes()), stat.st_size)
        self.assertNotEqual(before, cache_path(script))

    def test_a_changed_nested_script_changes_the_key(self) -> None:
        script = self._script(b"@echo off" + bytes([10]))
        before = cache_path(script)
        nested = self.root / "vcvarsall.bat"
        nested.write_bytes(b"@echo off" + bytes([10]) + b"call one" + bytes([10]))
        middle = cache_path(script)
        nested.write_bytes(b"@echo off" + bytes([10]) + b"call two" + bytes([10]))
        after = cache_path(script)
        self.assertNotEqual(before, middle)
        self.assertNotEqual(middle, after)

    def test_an_unchanged_script_keeps_the_key(self) -> None:
        script = self._script(b"@echo off" + bytes([10]))
        self.assertEqual(cache_path(script), cache_path(script))


if __name__ == "__main__":
    unittest.main()
