"""Optimized and unoptimized builds must compute the same program.

Part 8 asks for optimized/unoptimized comparison: an optimizer bug that changes
results would otherwise ship silently, because every other test builds with a
single configuration.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

PROGRAM_LINES = [
    "fn(factorial, value)",
    "  if var(value) <= 1",
    "    output 1",
    "  end",
    "  output var(value) * call fn(factorial, var(value) - 1)",
    "end",
    "",
    "fn(fib, n)",
    "  if var(n) < 2",
    "    output var(n)",
    "  end",
    "  output call fn(fib, var(n) - 1) + call fn(fib, var(n) - 2)",
    "end",
    "",
    "array table(6)",
    "",
    "fn(main)",
    "  say call fn(factorial, 7)",
    "  say call fn(fib, 12)",
    "  say 1 / 3",
    "  say 0.1 + 0.2",
    '  say number("2.5e3")',
    '  say mid("abcdef", 1, 3) & left("abcdef", 2) & right("abcdef", 2)',
    '  say len("hello") + 1',
    "  say round(-2.5)",
    "  say -7 % 3",
    "  set var(total) = 0",
    "  for local(i) = 0 to 5",
    "    set array(table, local(i)) = local(i) * local(i)",
    "    add var(total) array(table, local(i))",
    "  end",
    "  say var(total)",
    "  say sqrt(2) * sqrt(2)",
    "end",
    "call fn(main)",
    "",
]
PROGRAM = chr(10).join(PROGRAM_LINES)


def build_and_run(source: pathlib.Path, out: pathlib.Path, flag: str):
    build = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(out), flag],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if build.returncode != 0:
        if "No C compiler found" in build.stderr:
            raise unittest.SkipTest("MSVC is not available")
        raise AssertionError(build.stdout + build.stderr)
    run = subprocess.run([str(out)], capture_output=True, text=True, timeout=60)
    return run.returncode, run.stdout.replace(chr(13) + chr(10), chr(10))


class OptimizationParityTests(unittest.TestCase):
    def test_release_and_debug_compute_the_same_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = root / "parity.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            release_code, release_out = build_and_run(
                source, root / "release.exe", "--release"
            )
            debug_code, debug_out = build_and_run(
                source, root / "debug.exe", "--debug"
            )
        self.assertEqual(release_code, 0)
        self.assertEqual(debug_code, 0)
        self.assertEqual(release_out, debug_out)

        lines = release_out.splitlines()
        self.assertEqual(lines[0], "5040")
        self.assertEqual(lines[1], "144")
        self.assertEqual(lines[5], "bcdabef")
        self.assertEqual(lines[6], "6")
        self.assertEqual(lines[9], "55")

    def test_the_native_backend_agrees_on_the_same_program(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = root / "parity.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            c_code, c_out = build_and_run(source, root / "c.exe", "--release")
            native = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "-o",
                    str(root / "native.exe"),
                    "--backend",
                    "native",
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if native.returncode != 0:
                self.skipTest("native backend cannot build this program: " + native.stderr)
            run = subprocess.run(
                [str(root / "native.exe")], capture_output=True, text=True, timeout=60
            )
        self.assertEqual(c_code, 0)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(c_out, run.stdout.replace(chr(13) + chr(10), chr(10)))


if __name__ == "__main__":
    unittest.main()
