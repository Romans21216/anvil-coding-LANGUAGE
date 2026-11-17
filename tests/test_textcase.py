"""`upper(text)` / `lower(text)` convert case and yield text, both backends."""

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
from tests.test_native_x64 import NativeRunMixin  # noqa: E402


def run_c(text: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        source = temp_path / "sample.ANVL"
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
            [str(executable)], capture_output=True, text=True, timeout=15
        )
    if result.returncode != 0:
        raise AssertionError(f"exit {result.returncode}: {result.stdout}{result.stderr}")
    return result.stdout


class CaseParseTests(unittest.TestCase):
    def test_upper_assigns_a_text_variable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = 'fn(main)\n  set var(name) = "Ada"\n  set var(tag) = upper(var(name))\nend\n'
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
        for node in functions["main"].body:
            if node.kind == "set" and node.name == "tag":
                self.assertTrue(node.string)
                break
        else:
            self.fail("tag assignment not found")

    def test_case_builtins_reject_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            text = "fn(main)\n  set var(n) = upper(42)\nend\n"
            path.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(path, text)
            with self.assertRaises(CompileError) as caught:
                emit_c(path, functions, top, variables, arrays)
        self.assertIn("expected a string", str(caught.exception))


class CaseCRuntimeTests(unittest.TestCase):
    def _expect(self, text: str, want: str) -> None:
        self.assertEqual(run_c(text), want)

    def test_upper_and_lower(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "Ada Lovelace"\n'
            "  say upper(var(name))\n  say lower(var(name))\nend\ncall fn(main)\n",
            "ADA LOVELACE\nada lovelace\n",
        )

    def test_mixed_input_and_punctuation(self) -> None:
        self._expect(
            'fn(main)\n  say upper("MiXeD 123!")\nend\ncall fn(main)\n',
            "MIXED 123!\n",
        )

    def test_store_back_into_a_variable(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "Ada"\n  set var(tag) = lower(var(name))\n'
            '  say "tag: " & var(tag)\nend\ncall fn(main)\n',
            "tag: ada\n",
        )

    def test_compose_with_len(self) -> None:
        self._expect(
            'fn(main)\n  set var(name) = "Ada"\n'
            '  say "len: ", len(upper(var(name)))\nend\ncall fn(main)\n',
            "len: 3\n",
        )

    def test_join_two_converted_values(self) -> None:
        self._expect(
            'fn(main)\n  say upper("a") & "-" & upper("b")\nend\ncall fn(main)\n',
            "A-B\n",
        )


class CaseNativeTests(NativeRunMixin, unittest.TestCase):
    def _run(self, text: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "sample.ANVL"
            source.write_text(text, encoding="utf-8")
            functions, top, variables, arrays = parse(source, text)
            executable = temp_path / "sample.exe"
            executable.write_bytes(
                NativeCodegen(source, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_native_upper_and_lower(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "Ada Lovelace"\n'
                "  say upper(var(name))\n  say lower(var(name))\nend\ncall fn(main)\n"
            ),
            "ADA LOVELACE\nada lovelace\n",
        )

    def test_native_mixed_input_and_punctuation(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say upper("MiXeD 123!")\nend\ncall fn(main)\n'),
            "MIXED 123!\n",
        )

    def test_native_store_back_into_a_variable(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "Ada"\n'
                "  set var(tag) = lower(var(name))\n"
                '  say "tag: " & var(tag)\nend\ncall fn(main)\n'
            ),
            "tag: ada\n",
        )

    def test_native_compose_with_len(self) -> None:
        self.assertEqual(
            self._run(
                'fn(main)\n  set var(name) = "Ada"\n'
                '  say "len: ", len(upper(var(name)))\nend\ncall fn(main)\n'
            ),
            "len: 3\n",
        )

    def test_native_join_two_converted_values(self) -> None:
        self.assertEqual(
            self._run('fn(main)\n  say upper("a") & "-" & upper("b")\nend\ncall fn(main)\n'),
            "A-B\n",
        )


if __name__ == "__main__":
    unittest.main()
