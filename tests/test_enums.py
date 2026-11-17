"""Enums give named states that compile to plain numbers."""

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
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

PROGRAM = (
    "enum State idle, playing, paused\n"
    "\n"
    "fn(label, s)\n"
    "  if var(s) = playing\n"
    '    output "playing"\n'
    "  end\n"
    "  if var(s) = paused\n"
    '    output "paused"\n'
    "  end\n"
    '  output "idle"\n'
    "end\n"
    "\n"
    "fn(main)\n"
    "  set var(now) = playing\n"
    "  say call fn(label, var(now))\n"
    "  set var(now) = paused\n"
    "  say call fn(label, var(now))\n"
    "  say var(now)\n"
    "end\n"
    "call fn(main)\n"
)
EXPECTED = "playing\npaused\n2\n"


def run(source: str, backend: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path = temp_path / "sample.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        if backend == "native":
            executable = temp_path / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
        else:
            c_file = temp_path / "sample.c"
            c_file.write_text(
                emit_c(path, functions, top, variables, arrays), encoding="utf-8"
            )
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            executable = temp_path / "sample.exe"
            build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=20
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


class EnumTests(unittest.TestCase):
    def test_named_states_work_on_both_backends(self) -> None:
        self.assertEqual(run(PROGRAM, "c"), EXPECTED)
        self.assertEqual(run(PROGRAM, "native"), EXPECTED)

    def test_values_count_from_zero(self) -> None:
        source = (
            "enum Dir north, east, south, west\n"
            "fn(main)\n  say south\n  say west\nend\ncall fn(main)\n"
        )
        self.assertEqual(run(source, "c"), "2\n3\n")
        self.assertEqual(run(source, "native"), "2\n3\n")

    def test_a_duplicate_value_is_rejected(self) -> None:
        source = "enum A one, two\nenum B two, three\nfn(main)\n  say 1\nend\n"
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bad.ANVL"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, source)
        self.assertIn("already declared", str(caught.exception))

    def test_a_value_colliding_with_a_variable_is_rejected(self) -> None:
        source = (
            "fn(main)\n  set var(playing) = 1\n  say var(playing)\nend\n"
            "call fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "ok.ANVL"
            path.write_text(source, encoding="utf-8")
            parse(path, source)

        source = (
            "enum State playing, paused\n"
            "fn(main)\n  set var(playing) = 1\n  say var(playing)\nend\n"
            "call fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bad.ANVL"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, source)
        self.assertIn("conflicts with a function or variable", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
