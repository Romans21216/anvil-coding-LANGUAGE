"""Annotated bool variables print as true/false; numbers and comparisons don't."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

PROGRAM = (
    "fn(main)\n"
    "  set var(alive): bool = true\n"
    "  set var(dead): bool = false\n"
    "  set var(score): number = 7\n"
    "  say var(alive)\n"
    "  say var(dead)\n"
    "  say var(score)\n"
    "  say 1 = 1\n"
    "  if var(alive)\n"
    '    say "yes"\n'
    "  end\n"
    "end\n"
    "call fn(main)\n"
)
EXPECTED = "true\nfalse\n7\n1\nyes\n"


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


class BoolPrintingTests(unittest.TestCase):
    def test_bool_variables_print_as_words(self) -> None:
        for backend in ("c", "native"):
            with self.subTest(backend=backend):
                self.assertEqual(run(PROGRAM, backend), EXPECTED)

    def test_a_bool_flipped_in_a_loop_stays_a_word(self) -> None:
        source = (
            "fn(main)\n"
            "  set var(on): bool = true\n"
            "  set var(i) = 0\n"
            "  while var(i) < 1\n"
            "    set var(on) = false\n"
            "    add var(i) 1\n"
            "  end\n"
            "  say var(on)\n"
            "end\ncall fn(main)\n"
        )
        self.assertEqual(run(source, "c"), "false\n")
        self.assertEqual(run(source, "native"), "false\n")


if __name__ == "__main__":
    unittest.main()
