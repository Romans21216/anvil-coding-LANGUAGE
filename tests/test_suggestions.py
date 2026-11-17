"""Unknown names name the closest declared name when the guess is safe."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.suggestions import closest_name  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

TYPO_FUNCTION = (
    "fn(hello)\n"
    '  say "hi"\n'
    "end\n"
    "fn(main)\n"
    "  call fn(helo)\n"
    "end\n"
    "call fn(main)\n"
)

TYPO_VARIABLE = (
    "fn(main)\n"
    "  set var(speed) = 1\n"
    "  say var(speeed)\n"
    "end\n"
    "call fn(main)\n"
)

SHORT_VARIABLE = (
    "fn(main)\n"
    "  set var(x) = 1\n"
    "  say var(y)\n"
    "end\n"
    "call fn(main)\n"
)


def diagnostic(source: str, *arguments: str) -> str:
    with tempfile.TemporaryDirectory() as temp:
        path = pathlib.Path(temp) / "probe.ANVL"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(path), "--check", *arguments],
            capture_output=True,
            text=True,
            timeout=120,
        )
    return result.stdout + result.stderr


class ClosestNameTests(unittest.TestCase):
    def test_a_one_edit_typo_is_suggested(self) -> None:
        self.assertEqual(closest_name("helo", {"hello", "main"}), "hello")

    def test_short_names_are_never_corrected(self) -> None:
        self.assertIsNone(closest_name("y", {"x"}))

    def test_distant_names_are_not_suggested(self) -> None:
        self.assertIsNone(closest_name("abcdefgh", {"zzzzzzzz"}))

    def test_an_ambiguous_tie_is_not_suggested(self) -> None:
        self.assertIsNone(closest_name("abc", {"abcd", "abcf"}))

    def test_case_only_differences_are_suggested(self) -> None:
        self.assertEqual(closest_name("Hello", {"hello"}), "hello")


class DiagnosticSuggestionTests(unittest.TestCase):
    def test_a_misspelled_function_names_the_real_one(self) -> None:
        output = diagnostic(TYPO_FUNCTION)
        self.assertIn("unknown function 'helo'", output)
        self.assertIn("did you mean 'hello'?", output)

    def test_the_native_backend_suggests_too(self) -> None:
        output = diagnostic(TYPO_FUNCTION, "--backend", "native")
        self.assertIn("did you mean 'hello'?", output)

    def test_a_misspelled_variable_names_the_real_one(self) -> None:
        output = diagnostic(TYPO_VARIABLE)
        self.assertIn("unknown variable 'speeed'", output)
        self.assertIn("did you mean 'speed'?", output)

    def test_a_one_letter_name_gets_no_guess(self) -> None:
        output = diagnostic(SHORT_VARIABLE)
        self.assertIn("unknown variable 'y'", output)
        self.assertNotIn("did you mean", output)


if __name__ == "__main__":
    unittest.main()
