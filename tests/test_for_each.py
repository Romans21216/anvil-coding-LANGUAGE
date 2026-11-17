"""`for each <item> in <list>` walks a growable list in order."""

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

PROGRAM = (
    "list nums\n"
    "fn(main)\n"
    "  add nums 4\n  add nums 7\n  add nums 9\n"
    "  set var(total) = 0\n"
    "  for each v in nums\n    add var(total) var(v)\n  end\n"
    "  say var(total)\n"
    "  for each v in nums\n    if var(v) = 7\n      continue\n    end\n"
    "    say var(v)\n  end\n"
    "end\ncall fn(main)\n"
)
EXPECTED = "20\n4\n9\n"


def run(source: str, backend: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path = temp_path / "sample.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        if backend == "native":
            executable = temp_path / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
        else:
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


class ForEachTests(unittest.TestCase):
    def test_walks_the_list_in_order(self) -> None:
        self.assertEqual(run(PROGRAM, "c"), EXPECTED)
        self.assertEqual(run(PROGRAM, "native"), EXPECTED)

    def test_empty_list_runs_the_body_zero_times(self) -> None:
        source = (
            "list nums\nfn(main)\n  set var(seen) = 0\n"
            "  for each v in nums\n    add var(seen) 1\n  end\n"
            "  say var(seen)\nend\ncall fn(main)\n"
        )
        self.assertEqual(run(source, "c"), "0\n")
        self.assertEqual(run(source, "native"), "0\n")

    def test_break_leaves_the_loop(self) -> None:
        source = (
            "list nums\nfn(main)\n  add nums 1\n  add nums 2\n  add nums 3\n"
            "  for each v in nums\n    say var(v)\n    break\n  end\n"
            "  say count(nums)\nend\ncall fn(main)\n"
        )
        self.assertEqual(run(source, "c"), "1\n3\n")
        self.assertEqual(run(source, "native"), "1\n3\n")

    def test_nested_loops_over_two_lists(self) -> None:
        source = (
            "list rows\nlist cols\nfn(main)\n  add rows 2\n  add rows 3\n"
            "  add cols 10\n  add cols 20\n"
            "  for each r in rows\n    for each c in cols\n"
            "      say var(r) * var(c)\n    end\n  end\nend\ncall fn(main)\n"
        )
        expected = "20\n40\n30\n60\n"
        self.assertEqual(run(source, "c"), expected)
        self.assertEqual(run(source, "native"), expected)

    def test_unknown_list_is_reported(self) -> None:
        source = "fn(main)\n  for each v in missing\n    say var(v)\n  end\nend\n"
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bad.ANVL"
            path.write_text("list nums\n" + source, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, "list nums\n" + source)
        self.assertIn("unknown list 'missing'", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
