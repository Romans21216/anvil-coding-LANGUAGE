"""libraries-text and libraries-math: a second pair of shipped libraries."""

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
        "library import text",
        "library import math",
        "",
        "fn(main)",
        '  say "[" & call fn(pad-right, "ab", 5) & "]"',
        '  say "[" & call fn(center, "hi", 6) & "]"',
        '  say call fn(capitalize, "hello")',
        '  say call fn(index-of, "hello world", "world")',
        '  say call fn(index-of, "hello", "zz")',
        '  say call fn(count-words, "the quick brown fox")',
        '  say call fn(is-palindrome, "racecar")',
        '  say call fn(is-palindrome, "hello")',
        '  say call fn(left-of, "key=value", "=")',
        '  say call fn(right-of, "key=value", "=")',
        "  say call fn(nth-prime, 10)",
        "  say call fn(primes-below, 20)",
        "  say call fn(digits-sum, 12345)",
        "  say call fn(reverse-number, 1234)",
        "  say call fn(reverse-number, -1234)",
        "  say call fn(is-palindrome-number, 12321)",
        "  say call fn(hypotenuse, 3, 4)",
        "  say call fn(area-circle, 1)",
        "  say call fn(to-degrees, 3.141592653589793)",
        "  say call fn(to-radians, 180)",
        "end",
        "call fn(main)",
        "",
    ]
)

EXPECTED = [
    "[ab   ]",      # pad-right
    "[  hi  ]",     # center
    "Hello",        # capitalize
    "6",            # index-of finds "world"
    "-1",           # index-of misses
    "4",            # count-words
    "1",            # racecar is a palindrome
    "0",            # hello is not
    "key",          # left-of
    "value",        # right-of
    "29",           # 10th prime
    "8",            # primes below 20
    "15",           # digits of 12345
    "4321",         # reverse 1234
    "-4321",        # reverse keeps the sign
    "1",            # 12321 is a numeric palindrome
    "5",            # 3-4-5
    "3.141593",     # circle of radius 1
    "180",          # pi radians in degrees
    "3.141593",     # 180 degrees in radians
]


class MoreLibraryTests(unittest.TestCase):
    def _run(self, backend: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            source = base / "more.ANVL"
            source.write_text(SOURCE, encoding="utf-8")
            executable = base / "more.exe"
            functions, top, variables, arrays = parse(source, SOURCE)
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(source, functions, top, variables, arrays).generate()
                )
            else:
                compiler = find_compiler(None)
                if compiler is None:
                    raise unittest.SkipTest("MSVC is not available")
                c_file = base / "more.c"
                c_file.write_text(
                    emit_c(source, functions, top, variables, arrays), encoding="utf-8"
                )
                build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_text_and_math_agree_on_c(self) -> None:
        self.assertEqual(self._run("c"), EXPECTED)

    def test_text_and_math_agree_natively(self) -> None:
        self.assertEqual(self._run("native"), EXPECTED)

    def test_the_folders_hold_what_the_readme_promises(self) -> None:
        expected = {
            "libraries-text": {
                "pad-right", "center", "capitalize", "index-of",
                "count-words", "is-palindrome", "left-of", "right-of",
            },
            "libraries-math": {
                "nth-prime", "primes-below", "digits-sum", "reverse-number",
                "is-palindrome-number", "hypotenuse", "area-circle",
                "to-degrees", "to-radians",
            },
        }
        for folder, names in expected.items():
            present = {path.stem for path in (ROOT / folder).glob("*.ANVL")}
            with self.subTest(folder=folder):
                self.assertEqual(present, names)


if __name__ == "__main__":
    unittest.main()
