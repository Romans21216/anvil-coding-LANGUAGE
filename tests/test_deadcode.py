"""Unreachable Anvil functions must not reach generated C or native output."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.codegen import emit_c  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

PROGRAM = """\
fn(used)
  output 7
end

fn(unused_helper)
  say "never called"
end

fn(chain_a)
  output call fn(chain_b) + 1
end

fn(chain_b)
  output 5
end

fn(recurse, n)
  if var(n) <= 0
    output 0
  end
  output call fn(recurse, var(n) - 1)
end

fn(main)
  say call fn(used)
  say call fn(chain_a)
  say call fn(recurse, 3)
end
call fn(main)
"""

ENGINE_PROGRAM = """\
fn(hidden_helper)
  output 1
end

fn(update)
  set var(tick) = var(tick) + 1
end

fn(draw)
  display rect(0, 0, 4, 4)
end
"""


def compile_c(source: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "sample.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
        return emit_c(path, functions, top, variables, arrays)


class CReachabilityTests(unittest.TestCase):
    def test_unused_function_is_absent_from_generated_c(self) -> None:
        generated = compile_c(PROGRAM)
        self.assertNotIn("unused_helper", generated)
        self.assertIn("anvil_used", generated)

    def test_transitive_and_recursive_calls_are_kept(self) -> None:
        generated = compile_c(PROGRAM)
        self.assertIn("anvil_chain_a", generated)
        self.assertIn("anvil_chain_b", generated)
        self.assertIn("anvil_recurse", generated)

    def test_engine_callbacks_are_kept_and_helpers_dropped(self) -> None:
        generated = compile_c(ENGINE_PROGRAM)
        self.assertIn("anvil_draw", generated)
        self.assertIn("anvil_update", generated)
        self.assertNotIn("hidden_helper", generated)


class NativeReachabilityTests(unittest.TestCase):
    def test_unused_function_is_absent_from_native_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(PROGRAM, encoding="utf-8")
            functions, top, variables, arrays = parse(path, PROGRAM)
            image = NativeCodegen(path, functions, top, variables, arrays).generate()
        # Function names are not embedded, but the unused body's literal is.
        self.assertNotIn(b"never called", image)

    def test_reachable_literals_stay_and_unreachable_ones_go(self) -> None:
        source = (
            "fn(used)" + chr(10) + '  say "used-marker"' + chr(10) + "  output 1" + chr(10) + "end" + chr(10) + chr(10)
            + "fn(unused_helper)" + chr(10) + '  say "never called"' + chr(10) + "end" + chr(10) + chr(10)
            + "fn(main)" + chr(10) + "  say call fn(used)" + chr(10) + "end" + chr(10) + "call fn(main)" + chr(10)
        )
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            image = NativeCodegen(path, functions, top, variables, arrays).generate()
        self.assertIn(b"used-marker", image)
        self.assertNotIn(b"never called", image)

    def test_native_and_c_agree_on_reachable_output(self) -> None:
        import subprocess

        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            path = temp_path / "sample.ANVL"
            path.write_text(PROGRAM, encoding="utf-8")
            functions, top, variables, arrays = parse(path, PROGRAM)
            executable = temp_path / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=15
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.replace("\r\n", "\n"), "7\n6\n0\n")


if __name__ == "__main__":
    unittest.main()
