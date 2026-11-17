"""Build thin by default: release output, with debug and dynamic-CRT opt-ins."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.modules import load_program  # noqa: E402

PROGRAM = 'fn(main)\n  say "hi"\nend\ncall fn(main)\n'


class ThinBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        found = find_compiler(None)
        if found is None:
            raise unittest.SkipTest("MSVC is not available")
        cls.compiler = found[1]

    def _build(self, release: bool, dynamic_runtime: bool = False) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            path = base / "program.ANVL"
            path.write_text(PROGRAM, encoding="utf-8")
            program = load_program(path, PROGRAM)
            c_file = base / "program.c"
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
            executable = base / "program.exe"
            build_c(self.compiler, c_file, executable, release, (), dynamic_runtime)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                raise AssertionError(result.stdout + result.stderr)
            return executable.stat().st_size, result.stdout.replace("\r\n", "\n")

    def test_release_output_is_smaller_than_debug(self) -> None:
        release_size, release_output = self._build(True)
        debug_size, debug_output = self._build(False)
        self.assertEqual(release_output, "hi\n")
        self.assertEqual(debug_output, "hi\n")
        self.assertLess(release_size, debug_size)
        self.assertGreater(debug_size / release_size, 1.5)

    def test_dynamic_runtime_is_much_smaller_and_still_runs(self) -> None:
        release_size, _ = self._build(True)
        dynamic_size, output = self._build(True, dynamic_runtime=True)
        self.assertEqual(output, "hi\n")
        self.assertLess(dynamic_size * 5, release_size)


if __name__ == "__main__":
    unittest.main()
