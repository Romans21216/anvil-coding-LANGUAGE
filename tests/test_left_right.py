"""`left(text, count)` and `right(text, count)` take text from either end."""

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
from tests.test_native_x64 import NativeRunMixin  # noqa: E402


def run_c(text: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        source = temp_path / "sample.ANVL"
        source.write_text(text, encoding="utf-8")
        functions, top, variables, arrays = parse(source, text)
        c_file = temp_path / "sample.c"
        c_file.write_text(
            emit_c(source, functions, top, variables, arrays), encoding="utf-8"
        )
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        executable = temp_path / "sample.exe"
        build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=15
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout


PROGRAM = (
    'fn(main)\n  set var(name) = "hello"\n'
    '  say left(var(name), 3)\n  say right(var(name), 2)\n'
    '  say "[" & left(var(name), 0) & "]"\n'
    '  say "[" & right(var(name), 0) & "]"\n'
    '  say left(var(name), 99)\n  say right(var(name), 99)\n'
    '  say "[" & left(var(name), -2) & "]"\n'
    '  say "[" & right(var(name), -2) & "]"\n'
    "end\ncall fn(main)\n"
)
EXPECTED = "hel\nlo\n[]\n[]\nhello\nhello\n[]\n[]\n"


class LeftRightCRuntimeTests(unittest.TestCase):
    def _expect(self, text: str, want: str) -> None:
        self.assertEqual(run_c(text), want)

    def test_edges_and_clamping(self) -> None:
        self._expect(PROGRAM, EXPECTED)

    def test_assignment_and_expressions(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "goodbye"\n'
            '  set var(head) = left(var(name), 4)\n'
            '  set var(tail) = right(var(name), len(var(name)) - 4)\n'
            "  say var(head) & \"/\" & var(tail)\n"
            '  say right("abcdef", 2 + 2)\n'
            "end\ncall fn(main)\n",
            "good/bye\ncdef\n",
        )


class LeftRightNativeTests(NativeRunMixin, unittest.TestCase):
    def _run(self, text: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "sample.ANVL"
            source.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(source, text)
            executable = temp_path / "sample.exe"
            executable.write_bytes(
                NativeCodegen(source, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_native_edges_and_clamping(self) -> None:
        self.assertEqual(self._run(PROGRAM), EXPECTED)

    def test_native_literal_arguments(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  say left("hello", 3)\n  say right("hello", 3)\n'
                '  say left("hi", 10)\n  say right("hi", 10)\nend\ncall fn(main)\n'
            ),
            "hel\nllo\nhi\nhi\n",
        )

    def test_native_assignment_and_expressions(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "goodbye"\n'
                '  set var(head) = left(var(name), 4)\n'
                '  set var(tail) = right(var(name), len(var(name)) - 4)\n'
                "  say var(head) & \"/\" & var(tail)\n"
                '  say right("abcdef", 2 + 2)\n'
                "end\ncall fn(main)\n"
            ),
            "good/bye\ncdef\n",
        )

    def test_native_text_arguments_require_text(self) -> None:
        with self.assertRaises(Exception):
            self._run("fn(main)\n  say left(42, 2)\nend\ncall fn(main)\n")


if __name__ == "__main__":
    unittest.main()
