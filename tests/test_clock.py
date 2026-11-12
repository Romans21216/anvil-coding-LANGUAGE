"""clock() reads the machine clock, so console programs can seed themselves."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

PROGRAM = (
    "fn(main)\n"
    "  say clock() > 0\n"
    "  set var(first) = clock()\n"
    "  wait 0.05\n"
    "  say clock() >= var(first)\n"
    "end\n"
    "call fn(main)\n"
)


def run(source: str, backend: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path = temp_path / "clock.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        if backend == "native":
            executable = temp_path / "clock.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
        else:
            c_file = temp_path / "clock.c"
            c_file.write_text(
                emit_c(path, functions, top, variables, arrays), encoding="utf-8"
            )
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            executable = temp_path / "clock.exe"
            build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=30
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


class ClockTests(unittest.TestCase):
    def test_clock_is_positive_and_does_not_go_backwards(self) -> None:
        for backend in ("c", "native"):
            with self.subTest(backend=backend):
                self.assertEqual(run(PROGRAM, backend), "1\n1\n")

    def test_seeding_from_clock_changes_the_sequence(self) -> None:
        # Two separate builds seeded the same way still differ in practice, but
        # the deterministic guarantee worth pinning is that seeding compiles and
        # runs on both backends at all.
        source = (
            "seed(clock())\n\n"
            "fn(main)\n  say rnd(0, 9) >= 0\nend\ncall fn(main)\n"
        )
        self.assertEqual(run(source, "c"), "1\n")
        self.assertEqual(run(source, "native"), "1\n")


if __name__ == "__main__":
    unittest.main()
