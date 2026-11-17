"""random(seed) is a compiler builtin: no include, same value on both backends."""

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
from compiler.native_codegen import NativeCodegen  # noqa: E402

SOURCE = (
    "fn(main)\n"
    "  say random(12345)\n"
    "  say random(1)\n"
    "end\ncall fn(main)\n"
)

EXPECTED = "1245520449\n1276795139\n"


def run(backend: str, source: str = SOURCE) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        (temp_path / "random_pipeline.ANVL").write_text(
            (ROOT / "stdlib" / "random_pipeline.ANVL").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        path = temp_path / "call.ANVL"
        path.write_text(source, encoding="utf-8")
        program = load_program(path, source)
        if backend == "native":
            executable = temp_path / "call.exe"
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
            c_file = temp_path / "call.c"
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
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            executable = temp_path / "call.exe"
            build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=60
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


class RandomBuiltinTests(unittest.TestCase):
    def test_random_needs_no_include_and_matches_across_backends(self) -> None:
        for backend in ("c", "native"):
            with self.subTest(backend=backend):
                self.assertEqual(run(backend), EXPECTED)

    def test_builtin_agrees_with_calling_the_mixer_directly(self) -> None:
        direct_lines = [
            'include "random_pipeline.ANVL"',
            "",
            "fn(main)",
            "  say call fn(random-pipeline, 12345)",
            "  say call fn(random-pipeline, 1)",
            "end",
            "call fn(main)",
            "",
        ]
        self.assertEqual(run("native"), run("native", chr(10).join(direct_lines)))


if __name__ == "__main__":
    unittest.main()
