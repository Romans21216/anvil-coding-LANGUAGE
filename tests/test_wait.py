"""`wait <seconds>`: pause a console program without busy-work tricks."""

from __future__ import annotations

import pathlib
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.common import CompileError  # noqa: E402
from compiler.parser import parse  # noqa: E402
from tests.test_say import compile_and_run  # noqa: E402
from tests.test_native_x64 import NativeRunMixin  # noqa: E402

PAUSE = 0.15
PROGRAM = f"""fn(main)
  say "before"
  wait {PAUSE}
  say "after"
end
call fn(main)
"""


def parse_source(text: str):
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "sample.ANVL"
        path.write_text(text, encoding="utf-8")
        return parse(path, text)


class WaitParseTests(unittest.TestCase):
    def test_wait_parses_with_its_expression(self) -> None:
        functions, _, _, _ = parse_source("fn(main)\n  wait 1 + 0.5\nend\n")
        self.assertEqual(functions["main"].body[0].kind, "wait")
        self.assertEqual(functions["main"].body[0].value, "1 + 0.5")

    def test_wait_needs_an_expression(self) -> None:
        with self.assertRaises(CompileError):
            parse_source("fn(main)\n  wait\nend\n")


def timed_run(runner) -> tuple[str, float]:
    started = time.perf_counter()
    output = runner()
    return output, time.perf_counter() - started


class WaitCRuntimeTests(unittest.TestCase):
    def test_wait_pauses_between_output(self) -> None:
        output, elapsed = timed_run(lambda: compile_and_run(PROGRAM))
        self.assertEqual(output, "before\nafter\n")
        self.assertGreaterEqual(elapsed, PAUSE * 0.7)

    def test_negative_wait_does_not_hang(self) -> None:
        output, elapsed = timed_run(
            lambda: compile_and_run('fn(main)\n  say "ok"\n  wait -5\nend\ncall fn(main)\n')
        )
        self.assertEqual(output, "ok\n")
        self.assertLess(elapsed, 2.0)


class WaitNativeRuntimeTests(NativeRunMixin, unittest.TestCase):
    def test_wait_pauses_between_output(self) -> None:
        output, elapsed = timed_run(lambda: self._run_source(PROGRAM))
        self.assertEqual(output, "before\nafter\n")
        self.assertGreaterEqual(elapsed, PAUSE * 0.7)

    def test_negative_wait_does_not_hang(self) -> None:
        output, elapsed = timed_run(
            lambda: self._run_source('fn(main)\n  say "ok"\n  wait -5\nend\ncall fn(main)\n')
        )
        self.assertEqual(output, "ok\n")
        self.assertLess(elapsed, 2.0)


if __name__ == "__main__":
    unittest.main()
