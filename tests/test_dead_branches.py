"""Statically dead branches are not emitted, and behavior is unchanged."""

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
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

DEAD = 'fn(main)\n  if 0\n    say "dead marker"\n  end\n  say "alive"\nend\ncall fn(main)\n'
LIVE = 'fn(main)\n  if 1\n    say "dead marker"\n  end\n  say "alive"\nend\ncall fn(main)\n'
ELSE = (
    "fn(main)\n  if 0\n    say \"never\"\n  else\n    say \"otherwise\"\n  end\nend\n"
    "call fn(main)\n"
)


def native_image(source: str) -> bytes:
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "p.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        return NativeCodegen(path, functions, top, variables, arrays).generate()


def run_c(source: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path = temp_path / "p.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        c_file = temp_path / "p.c"
        c_file.write_text(
            emit_c(path, functions, top, variables, arrays), encoding="utf-8"
        )
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        executable = temp_path / "p.exe"
        build_c(compiler[1], c_file, executable, release=True)
        return subprocess.run(
            [str(executable)], capture_output=True, text=True, timeout=20
        )


class DeadBranchTests(unittest.TestCase):
    def test_if_zero_runs_only_the_live_path(self) -> None:
        result = run_c(DEAD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "alive\n")

    def test_if_one_keeps_the_body(self) -> None:
        result = run_c(LIVE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "dead marker\nalive\n")

    def test_else_body_survives_a_dead_condition(self) -> None:
        result = run_c(ELSE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "otherwise\n")

    def test_dead_branch_is_absent_from_generated_c(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "p.ANVL"
            path.write_text(DEAD, encoding="utf-8")
            functions, top, variables, arrays = parse(path, DEAD)
            generated = emit_c(path, functions, top, variables, arrays)
        self.assertNotIn("dead marker", generated)
        self.assertIn("alive", generated)

    def test_dead_branch_shrinks_the_native_image(self) -> None:
        # One statement per branch is smaller than a PE section's padding, so
        # use a body big enough for the difference to show.
        body = "".join('    say "line"\n' for _ in range(20))
        dead = f"fn(main)\n  if 0\n{body}  end\n  say 1\nend\ncall fn(main)\n"
        live = f"fn(main)\n  if 1\n{body}  end\n  say 1\nend\ncall fn(main)\n"
        self.assertLess(len(native_image(dead)), len(native_image(live)))

    def test_an_unknown_array_in_a_dead_branch_is_still_reported(self) -> None:
        # Parse-time validation walks every node, dead branch or not.
        source = (
            "fn(main)\n  if 0\n    say array(missing, 0)\n  end\n  say 1\nend\n"
            "call fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "p.ANVL"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, source)
        self.assertIn("unknown array", str(caught.exception))

    def test_a_codegen_type_error_in_a_dead_branch_is_not_reported(self) -> None:
        # Documented boundary: dead branches are not emitted, so lowering-time
        # typing is skipped for them (parse-time validation still runs).
        source = (
            'fn(main)\n  if 0\n    say 1 + "a"\n  end\n  say 1\nend\n'
            "call fn(main)\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "p.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            generated = emit_c(path, functions, top, variables, arrays)
        self.assertIn("anvil_format_number(1.0)", generated)


if __name__ == "__main__":
    unittest.main()
