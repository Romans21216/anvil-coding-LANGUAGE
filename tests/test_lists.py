"""`list name` + `add name value` + `count(name)` grow a list on both backends."""

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
    "list nums\n\nfn(main)\n  add nums 5\n  add nums 7\n  add nums 9\n"
    "  say count(nums)\n  say array(nums, 0)\n  say array(nums, 1)\n"
    "  say array(nums, 2)\n  set var(total) = 0\n"
    "  for local(i) = 0 to count(nums) - 1\n"
    "    add var(total) array(nums, local(i))\n  end\n"
    '  say "total=" & var(total)\nend\ncall fn(main)\n'
)
EXPECTED = "3\n5\n7\n9\ntotal=21\n"


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


class ListCRuntimeTests(unittest.TestCase):
    def test_add_count_and_read(self) -> None:
        self.assertEqual(run_c(PROGRAM), EXPECTED)

    def test_empty_list_counts_zero(self) -> None:
        self.assertEqual(
            run_c("list items\nfn(main)\n  say count(items)\nend\ncall fn(main)\n"),
            "0\n",
        )

    def test_list_inside_a_function(self) -> None:
        self.assertEqual(
            run_c(
                "list words\nfn(fill)\n  add words 1\n  add words 2\nend\n"
                "fn(main)\n  call fn(fill)\n  say count(words)\n"
                "  say array(words, 1)\nend\ncall fn(main)\n"
            ),
            "2\n2\n",
        )

    def test_unknown_list_is_a_clear_error(self) -> None:
        with self.assertRaises(CompileError) as caught:
            run_c("fn(main)\n  say count(missing)\nend\ncall fn(main)\n")
        self.assertIn("unknown list", str(caught.exception))


class ListIncludeTests(unittest.TestCase):
    """Each included file may declare its own list."""

    def _build(self, temp: pathlib.Path) -> tuple[pathlib.Path, str]:
        (temp / "lib1.ANVL").write_text(
            "list alpha\n\nfn(fill_alpha)\n  add alpha 10\nend\n\n"
            "fn(count_alpha)\n  output count(alpha)\nend\n",
            encoding="utf-8",
        )
        (temp / "lib2.ANVL").write_text(
            "list beta\n\nfn(fill_beta)\n  add beta 20\nend\n\n"
            "fn(count_beta)\n  output count(beta)\nend\n",
            encoding="utf-8",
        )
        main = temp / "main.ANVL"
        text = (
            'include "lib1.ANVL"\ninclude "lib2.ANVL"\n\n'
            "fn(main)\n  call fn(fill_alpha)\n  call fn(fill_beta)\n"
            "  say call fn(count_alpha)\n  say call fn(count_beta)\n"
            "end\ncall fn(main)\n"
        )
        main.write_text(text, encoding="utf-8")
        return main, text

    def test_c_backend_lists_across_includes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            main, text = self._build(temp_path)
            functions, top, variables, arrays = parse(
                main, text, include_root=temp_path
            )
            c_file = temp_path / "main.c"
            c_file.write_text(
                emit_c(main, functions, top, variables, arrays), encoding="utf-8"
            )
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            executable = temp_path / "main.exe"
            build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "1\n1\n")

    def test_native_backend_lists_across_includes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            main, text = self._build(temp_path)
            functions, top, variables, arrays = parse(
                main, text, include_root=temp_path
            )
            executable = temp_path / "main.exe"
            executable.write_bytes(
                NativeCodegen(main, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "1\n1\n")


class ListNativeTests(NativeRunMixin, unittest.TestCase):
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
        return result.stdout.replace("\r\n", "\n")

    def test_native_add_count_and_read(self) -> None:
        self.assertEqual(self._run(PROGRAM), EXPECTED)

    def test_native_empty_list_counts_zero(self) -> None:
        self.assertEqual(
            self._run("list items\nfn(main)\n  say count(items)\nend\ncall fn(main)\n"),
            "0\n",
        )

    def test_native_list_inside_a_function(self) -> None:
        self.assertEqual(
            self._run(
                "list words\nfn(fill)\n  add words 1\n  add words 2\nend\n"
                "fn(main)\n  call fn(fill)\n  say count(words)\n"
                "  say array(words, 1)\nend\ncall fn(main)\n"
            ),
            "2\n2\n",
        )


if __name__ == "__main__":
    unittest.main()
