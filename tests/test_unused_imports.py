"""Unused imports are reported, and --deny-warnings makes them fatal."""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.builtin_usage import module_is_used, unused_imports, used_builtins  # noqa: E402
from compiler.modules import load_program  # noqa: E402

ANVIL = ROOT / "compiler" / "anvil.py"


class UnusedImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = pathlib.Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _program(self, source: str, name: str = "program.ANVL"):
        path = self.base / name
        path.write_text(source, encoding="utf-8")
        return path, load_program(path, source)

    def test_an_unused_import_is_reported(self) -> None:
        path, program = self._program(
            "import math\n\nfn(main)\n  say 1\nend\ncall fn(main)\n"
        )
        self.assertEqual([n.value for n in unused_imports(program.functions, program.top)], ["math"])

    def test_a_used_import_is_not_reported(self) -> None:
        path, program = self._program(
            "import math\n\nfn(main)\n  say floor(3.7)\nend\ncall fn(main)\n"
        )
        self.assertEqual(unused_imports(program.functions, program.top), [])

    def test_the_check_is_per_module_not_just_per_builtin(self) -> None:
        # floor is a math builtin, so importing text does not cover it.
        path, program = self._program(
            "import text\n\nfn(main)\n  say floor(3.7)\nend\ncall fn(main)\n"
        )
        used = used_builtins(program.functions, program.top)
        self.assertEqual(used, ["floor"])
        self.assertFalse(module_is_used("text", used))
        self.assertTrue(module_is_used("math", used))
        self.assertEqual([n.value for n in unused_imports(program.functions, program.top)], ["text"])

    def test_an_empty_builtins_import_is_reported(self) -> None:
        path, program = self._program(
            "import builtins\n\nfn(main)\n  say 1 + 1\nend\ncall fn(main)\n"
        )
        self.assertEqual(
            [n.value for n in unused_imports(program.functions, program.top)], ["builtins"]
        )

    def test_the_cli_prints_a_warning_with_a_caret_and_still_builds(self) -> None:
        path, _ = self._program("import math\n\nfn(main)\n  say 1\nend\ncall fn(main)\n")
        result = subprocess.run(
            [sys.executable, str(ANVIL), str(path), "--check"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("warning: import 'math' is never used", result.stderr)
        self.assertIn("import math", result.stderr)   # the rendered source line
        self.assertIn("^", result.stderr)

    def test_deny_warnings_fails_the_build(self) -> None:
        path, _ = self._program("import math\n\nfn(main)\n  say 1\nend\ncall fn(main)\n")
        result = subprocess.run(
            [sys.executable, str(ANVIL), str(path), "--check", "--deny-warnings"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("1 warning(s) treated as errors", result.stderr)

    def test_a_used_import_builds_quietly(self) -> None:
        path, _ = self._program(
            "import math\n\nfn(main)\n  say floor(3.7)\nend\ncall fn(main)\n"
        )
        result = subprocess.run(
            [sys.executable, str(ANVIL), str(path), "--check", "--deny-warnings"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("warning", result.stderr)


if __name__ == "__main__":
    unittest.main()
