"""libraries-units and libraries-validate: conversions and text predicates."""

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
        "library import units",
        "library import validate",
        "",
        "fn(main)",
        "  say call fn(celsius-to-fahrenheit, 100)",
        "  say call fn(fahrenheit-to-celsius, 212)",
        "  say call fn(celsius-to-kelvin, 0)",
        "  say call fn(kelvin-to-celsius, 273.15)",
        "  say call fn(km-to-miles, 10)",
        "  say call fn(miles-to-km, 10)",
        "  say call fn(kg-to-pounds, 10)",
        "  say call fn(pounds-to-kg, 10)",
        "  say call fn(meters-to-feet, 10)",
        "  say call fn(feet-to-meters, 10)",
        '  say call fn(is-empty, "")',
        '  say call fn(is-empty, "x")',
        '  say call fn(is-digit-text, "12345")',
        '  say call fn(is-digit-text, "12a45")',
        '  say call fn(is-alpha-text, "Hello")',
        '  say call fn(is-alpha-text, "Hello1")',
        '  say call fn(is-number-text, "-42")',
        '  say call fn(is-number-text, "-")',
        '  say call fn(is-space-text, "   ")',
        '  say call fn(is-space-text, " a ")',
        '  say call fn(is-upper-text, "ABC")',
        '  say call fn(is-upper-text, "ABc")',
        "end",
        "call fn(main)",
        "",
    ]
)

EXPECTED = [
    "212", "100", "273.15", "0",
    "6.213712", "16.09344", "22.046226", "4.535924", "32.808399", "3.048",
    "1", "0",   # is-empty
    "1", "0",   # is-digit-text
    "1", "0",   # is-alpha-text
    "1", "0",   # is-number-text
    "1", "0",   # is-space-text
    "1", "0",   # is-upper-text
]


class UnitsAndValidateTests(unittest.TestCase):
    def _run(self, backend: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            source = base / "uv.ANVL"
            source.write_text(SOURCE, encoding="utf-8")
            executable = base / "uv.exe"
            functions, top, variables, arrays = parse(source, SOURCE)
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(source, functions, top, variables, arrays).generate()
                )
            else:
                compiler = find_compiler(None)
                if compiler is None:
                    raise unittest.SkipTest("MSVC is not available")
                c_file = base / "uv.c"
                c_file.write_text(
                    emit_c(source, functions, top, variables, arrays), encoding="utf-8"
                )
                build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_units_and_predicates_agree_on_c(self) -> None:
        self.assertEqual(self._run("c"), EXPECTED)

    def test_units_and_predicates_agree_natively(self) -> None:
        self.assertEqual(self._run("native"), EXPECTED)

    def test_folders_hold_the_advertised_functions(self) -> None:
        expected = {
            "libraries-units": {
                "celsius-to-fahrenheit", "fahrenheit-to-celsius",
                "celsius-to-kelvin", "kelvin-to-celsius", "km-to-miles",
                "miles-to-km", "kg-to-pounds", "pounds-to-kg",
                "meters-to-feet", "feet-to-meters",
            },
            "libraries-validate": {
                "is-empty", "is-digit-text", "is-alpha-text",
                "is-number-text", "is-space-text", "is-upper-text",
            },
        }
        for folder, names in expected.items():
            present = {path.stem for path in (ROOT / folder).glob("*.ANVL")}
            with self.subTest(folder=folder):
                self.assertEqual(present, names)


if __name__ == "__main__":
    unittest.main()
