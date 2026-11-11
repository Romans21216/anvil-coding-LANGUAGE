"""Tests for located, source-annotated compiler diagnostics."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.common import CompileError  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.diagnostics import render  # noqa: E402
from compiler.parser import parse  # noqa: E402


class DiagnosticRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.source = self.root / "main.ANVL"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, text: str) -> pathlib.Path:
        self.source.write_text(text, encoding="utf-8")
        return self.source

    def test_renders_source_line_and_caret(self) -> None:
        path = self._write("let a = 1\nlet b = 2\n")
        message = f"{path}:2: unexpected token"
        out = render(message)
        lines = out.splitlines()
        self.assertEqual(lines[0], message)
        self.assertIn("let b = 2", lines[1])
        self.assertTrue(lines[2].rstrip().endswith("^"))

    def test_points_at_quoted_token(self) -> None:
        path = self._write("    health = hp - 1\n")
        out = render(f"{path}:1: undefined variable 'hp'")
        code_line, caret = out.splitlines()[1], out.splitlines()[2]
        position = code_line.index("hp")
        self.assertEqual(caret.index("^"), position)

    def test_prefers_whole_word_token(self) -> None:
        path = self._write("array = 1\nx = a + 1\n")
        out = render(f"{path}:2: undefined variable 'a'")
        code_line, caret = out.splitlines()[1], out.splitlines()[2]
        self.assertEqual(caret.index("^"), code_line.index("a +"))

    def test_explicit_column_wins(self) -> None:
        path = self._write("value = 12345\n")
        out = render(f"{path}:1:7: bad literal")
        caret = out.splitlines()[2]
        self.assertEqual(caret.index("^"), 6 + len("    1 | "))

    def test_unknown_file_is_unchanged(self) -> None:
        message = f"{self.root / 'missing.ANVL'}:3: unexpected end of file"
        self.assertEqual(render(message), message)

    def test_line_out_of_range_is_unchanged(self) -> None:
        path = self._write("one line\n")
        message = f"{path}:9: unexpected end of file"
        self.assertEqual(render(message), message)

    def test_message_without_location_is_unchanged(self) -> None:
        message = "--emit-c applies only to --backend c"
        self.assertEqual(render(message), message)

    def test_parse_error_is_annotated(self) -> None:
        path = self._write("let a = \n")
        with self.assertRaises(CompileError) as caught:
            parse(path, path.read_text(encoding="utf-8"))
        rendered = render(str(caught.exception))
        self.assertIn("let a =", rendered)
        self.assertIn("^", rendered)


class CheckModeTests(unittest.TestCase):
    """--check validates a program without building anything."""

    def setUp(self) -> None:
        self.example = (
            pathlib.Path(__file__).resolve().parents[1] / "examples" / "first_world.ANVL"
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, argv: list[str]) -> int:
        import contextlib
        import io
        from compiler.cli import main

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            old = sys.argv
            sys.argv = argv
            try:
                return main()
            finally:
                sys.argv = old

    def test_valid_program_returns_zero(self) -> None:
        self.assertEqual(self._run(["anvil", str(self.example), "--check"]), 0)

    def test_invalid_program_returns_one_and_writes_nothing(self) -> None:
        broken = self.root / "broken.ANVL"
        broken.write_text("let a = 1\nthis is not anvil\n", encoding="utf-8")
        self.assertEqual(self._run(["anvil", str(broken), "--check"]), 1)
        self.assertEqual(list(self.root.glob("*.exe")), [])
        self.assertEqual(list(self.root.glob("*.c")), [])

    def test_check_with_native_backend_writes_nothing(self) -> None:
        console = self.root / "console.ANVL"
        console.write_text(
            'fn(main)\n  say "hi"\nend\ncall fn(main)\n', encoding="utf-8"
        )
        self.assertEqual(
            self._run(["anvil", str(console), "--check", "--backend", "native"]), 0
        )
        self.assertEqual(list(self.root.glob("*.exe")), [])

    def test_check_with_native_backend_reports_type_errors(self) -> None:
        broken = self.root / "native-type-error.ANVL"
        broken.write_text(
            'fn(main)\n  say 1 + "a"\nend\ncall fn(main)\n', encoding="utf-8"
        )
        self.assertEqual(
            self._run(["anvil", str(broken), "--check", "--backend", "native"]), 1
        )
        self.assertEqual(list(self.root.glob("*.exe")), [])

    def test_check_reports_type_errors_from_lowering(self) -> None:
        # Type errors only surface in code generation; --check must run it.
        broken = self.root / "type-error.ANVL"
        broken.write_text(
            'fn(main)\n  say 1 + "a"\nend\ncall fn(main)\n', encoding="utf-8"
        )
        self.assertEqual(self._run(["anvil", str(broken), "--check"]), 1)
        self.assertEqual(list(self.root.glob("*.c")), [])

    def test_missing_source_file_reports_a_clear_error(self) -> None:
        missing = self.root / "does-not-exist.ANVL"
        self.assertEqual(self._run(["anvil", str(missing), "--check"]), 1)

    def test_invalid_utf8_source_reports_a_clear_error(self) -> None:
        bad = self.root / "latin1.ANVL"
        bad.write_bytes(b'fn(main)\n  say "caf\xe9"\nend\ncall fn(main)\n')
        self.assertEqual(self._run(["anvil", str(bad), "--check"]), 1)

    def test_common_builtin_mistakes_get_a_suggestion(self) -> None:
        path = self.root / "suggest.ANVL"
        source = "fn(main)\n  say random(1, 10)\nend\ncall fn(main)\n"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        with self.assertRaises(CompileError) as caught:
            emit_c(path, functions, top, variables, arrays)
        self.assertIn("did you mean rnd(low, high)?", str(caught.exception))

    def test_unknown_name_without_a_suggestion_keeps_the_variable_hint(self) -> None:
        path = self.root / "mystery.ANVL"
        source = "fn(main)\n  say mystery(1)\nend\ncall fn(main)\n"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        with self.assertRaises(CompileError) as caught:
            emit_c(path, functions, top, variables, arrays)
        self.assertIn("variables are written var(mystery)", str(caught.exception))

    def test_local_variable_used_as_global_names_the_real_fix(self) -> None:
        path = self.root / "local-mixup.ANVL"
        source = "fn(main)\n  for local(i) = 0 to 1\n    say var(i)\n  end\nend\ncall fn(main)\n"
        path.write_text(source, encoding="utf-8")
        with self.assertRaises(CompileError) as caught:
            parse(path, source)
        self.assertIn("write local(i) instead of var(i)", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
