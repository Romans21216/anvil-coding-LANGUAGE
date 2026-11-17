"""libraries-geometry: shape math on both backends."""

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
        "library import geometry",
        "",
        "fn(main)",
        "  say call fn(area-rect, 3, 4)",
        "  say call fn(perimeter-rect, 3, 4)",
        "  say call fn(area-triangle, 6, 4)",
        "  say call fn(area-triangle-sides, 3, 4, 5)",
        "  say call fn(area-triangle-sides, 1, 1, 10)",
        "  say call fn(circumference, 1)",
        "  say call fn(point-in-rect, 5, 5, 0, 0, 10, 10)",
        "  say call fn(point-in-rect, 15, 5, 0, 0, 10, 10)",
        "  say call fn(normalize-angle, -90)",
        "  say call fn(normalize-angle, 450)",
        "  say call fn(normalize-angle, 1080)",
        "  say call fn(distance-squared, 0, 0, 3, 4)",
        "end",
        "call fn(main)",
        "",
    ]
)

EXPECTED = [
    "12",        # area-rect
    "14",        # perimeter-rect
    "12",        # area-triangle
    "6",         # Heron 3-4-5
    "0",         # 1,1,10 cannot close
    "6.283185",  # circumference of 1
    "1",         # inside
    "0",         # outside
    "270",       # -90 normalises
    "90",        # 450 normalises
    "0",         # 1080 normalises
    "25",        # 3-4 distance squared
]


class GeometryTests(unittest.TestCase):
    def _run(self, backend: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            source = base / "geo.ANVL"
            source.write_text(SOURCE, encoding="utf-8")
            executable = base / "geo.exe"
            functions, top, variables, arrays = parse(source, SOURCE)
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(source, functions, top, variables, arrays).generate()
                )
            else:
                compiler = find_compiler(None)
                if compiler is None:
                    raise unittest.SkipTest("MSVC is not available")
                c_file = base / "geo.c"
                c_file.write_text(
                    emit_c(source, functions, top, variables, arrays), encoding="utf-8"
                )
                build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_geometry_agrees_on_c(self) -> None:
        self.assertEqual(self._run("c"), EXPECTED)

    def test_geometry_agrees_natively(self) -> None:
        self.assertEqual(self._run("native"), EXPECTED)

    def test_the_folder_holds_eight_functions(self) -> None:
        present = {path.stem for path in (ROOT / "libraries-geometry").glob("*.ANVL")}
        self.assertEqual(
            present,
            {
                "area-rect", "perimeter-rect", "area-triangle",
                "area-triangle-sides", "circumference", "point-in-rect",
                "normalize-angle", "distance-squared",
            },
        )


if __name__ == "__main__":
    unittest.main()
