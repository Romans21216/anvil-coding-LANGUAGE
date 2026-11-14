"""`import builtins` plus the compiler's own analysis of what a program needs."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.builtin_usage import BUILTIN_MODULES, used_builtins  # noqa: E402
from compiler.common import CompileError  # noqa: E402
from compiler.modules import load_program  # noqa: E402
from compiler.parser import parse  # noqa: E402

PROGRAM = (
    "import builtins\n"
    "\n"
    "fn(main)\n"
    '  say floor(3.7)\n'
    '  say upper("hi")\n'
    "end\n"
    "call fn(main)\n"
)


class ImportStatementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _parse(self, source: str):
        path = self.base / "program.ANVL"
        path.write_text(source, encoding="utf-8")
        return path, load_program(path, source)

    def test_import_is_a_top_level_statement(self) -> None:
        path, program = self._parse(PROGRAM)
        self.assertEqual(program.top[0].kind, "import")
        self.assertEqual(program.top[0].value, "builtins")

    def test_the_compiler_resolves_only_the_builtins_that_are_used(self) -> None:
        _, program = self._parse(PROGRAM)
        self.assertEqual(used_builtins(program.functions, program.top), ["floor", "upper"])

    def test_an_unused_import_resolves_to_nothing(self) -> None:
        _, program = self._parse(
            "import builtins\n\nfn(main)\n  say 1 + 1\nend\ncall fn(main)\n"
        )
        self.assertEqual(used_builtins(program.functions, program.top), [])

    def test_unreachable_functions_do_not_pull_builtins_in(self) -> None:
        source = (
            "import builtins\n"
            "\n"
            "fn(spare)\n"
            "  output sqrt(16)\n"
            "end\n"
            "\n"
            "fn(main)\n"
            "  say abs(-2)\n"
            "end\n"
            "call fn(main)\n"
        )
        _, program = self._parse(source)
        self.assertEqual(used_builtins(program.functions, program.top), ["abs"])

    def test_unknown_module_is_rejected_with_the_available_list(self) -> None:
        path = self.base / "program.ANVL"
        path.write_text(
            "import telepathy\n\nfn(main)\n  say 1\nend\ncall fn(main)\n", encoding="utf-8"
        )
        with self.assertRaises(CompileError) as caught:
            parse(path, path.read_text(encoding="utf-8"))
        message = str(caught.exception)
        self.assertIn("unknown import 'telepathy'", message)
        for module in BUILTIN_MODULES:
            self.assertIn(module, message)

    def test_import_inside_a_function_is_rejected(self) -> None:
        path = self.base / "program.ANVL"
        path.write_text(
            "fn(main)\n  import builtins\n  say 1\nend\ncall fn(main)\n", encoding="utf-8"
        )
        with self.assertRaises(CompileError) as caught:
            parse(path, path.read_text(encoding="utf-8"))
        self.assertIn("import must be at top level", str(caught.exception))

    def test_the_program_still_runs_on_both_backends(self) -> None:
        from compiler.build import build_c, find_compiler
        from compiler.codegen import emit_c
        from compiler.native_codegen import NativeCodegen

        path, program = self._parse(PROGRAM)
        compiler = find_compiler(None)
        for backend in ("c", "native"):
            with self.subTest(backend=backend):
                executable = self.base / f"program_{backend}.exe"
                if backend == "native":
                    executable.write_bytes(
                        NativeCodegen(
                            path,
                            program.functions,
                            program.top,
                            program.variables,
                            program.arrays,
                        ).generate()
                    )
                else:
                    if compiler is None:
                        raise unittest.SkipTest("MSVC is not available")
                    c_file = self.base / "program.c"
                    c_file.write_text(
                        emit_c(
                            path,
                            program.functions,
                            program.top,
                            program.variables,
                            program.arrays,
                        ),
                        encoding="utf-8",
                    )
                    build_c(compiler[1], c_file, executable, True)
                result = subprocess.run(
                    [str(executable)], capture_output=True, text=True, timeout=60
                )
                self.assertEqual(result.stdout.replace("\r\n", "\n"), "3\nHI\n")


if __name__ == "__main__":
    unittest.main()
