"""save_number/save_text: bounded, typed, atomic saves with readable errors."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402


def compile_program(temp_path: pathlib.Path, source: str) -> pathlib.Path:
    path = temp_path / "save.ANVL"
    path.write_text(source, encoding="utf-8")
    functions, top, variables, arrays = parse(path, source)
    c_file = temp_path / "save.c"
    c_file.write_text(
        emit_c(path, functions, top, variables, arrays), encoding="utf-8"
    )
    compiler = find_compiler(None)
    if compiler is None:
        raise unittest.SkipTest("MSVC is not available")
    executable = temp_path / "save.exe"
    build_c(compiler[1], c_file, executable, release=True)
    return executable


def run_program(
    executable: pathlib.Path, save_dir: pathlib.Path
) -> subprocess.CompletedProcess:
    environment = dict(os.environ)
    environment["ANVIL_SAVE_DIR"] = str(save_dir)
    return subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        timeout=30,
        env=environment,
    )


def lines_of(result: subprocess.CompletedProcess) -> list[str]:
    return result.stdout.replace("\r\n", "\n").splitlines()


ROUND_TRIP = (
    "fn(main)\n"
    '  say save_number("player.hp", 42.5)\n'
    '  say load_number("player.hp")\n'
    '  say save_text("player.name", "Ada")\n'
    '  say load_text("player.name")\n'
    '  say save_exists("player.hp")\n'
    "  say save_error()\n"
    "end\ncall fn(main)\n"
)


class SaveRoundTripTests(unittest.TestCase):
    def test_numbers_and_text_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            executable = compile_program(root, ROUND_TRIP)
            result = run_program(executable, root / "saves")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                lines_of(result), ["1", "42.5", "1", "Ada", "1", ""]
            )
            self.assertTrue((root / "saves" / "player.hp.sav").is_file())
            self.assertTrue((root / "saves" / "player.name.sav").is_file())
            self.assertEqual(
                list((root / "saves").glob("*.tmp")), [], "temporary files left behind"
            )

    def test_values_persist_across_runs(self) -> None:
        writer = (
            "fn(main)\n"
            '  say save_number("run.count", 7)\n'
            '  say save_text("run.tag", "first")\n'
            "end\ncall fn(main)\n"
        )
        reader = (
            "fn(main)\n"
            '  say load_number("run.count")\n'
            '  say load_text("run.tag")\n'
            '  say save_exists("run.count")\n'
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            saves = root / "saves"
            first = run_program(compile_program(root, writer), saves)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = run_program(compile_program(root, reader), saves)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(lines_of(second), ["7", "first", "1"])

    def test_a_missing_slot_reads_as_empty_without_an_error(self) -> None:
        source = (
            "fn(main)\n"
            '  say load_number("nothing")\n'
            '  say "[" & load_text("nothing") & "]"\n'
            '  say save_exists("nothing")\n'
            "  say save_error()\n"
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            result = run_program(compile_program(root, source), root / "saves")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(lines_of(result), ["0", "[]", "0", ""])

    def test_reading_a_text_slot_as_a_number_is_named(self) -> None:
        source = (
            "fn(main)\n"
            '  say save_text("slot", "text")\n'
            '  say load_number("slot")\n'
            "  say save_error()\n"
            '  say save_number("slot2", 1)\n'
            '  say load_text("slot2")\n'
            "  say save_error()\n"
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            result = run_program(compile_program(root, source), root / "saves")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                lines_of(result),
                [
                    "1",
                    "0",
                    "the save holds text, not a number",
                    "1",
                    "",
                    "the save holds a number, not text",
                ],
            )

    def test_delete_removes_the_value(self) -> None:
        source = (
            "fn(main)\n"
            '  say save_number("gone", 3)\n'
            '  say save_delete("gone")\n'
            '  say save_exists("gone")\n'
            '  say load_number("gone")\n'
            '  say save_delete("gone")\n'
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            result = run_program(compile_program(root, source), root / "saves")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(lines_of(result), ["1", "1", "0", "0", "0"])


class SaveSlotValidationTests(unittest.TestCase):
    def test_a_traversal_slot_is_rejected(self) -> None:
        source = (
            "fn(main)\n"
            '  say save_number("../escape", 1)\n'
            "  say save_error()\n"
            '  say save_exists("../escape")\n'
            '  say save_number("", 1)\n'
            "  say save_error()\n"
            '  say save_number("a/b", 1)\n'
            "  say save_error()\n"
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            result = run_program(compile_program(root, source), root / "saves")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                lines_of(result),
                [
                    "0",
                    "the save slot is invalid",
                    "0",
                    "0",
                    "the save slot is invalid",
                    "0",
                    "the save slot is invalid",
                ],
            )
            self.assertFalse((root / "escape.sav").exists())

    def test_a_slot_longer_than_64_bytes_is_rejected(self) -> None:
        long_slot = "x" * 65
        source = (
            "fn(main)\n"
            f'  say save_number("{long_slot}", 1)\n'
            "  say save_error()\n"
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            result = run_program(compile_program(root, source), root / "saves")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                lines_of(result), ["0", "the save slot is invalid"]
            )

    def test_a_255_byte_text_value_saves(self) -> None:
        text = "y" * 255
        source = (
            "fn(main)\n"
            f'  say save_text("long", "{text}")\n'
            '  say len(load_text("long"))\n'
            "  say save_error()\n"
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            result = run_program(compile_program(root, source), root / "saves")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(lines_of(result), ["1", "255", ""])

    def test_the_default_root_is_localappdata_anvil_project(self) -> None:
        """Without ANVIL_SAVE_DIR the slot lands under %LOCALAPPDATA%\\Anvil."""
        source = (
            "fn(main)\n"
            '  say save_number("slot", 5)\n'
            '  say load_number("slot")\n'
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            executable = compile_program(root, source)
            environment = dict(os.environ)
            environment.pop("ANVIL_SAVE_DIR", None)
            environment["LOCALAPPDATA"] = str(root / "localappdata")
            result = subprocess.run(
                [str(executable)],
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(lines_of(result), ["1", "5"])
            saved = root / "localappdata" / "Anvil" / "Anvil_Game" / "slot.sav"
            self.assertTrue(saved.is_file(), f"expected {saved}")


    def test_a_corrupt_save_file_is_reported(self) -> None:
        source = (
            "fn(main)\n"
            '  say load_number("broken")\n'
            "  say save_error()\n"
            "end\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            saves = root / "saves"
            saves.mkdir()
            (saves / "broken.sav").write_bytes(b"NOTASAVE" + b"\x00" * 16)
            result = run_program(compile_program(root, source), saves)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                lines_of(result), ["0", "the save is not a readable Anvil save"]
            )


if __name__ == "__main__":
    unittest.main()
