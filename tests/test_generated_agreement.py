"""Generate programs, build them on both backends, and compare what they print.

The hand-written agreement table covers shapes someone thought of. This sweep
composes valid programs from a seeded generator, so combinations nobody wrote
down get exercised too. A mismatch is always a defect: same source, two answers.
"""

from __future__ import annotations

import pathlib
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.common import CompileError  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402


def program(*lines: str) -> str:
    return "\n".join(lines) + "\n"


SHAPES = (
    "arith",
    "join",
    "if",
    "while",
    "for",
    "call",
    "divide",
    "remainder",
    "rounding",
    "text equal",
    "big product",
    "negate",
)


def program_for(rng: random.Random) -> tuple[str, str]:
    """One generated program plus a short label describing its shape."""
    a, b, c = rng.randint(1, 20), rng.randint(1, 20), rng.randint(1, 9)
    op1, op2 = rng.choice(["+", "-", "*"]), rng.choice(["+", "-", "*"])
    bound = rng.randint(2, 7)
    pick = rng.choice(SHAPES)

    if pick == "arith":
        return pick, program(
            "fn(main)", f"  say ({a} {op1} {b}) {op2} {c}", "end", "call fn(main)"
        )
    if pick == "join":
        return pick, program(
            "fn(main)", f'  say "value=" & ({a} {op1} {b})', "end", "call fn(main)"
        )
    if pick == "if":
        return pick, program(
            "fn(main)",
            f"  if {a} {rng.choice(['<', '>', '='])} {b}",
            f"    say {a}",
            "  else",
            f"    say {b}",
            "  end",
            "end",
            "call fn(main)",
        )
    if pick == "while":
        return pick, program(
            "fn(main)",
            "  set local(total) = 0",
            "  set local(i) = 0",
            f"  while local(i) < {bound}",
            "    set local(total) = local(total) + local(i)",
            "    set local(i) = local(i) + 1",
            "  end",
            "  say local(total)",
            "end",
            "call fn(main)",
        )
    if pick == "for":
        return pick, program(
            "fn(main)",
            "  set local(total) = 0",
            f"  for local(i) = 0 to {bound}",
            f"    set local(total) = local(total) + local(i) {op1} {c}",
            "  end",
            "  say local(total)",
            "end",
            "call fn(main)",
        )
    if pick == "divide":
        return pick, program(
            "fn(main)", f"  say {a} / {b}", f"  say {a} / 3", "end", "call fn(main)"
        )
    if pick == "remainder":
        return pick, program(
            "fn(main)", f"  say {a} % {b}", f"  say {b} % 3", "end", "call fn(main)"
        )
    if pick == "rounding":
        return pick, program(
            "fn(main)",
            f"  say floor({a} / 3)",
            f"  say round({a} / 3)",
            f"  say min({a}, {b}) + max({a}, {b})",
            "end",
            "call fn(main)",
        )
    if pick == "text equal":
        return pick, program(
            "fn(main)",
            f'  say "{a}" == "{b}"',
            '  say "same" == "same"',
            "end",
            "call fn(main)",
        )
    if pick == "big product":
        big = rng.randint(100000, 999999)
        return pick, program(
            "fn(main)",
            f"  say {big} * {big}",
            f"  say {big} * {big} + {a}",
            "end",
            "call fn(main)",
        )
    if pick == "negate":
        return pick, program(
            "fn(main)",
            f"  say -{a} + {b}",
            f"  say ({a} - {b}) * -1",
            "end",
            "call fn(main)",
        )
    return pick, program(
        "fn(combine, x, y, z)",
        f"  output (var(x) {op1} var(y)) {op2} var(z)",
        "end",
        "fn(main)",
        f"  say call fn(combine, {a}, {b}, {c})",
        "end",
        "call fn(main)",
    )


def run_backend(source: str, backend: str, compiler) -> str | None:
    """The program's output, or None when the backend refuses it."""
    with tempfile.TemporaryDirectory() as temp:
        work = pathlib.Path(temp)
        program_path = work / "program.ANVL"
        program_path.write_text(source, encoding="utf-8")
        executable = work / "program.exe"
        functions, top, variables, arrays = parse(program_path, source)
        try:
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(
                        program_path, functions, top, variables, arrays
                    ).generate()
                )
            else:
                c_file = work / "program.c"
                c_file.write_text(
                    emit_c(program_path, functions, top, variables, arrays),
                    encoding="utf-8",
                )
                build_c(str(compiler), c_file, executable, True)
        except CompileError:
            return None
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return f"exit {result.returncode}: {result.stdout}{result.stderr}"
        return result.stdout.replace("\r\n", "\n")


class GeneratedAgreementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        found = find_compiler(None)
        if found is None:
            raise unittest.SkipTest("MSVC is not available")
        cls.compiler = found[1]

    def test_generated_programs_print_the_same_on_both_backends(self) -> None:
        rng = random.Random(20261113)
        seen = set()
        for case in range(24):
            label, source = program_for(rng)
            seen.add(label)
            with self.subTest(case=f"{case}:{label}"):
                native = run_backend(source, "native", self.compiler)
                c_output = run_backend(source, "c", self.compiler)
                self.assertEqual(c_output, native, f"{label} disagreed:\n{source}")
        self.assertGreaterEqual(len(seen), 8, f"only saw {sorted(seen)}")


if __name__ == "__main__":
    unittest.main()
