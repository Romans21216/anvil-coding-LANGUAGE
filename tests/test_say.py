"""The `say` statement prints text and values — a beginner's first program."""

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
from tests.test_native_x64 import NativeRunMixin  # noqa: E402


def parse_source(text: str):
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "sample.ANVL"
        path.write_text(text, encoding="utf-8")
        return parse(path, text)


def compile_and_run(text: str) -> str:
    compiler = find_compiler(None)
    if compiler is None:
        self.skipTest("MSVC is not available")
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        c_file = temp_path / "sample.c"
        executable = temp_path / "sample.exe"
        source = temp_path / "sample.ANVL"
        source.write_text(text, encoding="utf-8")
        functions, top, variables, arrays = parse(source, text)
        c_file.write_text(
            emit_c(source, functions, top, variables, arrays), encoding="utf-8"
        )
        build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=15
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout


class SayParseTests(unittest.TestCase):
    def test_say_parses_as_a_statement(self) -> None:
        functions, top, variables, arrays = parse_source(
            'fn(main)\n  say "Hello"\nend\ncall fn(main)\n'
        )
        kinds = [node.kind for node in functions["main"].body]
        self.assertEqual(kinds, ["say"])
        self.assertEqual(functions["main"].body[0].value, '"Hello"')

    def test_say_supports_multiple_parts(self) -> None:
        functions, _, _, _ = parse_source(
            'fn(main)\n  say "Count: ", 3 + 4\nend\ncall fn(main)\n'
        )
        self.assertEqual(functions["main"].body[0].value, '"Count: ", 3 + 4')

    def test_native_backend_rejects_top_level_say_clearly(self) -> None:
        from compiler.native_codegen import NativeCodegen

        functions, top, variables, arrays = parse_source(
            'say "Hello"\nfn(main)\n  output 1\nend\ncall fn(main)\n'
        )
        with self.assertRaises(CompileError) as caught:
            NativeCodegen(
                pathlib.Path("sample.ANVL"), functions, top, variables, arrays
            ).generate()
        self.assertIn("top-level configuration is not implemented", str(caught.exception))


class NativeSayRuntimeTests(NativeRunMixin, unittest.TestCase):
    def test_say_prints_text_without_trailing_zero(self) -> None:
        self.assertEqual(
            self._run_source('fn(main)\n  say "Hello, world!"\nend\ncall fn(main)\n'),
            "Hello, world!\n",
        )

    def test_say_joins_text_and_numbers_on_one_line(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  set var(score) = 42\n  say "Score: ", var(score), " of ", 100\nend\ncall fn(main)\n'
            ),
            "Score: 42 of 100\n",
        )

    def test_say_supports_escapes(self) -> None:
        self.assertEqual(
            self._run_source('fn(main)\n  say "tab\there"\nend\ncall fn(main)\n'),
            "tab\there\n",
        )

    def test_say_then_output_keeps_return_semantics(self) -> None:
        self.assertEqual(
            self._run_source(
                'fn(main)\n  say "value follows"\n  output 7\nend\ncall fn(main)\n'
            ),
            "value follows\n7\n",
        )


class SayRuntimeTests(unittest.TestCase):
    def test_say_prints_text_and_newline(self) -> None:
        self.assertEqual(
            compile_and_run('fn(main)\n  say "Hello, world!"\nend\ncall fn(main)\n'),
            "Hello, world!\n",
        )

    def test_say_joins_text_and_numbers_on_one_line(self) -> None:
        self.assertEqual(
            compile_and_run(
                'fn(main)\n  set var(score) = 42\n  say "Score: ", var(score), " of ", 100\nend\ncall fn(main)\n'
            ),
            "Score: 42 of 100\n",
        )

    def test_say_formats_numbers_like_output(self) -> None:
        self.assertEqual(
            compile_and_run('fn(main)\n  say "Half: ", 0.5\nend\ncall fn(main)\n'),
            "Half: 0.5\n",
        )

    def test_say_supports_escapes(self) -> None:
        self.assertEqual(
            compile_and_run('fn(main)\n  say "tab\\there"\nend\ncall fn(main)\n'),
            "tab\there\n",
        )

    def test_top_level_say_runs_before_the_program(self) -> None:
        self.assertEqual(
            compile_and_run('say "starting"\nfn(main)\n  say "running"\nend\ncall fn(main)\n'),
            "starting\nrunning\n",
        )

    def test_say_then_output_keeps_return_semantics(self) -> None:
        self.assertEqual(
            compile_and_run(
                'fn(main)\n  say "value follows"\n  output 7\nend\ncall fn(main)\n'
            ),
            "value follows\n7\n",
        )


if __name__ == "__main__":
    unittest.main()
