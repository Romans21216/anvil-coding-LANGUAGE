"""Part 8: unbounded recursion stops with a diagnostic instead of an OS crash."""

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

SHALLOW = (
    "fn(sum, n)\n  if var(n) <= 0\n    output 0\n  end\n"
    "  output call fn(sum, var(n) - 1) + var(n)\nend\n"
    "fn(main)\n  say call fn(sum, 100)\nend\ncall fn(main)\n"
)
DEEP = (
    "fn(sum, n)\n  if var(n) <= 0\n    output 0\n  end\n"
    "  output call fn(sum, var(n) - 1) + var(n)\nend\n"
    "fn(main)\n  say call fn(sum, 200000)\nend\ncall fn(main)\n"
)


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
            [str(executable)], capture_output=True, text=True, timeout=60
        )
    return result.returncode, (result.stdout + result.stderr).replace("\r\n", "\n")


class RecursionBudgetTests(unittest.TestCase):
    def test_shallow_recursion_still_works(self) -> None:
        code, output = run_c(SHALLOW)
        self.assertEqual(code, 0, output)
        self.assertEqual(output, "5050\n")

    def test_unbounded_recursion_stops_with_a_diagnostic(self) -> None:
        code, output = run_c(DEEP)
        self.assertEqual(code, 2, output)
        self.assertIn("stack budget", output)
        self.assertIn("unbounded recursion", output)


if __name__ == "__main__":
    unittest.main()
