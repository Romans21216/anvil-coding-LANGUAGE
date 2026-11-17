"""Selective imports: `include fn(name) -- "lib.ANVL"` imports one function."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.common import CompileError  # noqa: E402
from compiler.modules import load_program  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402

LIBRARY = """\
fn(bump, n)
  output var(n) + 1
end

fn(move, n)
  output call fn(bump, var(n)) * 2
end

fn(unused, n)
  output var(n) - 100
end
"""

MAIN = """\
include fn(move) -- "lib/player.ANVL"

fn(main)
  say call fn(move--player, 10)
end
call fn(main)
"""

ALIASED = """\
include fn(move) -- "lib/player.ANVL" as p

fn(main)
  say call fn(move--p, 1)
end
call fn(main)
"""

GLOBAL_USE = """\
fn(hit, n)
  output var(n) + var(score)
end
"""


def build_tree(temp: pathlib.Path) -> pathlib.Path:
    library = temp / "lib"
    library.mkdir(parents=True, exist_ok=True)
    (library / "player.ANVL").write_text(LIBRARY, encoding="utf-8")
    (library / "globaluser.ANVL").write_text(GLOBAL_USE, encoding="utf-8")
    return library


def run(source: str, backend: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        build_tree(temp_path)
        path = temp_path / "main.ANVL"
        path.write_text(source, encoding="utf-8")
        program = load_program(path, source)
        if backend == "native":
            executable = temp_path / "main.exe"
            executable.write_bytes(
                NativeCodegen(
                    path, program.functions, program.top, program.variables, program.arrays
                ).generate()
            )
        else:
            c_file = temp_path / "main.c"
            c_file.write_text(
                emit_c(
                    path,
                    program.functions,
                    program.top,
                    program.variables,
                    program.arrays,
                ),
                encoding="utf-8",
            )
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            executable = temp_path / "main.exe"
            build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=20
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


class SelectiveImportTests(unittest.TestCase):
    def test_an_imported_function_and_its_callee_work(self) -> None:
        self.assertEqual(run(MAIN, "c"), "22\n")
        self.assertEqual(run(MAIN, "native"), "22\n")

    def test_an_alias_changes_the_qualifier(self) -> None:
        self.assertEqual(run(ALIASED, "c"), "4\n")

    def test_only_the_named_function_is_imported(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            build_tree(temp_path)
            path = temp_path / "main.ANVL"
            path.write_text(MAIN, encoding="utf-8")
            program = load_program(path, MAIN)
        self.assertIn("move--player", program.functions)
        self.assertIn("bump--player", program.functions)
        self.assertNotIn("unused--player", program.functions)

    def test_a_global_inside_the_module_is_rejected(self) -> None:
        source = (
            'include fn(hit) -- "lib/globaluser.ANVL"\n\n'
            "fn(main)\n  say call fn(hit--globaluser, 1)\nend\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            build_tree(temp_path)
            path = temp_path / "main.ANVL"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                load_program(path, source)
        message = str(caught.exception)
        self.assertIn("uses the global 'score'", message)
        self.assertIn("pass values as parameters", message)

    def test_a_missing_function_names_the_file(self) -> None:
        source = (
            'include fn(nope) -- "lib/player.ANVL"\n\n'
            "fn(main)\n  say 1\nend\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            build_tree(temp_path)
            path = temp_path / "main.ANVL"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                load_program(path, source)
        self.assertIn("player.ANVL has no function 'nope'", str(caught.exception))

    def test_a_whole_file_include_still_shares_its_namespace(self) -> None:
        source = (
            'include "lib/player.ANVL"\n\n'
            "fn(main)\n  say call fn(move, 3)\nend\ncall fn(main)\n"
        )
        self.assertEqual(run(source, "c"), "8\n")


if __name__ == "__main__":
    unittest.main()
