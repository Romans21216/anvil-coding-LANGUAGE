"""The shipped Essentials library: `library import essentials` from anywhere.

Every function lives in its own file under libraries-essentials/, next to the
compiler, so a program in any directory can import it without copying a folder.
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
SOURCE = NL.join(
    [
        "library import essentials",
        "",
        "fn(main)",
        "  say call fn(gcd, 48, 18)",
        "  say call fn(lcm, 4, 6)",
        "  say call fn(factorial, 5)",
        "  say call fn(is-prime, 97)",
        "  say call fn(is-prime, 91)",
        "  say call fn(clamp, 15, 0, 10)",
        "  say call fn(fib, 10)",
        "  say call fn(power, 2, 10)",
        "  say call fn(sign, -3)",
        "  say call fn(sum-to, 10)",
        "  say call fn(percent-of, 25, 200)",
        "  say call fn(round-to, 3.14159, 2)",
        "  say call fn(distance, 0, 0, 3, 4)",
        "  say call fn(random-range, 1, 6, 12345)",
        "  say call fn(random-chance, 50, 12345)",
        "  say call fn(random-pipeline, 12345)",
        "end",
        "call fn(main)",
        "",
    ]
)

EXPECTED = [
    "6",            # gcd
    "12",           # lcm
    "120",          # factorial
    "1",            # 97 is prime
    "0",            # 91 is not
    "10",           # clamp
    "55",           # fib(10)
    "1024",         # power(2, 10)
    "-1",           # sign
    "55",           # sum-to(10)
    "12.5",         # percent-of
    "3.14",         # round-to
    "5",            # distance 3-4-5
    "2",            # random-range(1, 6, 12345)
    "1",            # random-chance(50, 12345)
    "1245520449",   # the pinned mixer value for seed 12345
]


BATCH2 = NL.join(
    [
        "library import essentials",
        "",
        "fn(main)",
        "  say call fn(is-even, 4)",
        "  say call fn(is-odd, 4)",
        "  say call fn(square, 7)",
        "  say call fn(lerp, 0, 10, 0.25)",
        "  say call fn(map-range, 5, 0, 10, 0, 100)",
        '  say call fn(text-repeat, "ab", 3)',
        '  say "[" & call fn(pad-left, "7", 3) & "]"',
        '  say call fn(text-reverse, "abc")',
        "end",
        "call fn(main)",
        "",
    ]
)
EXPECTED2 = ["1", "0", "49", "2.5", "50", "ababab", "[  7]", "cba"]


class EssentialsTests(unittest.TestCase):
    def _run(self, backend: str, source_text: str = SOURCE) -> list[str]:
        with tempfile.TemporaryDirectory() as temp:
            base = pathlib.Path(temp)
            source = base / "essentials.ANVL"
            source.write_text(source_text, encoding="utf-8")
            executable = base / "essentials.exe"
            functions, top, variables, arrays = parse(source, source_text)
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(source, functions, top, variables, arrays).generate()
                )
            else:
                compiler = find_compiler(None)
                if compiler is None:
                    raise unittest.SkipTest("MSVC is not available")
                c_file = base / "essentials.c"
                c_file.write_text(
                    emit_c(source, functions, top, variables, arrays), encoding="utf-8"
                )
                build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.splitlines()

    def test_every_function_answers_on_the_c_backend(self) -> None:
        self.assertEqual(self._run("c"), EXPECTED)

    def test_every_function_answers_the_same_natively(self) -> None:
        self.assertEqual(self._run("native"), EXPECTED)

    def test_the_requested_functions_are_all_there(self) -> None:
        folder = ROOT / "libraries-essentials"
        present = {path.stem for path in folder.glob("*.ANVL")}
        for name in (
            "random-pipeline", "random-range", "random-chance", "gcd", "lcm",
            "factorial", "is-prime", "clamp", "fib", "power", "sign", "sum-to",
            "percent-of", "round-to", "distance",
        ):
            with self.subTest(function=name):
                self.assertIn(name, present)

    def test_text_and_range_helpers_agree_on_c(self) -> None:
        self.assertEqual(self._run("c", BATCH2), EXPECTED2)

    def test_text_and_range_helpers_agree_natively(self) -> None:
        self.assertEqual(self._run("native", BATCH2), EXPECTED2)


if __name__ == "__main__":
    unittest.main()
