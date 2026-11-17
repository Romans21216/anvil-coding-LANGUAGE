"""All six shipped libraries import together in one program."""

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
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

NL = chr(10)
SOURCE = NL.join(
    [
        "library import essentials",
        "library import math",
        "library import text",
        "library import geometry",
        "library import units",
        "library import validate",
        "",
        "fn(main)",
        "  say call fn(gcd, 48, 18)",
        "  say call fn(nth-prime, 5)",
        "  say call fn(capitalize, \"library\")",
        "  say call fn(area-rect, 2, 3)",
        "  say call fn(km-to-miles, 1)",
        '  say call fn(is-digit-text, "42")',
        "end",
        "call fn(main)",
        "",
    ]
)

EXPECTED = ["6", "11", "Library", "6", "0.621371", "1"]


class AllLibrariesImportTests(unittest.TestCase):
    def _run(self, backend: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            source = base / "everything.ANVL"
            source.write_text(SOURCE, encoding="utf-8")
            executable = base / "everything.exe"
            functions, top, variables, arrays = parse(source, SOURCE)
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(source, functions, top, variables, arrays).generate()
                )
            else:
                compiler = find_compiler(None)
                if compiler is None:
                    raise unittest.SkipTest("MSVC is not available")
                c_file = base / "everything.c"
                c_file.write_text(
                    emit_c(source, functions, top, variables, arrays), encoding="utf-8"
                )
                build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=90
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_six_imports_in_one_program_on_c(self) -> None:
        self.assertEqual(self._run("c"), EXPECTED)

    def test_six_imports_in_one_program_natively(self) -> None:
        self.assertEqual(self._run("native"), EXPECTED)


if __name__ == "__main__":
    unittest.main()
