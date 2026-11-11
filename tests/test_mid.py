"""`mid(text, start, count)` extracts a bounded slice of a text value."""

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


class MidCRuntimeTests(unittest.TestCase):
    def _expect(self, text: str, want: str) -> None:
        self.assertEqual(run_c(text), want)

    def test_full_and_partial_slices(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "hello"\n'
            "  say mid(var(name), 0, 5)\n  say mid(var(name), 1, 3)\n"
            "end\ncall fn(main)\n",
            "hello\nell\n",
        )

    def test_count_clamped_to_the_end(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "hello"\n'
            "  say mid(var(name), 4, 10)\nend\ncall fn(main)\n",
            "o\n",
        )

    def test_start_past_the_end_is_empty(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "hello"\n'
            "  say mid(var(name), 9, 2)\nend\ncall fn(main)\n",
            "\n",
        )

    def test_negative_start_clamps_to_zero(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "hello"\n'
            "  say mid(var(name), -1, 3)\nend\ncall fn(main)\n",
            "hel\n",
        )

    def test_joins_and_expressions(self) -> None:
        self._expect(
            'fn(main)\n  say "cut: " & mid("goodbye", 0, 4)\n'
            '  say mid("abcdef", 2, len("abcdef") - 4)\nend\ncall fn(main)\n',
            "cut: good\ncd\n",
        )


class MidNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_full_and_partial_slices(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "hello"\n'
                "  say mid(var(name), 0, 5)\n  say mid(var(name), 1, 3)\n"
                "end\ncall fn(main)\n"
            ),
            "hello\nell\n",
        )

    def test_native_count_clamped_to_the_end(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "hello"\n'
                "  say mid(var(name), 4, 10)\nend\ncall fn(main)\n"
            ),
            "o\n",
        )

    def test_native_start_past_the_end_is_empty(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "hello"\n'
                "  say mid(var(name), 9, 2)\nend\ncall fn(main)\n"
            ),
            "\n",
        )

    def test_native_negative_start_clamps_to_zero(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "hello"\n'
                "  say mid(var(name), -1, 3)\nend\ncall fn(main)\n"
            ),
            "hel\n",
        )

    def test_native_negative_count_is_empty(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "hello"\n'
                "  say mid(var(name), 1, -2)\nend\ncall fn(main)\n"
            ),
            "\n",
        )

    def test_native_joins_and_expressions(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  say "cut: " & mid("goodbye", 0, 4)\n'
                '  say mid("abcdef", 2, len("abcdef") - 4)\nend\ncall fn(main)\n'
            ),
            "cut: good\ncd\n",
        )


if __name__ == "__main__":
    unittest.main()
