"""`remove <list> <index>` shifts the tail down and shrinks the list."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402

PROGRAM = (
    "list nums\n"
    "fn(main)\n"
    "  add nums 10\n  add nums 20\n  add nums 30\n  add nums 40\n"
    "  say count(nums)\n"
    "  remove nums 1\n"
    "  say count(nums)\n"
    "  say array(nums, 0) + array(nums, 1) + array(nums, 2)\n"
    "  remove nums 9\n"
    "  say count(nums)\n"
    "  remove nums 0\n"
    "  say count(nums)\n"
    "  say array(nums, 0)\n"
    "end\n"
    "call fn(main)\n"
)
EXPECTED = "4\n3\n80\n3\n2\n30\n"

EMPTY_PROGRAM = (
    "list nums\nfn(main)\n  remove nums 0\n  say count(nums)\nend\ncall fn(main)\n"
)


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


class ListRemoveTests(unittest.TestCase):
    def test_remove_shifts_and_counts_down(self) -> None:
        self.assertEqual(run(PROGRAM, "c"), EXPECTED)
        self.assertEqual(run(PROGRAM, "native"), EXPECTED)

    def test_out_of_range_remove_is_a_no_op(self) -> None:
        source = (
            "list nums\nfn(main)\n  add nums 1\n  remove nums 5\n"
            "  say count(nums)\n  say array(nums, 0)\nend\ncall fn(main)\n"
        )
        self.assertEqual(run(source, "c"), "1\n1\n")
        self.assertEqual(run(source, "native"), "1\n1\n")

    def test_remove_on_an_empty_list_is_a_no_op(self) -> None:
        self.assertEqual(run(EMPTY_PROGRAM, "c"), "0\n")
        self.assertEqual(run(EMPTY_PROGRAM, "native"), "0\n")

    def test_remove_takes_an_expression_index(self) -> None:
        source = (
            "list nums\nfn(main)\n  add nums 1\n  add nums 2\n  add nums 3\n"
            "  set var(pick) = 3 - 2\n  remove nums var(pick)\n"
            "  say count(nums)\n  say array(nums, 0)\n  say array(nums, 1)\n"
            "end\ncall fn(main)\n"
        )
        expected = "2\n1\n3\n"
        self.assertEqual(run(source, "c"), expected)
        self.assertEqual(run(source, "native"), expected)


if __name__ == "__main__":
    unittest.main()
