"""`trim(text)` removes leading and trailing spaces/tabs, both backends."""

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


class TrimCRuntimeTests(unittest.TestCase):
    def test_both_edges(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  say trim("  hi  ")\nend\ncall fn(main)\n'),
            "hi\n",
        )

    def test_no_edges_unchanged(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  say trim("no edges")\nend\ncall fn(main)\n'),
            "no edges\n",
        )

    def test_all_whitespace_becomes_empty(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  say trim("   ")\nend\ncall fn(main)\n'),
            "\n",
        )

    def test_joins_and_lengths(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(name) = "  Ada  "\n'
                '  say "[" & trim(var(name)) & "]"\n'
                '  say len(trim("  ab  "))\nend\ncall fn(main)\n'
            ),
            "[Ada]\n2\n",
        )

    def test_inner_spaces_survive(self) -> None:
        self.assertEqual(
            run_c('fn(main)\n  say trim("  a b c  ")\nend\ncall fn(main)\n'),
            "a b c\n",
        )


class TrimNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_both_edges(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say trim("  hi  ")\nend\ncall fn(main)\n'),
            "hi\n",
        )

    def test_native_no_edges_unchanged(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say trim("no edges")\nend\ncall fn(main)\n'),
            "no edges\n",
        )

    def test_native_all_whitespace_becomes_empty(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say trim("   ")\nend\ncall fn(main)\n'),
            "\n",
        )

    def test_native_joins_and_lengths(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "  Ada  "\n'
                '  say "[" & trim(var(name)) & "]"\n'
                '  say len(trim("  ab  "))\nend\ncall fn(main)\n'
            ),
            "[Ada]\n2\n",
        )

    def test_native_inner_spaces_survive(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say trim("  a b c  ")\nend\ncall fn(main)\n'),
            "a b c\n",
        )


if __name__ == "__main__":
    unittest.main()
