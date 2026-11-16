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
                "scene 2d\n\nfn(draw)\n  display ray_sphere(0, 0, 3, 1) -rgb(255, 0, 0)\nend\n",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("display ray_sphere(...) is not available", result.stderr)
            self.assertIn(":4:", result.stderr)

    def test_unsupported_builtins_name_the_call_site(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(root, "fn(main)\n  say body_create(0, 0, 1, 1)\nend\ncall fn(main)\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("'body_create' is not available in the wasm backend yet", result.stderr)
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

    def test_unavailable_shapes_are_refused(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                "scene 3d\n\nfn(draw)\n  display ray_sphere(0, 0, 3, 1) -rgb(255, 0, 0)\nend\n",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("display ray_sphere(...) is not available", result.stderr)



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



def _write_quad_bmp(path: pathlib.Path) -> None:
    import struct

    rows = [
        [(0, 0, 255), (255, 255, 255)],  # bottom row: blue, white
        [(255, 0, 0), (0, 255, 0)],  # top row: red, green
    ]
    data = b""
    for row in rows:
        data += b"".join(bytes((b, g, r)) for (r, g, b) in row)
        data += b"\x00" * ((4 - (2 * 3) % 4) % 4)
    header = b"BM" + struct.pack("<IHHI", 54 + len(data), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, 2, 2, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    path.write_bytes(header + info + data)


_IMAGE_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(pic) = 0",
        "",
        "fn(update)",
        "  if var(pic) = 0",
        '    set var(pic) = image_load("quad.bmp")',
        "    set var(tint) = image_tint(var(pic), 128, 255, 64)",
        "    set var(flip) = image_flip(var(pic), 1, 0)",
        "  end",
        "end",
        "",
        "fn(draw)",
        "  set var(d) = image_draw_scaled(var(pic), 100, 100, 200, 200)",
        "  set var(s) = image_draw(var(pic), 400, 100)",
        "  set var(r) = image_draw_rotated(var(pic), 700, 300, 90, 2)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmImageTests(unittest.TestCase):
    def test_literal_bmps_are_baked_and_drawn(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_quad_bmp(root / "quad.bmp")
            result, out = build(root, _IMAGE_PROGRAM)
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
            images = [op for op in ops if op[0] == "image"]
            self.assertEqual(len(images), 3)
            self.assertEqual(images[0], ["image", 2, 2, 100.0, 100.0, 200.0, 200.0, 0.0, 128, 255, 64, 1, 0, 1096806379])
            self.assertEqual(images[1][3:7], [400.0, 100.0, 2.0, 2.0])
            self.assertEqual(images[2][3:8], [698, 298, 4, 4, 90])

    def test_a_missing_bmp_is_a_located_build_error(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                'scene 2d\n\nfn(draw)\n  set var(p) = image_load("nope.bmp")\nend\n',
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("image_load cannot read \"nope.bmp\"", result.stderr)
            self.assertIn(":4:", result.stderr)

    def test_a_computed_path_reports_the_bake_limit(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "scene 2d",
                    'set var(name) = "quad.bmp"',
                    "set var(pic) = 0",
                    "",
                    "fn(update)",
                    "  if var(pic) = 0",
                    "    set var(pic) = image_load(var(name))",
                    "    say image_error()",
                    "  end",
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
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("only literal image_load() paths", run.stdout)



def _write_palette_bmp(path: pathlib.Path) -> None:
    import struct

    palette = [(10, 20, 30), (200, 100, 50)]
    body = bytes((0, 1)) + b"\x00" * 2
    entries = b"".join(bytes((b, g, r, 0)) for (r, g, b) in palette)
    entries += b"\x00" * (4 * (256 - len(palette)))
    offset = 54 + len(entries)
    header = b"BM" + struct.pack("<IHHI", offset + len(body), 0, 0, offset)
    info = struct.pack(
        "<IiiHHIIiiII", 40, 2, 1, 1, 8, 0, len(body), 2835, 2835, len(palette), 0
    )
    path.write_bytes(header + info + entries + body)


_REGION_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(pic) = 0",
        "set var(pal) = 0",
        "",
        "fn(update)",
        "  if var(pic) = 0",
        '    set var(pic) = image_load("quad.bmp")',
        '    set var(pal) = image_load("pal.bmp")',
        "  end",
        "end",
        "",
        "fn(draw)",
        "  set var(a) = image_draw_region(var(pic), 0, 0, 1, 1, 100, 100, 50, 50)",
        "  set var(b) = image_draw_region(var(pic), 1, 0, 1, 1, 160, 100, 50, 50)",
        "  set var(c) = image_draw_region(var(pic), 2, 2, 2, 2, 0, 0, 10, 10)",
        "  set var(d) = image_draw_scaled(var(pal), 300, 100, 20, 10)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmRegionTests(unittest.TestCase):
    def test_atlas_cells_and_eight_bit_bmps(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_quad_bmp(root / "quad.bmp")
            _write_palette_bmp(root / "pal.bmp")
            result, out = build(root, _REGION_PROGRAM)
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
            regions = [op for op in ops if op[0] == "image_region"]
            self.assertEqual(len(regions), 2, "the out-of-bounds cell must draw nothing")
            self.assertEqual(regions[0][3:11], [0, 0, 1, 1, 100, 100, 50, 50])
            self.assertEqual(regions[1][3:11], [1, 0, 1, 1, 160, 100, 50, 50])
            self.assertEqual(regions[0][-1], 1096806379)
            images = [op for op in ops if op[0] == "image"]
            self.assertEqual(len(images), 1)
            self.assertEqual(images[0][1:7], [2, 1, 300, 100, 20, 10])
            self.assertEqual(images[0][-1], 4067206025)



def _write_tone(path: pathlib.Path, frames: int = 800, rate: int = 8000, tag: int = 1) -> None:
    import math
    import struct

    samples = b"".join(
        struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * index / rate)))
        for index in range(frames)
    )
    header = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, tag, 1, rate, rate * 2, 2, 16)
    path.write_bytes(header + fmt + b"data" + struct.pack("<I", len(samples)) + samples)


_SOUND_PROGRAM = "\n".join(
    (
        "scene 2d",
        "set var(s) = 0",
        "set var(report) = 0",
        "",
        "fn(update)",
        "  if var(report) = 0",
        '    set var(s) = sound_load("tone.wav")',
        "    say var(s)",
        "    say sound_play(var(s))",
        "    say sound_active()",
        "    say sound_volume(1, 0.5)",
        "    say sound_stop_all()",
        "    say sound_active()",
        "    say sound_destroy(var(s))",
        "    say sound_error()",
        "    set var(report) = 1",
        "  end",
        "end",
        "",
        "fn(draw)",
        "  display rect(0, 0, 1, 1) -rgb(0, 0, 0)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmSoundTests(unittest.TestCase):
    def test_literal_wavs_are_baked_and_played(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_tone(root / "tone.wav")
            result, out = build(root, _SOUND_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.strip().splitlines()
            self.assertEqual(
                lines[:8], ["1", "1", "1", "0.5", "1", "0", "1", ""]
            )
            ops = json.loads(lines[-1])
            played = [op for op in ops if op[0] == "sound_play"]
            self.assertEqual(played, [["sound_play", 800, 1, 8000, 1, 12000, 1, 0, 1]])
            self.assertIn(["sound_volume", 1, 0.5], ops)
            self.assertIn(["sound_stop_all", 1], ops)

    def test_a_missing_wav_is_a_located_build_error(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                'scene 2d\n\nfn(draw)\n  set var(s) = sound_load("nope.wav")\nend\n',
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('sound_load cannot read "nope.wav"', result.stderr)
            self.assertIn(":4:", result.stderr)

    def test_compressed_wavs_are_refused_at_build_time(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_tone(root / "float.wav", tag=3)
            result, _ = build(
                root,
                'scene 2d\n\nfn(draw)\n  set var(s) = sound_load("float.wav")\nend\n',
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PCM only", result.stderr)




_LOOP_PROGRAM = "\n".join(
    (
        "scene 2d",
        "set var(s) = 0",
        "set var(report) = 0",
        "",
        "fn(update)",
        "  if var(report) = 0",
        '    set var(s) = sound_load("tone.wav")',
        "    say sound_duration(var(s))",
        "    say sound_play_loop(var(s))",
        "    say sound_pan(1, 2)",
        "    say sound_pitch(1, 9)",
        "    say sound_pan(1, -0.5)",
        "    say sound_pitch(1, 0.5)",
        "    say sound_stop(1)",
        "    set var(report) = 1",
        "  end",
        "end",
        "",
        "fn(draw)",
        "  display rect(0, 0, 1, 1) -rgb(0, 0, 0)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmLoopSoundTests(unittest.TestCase):
    def test_loop_pan_pitch_and_duration(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_tone(root / "tone.wav")
            result, out = build(root, _LOOP_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.strip().splitlines()
            self.assertEqual(lines[:7], ["0.1", "1", "1", "4", "-0.5", "0.5", "1"])
            ops = json.loads(lines[-1])
            played = [op for op in ops if op[0] == "sound_play"]
            self.assertEqual(played, [["sound_play", 800, 1, 8000, 1, 12000, 1, 1, 1]])
            self.assertIn(["sound_pan", 1, 1], ops)
            self.assertIn(["sound_pitch", 1, 4], ops)
            self.assertIn(["sound_pan", 1, -0.5], ops)
            self.assertIn(["sound_pitch", 1, 0.5], ops)
            self.assertIn(["sound_stop", 1, 1], ops)



_GROUP_PROGRAM = "\n".join(
    (
        "scene 2d",
        "set var(s) = 0",
        "set var(report) = 0",
        "",
        "fn(update)",
        "  if var(report) = 0",
        '    set var(s) = sound_load("tone.wav")',
        "    say sound_group(var(s), 2)",
        "    say sound_group(var(s), 9)",
        "    say sound_group_volume(0, 0.5)",
        "    say sound_group_mute(2, 1)",
        "    say sound_group_gain(2)",
        "    say sound_group_mute(2, 0)",
        "    say sound_group_gain(2)",
        "    say sound_play(var(s))",
        "    say sound_play(var(s))",
        "    say sound_group_stop(2)",
        "    say sound_active()",
        "    set var(report) = 1",
        "  end",
        "end",
        "",
        "fn(draw)",
        "  display rect(0, 0, 1, 1) -rgb(0, 0, 0)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmAudioGroupTests(unittest.TestCase):
    def test_groups_route_plays_and_stop_by_group(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_tone(root / "tone.wav")
            result, out = build(root, _GROUP_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.strip().splitlines()
            self.assertEqual(
                lines[:11], ["2", "0", "0.5", "1", "0", "0", "1", "1", "2", "2", "0"]
            )
            ops = json.loads(lines[-1])
            played = [op for op in ops if op[0] == "sound_play"]
            self.assertEqual([op[-1] for op in played], [2, 2])
            self.assertIn(["sound_group_volume", 0, 0.5], ops)
            self.assertIn(["sound_group_mute", 2, 1], ops)
            self.assertIn(["sound_group_mute", 2, 0], ops)
            self.assertIn(["sound_group_stop", 2, 2], ops)



_THREE_D_PROGRAM = "\n".join(
    (
        "scene 3d",
        "camera perspective 0 3 12",
        "camera fov(70)",
        "clear rgba(11, 16, 27, 255)",
        "",
        "fn(draw)",
        "  display plane(0, -1, 0, 14, 14) -rgb(33, 47, 64)",
        "  display cube(0, 0, 0, 2) -rgb(88, 164, 255)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmScene3DTests(unittest.TestCase):
    def test_cube_and_plane_emit_sorted_triangles(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _THREE_D_PROGRAM)
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
            summary = [op for op in ops if op[0] == "triangles"]
            self.assertEqual(len(summary), 1)
            self.assertEqual(summary[0][1], 14, "two plane triangles plus twelve cube triangles")
            min_x, max_x, min_y, max_y = summary[0][2:6]
            self.assertLess(min_x, 0)
            self.assertGreater(max_x, 960)
            self.assertGreater(min_y, 300, "geometry sits below the horizon")
            self.assertGreater(max_y, 600, "the floor extends past the bottom edge")

    def test_sphere_emits_a_bounded_triangle_fan(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 6",
                    "",
                    "fn(draw)",
                    "  display sphere(0, 0, 0, 1) -rgb(200, 120, 60)",
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
            summary = [op for op in ops if op[0] == "triangles"][0]
            self.assertEqual(summary[1], 320, "10 rings x 16 segments x 2 triangles")



sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_gltf_model import write_quad  # noqa: E402


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmModelTests(unittest.TestCase):
    def test_a_gltf_model_is_baked_and_drawn(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 6",
                    "clear rgba(10, 12, 18, 255)",
                    "",
                    "fn(draw)",
                    '  set var(d) = model_draw("quad.gltf", 0, 0, 0, 1, 0, 0, 0)',
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
            summary = [op for op in ops if op[0] == "triangles"]
            self.assertEqual(len(summary), 1)
            self.assertEqual(summary[0][1], 2, "a quad is two triangles")
            min_x, max_x, min_y, max_y = summary[0][2:6]
            self.assertTrue(390 <= min_x <= 400, min_x)
            self.assertTrue(560 <= max_x <= 575, max_x)
            self.assertTrue(235 <= min_y <= 245, min_y)
            self.assertTrue(405 <= max_y <= 420, max_y)

    def test_a_translated_model_moves_on_screen(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0), (0, 0, 0))
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 6",
                    "",
                    "fn(draw)",
                    '  set var(d) = model_draw("quad.gltf", -2, 0, 0, 1, 0, 0, 0)',
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
            summary = [op for op in ops if op[0] == "triangles"][0]
            self.assertLess(summary[2], 390, "the model shifts left when x is negative")



@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmShadowCullingTests(unittest.TestCase):
    def test_a_cube_submits_one_shadow_quad(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 4 9",
                    "set var(ang) = camera_angle(0, -22)",
                    "set var(sh) = shadow(1)",
                    "set var(gh) = shadow_height(0)",
                    "set var(al) = shadow_alpha(300)",
                    "",
                    "fn(update)",
                    "  say shadow_alpha(300)",
                    "end",
                    "",
                    "fn(draw)",
                    "  display cube(0, 2, 0, 2) -rgb(255, 140, 60)",
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
            lines = run.stdout.strip().splitlines()
            self.assertEqual(lines[0], "255", "shadow alpha clamps to 255")
            ops = json.loads(lines[-1])
            summary = [op for op in ops if op[0] == "triangles"][0]
            self.assertEqual(summary[1], 14, "twelve cube triangles plus two shadow triangles")

    def test_culling_skips_off_screen_models(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 6",
                    "set var(report) = 0",
                    "",
                    "fn(update)",
                    "  if var(report) = 2",
                    "    say mesh_culled()",
                    "    set var(report) = 3",
                    "  end",
                    "  set var(report) = compute(var(report) + 1)",
                    "end",
                    "",
                    "fn(draw)",
                    '  set var(d) = model_draw("quad.gltf", 40, 0, 0, 1, 0, 0, 0)',
                    "end",
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
                env={**os.environ, "ANVIL_WASM_FRAMES": "3"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines()[0], "1", "the model reports culled")
            self.assertNotIn("triangles", run.stdout)

    def test_a_model_shadow_adds_flattened_triangles(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 6",
                    "set var(sh) = shadow(1)",
                    "",
                    "fn(draw)",
                    '  set var(d) = model_draw("quad.gltf", 0, 0, 0, 1, 0, 0, 0)',
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
            summary = [op for op in ops if op[0] == "triangles"][0]
            self.assertEqual(summary[1], 4, "two model triangles plus two shadow triangles")



_MUSIC_PROGRAM = "\n".join(
    (
        "scene 2d",
        "set var(report) = 0",
        "",
        "fn(update)",
        "  if var(report) = 0",
        '    set var(loaded) = music_load("song.wav")',
        "    say var(loaded)",
        "    say music_length()",
        "    say music_play_loop()",
        "    say music_playing()",
        "    say music_volume(0.5)",
        "    say music_position()",
        "    set var(report) = 1",
        "  end",
        "end",
        "",
        "fn(draw)",
        "  display rect(0, 0, 1, 1) -rgb(0, 0, 0)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmMusicTests(unittest.TestCase):
    def test_a_baked_track_plays_and_reports_its_length(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_tone(root / "song.wav", frames=1600)
            result, out = build(root, _MUSIC_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.strip().splitlines()
            self.assertEqual(lines[:6], ["1", "0.2", "1", "1", "0.5", "0"])
            ops = json.loads(lines[-1])
            self.assertIn(["music_play", 1600, 1, 8000, 1, 1], ops)
            self.assertIn(["music_volume", 0.5], ops)

    def test_a_missing_track_is_a_located_build_error(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                'scene 2d\n\nfn(draw)\n  set var(m) = music_load("nope.wav")\nend\n',
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('music_load cannot read "nope.wav"', result.stderr)
            self.assertIn(":4:", result.stderr)

    def test_a_computed_track_path_reports_the_bake_limit(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_tone(root / "song.wav", frames=800)
            program = "\n".join(
                (
                    "scene 2d",
                    'set var(name) = "song.wav"',
                    "set var(report) = 0",
                    "",
                    "fn(update)",
                    "  if var(report) = 0",
                    "    say music_load(var(name))",
                    "    say music_error()",
                    "    set var(report) = 1",
                    "  end",
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
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("only the literal music_load() path", run.stdout)


if __name__ == "__main__":
    unittest.main()
