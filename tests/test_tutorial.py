"""Every tutorial example builds and runs, with the same output on both backends."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from tests.test_native_x64 import NativeRunMixin  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
TUTORIAL = ROOT / "examples" / "tutorial"

EXPECTED = {
    "01_hello": "Hello, world!\nThis is Anvil.\n",
    "02_numbers": "Score: 15\n11\n14\n1\n",
    "03_text": "Hello, ADA!\n3\nloud\n",
    "04_decisions": "teen\n",
    "05_loops": "hip\nhip\nhip\ncount 1\ncount 2\ncount 3\n3\n2\n1\n",
    "06_functions": "42\n7\n",
    "07_arrays": "Total: 60\n",
    "08_input": "What is your name? Hello, Ada!\n",
    "09_strings": "[Beginner]\nAnv\nvil\nvi\nA\n50\n",
    "10_program": "1 is odd\n2 is even\n3 is odd\n4 is even\n",
    "11_lists": "3\n20\ntotal=60\n",
}

INPUT = {"08_input": "Ada\n"}


class TutorialCRuntimeTests(unittest.TestCase):
    def _run(self, path: pathlib.Path) -> str:
        text = path.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / path.name
            source.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(source, text)
            c_file = temp_path / "sample.c"
            c_file.write_text(
                emit_c(source, functions, top, variables, arrays), encoding="utf-8"
            )
            compiler = find_compiler(None)
            if compiler is None:
                raise unittest.SkipTest("MSVC is not available")
            executable = temp_path / "sample.exe"
            build_c(compiler[1], c_file, executable, release=True)
            result = subprocess.run(
                [str(executable)],
                input=INPUT.get(path.stem, ""),
                capture_output=True,
                text=True,
                timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.replace("\r\n", "\n")

    def test_every_lesson(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(lesson=name):
                self.assertEqual(self._run(TUTORIAL / f"{name}.ANVL"), expected)


class TutorialNativeTests(NativeRunMixin, unittest.TestCase):
    def _run(self, path: pathlib.Path) -> str:
        text = path.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / path.name
            source.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(source, text)
            executable = temp_path / "sample.exe"
            executable.write_bytes(
                NativeCodegen(source, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)],
                input=INPUT.get(path.stem, ""),
                capture_output=True,
                text=True,
                timeout=20,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.replace("\r\n", "\n")

    def test_every_lesson(self) -> None:
        for name, expected in EXPECTED.items():
            with self.subTest(lesson=name):
                self.assertEqual(self._run(TUTORIAL / f"{name}.ANVL"), expected)


if __name__ == "__main__":
    unittest.main()
