"""WebAssembly console target: build with clang, run under Node (8.12)."""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
HOST = ROOT / "tools" / "wasm_host.mjs"
NEEDS = shutil.which("clang") and shutil.which("node") and shutil.which("wasm-ld")


def build(root: pathlib.Path, source_text: str, name: str = "program.ANVL"):
    source = root / name
    source.write_text(source_text, encoding="utf-8")
    out = root / "program.wasm"
    result = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "--backend", "wasm", "-o", str(out)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result, out


def run_wasm(path: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(HOST), str(path)], capture_output=True, text=True, timeout=60
    )


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmBuildTests(unittest.TestCase):
    def test_hello_prints_numbers_and_text(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(
                root, 'fn(main)\n  say "hello from wasm"\n  say 6 * 7\nend\ncall fn(main)\n'
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 500)
            page = out.with_suffix(".html")
            self.assertTrue(page.is_file(), "a host page should be generated")
            self.assertIn("program.wasm", page.read_text(encoding="utf-8"))
            run = run_wasm(out)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, "hello from wasm\n42\n")

    def test_strings_arrays_loops_and_calls(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "fn(add, a, b)",
                    "  output var(a) + var(b)",
                    "end",
                    "",
                    "set var(total) = 0",
                    "array scores(3)",
                    "",
                    "fn(main)",
                    '  set var(greeting) = "Hello" & " " & "world"',
                    "  say var(greeting)",
                    "  say len(var(greeting))",
                    "  say mid(var(greeting), 2, 5)",
                    "  say upper(var(greeting))",
                    '  say number("42.5")',
                    "  say floor(3.7)",
                    "  say call fn(add, 2, 3)",
                    "  set array(scores, 0) = 5",
                    "  set var(i) = 0",
                    "  while var(i) < 3",
                    "    add var(total) var(i)",
                    "    add var(i) 1",
                    "  end",
                    "  say var(total)",
                    "  say array(scores, 0)",
                    "  if var(total) > 2",
                    '    say "big"',
                    "  else",
                    '    say "small"',
                    "  end",
                    "end",
                    "call fn(main)",
                    "",
                )
            )
            result, out = build(root, program)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = run_wasm(out)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(
                run.stdout.splitlines(),
                ["Hello world", "11", "llo w", "HELLO WORLD", "42.5", "3", "5", "3", "5", "big"],
            )

    def test_check_accepts_a_console_program(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "check.ANVL"
            source.write_text("fn(main)\n  say 1 + 1\nend\ncall fn(main)\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "--backend", "wasm", "--check"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("ok", result.stdout)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmRejectionTests(unittest.TestCase):
    def test_graphics_statements_are_refused_with_a_location(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                "scene 2d\n\nfn(draw)\n  display rect(10, 10, 20, 20) -rgb(255, 0, 0)\nend\n",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("wasm backend runs console programs only", result.stderr)
            self.assertIn(":1:", result.stderr)

    def test_unsupported_builtins_name_the_call_site(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(root, "fn(main)\n  say time()\nend\ncall fn(main)\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("'time' is not available in the wasm backend yet", result.stderr)
            self.assertIn(":2:", result.stderr)


if __name__ == "__main__":
    unittest.main()
