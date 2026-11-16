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
            result, _ = build(root, "fn(main)\n  say image_load(\"pic.bmp\")\nend\ncall fn(main)\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("'image_load' is not available in the wasm backend yet", result.stderr)
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



@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmSaveTests(unittest.TestCase):
    def test_typed_slots_round_trip_with_the_c_error_names(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "fn(main)",
                    '  say save_number("high", 42)',
                    '  say load_number("high")',
                    '  say save_text("name", "Ada")',
                    '  say load_text("name")',
                    '  say load_number("name")',
                    "  say save_error()",
                    '  say load_text("high")',
                    "  say save_error()",
                    '  say save_exists("high")',
                    '  say save_delete("high")',
                    '  say save_exists("high")',
                    '  say load_number("high")',
                    "  say save_error()",
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
            self.assertEqual(
                run.stdout.splitlines(),
                [
                    "1",
                    "42",
                    "1",
                    "Ada",
                    "0",
                    "the save holds text, not a number",
                    "",
                    "the save holds a number, not text",
                    "1",
                    "1",
                    "0",
                    "0",
                    "",
                ],
            )

    def test_saves_persist_across_runs(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            store = root / "saves.json"
            write_result, write_out = build(
                root,
                'fn(main)\n  say save_number("level", 7)\n  say save_text("hero", "Ada")\nend\ncall fn(main)\n',
            )
            self.assertEqual(write_result.returncode, 0, write_result.stderr)
            environment = {**os.environ, "ANVIL_SAVE_FILE": str(store)}
            first = subprocess.run(
                ["node", str(HOST), str(write_out)],
                capture_output=True,
                text=True,
                timeout=60,
                env=environment,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout.splitlines(), ["1", "1"])

            read_result, read_out = build(
                root,
                'fn(main)\n  say load_number("level")\n  say load_text("hero")\nend\ncall fn(main)\n',
            )
            self.assertEqual(read_result.returncode, 0, read_result.stderr)
            second = subprocess.run(
                ["node", str(HOST), str(read_out)],
                capture_output=True,
                text=True,
                timeout=60,
                env=environment,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(second.stdout.splitlines(), ["7", "Ada"])

    def test_invalid_slots_and_oversized_text_are_refused(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "fn(main)",
                    '  say save_number("bad/slot", 1)',
                    "  say save_error()",
                    f'  say save_text("long", "{"x" * 256}")',
                    "  say save_error()",
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
            lines = run.stdout.splitlines()
            self.assertEqual(lines[0], "0")
            self.assertEqual(lines[1], "the save slot is invalid")
            self.assertEqual(lines[2], "0")
            self.assertEqual(lines[3], "the text is 256 bytes; the save limit is 255")



_PROGRAM_TEXT = "\n".join(
    (
        "fn(main)",
        '  say lower("AbC")',
        '  say trim("  hi  ")',
        '  say left("abcdef", 3)',
        '  say right("abcdef", 2)',
        '  say left("abc", 99)',
        '  say right("abc", -1)',
        '  say left("abcdef", 1.9)',
        '  say char("hello", 1)',
        '  say char("hello", 9)',
        '  say contains("abcdef", "cd")',
        '  say contains("abcdef", "zz")',
        '  say starts_with("abcdef", "abc")',
        '  say ends_with("abcdef", "def")',
        '  say starts_with("abc", "b")',
        '  say ends_with("abc", "abcd")',
        "end",
        "call fn(main)",
        "",
    )
)

_EXPECTED_TEXT = [
    "abc", "hi", "abc", "ef", "abc", "",
    "a", "e", "", "1", "0", "1", "1", "0", "0",
]


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmTextTests(unittest.TestCase):
    def test_text_helpers_match_the_c_backend(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _PROGRAM_TEXT)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), _EXPECTED_TEXT)

            source = root / "program.ANVL"
            executable = root / "program.exe"
            compiled = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            native = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60
            )
            self.assertEqual(native.stdout, run.stdout)



_NOISE_PROGRAM = "\n".join(
    (
        "fn(main)",
        "  say round(noise(0.5, 0.5, 0.5) * 1000000)",
        "  say round(noise(12.25, -3.75, 8.5) * 1000000)",
        "  say round(noise(-100.125, 200.875, 3.5) * 1000000)",
        "  say round(fbm(1.5, 2.5, 0.5, 4, 2, 0.5) * 1000000)",
        "  say round(fbm(-7.25, 3.5, 9.75, 6, 2.1, 0.45) * 1000000)",
        "  say round(fbm(0, 0, 0, 1, 2, 0.5) * 1000000)",
        '  say ord("A")',
        '  say ord("hello")',
        '  say ord("")',
        "  say chr(65)",
        "  say chr(97)",
        "  say len(chr(0))",
        "  say ord(chr(0))",
        "end",
        "call fn(main)",
        "",
    )
)

_NOISE_EXPECTED = [
    "175000",
    "351612",
    "97809",
    "-93333",
    "96055",
    "0",
    "65",
    "104",
    "0",
    "A",
    "a",
    "0",
    "0",
]


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmNoiseTests(unittest.TestCase):
    def test_noise_fbm_and_characters_match_the_c_backend(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _NOISE_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), _NOISE_EXPECTED)

            executable = root / "program.exe"
            compiled = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(root / "program.ANVL"),
                    "-o",
                    str(executable),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            native = subprocess.run(
                [str(executable)], capture_output=True, text=True, timeout=60
            )
            self.assertEqual(native.stdout, run.stdout)

    def test_out_of_range_chr_stops_with_the_same_message(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, "fn(main)\n  say chr(300)\nend\ncall fn(main)\n")
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("Anvil chr out of range", run.stderr)
            self.assertEqual(run.stdout, "")


if __name__ == "__main__":
    unittest.main()
