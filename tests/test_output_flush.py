"""`say` flushes each line so piped readers see output while the program runs."""

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

PROGRAM = 'fn(main)\n  say "first"\n  wait 1.5\n  say "second"\nend\ncall fn(main)\n'


class OutputFlushTests(unittest.TestCase):
    def test_a_say_line_reaches_a_pipe_before_the_program_exits(self) -> None:
        compiler = find_compiler(None)
        if compiler is None:
            raise unittest.SkipTest("MSVC is not available")
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            source = temp_path / "flush.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            functions, top, variables, arrays = parse(source, PROGRAM)
            c_file = temp_path / "flush.c"
            c_file.write_text(
                emit_c(source, functions, top, variables, arrays), encoding="utf-8"
            )
            executable = temp_path / "flush.exe"
            build_c(compiler[1], c_file, executable, release=True)
            process = subprocess.Popen(
                [str(executable)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                first = process.stdout.readline().strip()
                running = process.poll() is None
                rest = process.stdout.read()
            finally:
                process.kill()
                process.communicate()
        self.assertEqual(first, "first")
        # The program sleeps for 1.5 s after the first line; if the line were
        # block-buffered it would only arrive after exit.
        self.assertTrue(running, "the first line arrived only after the program exited")
        self.assertEqual(rest.strip(), "second")


if __name__ == "__main__":
    unittest.main()
