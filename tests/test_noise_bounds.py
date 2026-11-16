"""C8-7: `noise`/`fbm` coordinate bounds agree across both backends."""

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


def run(backend: str, text: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        source = temp_path / "sample.ANVL"
        source.write_text(text, encoding="utf-8")
        functions, top, variables, arrays = parse(source, text)
        executable = temp_path / "sample.exe"
        if backend == "native":
            executable.write_bytes(
                NativeCodegen(source, functions, top, variables, arrays).generate()
            )
        else:
            c_file = temp_path / "sample.c"
            c_file.write_text(
                emit_c(source, functions, top, variables, arrays), encoding="utf-8"
            )
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=60
        )
    return result.returncode, (result.stdout + result.stderr).replace("\r\n", "\n")


VALID = (
    "fn(main)\n"
    "  say noise(0, 0, 0)\n"
    "  say noise(1.5, 2.5, 3.5)\n"
    "  say noise(-2147483648, 0, 0)\n"
    "  say noise(2147483646, 0, 0)\n"
    "  say fbm(0, 0, 0, 4, 2, 0.5)\n"
    "end\ncall fn(main)\n"
)


class NoiseBoundsTests(unittest.TestCase):
    def test_valid_coordinates_match_on_both_backends(self) -> None:
        c_code, c_output = run("c", VALID)
        native_code, native_output = run("native", VALID)
        self.assertEqual(c_code, 0, c_output)
        self.assertEqual(native_code, 0, native_output)
        self.assertEqual(c_output, native_output)

    def test_out_of_range_coordinates_are_rejected_by_both_backends(self) -> None:
        # The accepted interval is [-2147483648, 2147483647): the exclusive
        # upper bound leaves room for the +1 lattice corner, and fbm must
        # reject a later octave whose scaled coordinate leaves the interval.
        for expression in (
            "noise(-2147483649, 0, 0)",
            "noise(2147483647, 0, 0)",
            "noise(0, 1e18, 0)",
            "fbm(1000000000, 0, 0, 4, 2, 0.5)",
        ):
            with self.subTest(expression=expression):
                source = f"fn(main)\n  say {expression}\nend\ncall fn(main)\n"
                for backend in ("c", "native"):
                    code, output = run(backend, source)
                    self.assertEqual(code, 2, f"{backend}: {output}")
                    self.assertIn("noise coordinate range error", output)


if __name__ == "__main__":
    unittest.main()
