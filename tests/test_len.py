"""`len(...)` counts the characters of a text value, both backends."""

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


class LenParseTests(unittest.TestCase):
    def test_len_parses_with_a_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  set var(name) = "Ada"\n  set var(n) = len(var(name))\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
        c_code = emit_c(path, functions, top, variables, arrays)
        self.assertIn("strlen", c_code)

    def test_len_rejects_a_number(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = "fn(main)\n  set var(n) = len(42)\nend\n"
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
            with self.assertRaises(CompileError) as caught:
                emit_c(path, functions, top, variables, arrays)
        self.assertIn("expected a string, got a number", str(caught.exception))


class LenCRuntimeTests(unittest.TestCase):
    def test_len_of_a_variable(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(name) = "Ada"\n'
                '  say "Len: ", len(var(name))\nend\ncall fn(main)\n'
            ),
            "Len: 3\n",
        )

    def test_len_of_a_literal(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  say len("hello")\nend\ncall fn(main)\n'),
            "5\n",
        )

    def test_len_in_arithmetic(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(name) = "Bo"\n'
                '  say "Score: ", len(var(name)) * 2 + 1\nend\ncall fn(main)\n'
            ),
            "Score: 5\n",
        )

    def test_len_of_an_empty_text(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(name) = ""\n'
                '  say "Len: ", len(var(name))\nend\ncall fn(main)\n'
            ),
            "Len: 0\n",
        )

    def test_len_inside_a_condition(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(name) = "Ada"\n'
                "  if len(var(name)) > 2\n"
                '    say "long"\n'
                "  else\n"
                '    say "short"\n'
                "  end\n"
                "end\ncall fn(main)\n"
            ),
            "long\n",
        )


class LenNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_len_of_a_variable(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "Ada"\n'
                '  say "Len: ", len(var(name))\nend\ncall fn(main)\n'
            ),
            "Len: 3\n",
        )

    def test_native_len_of_a_literal(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say len("hello")\nend\ncall fn(main)\n'),
            "5\n",
        )

    def test_native_len_in_arithmetic(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "Bo"\n'
                '  say "Score: ", len(var(name)) * 2 + 1\nend\ncall fn(main)\n'
            ),
            "Score: 5\n",
        )

    def test_native_len_of_an_empty_text(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = ""\n'
                '  say "Len: ", len(var(name))\nend\ncall fn(main)\n'
            ),
            "Len: 0\n",
        )


if __name__ == "__main__":
    unittest.main()
