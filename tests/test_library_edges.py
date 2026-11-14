"""Degenerate inputs across all seven libraries, pinned on both backends.

These are the cases that quietly break later: zero, negatives, empty text, and
inputs that make a formula divide by zero or take a square root of nothing.
"""

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
CALLS = [
    ("-- essentials", None),
    ("gcd(0,0)", "call fn(gcd, 0, 0)"),
    ("gcd(-12,18)", "call fn(gcd, -12, 18)"),
    ("lcm(0,5)", "call fn(lcm, 0, 5)"),
    ("factorial(0)", "call fn(factorial, 0)"),
    ("factorial(4)", "call fn(factorial, 4)"),
    ("factorial(-1)", "call fn(factorial, -1)"),
    ("fib(0)", "call fn(fib, 0)"),
    ("fib(1)", "call fn(fib, 1)"),
    ("power(7,0)", "call fn(power, 7, 0)"),
    ("power(2,-1)", "call fn(power, 2, -1)"),
    ("sum-to(0)", "call fn(sum-to, 0)"),
    ("sum-to(-5)", "call fn(sum-to, -5)"),
    ("is-prime(1)", "call fn(is-prime, 1)"),
    ("is-prime(2)", "call fn(is-prime, 2)"),
    ("clamp(5,0,10)", "call fn(clamp, 5, 0, 10)"),
    ("sign(0)", "call fn(sign, 0)"),
    ("percent-of(1,0)", "call fn(percent-of, 1, 0)"),
    ("distance(0,0,0,0)", "call fn(distance, 0, 0, 0, 0)"),
    ("-- text", None),
    ("index-of(abc,empty)", 'call fn(index-of, "abc", "")'),
    ("left-of(abc,x)", 'call fn(left-of, "abc", "x")'),
    ("right-of(abc,x)", 'call fn(right-of, "abc", "x")'),
    ("count-words(spaces)", 'call fn(count-words, "   ")'),
    ("is-palindrome(empty)", 'call fn(is-palindrome, "")'),
    ("pad-right(long,3)", 'call fn(pad-right, "abcdef", 3)'),
    ("center(ab,3)", 'call fn(center, "ab", 3)'),
    ("text-repeat(x,0)", 'call fn(text-repeat, "x", 0)'),
    ("-- math", None),
    ("nth-prime(1)", "call fn(nth-prime, 1)"),
    ("nth-prime(0)", "call fn(nth-prime, 0)"),
    ("primes-below(2)", "call fn(primes-below, 2)"),
    ("digits-sum(0)", "call fn(digits-sum, 0)"),
    ("reverse-number(1200)", "call fn(reverse-number, 1200)"),
    ("is-palindrome-number(0)", "call fn(is-palindrome-number, 0)"),
    ("-- units", None),
    ("celsius-to-fahrenheit(-40)", "call fn(celsius-to-fahrenheit, -40)"),
    ("km-to-miles(0)", "call fn(km-to-miles, 0)"),
    ("-- validate", None),
    ("is-empty(empty)", 'call fn(is-empty, "")'),
    ("is-digit-text(empty)", 'call fn(is-digit-text, "")'),
    ("is-alpha-text(empty)", 'call fn(is-alpha-text, "")'),
    ("is-number-text(empty)", 'call fn(is-number-text, "")'),
    ("is-space-text(empty)", 'call fn(is-space-text, "")'),
    ("is-upper-text(empty)", 'call fn(is-upper-text, "")'),
    ("-- geometry", None),
    ("area-triangle-sides(0,5,5)", "call fn(area-triangle-sides, 0, 5, 5)"),
    ("normalize-angle(360)", "call fn(normalize-angle, 360)"),
    ("point-in-rect(corner)", "call fn(point-in-rect, 0, 0, 0, 0, 10, 10)"),
    ("-- vector", None),
    ("normalize-x(0,0)", "call fn(normalize-x, 0, 0)"),
    ("dot(0,0,1,1)", "call fn(dot, 0, 0, 1, 1)"),
    ("length(0,0)", "call fn(length, 0, 0)"),
]

EXPECTED = [
    "-- essentials",
    "0", "6", "0",              # gcd, gcd(-12,18), lcm(0,5)
    "1", "24", "0",             # factorial 0, 4, -1
    "0", "1",                   # fib 0, 1
    "1", "0",                   # power(7,0), power(2,-1)
    "0", "0",                   # sum-to 0, -5
    "0", "1",                   # is-prime 1, 2
    "5", "0", "0", "0",         # clamp, sign, percent-of, distance
    "-- text",
    "0",                        # index-of with an empty needle
    "[abc]",                    # left-of with no separator
    "[]",                       # right-of with no separator
    "0",                        # count-words of blanks
    "1",                        # the empty text is a palindrome
    "[abcdef]",                 # pad-right never truncates
    "[ab ]",                    # center of an odd width pads right
    "[]",                       # text-repeat zero times
    "-- math",
    "2", "0", "0", "0",         # nth-prime 1, 0; primes-below 2; digits-sum 0
    "21",                       # reverse-number drops the leading zero
    "1",                        # 0 reverses to itself
    "-- units",
    "-40", "0",
    "-- validate",
    "1", "0", "0", "0", "0", "0",
    "-- geometry",
    "0",                        # sides that cannot close
    "0",                        # 360 normalises to 0
    "1",                        # a corner counts as inside
    "-- vector",
    "0", "0", "0",
]


class LibraryEdgeTests(unittest.TestCase):
    def _source(self) -> str:
        lines = ["library import essentials", "library import text", "library import math",
                 "library import units", "library import validate",
                 "library import geometry", "library import vector", "", "fn(main)"]
        for label, call in CALLS:
            if call is None:
                lines.append('  say "' + label + '"')
            elif label.startswith(("left-of", "right-of", "pad-right", "center", "text-repeat")):
                lines.append('  say "[" & ' + call + ' & "]"')
            else:
                lines.append("  say " + call)
        lines += ["end", "call fn(main)", ""]
        return NL.join(lines)

    def _run(self, backend: str) -> list[str]:
        source_text = self._source()
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            source = base / "edges.ANVL"
            source.write_text(source_text, encoding="utf-8")
            executable = base / "edges.exe"
            functions, top, variables, arrays = parse(source, source_text)
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(source, functions, top, variables, arrays).generate()
                )
            else:
                compiler = find_compiler(None)
                if compiler is None:
                    raise unittest.SkipTest("MSVC is not available")
                c_file = base / "edges.c"
                c_file.write_text(
                    emit_c(source, functions, top, variables, arrays), encoding="utf-8"
                )
                build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=90
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_degenerate_inputs_agree_on_c(self) -> None:
        self.assertEqual(self._run("c"), EXPECTED)

    def test_degenerate_inputs_agree_natively(self) -> None:
        self.assertEqual(self._run("native"), EXPECTED)


if __name__ == "__main__":
    unittest.main()
