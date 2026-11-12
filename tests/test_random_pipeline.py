"""The stdlib 32-stage mixer, pinned by output so its behaviour cannot drift."""

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

PIPELINE = ROOT / "stdlib" / "random_pipeline.ANVL"

DRIVER = (
    'include "random_pipeline.ANVL"\n\n'
    "fn(main)\n"
    "  say call fn(random-pipeline, 12345)\n"
    "  say call fn(random-pipeline, 1)\n"
    "  say call fn(random-pipeline, 4294967295)\n"
    "end\ncall fn(main)\n"
)

EXPECTED = "1245520449\n1276795139\n"


def run(source: str, backend: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        (temp_path / "random_pipeline.ANVL").write_text(
            PIPELINE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        path = temp_path / "driver.ANVL"
        path.write_text(source, encoding="utf-8")
        program = load_program(path, source)
        if backend == "native":
            executable = temp_path / "driver.exe"
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
            c_file = temp_path / "driver.c"
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
            executable = temp_path / "driver.exe"
            build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=60
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


class RandomPipelineTests(unittest.TestCase):
    def test_outputs_are_pinned_on_both_backends(self) -> None:
        for backend in ("c", "native"):
            with self.subTest(backend=backend):
                output = run(DRIVER, backend)
                self.assertTrue(output.startswith(EXPECTED), output)

    def test_the_same_seed_always_gives_the_same_value(self) -> None:
        source = (
            'include "random_pipeline.ANVL"\n\n'
            "fn(main)\n"
            "  say call fn(random-pipeline, 777)\n"
            "  say call fn(random-pipeline, 777)\n"
            "end\ncall fn(main)\n"
        )
        self.assertEqual(run(source, "c").split("\n")[0], run(source, "c").split("\n")[1])


if __name__ == "__main__":
    unittest.main()
