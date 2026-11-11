"""Optional type annotations: number, text and bool, with inference as the default."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.common import CompileError  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402

PROGRAM = (
    "fn(main)\n"
    "  set var(score): number = 5\n"
    '  set var(name): text = "ada"\n'
    "  set var(alive): bool = true\n"
    "  set var(grown): bool = var(score) > 3\n"
    "  say var(score) + 1\n"
    "  say len(var(name))\n"
    "  say var(alive)\n"
    "  say var(grown)\n"
    "end\n"
    "call fn(main)\n"
)
EXPECTED = "6\n3\n1\n1\n"


def _parse(source: str, temp: pathlib.Path):
    path = temp / "sample.ANVL"
    path.write_text(source, encoding="utf-8")
    return path, parse(path, source)


def run_c(source: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path, (functions, top, variables, arrays) = _parse(source, temp_path)
        c_file = temp_path / "sample.c"
        c_file.write_text(
            emit_c(path, functions, top, variables, arrays), encoding="utf-8"
        )
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        executable = temp_path / "sample.exe"
        build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=20
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


def run_native(source: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path, (functions, top, variables, arrays) = _parse(source, temp_path)
        executable = temp_path / "sample.exe"
        executable.write_bytes(
            NativeCodegen(path, functions, top, variables, arrays).generate()
        )
        result = subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=20
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout.replace("\r\n", "\n")


class AnnotationTests(unittest.TestCase):
    def test_annotations_run_on_both_backends(self) -> None:
        self.assertEqual(run_c(PROGRAM), EXPECTED)
        self.assertEqual(run_native(PROGRAM), EXPECTED)

    def test_inference_still_works_without_annotations(self) -> None:
        plain = (
            "fn(main)\n  set var(n) = 4\n  set var(t) = \"ab\"\n"
            "  say var(n) + 1\n  say len(var(t))\nend\ncall fn(main)\n"
        )
        self.assertEqual(run_c(plain), "5\n2\n")
        self.assertEqual(run_native(plain), "5\n2\n")

    def test_mismatches_are_reported_before_codegen(self) -> None:
        cases = (
            ('set var(score): number = "ada"', "declared number but this value is text"),
            ("set var(name): text = 5", "declared text but this value is a number"),
            ("set var(alive): bool = 5", "declared bool but this value is a number"),
            ('set var(x): str = "a"', "unknown type 'str'"),
        )
        for line, expected in cases:
            with self.subTest(line=line), tempfile.TemporaryDirectory() as temp:
                source = f"fn(main)\n  {line}\nend\ncall fn(main)\n"
                path = pathlib.Path(temp) / "bad.ANVL"
                path.write_text(source, encoding="utf-8")
                with self.assertRaises(CompileError) as caught:
                    parse(path, source)
                self.assertIn(expected, str(caught.exception))

    def test_a_comparison_counts_as_bool(self) -> None:
        source = (
            "fn(main)\n  set var(ok): bool = 2 > 1\n  say var(ok)\nend\n"
            "call fn(main)\n"
        )
        self.assertEqual(run_c(source), "1\n")
        self.assertEqual(run_native(source), "1\n")


if __name__ == "__main__":
    unittest.main()
