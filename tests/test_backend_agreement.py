"""Both backends must agree on what compiles, and say the same thing when not.

A disagreement here is a real defect: a program that builds on one backend and
silently misbehaves on the other. The one documented exception is an image call,
which the native backend cannot implement yet and refuses with a clear message.
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
from compiler.common import CompileError  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402

BOTH_ACCEPT = {
    "plain": 'fn(main)\n  say 1\nend\ncall fn(main)\n',
    "join text": 'fn(main)\n  say "a" & 1\nend\ncall fn(main)\n',
    "text literal": 'fn(main)\n  say "hello"\nend\ncall fn(main)\n',
    "text parameter": (
        "fn(shout, s)\n  output upper(var(s))\nend\n"
        'fn(main)\n  say call fn(shout, "ada")\nend\ncall fn(main)\n'
    ),
    "numbers": "fn(main)\n  say (1 + 2) * 3\n  say 7 % 4\nend\ncall fn(main)\n",
    "bool values": "fn(main)\n  say 1 > 0 and 2 > 1\nend\ncall fn(main)\n",
}

BOTH_REJECT = {
    "text plus number": ('fn(main)\n  say "a" + 1\nend\ncall fn(main)\n', "expected a number, got a string"),
    "number times text": ('fn(main)\n  say 2 * "a"\nend\ncall fn(main)\n', "expected a number, got a string"),
    "text if condition": ('fn(main)\n  if "yes"\n    say 1\n  end\nend\ncall fn(main)\n', "expected a number, got a string"),
    "unknown function": ("fn(main)\n  say call fn(nope, 1)\nend\ncall fn(main)\n", "unknown function 'nope'"),
    "wrong arity": (
        "fn(f, a, b)\n  output var(a)\nend\nfn(main)\n  say call fn(f, 1)\nend\ncall fn(main)\n",
        "expects 2 argument(s), got 1",
    ),
}

NATIVE_ONLY_REJECT = {
    "image_load": ('fn(main)\n  say image_load("nope.bmp")\nend\ncall fn(main)\n', "not available in the native x64 backend"),
}


class BackendAgreementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _program(self, source: str):
        path = self.base / "case.ANVL"
        path.write_text(source, encoding="utf-8")
        return path, parse(path, source)

    def _build(self, source: str, backend: str) -> str | None:
        """None when the backend accepts, otherwise the error message."""
        path, program = self._program(source)
        functions, top, variables, arrays = program
        try:
            if backend == "c":
                emit_c(path, functions, top, variables, arrays)
            else:
                NativeCodegen(path, functions, top, variables, arrays).generate()
        except CompileError as error:
            return str(error)
        return None

    def test_both_backends_accept_this_program(self) -> None:
        for label, source in BOTH_ACCEPT.items():
            with self.subTest(case=label):
                for backend in ("c", "native"):
                    self.assertIsNone(self._build(source, backend), f"{label} on {backend}")

    def test_both_backends_refuse_with_the_same_message(self) -> None:
        for label, (source, expected) in BOTH_REJECT.items():
            with self.subTest(case=label):
                c_error = self._build(source, "c")
                native_error = self._build(source, "native")
                self.assertIsNotNone(c_error, f"{label} compiled on c")
                self.assertIsNotNone(native_error, f"{label} compiled on native")
                self.assertIn(expected, c_error)
                self.assertIn(expected, native_error)

    def test_the_documented_native_gap_says_so_clearly(self) -> None:
        for label, (source, expected) in NATIVE_ONLY_REJECT.items():
            with self.subTest(case=label):
                self.assertIsNone(self._build(source, "c"))
                native_error = self._build(source, "native")
                self.assertIsNotNone(native_error)
                self.assertIn(expected, native_error)
                self.assertIn("--backend c", native_error)


    def test_both_backends_emit_the_same_bytes(self) -> None:
        """No newline translation: stdout must match byte for byte."""
        source = (
            "fn(main)\n  say 1\n  say \"two\"\n  say 3.5\nend\ncall fn(main)\n"
        )
        for label, program_source in (("basic", source),):
            with self.subTest(case=label):
                path, _ = self._program(program_source)
                outputs = {}
                for backend in ("c", "native"):
                    executable = self.base / f"bytes_{backend}.exe"
                    functions, top, variables, arrays = parse(path, program_source)
                    if backend == "native":
                        executable.write_bytes(
                            NativeCodegen(
                                path, functions, top, variables, arrays
                            ).generate()
                        )
                    else:
                        compiler = find_compiler(None)
                        if compiler is None:
                            raise unittest.SkipTest("MSVC is not available")
                        import tempfile as _tempfile

                        with _tempfile.TemporaryDirectory() as temp:
                            c_file = pathlib.Path(temp) / "program.c"
                            c_file.write_text(
                                emit_c(path, functions, top, variables, arrays),
                                encoding="utf-8",
                            )
                            build_c(compiler[1], c_file, executable, True)
                    result = subprocess.run(
                        [str(executable)], capture_output=True, text=True, timeout=60
                    )
                    outputs[backend] = result.stdout
                self.assertEqual(outputs["c"], outputs["native"])


if __name__ == "__main__":
    unittest.main()
