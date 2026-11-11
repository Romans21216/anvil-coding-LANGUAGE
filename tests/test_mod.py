"""`%` gives the floating-point remainder on both backends (fmod semantics)."""

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

PROGRAM = (
    "fn(main)\n  say 7 % 3\n  say 7.5 % 2\n  say -7 % 3\n  say 7 % -3\n"
    "  say 0 % 5\n  say 2 + 7 % 3\n  say (2 + 7) % 3\nend\ncall fn(main)\n"
)
EXPECTED = "1\n1.5\n-1\n1\n0\n3\n0\n"


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


class ModCRuntimeTests(unittest.TestCase):
    def test_remainder_cases(self) -> None:
        self.assertEqual(run_c(PROGRAM), EXPECTED)

    def test_remainder_in_a_variable(self) -> None:
        self.assertEqual(
            run_c(
                'fn(main)\n  set var(n) = 17\n  set var(rest) = var(n) % 5\n'
                "  say var(rest)\nend\ncall fn(main)\n"
            ),
            "2\n",
        )


class ModNativeTests(NativeRunMixin, unittest.TestCase):
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

    def test_native_remainder_cases(self) -> None:
        self.assertEqual(self._run(PROGRAM), EXPECTED)

    def test_native_remainder_in_a_variable(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(n) = 17\n  set var(rest) = var(n) % 5\n'
                "  say var(rest)\nend\ncall fn(main)\n"
            ),
            "2\n",
        )


if __name__ == "__main__":
    unittest.main()
