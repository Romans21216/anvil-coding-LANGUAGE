"""Text equality: `if var(answer) = "open"` works on both backends."""

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

PROGRAM = """fn(main)
  ask "Password? ", var(guess)
  if var(guess) = "open"
    say "welcome"
  else
    say "denied"
  end
end
call fn(main)
"""


def run_c(text: str, stdin_text: str) -> str:
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
            [str(executable)],
            capture_output=True,
            text=True,
            input=stdin_text,
            timeout=15,
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout


class TextCompareCRuntimeTests(unittest.TestCase):
    def test_equal_answer_takes_the_if_branch(self) -> None:
        self.assertEqual(run_c(PROGRAM, "open\n"), "Password? welcome\n")

    def test_different_answer_takes_the_else_branch(self) -> None:
        self.assertEqual(run_c(PROGRAM, "wrong\n"), "Password? denied\n")

    def test_not_equal_operator(self) -> None:
        source = (
            'fn(main)\n  set var(mode) = "demo"\n  if var(mode) != "demo"\n'
            '    say "live"\n  else\n    say "demo"\n  end\nend\ncall fn(main)\n'
        )
        self.assertEqual(run_c(source, ""), "demo\n")

    def test_compare_against_an_asked_answer_without_join(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  ask var(word)\n  if var(word) = "yes"\n    say "ok"\n  end\nend\ncall fn(main)\n',
                "yes\n",
            ),
            "ok\n",
        )

    def test_text_and_number_comparison_is_rejected(self) -> None:
        # Expression lowering happens during code generation, not at parse time.
        source = (
            'fn(main)\n  set var(name) = "Ada"\n  if var(name) = 1\n'
            '    say "never"\n  end\nend\ncall fn(main)\n'
        )
        with self.assertRaises(CompileError) as caught:
            run_c(source, "")
        self.assertIn("cannot compare text with a number", str(caught.exception))


class TextCompareNativeRuntimeTests(NativeRunMixin, unittest.TestCase):
    def test_equal_answer_takes_the_if_branch(self) -> None:
        self.assertEqual(self._run_with_stdin(PROGRAM, "open\n"), "Password? welcome\n")

    def test_different_answer_takes_the_else_branch(self) -> None:
        self.assertEqual(self._run_with_stdin(PROGRAM, "wrong\n"), "Password? denied\n")

    def test_not_equal_operator(self) -> None:
        source = (
            'fn(main)\n  set var(mode) = "demo"\n  if var(mode) != "demo"\n'
            '    say "live"\n  else\n    say "demo"\n  end\nend\ncall fn(main)\n'
        )
        self.assertEqual(self._run_with_stdin(source, ""), "demo\n")

    def _run_with_stdin(self, source: str, stdin_text: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)],
                capture_output=True,
                text=True,
                input=stdin_text,
                timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout


if __name__ == "__main__":
    unittest.main()
