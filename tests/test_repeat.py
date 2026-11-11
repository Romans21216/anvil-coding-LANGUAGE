"""`repeat <count>` runs a block that many times (sugar over for loops)."""

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


class RepeatParseTests(unittest.TestCase):
    def test_repeat_desugars_to_a_counted_for_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  repeat 3\n    say "hi"\n  end\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
        node = functions["main"].body[0]
        self.assertEqual(node.kind, "for")
        self.assertEqual(node.params, ["1", "3", "1"])
        self.assertEqual(len(node.body), 1)

    def test_repeat_needs_a_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = "fn(main)\n  repeat\n  end\nend\n"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, text)
        self.assertIn("repeat needs a count", str(caught.exception))

    def test_repeat_needs_a_function(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'repeat 2\n  say "x"\nend\n'
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, text)
        self.assertIn("must be inside a function", str(caught.exception))


class RepeatCRuntimeTests(unittest.TestCase):
    def _expect(self, text: str, want: str) -> None:
        code, out = run_c(text)
        self.assertEqual(code, 0, out)
        self.assertEqual(out, want)

    def test_repeat_runs_the_block_n_times(self) -> None:
        self._expect(
            'fn(main)\n  repeat 3\n    say "hi"\n  end\nend\ncall fn(main)\n',
            "hi\nhi\nhi\n",
        )

    def test_repeat_zero_runs_nothing(self) -> None:
        self._expect(
            'fn(main)\n  repeat 0\n    say "no"\n  end\nend\ncall fn(main)\n',
            "",
        )

    def test_repeat_accepts_an_expression_count(self) -> None:
        self._expect(
            'fn(main)\n  set var(n) = 2\n  repeat var(n) * 2\n    say "x"\n  end\n'
            "end\ncall fn(main)\n",
            "x\nx\nx\nx\n",
        )

    def test_nested_repeats(self) -> None:
        self._expect(
            'fn(main)\n  repeat 2\n    repeat 2\n      say "nest"\n    end\n  end\n'
            "end\ncall fn(main)\n",
            "nest\nnest\nnest\nnest\n",
        )

    def test_negative_count_runs_nothing(self) -> None:
        self._expect(
            'fn(main)\n  repeat -3\n    say "no"\n  end\nend\ncall fn(main)\n',
            "",
        )

    def test_repeat_with_wait(self) -> None:
        self._expect(
            'fn(main)\n  repeat 2\n    say "tick"\n    wait 0.01\n  end\n'
            "end\ncall fn(main)\n",
            "tick\ntick\n",
        )


class RepeatNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_repeat_runs_the_block_n_times(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  repeat 3\n    say "hi"\n  end\nend\ncall fn(main)\n'
            ),
            "hi\nhi\nhi\n",
        )

    def test_native_repeat_zero_and_negative_run_nothing(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  repeat 0\n    say "no"\n  end\n  repeat -2\n'
                '    say "no"\n  end\nend\ncall fn(main)\n'
            ),
            "",
        )

    def test_native_repeat_expression_count_and_nesting(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(n) = 2\n  repeat var(n) * 2\n    say "x"\n  end\n'
                '  repeat 2\n    repeat 2\n      say "nest"\n    end\n  end\n'
                "end\ncall fn(main)\n"
            ),
            "x\nx\nx\nx\nnest\nnest\nnest\nnest\n",
        )

    def test_native_repeat_with_arithmetic_body(self) -> None:
        self.assertEqual(
            self._run(
                "fn(main)\n  set var(total) = 0\n"
                "  repeat 4\n    set var(total) = var(total) + 2\n  end\n"
                '  say var(total)\nend\ncall fn(main)\n'
            ),
            "8\n",
        )


if __name__ == "__main__":
    unittest.main()
