"""WebAssembly console target: build with clang, run under Node (8.12)."""

from __future__ import annotations

import json
import os
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
    def test_unsupported_shapes_name_the_line(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                "scene 2d\n\nfn(draw)\n  display cube(0, 0, 0, 1) -rgb(255, 0, 0)\nend\n",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("display cube(...) is not available", result.stderr)
            self.assertIn(":4:", result.stderr)

    def test_unsupported_builtins_name_the_call_site(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(root, "fn(main)\n  say noise(0, 0, 0)\nend\ncall fn(main)\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("'noise' is not available in the wasm backend yet", result.stderr)
            self.assertIn(":2:", result.stderr)



@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmCanvasTests(unittest.TestCase):
    def test_a_2d_scene_emits_canvas_commands(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "scene 2d",
                    "clear rgba(10, 20, 30, 255)",
                    "",
                    "fn(draw)",
                    "  display rect(10, 20, 100, 50) -rgb(255, 0, 0)",
                    "  display circle(200, 120, 30) -rgb(0, 255, 0)",
                    "  display line(0, 0, 50, 50) -rgb(0, 0, 255)",
                    '  display text("hi") -l(30, 40) -rgb(255, 255, 0)',
                    "end",
                    "",
                )
            )
            result, out = build(root, program)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            ops = json.loads(run.stdout.strip().splitlines()[-1])
            self.assertEqual(
                ops,
                [
                    ["clear", 10, 20, 30, 255],
                    ["rect", 10.0, 20.0, 100.0, 50.0, 255, 0, 0, 255],
                    ["circle", 200.0, 120.0, 30.0, 0, 255, 0, 255],
                    ["line", 0.0, 0.0, 50.0, 50.0, 1.0, 0, 0, 255, 255],
                    ["text", 30.0, 40.0, "hi", 255, 255, 0, 255],
                    ["present"],
                ],
            )

    def test_the_host_page_draws_on_a_canvas(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, "scene 2d\n\nfn(draw)\n  display rect(0, 0, 10, 10) -rgb(1, 2, 3)\nend\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            page = out.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn('<canvas id="screen"', page)
            self.assertIn("getContext(\"2d\")", page)
            self.assertIn("requestAnimationFrame", page)

    def test_three_d_and_other_shapes_are_refused(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(root, "scene 3d\n\nfn(draw)\n  display cube(0, 0, 0, 1) -rgb(255, 0, 0)\nend\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("draws 'scene 2d' only", result.stderr)

            result, _ = build(root, "scene 2d\n\nfn(draw)\n  display cube(0, 0, 0, 1) -rgb(255, 0, 0)\nend\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("display cube(...) is not available in the wasm backend", result.stderr)



@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmInputTests(unittest.TestCase):
    def test_keyboard_mouse_and_time_reach_the_program(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "scene 2d",
                    "",
                    "fn(update)",
                    "  if pressed(A)",
                    '    say "pressed"',
                    "  end",
                    "  if held(A)",
                    '    say "held"',
                    "  end",
                    "  say mouse_x()",
                    "  say mouse_y()",
                    "  say round(delta() * 1000)",
                    "end",
                    "",
                    "fn(draw)",
                    "  display rect(0, 0, 1, 1) -rgb(0, 0, 0)",
                    "end",
                    "",
                )
            )
            result, out = build(root, program)
            self.assertEqual(result.returncode, 0, result.stderr)
            script = json.dumps(
                [
                    ["key", 65, 1],
                    ["frame", 16],
                    ["frame", 16],
                    ["key", 65, 0],
                    ["frame", 16],
                    ["mouse", 100, 50],
                    ["frame", 16],
                ]
            )
            run = subprocess.run(
                ["node", str(HOST), "--input", script, str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(
                run.stdout.splitlines(),
                [
                    "pressed",
                    "held",
                    "-1",
                    "-1",
                    "16",
                    "held",
                    "-1",
                    "-1",
                    "16",
                    "-1",
                    "-1",
                    "16",
                    "100",
                    "50",
                    "16",
                ],
            )

    def test_time_accumulates_across_frames(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "scene 2d",
                    "",
                    "fn(update)",
                    "  say round(delta() * 1000)",
                    "  say round(time() * 1000)",
                    "end",
                    "",
                    "fn(draw)",
                    "  display rect(0, 0, 1, 1) -rgb(0, 0, 0)",
                    "end",
                    "",
                )
            )
            result, out = build(root, program)
            self.assertEqual(result.returncode, 0, result.stderr)
            script = json.dumps([["frame", 100], ["frame", 100]])
            run = subprocess.run(
                ["node", str(HOST), "--input", script, str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), ["100", "100", "100", "200"])

    def test_the_host_page_wires_input_events(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, "scene 2d\n\nfn(draw)\n  display rect(0, 0, 1, 1) -rgb(0, 0, 0)\nend\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            page = out.with_suffix(".html").read_text(encoding="utf-8")
            for needle in ("keydown", "keyup", "mousemove", "mousedown", "wheel", "anvil_key"):
                self.assertIn(needle, page)



@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmMathTests(unittest.TestCase):
    def test_trig_matches_libm(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _MATH_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(
                run.stdout.splitlines(),
                [
                    "0",
                    "1000",
                    "1000",
                    "-1000",
                    "479426",
                    "-416147",
                    "841470985",
                    "-839071529",
                    "-598472144",
                    "-349994",
                ],
            )

    def test_rnd_stays_inside_its_inclusive_range(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "fn(main)",
                    "  set var(i) = 0",
                    "  set var(bad) = 0",
                    "  while var(i) < 500",
                    "    set var(v) = rnd(0, 9)",
                    "    if var(v) < 0",
                    "      set var(bad) = compute(var(bad) + 1)",
                    "    end",
                    "    if var(v) > 9",
                    "      set var(bad) = compute(var(bad) + 1)",
                    "    end",
                    "    set var(i) = compute(var(i) + 1)",
                    "  end",
                    "  say var(bad)",
                    '  say rnd(4, 4)',
                    "end",
                    "call fn(main)",
                    "",
                )
            )
            result, out = build(root, program)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), ["0", "4"])


_MATH_PROGRAM = "\n".join(
    (
        "fn(main)",
        "  say round(sin(0) * 1000)",
        "  say round(cos(0) * 1000)",
        "  say round(sin(1.5707963267948966) * 1000)",
        "  say round(cos(3.141592653589793) * 1000)",
        "  say round(sin(0.5) * 1000000)",
        "  say round(cos(2.0) * 1000000)",
        "  say round(sin(1.0) * 1000000000)",
        "  say round(cos(10.0) * 1000000000)",
        "  say round(sin(-2.5) * 1000000000)",
        "  say round(sin(1e6) * 1000000)",
        "end",
        "call fn(main)",
        "",
    )
)


if __name__ == "__main__":
    unittest.main()
