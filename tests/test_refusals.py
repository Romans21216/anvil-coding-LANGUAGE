"""The compiler must refuse these programs, with these messages.

This is the regression net for "you physically can't mess up": every case here
was a real hole at some point, or a rule worth never losing.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ANVIL = ROOT / "compiler" / "anvil.py"

REFUSED = {
    "wrong arity": (
        "fn(f, a, b)\n  output var(a)\nend\nfn(main)\n  say call fn(f, 1)\nend\ncall fn(main)\n",
        "function 'f' expects 2 argument(s), got 1",
    ),
    "number into a text builtin": (
        'fn(main)\n  say upper(5)\nend\ncall fn(main)\n',
        "expected a string, got a number",
    ),
    "text into a number builtin": (
        'fn(main)\n  say floor("x")\nend\ncall fn(main)\n',
        "expected a number, got a string",
    ),
    "text if condition": (
        'fn(main)\n  if "yes"\n    say 1\n  end\nend\ncall fn(main)\n',
        "expected number, got string",
    ),
    "duplicate parameter": (
        "fn(f, a, a)\n  output var(a)\nend\nfn(main)\n  say 1\nend\ncall fn(main)\n",
        "duplicate parameter in function 'f'",
    ),
    "parameter shadowing": (
        "fn(f, a)\n  set local(a) = 1\n  output local(a)\nend\n"
        "fn(main)\n  say call fn(f, 2)\nend\ncall fn(main)\n",
        "conflicts with a function parameter",
    ),
    "unknown function": (
        "fn(main)\n  say call fn(nope, 1)\nend\ncall fn(main)\n",
        "unknown function 'nope'",
    ),
    "undefined variable": (
        "fn(main)\n  say var(ghost)\nend\ncall fn(main)\n",
        "unknown variable 'ghost'",
    ),
    "missing end": (
        "fn(main)\n  say 1\ncall fn(main)\n",
        "unclosed function; expected 'end'",
    ),
    "duplicate function": (
        "fn(main)\n  say 1\nend\nfn(main)\n  say 2\nend\ncall fn(main)\n",
        "duplicate function 'main'",
    ),
    "call a variable": (
        "fn(main)\n  set var(g) = 1\n  say call fn(var(g), 2)\nend\ncall fn(main)\n",
        "unknown function 'var(g)'",
    ),
}

WARNED = {
    "unused import": (
        "import math\n\nfn(main)\n  say 1\nend\ncall fn(main)\n",
        "warning: import 'math' is never used",
    ),
    "unreachable code": (
        'fn(f, a)\n  output var(a)\n  say "dead"\nend\n'
        "fn(main)\n  say call fn(f, 1)\nend\ncall fn(main)\n",
        "warning: unreachable statement after output",
    ),
    "unused local": (
        "fn(main)\n  set local(spare) = 1\n  say 2\nend\ncall fn(main)\n",
        "warning: unused local 'spare'",
    ),
    "division by zero": (
        "fn(main)\n  say 1 / 0\nend\ncall fn(main)\n",
        "warning: division by zero",
    ),
}


class RefusalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = __import__("tempfile").TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, source: str, *flags: str) -> subprocess.CompletedProcess:
        path = self.base / "case.ANVL"
        path.write_text(source, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(ANVIL), str(path), "--check", *flags],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_broken_programs_are_refused_with_a_specific_message(self) -> None:
        for label, (source, expected) in REFUSED.items():
            with self.subTest(case=label):
                result = self._run(source)
                self.assertEqual(result.returncode, 1, f"{label} was accepted: {result.stdout}")
                self.assertIn(expected, result.stderr)
                self.assertIn("^", result.stderr, f"{label} printed no caret")

    def test_questionable_programs_warn_but_still_build(self) -> None:
        for label, (source, expected) in WARNED.items():
            with self.subTest(case=label):
                result = self._run(source)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(expected, result.stderr)

    def test_every_warning_becomes_an_error_under_deny_warnings(self) -> None:
        for label, (source, expected) in WARNED.items():
            with self.subTest(case=label):
                result = self._run(source, "--deny-warnings")
                self.assertEqual(result.returncode, 1, label)
                self.assertIn("warning(s) treated as errors", result.stderr)


if __name__ == "__main__":
    unittest.main()
