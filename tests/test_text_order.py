"""Text ordering: `<`, `<=`, `>`, `>=` compare text alphabetically."""

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

PROGRAM = (
    'fn(main)\n'
    '  set var(a) = "apple"\n'
    '  set var(b) = "banana"\n'
    '  if var(a) < var(b)\n'
    '    say "a first"\n'
    '  end\n'
    '  if var(b) > var(a)\n'
    '    say "b last"\n'
    '  end\n'
    '  if var(a) <= var(a)\n'
    '    say "self le"\n'
    '  end\n'
    '  if var(a) >= var(b)\n'
    '    say "wrong"\n'
    '  else\n'
    '    say "correct"\n'
    '  end\n'
    '  if "apple" = var(a)\n'
    '    say "eq"\n'
    '  end\n'
    'end\n'
    'call fn(main)\n'
)
WANT = "a first\nb last\nself le\ncorrect\neq\n"


class TextOrderParseTests(unittest.TestCase):
    def test_text_cannot_compare_with_a_number(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  set var(a) = "apple"\n  if var(a) < 3\n    say "x"\n  end\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
            with self.assertRaises(CompileError) as caught:
                emit_c(path, functions, top, variables, arrays)
        self.assertIn("cannot compare text with a number", str(caught.exception))


class TextOrderCRuntimeTests(unittest.TestCase):
    def test_full_program(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "sample.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            functions, top, variables, arrays = parse(source, PROGRAM)
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
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, WANT)

    def test_prefix_orders_before_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "sample.ANVL"
            text = (
                'fn(main)\n  set var(a) = "app"\n  set var(b) = "apple"\n'
                "  if var(a) < var(b)\n    say \"prefix\"\n  end\nend\ncall fn(main)\n"
            )
            source.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(source, text)
            c_file = temp_path / "sample.c"
            c_file.write_text(
                emit_c(source, functions, top, variables, arrays), encoding="utf-8"
            )
            compiler = find_compiler(None)
            executable = temp_path / "sample.exe"
            build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.stdout, "prefix\n")


class TextOrderNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_full_program(self) -> None:
        self.assertEqual(self._run(PROGRAM), WANT)

    def test_native_prefix_orders_before_extension(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(a) = "app"\n  set var(b) = "apple"\n'
                "  if var(a) < var(b)\n    say \"prefix\"\n  end\nend\ncall fn(main)\n"
            ),
            "prefix\n",
        )

    def test_native_literal_on_the_left(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(b) = "banana"\n'
                '  if "apple" < var(b)\n    say "apple first"\n  end\n'
                "end\ncall fn(main)\n"
            ),
            "apple first\n",
        )

    def test_native_mixed_case_orders_by_bytes(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  if "Zebra" < "apple"\n    say "capitals first"\n'
                "  end\nend\ncall fn(main)\n"
            ),
            "capitals first\n",
        )


if __name__ == "__main__":
    unittest.main()
