"""`stop` ends the program immediately with exit code 0, both backends."""

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


def run_c(text: str) -> tuple[int, str]:
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
    return result.returncode, result.stdout


class StopCRuntimeTests(unittest.TestCase):
    def test_stop_ends_the_program(self) -> None:
        code, out = run_c(
            'fn(main)\n  say "before"\n  stop\n  say "after"\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "before\n")

    def test_stop_inside_a_condition(self) -> None:
        code, out = run_c(
            'fn(main)\n  say "before"\n  if 1 = 1\n    stop\n  end\n'
            '  say "after"\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "before\n")

    def test_stop_after_a_loop(self) -> None:
        code, out = run_c(
            'fn(main)\n  repeat 2\n    say "tick"\n  end\n  stop\n'
            '  say "never"\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "tick\ntick\n")

    def test_skipped_stop_lets_the_program_finish(self) -> None:
        code, out = run_c(
            'fn(main)\n  if 1 = 2\n    stop\n  end\n  say "done"\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "done\n")

    def test_stop_parses(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  stop\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
        self.assertEqual(functions["main"].body[0].kind, "stop")


class StopNativeTests(NativeRunMixin, unittest.TestCase):
    def _run(self, text: str) -> tuple[int, str]:
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
        return result.returncode, result.stdout

    def test_native_stop_ends_the_program(self) -> None:
        code, out = self._run(
            'fn(main)\n  say "before"\n  stop\n  say "after"\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "before\n")

    def test_native_stop_inside_a_condition(self) -> None:
        code, out = self._run(
            'fn(main)\n  say "before"\n  if 1 = 1\n    stop\n  end\n'
            '  say "after"\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "before\n")

    def test_native_stop_after_a_loop(self) -> None:
        code, out = self._run(
            'fn(main)\n  repeat 2\n    say "tick"\n  end\n  stop\n'
            '  say "never"\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "tick\ntick\n")

    def test_native_skipped_stop_lets_the_program_finish(self) -> None:
        code, out = self._run(
            'fn(main)\n  if 1 = 2\n    stop\n  end\n  say "done"\nend\ncall fn(main)\n'
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "done\n")


if __name__ == "__main__":
    unittest.main()
