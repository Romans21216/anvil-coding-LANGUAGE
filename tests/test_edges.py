"""`starts_with(text, prefix)` / `ends_with(text, suffix)` match text edges."""

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


class EdgeParseTests(unittest.TestCase):
    def test_edge_builtins_reject_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  set var(n) = starts_with("abc", 5)\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
            with self.assertRaises(CompileError) as caught:
                emit_c(path, functions, top, variables, arrays)
        self.assertIn("expected a string", str(caught.exception))


class EdgeCRuntimeTests(unittest.TestCase):
    def _expect(self, text: str, want: str) -> None:
        self.assertEqual(run_c(text), want)

    def test_starts_and_ends(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "hello.txt"\n'
            '  say starts_with(var(name), "hello")\n'
            '  say starts_with(var(name), "world")\n'
            '  say ends_with(var(name), ".txt")\n'
            '  say ends_with(var(name), ".doc")\nend\ncall fn(main)\n',
            "1\n0\n1\n0\n",
        )

    def test_whole_text_as_the_edge(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "hello.txt"\n'
            '  say starts_with(var(name), "hello.txt")\n'
            '  say ends_with(var(name), "o.txt")\nend\ncall fn(main)\n',
            "1\n1\n",
        )

    def test_suffix_longer_than_text(self) -> None:
        self._expect(
            'fn(main)\n  say ends_with("hi", "hello.txt")\nend\ncall fn(main)\n',
            "0\n",
        )


class EdgeNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_starts(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "hello.txt"\n'
                '  say starts_with(var(name), "hello")\n'
                '  say starts_with(var(name), "world")\n'
                '  say starts_with(var(name), "hello.txt")\nend\ncall fn(main)\n'
            ),
            "1\n0\n1\n",
        )

    def test_native_ends(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "hello.txt"\n'
                '  say ends_with(var(name), ".txt")\n'
                '  say ends_with(var(name), ".doc")\n'
                '  say ends_with("hi", "hello.txt")\n'
                '  say ends_with("abc", "abc")\n'
                '  say ends_with("abc", "c")\n'
                '  say ends_with("abc", "")\nend\ncall fn(main)\n'
            ),
            "1\n0\n0\n1\n1\n1\n",
        )

    def test_native_empty_prefix_always_matches(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say starts_with("anything", "")\nend\ncall fn(main)\n'),
            "1\n",
        )


if __name__ == "__main__":
    unittest.main()
