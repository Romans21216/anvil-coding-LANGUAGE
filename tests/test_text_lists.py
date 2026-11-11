"""Text lists (`list names: text`) hold 256-byte text values."""

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
from compiler.parser import parse  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402

PROGRAM = (
    "list names: text\n"
    "fn(main)\n"
    '  add names "ada"\n  add names "grace"\n  add names "alan"\n'
    "  say count(names)\n"
    "  say array(names, 0)\n"
    "  say len(array(names, 1))\n"
    '  say array(names, 0) & " " & array(names, 2)\n'
    "  set var(pick) = 1\n"
    "  say array(names, var(pick))\n"
    "  for each n in names\n"
    "    say var(n)\n"
    "  end\n"
    "end\ncall fn(main)\n"
)
EXPECTED = "3\nada\n5\nada alan\ngrace\nada\ngrace\nalan\n"


def run_c(source: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path = temp_path / "sample.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        c_file = temp_path / "sample.c"
        c_file.write_text(
            emit_c(path, functions, top, variables, arrays), encoding="utf-8"
        )
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        executable = temp_path / "sample.exe"
        build_c(compiler[1], c_file, executable, release=True)
        return subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=20
        )


class TextListTests(unittest.TestCase):
    def test_text_lists_hold_and_return_text(self) -> None:
        result = run_c(PROGRAM)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), EXPECTED)

    def test_out_of_range_read_reports_and_exits(self) -> None:
        source = (
            "list names: text\nfn(main)\n  add names \"ada\"\n"
            "  say array(names, 3)\nend\ncall fn(main)\n"
        )
        result = run_c(source)
        self.assertEqual(result.returncode, 2)
        self.assertIn("outside 0..0", result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_unknown_list_type_is_rejected(self) -> None:
        source = "list names: mystery\nfn(main)\n  say 1\nend\ncall fn(main)\n"
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bad.ANVL"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, source)
        self.assertIn("unknown list type", str(caught.exception))

    def test_native_backend_names_the_limitation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(PROGRAM, encoding="utf-8")
            functions, top, variables, arrays = parse(path, PROGRAM)
            with self.assertRaises(CompileError) as caught:
                NativeCodegen(path, functions, top, variables, arrays).generate()
        self.assertIn("not available in the native x64 backend", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
