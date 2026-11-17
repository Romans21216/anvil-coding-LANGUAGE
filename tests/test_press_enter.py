"""`press enter`: pause until the player presses Enter, in both backends."""

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
from tests.test_native_x64 import NativeRunMixin  # noqa: E402

PROGRAM = """fn(main)
  say "ready"
  press enter
  say "go"
end
call fn(main)
"""


def compile_binary(text: str, backend: str, temp_path: pathlib.Path) -> pathlib.Path:
    source = temp_path / "sample.ANVL"
    source.write_text(text, encoding="utf-8")
    functions, top, variables, arrays = parse(source, text)
    if backend == "native":
        from compiler.native_codegen import NativeCodegen

        executable = temp_path / "sample.exe"
        executable.write_bytes(
            NativeCodegen(source, functions, top, variables, arrays).generate()
        )
        return executable
    c_file = temp_path / "sample.c"
    c_file.write_text(
        emit_c(source, functions, top, variables, arrays), encoding="utf-8"
    )
    compiler = find_compiler(None)
    if compiler is None:
        raise unittest.SkipTest("MSVC is not available")
    executable = temp_path / "sample.exe"
    build_c(compiler[1], c_file, executable, release=True)
    return executable


def run_with_input(executable: pathlib.Path, stdin_text: str):
    return subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        input=stdin_text,
        timeout=15,
    )


class PressEnterTests(NativeRunMixin, unittest.TestCase):
    def _assert_program(self, backend: str) -> None:
        with tempfile.TemporaryDirectory() as temp:
            executable = compile_binary(PROGRAM, backend, pathlib.Path(temp))
            result = run_with_input(executable, "\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "ready\nPress Enter to continue...\ngo\n")

    def test_c_backend_waits_for_enter(self) -> None:
        self._assert_program("c")

    def test_native_backend_waits_for_enter(self) -> None:
        self._assert_program("native")

    def test_typed_text_is_discarded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            executable = compile_binary(PROGRAM, "c", pathlib.Path(temp))
            result = run_with_input(executable, "hello there\n")
        self.assertEqual(result.returncode, 0)
        self.assertIn("go\n", result.stdout)

    def test_top_level_press_enter_runs_during_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            executable = compile_binary(
                'press enter\nfn(main)\n  say "started"\nend\ncall fn(main)\n',
                "c",
                pathlib.Path(temp),
            )
            result = run_with_input(executable, "\n")
        self.assertEqual(
            result.stdout, "Press Enter to continue...\nstarted\n"
        )


if __name__ == "__main__":
    unittest.main()
