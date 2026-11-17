"""`break` and `continue` in for, while and repeat loops on both backends."""

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

PROGRAM = """\
fn(main)
  set var(sum) = 0
  for local(i) = 1 to 10
    if local(i) = 4
      continue
    end
    if local(i) = 7
      break
    end
    set var(sum) = var(sum) + local(i)
  end
  say var(sum)
  set var(n) = 0
  while var(n) < 10
    set var(n) = var(n) + 1
    if var(n) = 3
      continue
    end
    if var(n) = 5
      break
    end
  end
  say var(n)
  set var(count) = 0
  repeat 5
    set var(count) = var(count) + 1
    if var(count) = 2
      break
    end
  end
  say var(count)
  set var(outer) = 0
  for local(a) = 1 to 3
    for local(b) = 1 to 3
      if local(b) = 2
        break
      end
      set var(outer) = var(outer) + 1
    end
  end
  say var(outer)
  set var(inner_continue) = 0
  for local(c) = 1 to 3
    for local(d) = 1 to 3
      if local(d) = 2
        continue
      end
      set var(inner_continue) = var(inner_continue) + 1
    end
  end
  say var(inner_continue)
end
call fn(main)
"""

EXPECTED = "17\n5\n2\n3\n6\n"


def run_c(source: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        path = temp_path / "sample.ANVL"
        path.write_text(source, encoding="utf-8")
        functions, top, variables, arrays = parse(path, source)
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


class BreakContinueCTests(unittest.TestCase):
    def test_break_and_continue_in_every_loop_shape(self) -> None:
        self.assertEqual(run_c(PROGRAM), EXPECTED)

    def test_break_outside_a_loop_is_rejected(self) -> None:
        source = "fn(main)\n  break\nend\ncall fn(main)\n"
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bad.ANVL"
            path.write_text(source, encoding="utf-8")
            with self.assertRaises(CompileError) as caught:
                parse(path, source)
        self.assertIn("break must be inside a loop", str(caught.exception))


class BreakContinueNativeTests(unittest.TestCase):
    def _run(self, source: str) -> str:
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "sample.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "sample.exe"
            executable.write_bytes(
                NativeCodegen(path, functions, top, variables, arrays).generate()
            )
            result = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=20
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.replace("\r\n", "\n")

    def test_break_and_continue_in_every_loop_shape(self) -> None:
        self.assertEqual(self._run(PROGRAM), EXPECTED)


if __name__ == "__main__":
    unittest.main()
