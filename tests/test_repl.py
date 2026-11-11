"""The interactive shell runs real statements and remembers assignments."""

from __future__ import annotations

import io
import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.repl import (  # noqa: E402
    PROMPT,
    ReplError,
    Shell,
    hello_main,
    repl_main,
    statement_depth,
)


class StatementDepthTests(unittest.TestCase):
    def test_plain_lines_are_closed(self) -> None:
        self.assertEqual(statement_depth(["say 1"]), 0)

    def test_blocks_stay_open_until_end(self) -> None:
        self.assertEqual(statement_depth(["repeat 2"]), 1)
        self.assertEqual(statement_depth(["repeat 2", 'say "ho"']), 1)
        self.assertEqual(statement_depth(["repeat 2", 'say "ho"', "end"]), 0)

    def test_if_else_end_counts_once(self) -> None:
        self.assertEqual(
            statement_depth(["if 1 > 0", "say 1", "else", "say 2", "end"]), 0
        )


class ShellTests(unittest.TestCase):
    def test_assignment_echoes_the_value(self) -> None:
        shell = Shell()
        self.assertEqual(shell.eval("x = 2"), "x = 2\n")
        self.assertEqual(shell.eval("y = x + 5"), "y = 7\n")

    def test_bare_names_work_after_they_are_remembered(self) -> None:
        shell = Shell()
        shell.eval("name = \"Ada\"")
        self.assertEqual(shell.eval("say name & \"!\"") .strip(), "Ada!")
        self.assertEqual(shell.eval("say len(name)").strip(), "3")

    def test_statements_do_not_pollute_the_history(self) -> None:
        shell = Shell()
        shell.eval("x = 1")
        shell.eval('say "noise"')
        self.assertEqual(shell.history, ["set var(x) = 1"])

    def test_blocks_run_but_are_not_remembered(self) -> None:
        shell = Shell()
        self.assertEqual(shell.eval('repeat 2\nsay "ho"\nend').strip(), "ho\nho")

    def test_unknown_names_report_a_caret_diagnostic(self) -> None:
        shell = Shell()
        with self.assertRaises(ReplError) as caught:
            shell.eval("say missing + 1")
        self.assertIn("missing", str(caught.exception))

    def test_text_functions_work_in_the_shell(self) -> None:
        shell = Shell()
        shell.eval('word = "beginner"')
        self.assertEqual(shell.eval("say left(word, 3)").strip(), "beg")
        self.assertEqual(shell.eval("say right(word, 4)").strip(), "nner")
        self.assertEqual(shell.eval("say mid(word, 3, 2)").strip(), "in")


class ReplLoopTests(unittest.TestCase):
    def test_scripted_session(self) -> None:
        stdin = io.StringIO("x = 2\nsay x * 3\n:quit\n")
        stdout = io.StringIO()
        self.assertEqual(repl_main(stdin=stdin, stdout=stdout), 0)
        out = stdout.getvalue()
        self.assertIn(PROMPT, out)
        self.assertIn("x = 2", out)
        self.assertIn("6", out)

    def test_end_of_input_leaves_cleanly(self) -> None:
        stdout = io.StringIO()
        self.assertEqual(repl_main(stdin=io.StringIO(""), stdout=stdout), 0)
        self.assertIn("Anvil shell", stdout.getvalue())

    def test_ask_remembers_the_answer(self) -> None:
        stdin = io.StringIO(
            'ask var(name)\nAda\nsay "hello, " & var(name)\n'
            'ask "age? ", var(age)\n42\nsay var(age) + 1\n:quit\n'
        )
        stdout = io.StringIO()
        repl_main(stdin=stdin, stdout=stdout)
        out = stdout.getvalue()
        self.assertIn("hello, Ada", out)
        self.assertIn("age? ", out)
        self.assertIn("43", out)

    def test_ask_without_a_reader_is_a_clear_error(self) -> None:
        shell = Shell()
        with self.assertRaises(ReplError) as caught:
            shell.eval("ask var(name)")
        self.assertIn("interactive terminal", str(caught.exception))

    def test_clear_forgets_declarations(self) -> None:
        stdin = io.StringIO("list nums\nadd nums 3\n:clear\ncount(nums)\n:quit\n")
        stdout = io.StringIO()
        repl_main(stdin=stdin, stdout=stdout)
        out = stdout.getvalue()
        self.assertIn("cleared", out)
        self.assertIn("unknown list", out)

    def test_vars_lists_declarations(self) -> None:
        stdin = io.StringIO("list nums\nadd nums 3\n:vars\n:quit\n")
        stdout = io.StringIO()
        repl_main(stdin=stdin, stdout=stdout)
        out = stdout.getvalue()
        self.assertIn("list nums", out)
        self.assertIn("add nums 3", out)

    def test_help_and_clear(self) -> None:
        stdin = io.StringIO(":help\nx = 1\n:clear\n:vars\n:quit\n")
        stdout = io.StringIO()
        repl_main(stdin=stdin, stdout=stdout)
        out = stdout.getvalue()
        self.assertIn("remember a value", out)
        self.assertIn("cleared", out)
        self.assertIn("(nothing remembered yet)", out)


class HelloGreetingTests(unittest.TestCase):
    def test_hello_runs_a_real_program(self) -> None:
        out = io.StringIO()
        self.assertEqual(hello_main(stdout=out), 0)
        text = out.getvalue()
        self.assertIn("Hello from Anvil!", text)
        self.assertIn("This program was compiled and run just now.", text)
        self.assertIn("--repl", text)

    def test_cli_hello_exits_cleanly(self) -> None:
        root = pathlib.Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "compiler" / "anvil.py"), "--hello"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Hello from Anvil!", result.stdout)

    def test_lists_and_bare_expressions(self) -> None:
        shell = Shell()
        self.assertEqual(shell.eval("list nums"), "")
        self.assertEqual(shell.eval("add nums 5"), "")
        self.assertEqual(shell.eval("add nums 7"), "")
        self.assertEqual(shell.eval("count(nums)").strip(), "2")
        self.assertEqual(shell.eval("array(nums, 1)").strip(), "7")

    def test_bare_expression_prints_its_value(self) -> None:
        shell = Shell()
        self.assertEqual(shell.eval("1 + 2").strip(), "3")
        shell.eval("x = 3")
        self.assertEqual(shell.eval("x * 2").strip(), "6")

    def test_statements_produce_no_stray_zero(self) -> None:
        shell = Shell()
        self.assertEqual(shell.eval("list nums"), "")
        self.assertEqual(shell.eval("add nums 1"), "")

    def test_c_backend_hello_has_no_build_chatter(self) -> None:
        from compiler.build import find_compiler

        if find_compiler(None) is None:
            self.skipTest("MSVC is not available")
        out = io.StringIO()
        self.assertEqual(hello_main(backend="c", stdout=out), 0)
        text = out.getvalue()
        self.assertTrue(text.startswith("Hello from Anvil!"), text)
        self.assertNotIn("Generating Code", text)
        self.assertNotIn("anvil_runtime.c", text)

    def test_banner_shows_a_first_example(self) -> None:
        stdout = io.StringIO()
        repl_main(stdin=io.StringIO(":quit\n"), stdout=stdout)
        self.assertIn('say "Hello, " & "world"', stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
