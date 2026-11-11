"""Functions can return text; the result joins, compares and stores."""

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
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402


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
    return result.stdout.replace("\r\n", "\n")


class TextFunctionCRuntimeTests(unittest.TestCase):
    def test_literal_return_prints(self) -> None:
        self.assertEqual(
            run_c(
                'fn(greet)\n  output "hello"\nend\n'
                "fn(main)\n  say call fn(greet)\nend\ncall fn(main)\n"
            ),
            "hello\n",
        )

    def test_joined_return(self) -> None:
        self.assertEqual(
            run_c(
                'fn(glue)\n  output "a" & "b"\nend\n'
                "fn(main)\n  say call fn(glue)\nend\ncall fn(main)\n"
            ),
            "ab\n",
        )

    def test_builtin_return(self) -> None:
        self.assertEqual(
            run_c(
                'fn(shout)\n  output upper("hey")\nend\n'
                "fn(main)\n  say call fn(shout)\nend\ncall fn(main)\n"
            ),
            "HEY\n",
        )

    def test_return_stored_and_joined(self) -> None:
        self.assertEqual(
            run_c(
                'fn(greet)\n  output "hello"\nend\n'
                'fn(main)\n  set var(msg) = call fn(greet)\n'
                '  say var(msg) & "!"\nend\ncall fn(main)\n'
            ),
            "hello!\n",
        )

    def test_return_compared_as_text(self) -> None:
        self.assertEqual(
            run_c(
                'fn(greet)\n  output "hello"\nend\n'
                'fn(main)\n  if call fn(greet) = "hello"\n    say "matched"\n  end\n'
                "end\ncall fn(main)\n"
            ),
            "matched\n",
        )

    def test_text_function_calls_another(self) -> None:
        self.assertEqual(
            run_c(
                'fn(inner)\n  output "deep"\nend\n'
                "fn(outer)\n  output call fn(inner)\nend\n"
                "fn(main)\n  say call fn(outer)\nend\ncall fn(main)\n"
            ),
            "deep\n",
        )

    def test_return_inside_a_join(self) -> None:
        self.assertEqual(
            run_c(
                'fn(greet)\n  output "hi"\nend\n'
                'fn(main)\n  say "say: " & call fn(greet)\nend\ncall fn(main)\n'
            ),
            "say: hi\n",
        )

    def test_join_of_a_returned_join(self) -> None:
        self.assertEqual(
            run_c(
                'fn(tag)\n  output "x" & "y"\nend\n'
                'fn(main)\n  say "[" & call fn(tag) & "]"\n'
                "  say len(call fn(tag))\nend\ncall fn(main)\n"
            ),
            "[xy]\n2\n",
        )

    def test_nested_function_joins(self) -> None:
        self.assertEqual(
            run_c(
                'fn(inner)\n  output "i" & "j"\nend\n'
                'fn(outer)\n  output "[" & call fn(inner) & "]" & "!"\nend\n'
                "fn(main)\n  say call fn(outer)\n"
                '  say "<" & call fn(outer) & ">"\n'
                '  set var(x) = call fn(inner) & "-" & call fn(inner)\n'
                "  say var(x)\nend\ncall fn(main)\n"
            ),
            "[ij]!\n<[ij]!>\nij-ij\n",
        )


class TextFunctionNativeTests(unittest.TestCase):
    def _run(self, text: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "sample.ANVL"
            source.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(source, text)
            executable = pathlib.Path(temp) / "sample.exe"
            executable.write_bytes(
                NativeCodegen(source, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.replace("\r\n", "\n")

    def test_native_literal_return_prints(self) -> None:
        self.assertEqual(
            self._run(
                'fn(greet)\n  output "hello"\nend\n'
                "fn(main)\n  say call fn(greet)\nend\ncall fn(main)\n"
            ),
            "hello\n",
        )

    def test_native_joined_return(self) -> None:
        self.assertEqual(
            self._run(
                'fn(glue)\n  output "a" & "b"\nend\n'
                "fn(main)\n  say call fn(glue)\nend\ncall fn(main)\n"
            ),
            "ab\n",
        )

    def test_native_return_stored_joined_and_compared(self) -> None:
        self.assertEqual(
            self._run(
                'fn(greet)\n  output "hello"\nend\n'
                "fn(main)\n  set var(msg) = call fn(greet)\n"
                '  say var(msg) & "!"\n'
                '  if call fn(greet) = "hello"\n    say "matched"\n  end\n'
                '  say "[" & call fn(greet) & "]"\n'
                "  say len(call fn(greet))\n"
                "end\ncall fn(main)\n"
            ),
            "hello!\nmatched\n[hello]\n5\n",
        )

    def test_native_text_function_calls_another(self) -> None:
        self.assertEqual(
            self._run(
                'fn(inner)\n  output "deep"\nend\n'
                "fn(outer)\n  output call fn(inner)\nend\n"
                "fn(main)\n  say call fn(outer)\nend\ncall fn(main)\n"
            ),
            "deep\n",
        )

    def test_native_join_of_a_returned_join(self) -> None:
        self.assertEqual(
            self._run(
                'fn(tag)\n  output "x" & "y"\nend\n'
                'fn(main)\n  say "[" & call fn(tag) & "]"\n'
                "  say len(call fn(tag))\nend\ncall fn(main)\n"
            ),
            "[xy]\n2\n",
        )


if __name__ == "__main__":
    unittest.main()
