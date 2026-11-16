"""Every documented error code matches a real diagnostic and explains itself."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.error_codes import (  # noqa: E402
    CATEGORIES,
    by_code,
    classify,
    code_list,
    explain,
    message_body,
)

QUOTE = chr(34)

SAMPLES = {
    "ANV101": "prog.ANVL:2: unknown name 'hp' (variables are written var(hp))",
    "ANV102": "prog.ANVL:3: unknown variable 'hp'; assign it with set var(hp) first",
    "ANV103": "prog.ANVL:4: unknown local variable 'i'; declare it with set local(i) first",
    "ANV104": "prog.ANVL:5: unknown function 'helo'",
    "ANV105": "prog.ANVL:6: function 'add' expects 2 argument(s), got 1",
    "ANV106": "prog.ANVL:1: unclosed function; expected 'end'",
    "ANV107": "prog.ANVL:7: unterminated string: no closing " + QUOTE,
    "ANV108": "prog.ANVL:8: numeric literal must be finite",
    "ANV109": "prog.ANVL:9: only configuration, initial values, and calls are allowed at top level",
    "ANV110": "prog.ANVL: none: define at least one fn(name) function",
}


class ClassifyTests(unittest.TestCase):
    def test_every_code_matches_its_message(self) -> None:
        self.assertEqual(set(SAMPLES), {category.code for category in CATEGORIES})
        for code, message in SAMPLES.items():
            with self.subTest(code=code):
                category = classify(message)
                self.assertIsNotNone(category, message)
                self.assertEqual(category.code, code)

    def test_an_unrelated_message_has_no_code(self) -> None:
        self.assertIsNone(classify("prog.ANVL:2: something else entirely"))

    def test_a_column_survives_the_strip(self) -> None:
        message = "prog.ANVL:12:7: unknown function 'helo'"
        self.assertEqual(message_body(message), "unknown function 'helo'")
        self.assertEqual(classify(message).code, "ANV104")

    def test_codes_are_unique(self) -> None:
        codes = [category.code for category in CATEGORIES]
        self.assertEqual(len(codes), len(set(codes)))


class ExplainTests(unittest.TestCase):
    def test_an_explanation_names_the_code_and_gives_a_fix(self) -> None:
        text = explain("ANV104")
        self.assertIsNotNone(text)
        self.assertIn("error[ANV104]", text)
        self.assertIn("Cause:", text)
        self.assertIn("Fix:", text)

    def test_lookup_ignores_case(self) -> None:
        self.assertEqual(by_code("anv101").code, "ANV101")

    def test_an_unknown_code_returns_none(self) -> None:
        self.assertIsNone(explain("ANV999"))
        self.assertIsNone(by_code("nope"))

    def test_the_list_names_every_code(self) -> None:
        listing = code_list()
        for category in CATEGORIES:
            self.assertIn(category.code, listing)


class DocTests(unittest.TestCase):
    def test_the_generated_page_lists_every_code(self) -> None:
        page = (
            pathlib.Path(__file__).resolve().parents[1] / "docs" / "ERRORS.md"
        ).read_text(encoding="utf-8")
        rows = [line for line in page.splitlines() if line.startswith("| `ANV")]
        self.assertEqual(len(rows), len(CATEGORIES))
        for category in CATEGORIES:
            self.assertIn("`" + category.code + "`", page)


class ExplainCliTests(unittest.TestCase):
    def _run(self, *arguments: str):
        compiler = pathlib.Path(__file__).resolve().parents[1] / "compiler" / "anvil.py"
        return subprocess.run(
            [sys.executable, str(compiler), *arguments],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_a_known_code_prints_cause_and_fix(self) -> None:
        result = self._run("--explain", "ANV102")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("error[ANV102]", result.stdout)
        self.assertIn("Cause:", result.stdout)
        self.assertIn("Fix:", result.stdout)

    def test_an_unknown_code_lists_the_known_ones(self) -> None:
        result = self._run("--explain", "ANV999")
        self.assertEqual(result.returncode, 2)
        self.assertIn("ANV101", result.stderr)

    def test_explain_needs_no_source_file(self) -> None:
        result = self._run("--explain", "ANV107")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
