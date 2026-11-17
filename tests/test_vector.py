"""libraries-vector: two-dimensional vector math on both backends."""

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
        "library import vector",
        "",
        "fn(main)",
        "  say call fn(dot, 1, 2, 3, 4)",
        "  say call fn(length, 3, 4)",
        "  say call fn(normalize-x, 3, 4)",
        "  say call fn(normalize-y, 3, 4)",
        "  say call fn(normalize-x, 0, 0)",
        "  say call fn(rotate-x, 1, 0, 180)",
        "  say call fn(rotate-y, 1, 0, 90)",
        "  say call fn(reflect-x, 1, 1, 0, 1)",
        "  say call fn(reflect-y, 1, 1, 0, 1)",
        "end",
        "call fn(main)",
        "",
    ]
)
EXPECTED = ["11", "5", "0.6", "0.8", "0", "-1", "1", "1", "-1"]


class VectorTests(unittest.TestCase):
    def _run(self, backend: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            source = base / "vec.ANVL"
            source.write_text(SOURCE, encoding="utf-8")
            executable = base / "vec.exe"
            functions, top, variables, arrays = parse(source, SOURCE)
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(source, functions, top, variables, arrays).generate()
                )
            else:
                compiler = find_compiler(None)
                if compiler is None:
                    raise unittest.SkipTest("MSVC is not available")
                c_file = base / "vec.c"
                c_file.write_text(
                    emit_c(source, functions, top, variables, arrays), encoding="utf-8"
                )
                build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_vector_math_agrees_on_c(self) -> None:
        self.assertEqual(self._run("c"), EXPECTED)

    def test_vector_math_agrees_natively(self) -> None:
        self.assertEqual(self._run("native"), EXPECTED)

    def test_the_folder_holds_eight_functions(self) -> None:
        present = {path.stem for path in (ROOT / "libraries-vector").glob("*.ANVL")}
        self.assertEqual(
            present,
            {
                "dot", "length", "normalize-x", "normalize-y",
                "rotate-x", "rotate-y", "reflect-x", "reflect-y",
            },
        )


if __name__ == "__main__":
    unittest.main()
