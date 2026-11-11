"""Text parameters: functions accept and use text arguments on both backends."""

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

PROGRAM = """\
fn(greet, who)
  output "hi " & var(who)
end

fn(shout, s)
  output upper(var(s)) & "!"
end

fn(tag, mark, n)
  output "[" & var(mark) & "]" & var(n)
end

fn(is_hi, s)
  if var(s) = "hi"
    output 1
  end
  output 0
end

fn(echo, s)
  output var(s)
end

fn(repeat_text, s, n)
  if var(n) <= 0
    output ""
  end
  output var(s) & call fn(repeat_text, var(s), var(n) - 1)
end

fn(main)
  set var(name) = "Bob"
  say call fn(greet, var(name))
  say call fn(shout, "quiet")
  say call fn(tag, "x", 7)
  say call fn(is_hi, "hi")
  say call fn(is_hi, "ho")
  say call fn(echo, call fn(greet, "ada"))
  say len(call fn(repeat_text, "ab", 3))
end
call fn(main)
"""

EXPECTED = "hi Bob\nQUIET!\n[x]7\n1\n0\nhi ada\n6\n"


def run_c(source: str) -> str:
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
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=20
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


class TextParameterCTests(unittest.TestCase):
    def test_text_parameters_work_end_to_end(self) -> None:
        self.assertEqual(run_c(PROGRAM), EXPECTED)

    def test_text_parameter_rejects_a_number_argument(self) -> None:
        # `upper()` forces the parameter to be text, so a number is rejected.
        source = (
            "fn(shout, s)\n  output upper(var(s))\nend\n"
            "fn(main)\n  say call fn(shout, 5)\nend\ncall fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bad.ANVL"
            path.write_text(source, encoding="utf-8")
            # The kind check runs during validation, so it fires before codegen.
            with self.assertRaises(CompileError) as caught:
                functions, top, variables, arrays = parse(path, source)
                emit_c(path, functions, top, variables, arrays)
        self.assertIn("takes text", str(caught.exception))

    def test_a_number_joined_into_a_parameter_is_legal(self) -> None:
        source = (
            'fn(greet, who)\n  output "hi " & var(who)\nend\n'
            "fn(main)\n  say call fn(greet, 5)\nend\ncall fn(main)\n"
        )
        self.assertEqual(run_c(source), "hi 5\n")


class TextParameterNativeTests(unittest.TestCase):
    def _run(self, source: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=20
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.replace("\r\n", "\n")

    def test_text_parameters_work_end_to_end(self) -> None:
        self.assertEqual(self._run(PROGRAM), EXPECTED)

    def test_native_names_the_parameter_on_a_kind_mismatch(self) -> None:
        source = (
            "fn(add, n)\n  output var(n) + 1\nend\n"
            'fn(main)\n  say call fn(add, "x")\nend\ncall fn(main)\n'
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bad.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            with self.assertRaises(CompileError) as caught:
                NativeCodegen(path, functions, top, variables, arrays).generate()
        self.assertIn("takes a number, but this argument is text", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
