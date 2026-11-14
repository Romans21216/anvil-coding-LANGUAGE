"""Recursive text-returning functions.

The C backend builds the reversed text correctly. The native backend shares its
text scratch buffers per call site, so a recursive call rewrites the buffer an
outer frame is still pointing at and the join reads the wrong characters. The
native case is marked expectedFailure: when the buffers become per-frame this
test turns into an unexpected success and the marker should be removed.
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
        "fn(reverse-from, text, index)",
        "  if var(index) < 0",
        '    output ""',
        "  end",
        '  output mid(var(text), var(index), 1) & call fn(reverse-from, var(text), var(index) - 1)',
        "end",
        "",
        "fn(reverse, text)",
        "  output call fn(reverse-from, var(text), len(var(text)) - 1)",
        "end",
        "",
        "fn(main)",
        '  say call fn(reverse, "abc")',
        "end",
        "call fn(main)",
        "",
    ]
)


def run(backend: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        base = pathlib.Path(temp)
        source = base / "rev.ANVL"
        source.write_text(SOURCE, encoding="utf-8")
        executable = base / "rev.exe"
        functions, top, variables, arrays = parse(source, SOURCE)
        if backend == "native":
            executable.write_bytes(
                NativeCodegen(source, functions, top, variables, arrays).generate()
            )
        else:
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            c_file = base / "rev.c"
            c_file.write_text(
                emit_c(source, functions, top, variables, arrays), encoding="utf-8"
            )
            build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=60
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stderr}")
    return result.stdout.strip()


class TextRecursionTests(unittest.TestCase):
    def test_c_reverses_text_recursively(self) -> None:
        self.assertEqual(run("c"), "cba")

    @unittest.expectedFailure
    def test_native_reverses_text_recursively(self) -> None:
        # Known limitation: static per-call-site text buffers. "abc" currently
        # comes back as "aaa" because the recursive call overwrites the buffer
        # the outer frame still points at.
        self.assertEqual(run("native"), "cba")


if __name__ == "__main__":
    unittest.main()
