"""`write` prints without a trailing newline; `say` keeps its newline."""

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


class WriteCRuntimeTests(unittest.TestCase):
    def _expect(self, text: str, want: str) -> None:
        self.assertEqual(run_c(text), want)

    def test_write_then_say_share_a_line(self) -> None:
        self._expect(
            'fn(main)\n  write "Score: "\n  say 42\nend\ncall fn(main)\n',
            "Score: 42\n",
        )

    def test_writes_concatenate(self) -> None:
        self._expect(
            'fn(main)\n  write "a" & "-" & "b"\n  write 7\n  say "done"\n'
            "end\ncall fn(main)\n",
            "a-b7done\n",
        )

    def test_write_alone_leaves_the_line_open(self) -> None:
        self._expect(
            'fn(main)\n  write "no newline"\nend\ncall fn(main)\n',
            "no newline",
        )

    def test_text_values_write_inline(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "Ada"\n  write "Hi, " & var(name)\n'
            '  say "!"\nend\ncall fn(main)\n',
            "Hi, Ada!\n",
        )


class WriteNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_write_then_say_share_a_line(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  write "Score: "\n  say 42\nend\ncall fn(main)\n'),
            "Score: 42\n",
        )

    def test_native_writes_concatenate(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  write "a" & "-" & "b"\n  write 7\n  say "done"\n'
                "end\ncall fn(main)\n"
            ),
            "a-b7done\n",
        )

    def test_native_write_alone_leaves_the_line_open(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  write "no newline"\nend\ncall fn(main)\n'),
            "no newline",
        )

    def test_native_text_values_write_inline(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "Ada"\n  write "Hi, " & var(name)\n'
                '  say "!"\nend\ncall fn(main)\n'
            ),
            "Hi, Ada!\n",
        )


if __name__ == "__main__":
    unittest.main()
