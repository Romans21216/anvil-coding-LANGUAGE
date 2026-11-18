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


def build(
    root: pathlib.Path,
    source_text: str,
    name: str = "program.ANVL",
    extra_args: tuple[str, ...] = (),
):
    source = root / name
    source.write_text(source_text, encoding="utf-8")
    out = root / "program.wasm"
    result = subprocess.run(
        [
            sys.executable,
            str(COMPILER),
            str(source),
            "--backend",
            "wasm",
            "-o",
            str(out),
            *extra_args,
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result, out


def run_wasm(path: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(HOST), str(path)], capture_output=True, text=True, timeout=60
    )


class WasmDebugInfoOptionTests(unittest.TestCase):
    def test_debug_info_rejects_non_wasm_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "program.ANVL"
            source.write_text("fn(main)\nend\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "--debug-info"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--debug-info applies only to --backend wasm", result.stderr)

    def test_debug_info_requires_a_linked_wasm_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = root / "program.ANVL"
            source.write_text("fn(main)\nend\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "--debug-info",
                    "--emit-c",
                    str(root / "generated.c"),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
        self.assertEqual(result.returncode, 1)
        self.assertIn("--debug-info requires a linked WASM output", result.stderr)


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
            self.assertNotIn(b".debug_line", out.read_bytes())
            page = out.with_suffix(".html")
            self.assertTrue(page.is_file(), "a host page should be generated")
            self.assertIn("program.wasm", page.read_text(encoding="utf-8"))
            run = run_wasm(out)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout, "hello from wasm\n42\n")

    def test_debug_info_contains_dwarf_lines_mapped_to_anvil_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source_text = "fn(main)\n  say 42\nend\ncall fn(main)\n"
            result, out = build(
                root,
                source_text,
                name="program with spaces.ANVL",
                extra_args=("--debug-info",),
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            generated = (root / ".anvil-cache" / "program.wasm.c").read_text(
                encoding="utf-8"
            )
            source = root / "program with spaces.ANVL"
            self.assertIn(
                f"#line 2 {json.dumps(str(source.resolve()))}", generated
            )
            module = out.read_bytes()
            self.assertIn(b".debug_line", module)
            self.assertIn(source.name.encode("utf-8"), module)
            objdump = shutil.which("llvm-objdump")
            if objdump:
                lines = subprocess.run(
                    [objdump, "--source", "--line-numbers", "--disassemble", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                self.assertEqual(lines.returncode, 0, lines.stderr)
                self.assertIn(f"{source.resolve()}:2", lines.stdout)
                self.assertIn("say 42", lines.stdout)

            function_map = json.loads(
                out.with_suffix(".map.json").read_text(encoding="utf-8")
            )
            self.assertEqual(function_map["anvil_main"], {"name": "main", "line": 1})

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
    def test_ray_sphere_requires_a_3d_scene(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                "scene 2d\n\nfn(draw)\n  display ray_sphere(0, 0, 3, 1) -rgb(255, 0, 0)\nend\n",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("display ray_sphere(...) requires scene 3d", result.stderr)
            self.assertIn(":4:", result.stderr)

    def test_unsupported_shapes_name_the_line(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                "scene 3d\n\nfn(draw)\n  display torus(0, 0, 3, 1) -rgb(255, 0, 0)\nend\n",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("display torus(...) is not available", result.stderr)
            self.assertIn(":4:", result.stderr)

    def test_unsupported_builtins_name_the_call_site(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(root, "fn(main)\n  say window_on_top(1)\nend\ncall fn(main)\n")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("'window_on_top' is not available in the wasm backend yet", result.stderr)
            self.assertIn(":2:", result.stderr)



@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmCanvasTests(unittest.TestCase):
    def test_dynamic_numeric_text_uses_shared_fractional_formatter(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = (
                "set var(amount) = 0.333333333\nscene 2d\n\nfn(draw)\n"
                "  set local(part) = 0.666666666\n"
                "  display text(\"value: \" + var(amount) + \" part: \" + local(part) + \" sum: \" + (1 + 2)) -l(5, 7)\n"
                "end\n"
            )
            result, out = build(root, source)
            self.assertEqual(result.returncode, 0, result.stderr)
            c_source = out.parent / ".anvil-cache" / f"{out.stem}.wasm.c"
            generated = c_source.read_text(encoding="utf-8")
            self.assertIn("anvil_str_from_number", generated)

            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            ops = json.loads(run.stdout.strip().splitlines()[-1])
            self.assertIn(
                ["text", 5.0, 7.0, "value: 0.333333 part: 0.666667 sum: 3", 255, 255, 255, 255],
                ops,
            )

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
            ops = [op for op in ops if op[0] != "scene_mode"]
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

    def test_ray_sphere_emits_a_shaded_mesh(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(
                root,
                "scene 3d\ncamera perspective 0 0 8\n\nfn(draw)\n"
                "  display ray_sphere(-0.7, 0, 3, 1) -rgb(210, 70, 40)\n"
                "  display ray_sphere(0.7, 0, 5, 1) -rgb(60, 100, 230)\nend\n",
            )
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
            batch = next(op for op in ops if op[0] == "triangles")
            self.assertGreater(batch[1], 1000)
            self.assertLess(batch[2], 480)
            self.assertGreater(batch[3], 480)
            self.assertGreater(batch[6], 20)
            self.assertGreater(batch[8], batch[7])

    def test_ray_sphere_tessellation_obeys_frame_triangle_cap(self) -> None:
        draw = [
            "scene 3d",
            "camera perspective 0 0 8",
            "",
            "fn(draw)",
        ]
        for _ in range(32):
            draw.append("  display ray_sphere(0, 0, 0, 5) -rgb(210, 70, 40)")
        draw += ["end", ""]
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, "\n".join(draw))
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        ops = json.loads(run.stdout.strip().splitlines()[-1])
        batch = next(op for op in ops if op[0] == "triangles")
        self.assertGreater(batch[1], 0)
        self.assertLessEqual(batch[1], 16384)



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
    def test_lighting_builtins_validate_and_return_previous_values(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "scene 3d",
                    "fn(update)",
                    "  say light(0, 0, 1)",
                    "  say light(0, 0, 0)",
                    "  say light_ambient(0.1)",
                    "  say light_intensity(0.5)",
                    "end",
                    "fn(main)",
                    "end",
                    "fn(draw)",
                    "end",
                    "",
                )
            )
            result, out = build(root, program)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = run_wasm(out)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines()[:4], ["1", "0", "0.28", "1"])

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
from test_gltf_model import write_glb, write_quad  # noqa: E402
from test_gltf_morph import (  # noqa: E402
    write_morph_glb,
    write_morph_model,
    write_two_target_morph_model,
)
from test_gltf_ray_mesh import write_animated_morph_glb  # noqa: E402
from test_gltf_skins import write_skinned_model  # noqa: E402


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmModelTests(unittest.TestCase):
    def test_static_glb_model_draw_reaches_the_wasm_renderer(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_glb(root, "quad.glb", (1.0, 0.0, 0.0))
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 5",
                    "camera fov(60)",
                    "fn(draw)",
                    '  set var(ok) = model_draw("quad.glb", 0, 0, 0, 1, 0, 0, 0)',
                    "end",
                    "",
                )
            )
            result, output = build(root, program, "static_glb.ANVL")
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(output)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            records = json.loads(run.stdout.strip().splitlines()[-1])
            summaries = [record for record in records if record[0] == "triangles"]
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0][1], 2, "the embedded GLB quad has two triangles")

    def test_instance_capacity_matches_c_and_recovers_after_destroy(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_morph_model(root, "instance.gltf")
            program = "\n".join(
                (
                    "scene 3d",
                    "fn(draw)",
                    '  set var(first) = model_instance("instance.gltf")',
                    "  set var(failures) = 0",
                    "  for local(i) = 0 to 62",
                    '    set var(handle) = model_instance("instance.gltf")',
                    "    if var(handle) = 0",
                    "      add var(failures) 1",
                    "    end",
                    "  end",
                    '  set var(overflow) = model_instance("instance.gltf")',
                    '  set var(released) = model_instance_destroy("instance.gltf", var(first))',
                    '  set var(replacement) = model_instance("instance.gltf")',
                    '  say "capacity " & var(failures) & "," & var(overflow) & "," & var(released) & "," & var(replacement)',
                    '  say "old " & model_instance_morph("instance.gltf", var(first), 0, 1)',
                    '  say "new " & model_instance_morph("instance.gltf", var(replacement), 0, 1)',
                    '  say "done"',
                    "end",
                    "",
                )
            )
            result, output = build(root, program, "instance_capacity")
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(output)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
        lines = run.stdout.strip().splitlines()
        self.assertIn("capacity 0,0,1,65", lines)
        self.assertIn("old 0", lines)
        self.assertIn("new 0", lines)

    def test_instance_morph_draws_use_independent_generation_checked_handles(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_morph_model(root, "instance.gltf")
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 8",
                    "fn(draw)",
                    '  set var(old) = model_instance("instance.gltf")',
                    '  set var(destroyed) = model_instance_destroy("instance.gltf", var(old))',
                    "  for local(i) = 0 to 69",
                    '    set var(reused) = model_instance("instance.gltf")',
                    '    set var(destroyed) = model_instance_destroy("instance.gltf", var(reused))',
                    "  end",
                    '  set var(a) = model_instance("instance.gltf")',
                    '  set var(b) = model_instance("instance.gltf")',
                    '  set var(stale) = model_instance_morph("instance.gltf", var(old), 0, 1)',
                    '  set var(stale_draw) = model_draw_instance("instance.gltf", var(old), 0, 0, 0, 1, 0, 0, 0)',
                    '  set var(pa) = model_instance_morph("instance.gltf", var(a), 0, 1)',
                    '  set var(pb) = model_instance_morph("instance.gltf", var(b), 0, 0)',
                    '  set var(da) = model_draw_instance("instance.gltf", var(a), -2, 0, 0, 1, 0, 0, 0)',
                    '  set var(db) = model_draw_instance("instance.gltf", var(b), 2, 0, 0, 1, 0, 0, 0)',
                    '  set var(fractional) = model_instance_morph("instance.gltf", var(b), 0.5, 1)',
                    '  set var(negative) = model_instance_morph("instance.gltf", var(b), -1, 1)',
                    '  set var(outside) = model_instance_morph("instance.gltf", var(b), 1, 1)',
                    '  set var(valid_previous) = model_instance_morph("instance.gltf", var(b), 0, 1)',
                    '  say "weights " & var(pb) & "," & model_instance_morph("instance.gltf", var(a), 0, 0) & "," & var(stale) & "," & var(stale_draw)',
                    '  say "indices " & var(fractional) & "," & var(negative) & "," & var(outside) & "," & var(valid_previous)',
                    "end",
                    "",
                )
            )
            result, output = build(root, program, "instance_morph")
            self.assertEqual(result.returncode, 0, result.stderr)
            dumped_triangles = root / "triangles.json"
            run = subprocess.run(
                ["node", str(HOST), "--record", str(output)],
                capture_output=True,
                text=True,
                timeout=60,
                env={
                    **os.environ,
                    "ANVIL_WASM_FRAMES": "1",
                    "ANVIL_WASM_DUMP_TRIANGLES": str(dumped_triangles),
                },
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.strip().splitlines()
            self.assertIn("weights 0,1,0,0", lines)
            self.assertIn("indices 0,0,0,0", lines)
            records = json.loads(lines[-1])
            triangles = [record for record in records if record[0] == "triangles"]
            self.assertEqual(len(triangles), 1)
            self.assertEqual(triangles[0][1], 2)
            vertices = json.loads(dumped_triangles.read_text(encoding="utf-8"))
            self.assertEqual(len(vertices), 2)
            centers = [
                sum((triangle[0], triangle[3], triangle[6])) / 3
                for triangle in vertices
            ]
            self.assertAlmostEqual(centers[1] - centers[0], 130, delta=3, msg=str(centers))

    def test_morphed_model_culls_only_groups_outside_all_supported_poses(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_two_target_morph_model(
                root,
                "groups.gltf",
                group_translations=((0.0, 0.0, 0.0), (200.0, 0.0, 0.0)),
                target_deltas=((-4.0, 0.0, 0.0), (0.0, -4.0, 0.0)),
            )

            def capture(name: str, placement_x: float) -> tuple[list[str], list]:
                program = "\n".join(
                    (
                        "scene 3d",
                        "camera perspective 0 0 12",
                        "fn(draw)",
                        "  set var(culling) = mesh_culling(1)",
                        f'  set var(ok) = model_draw("groups.gltf", {placement_x}, 0, 0, 1, 0, 0, 0)',
                        "  say mesh_drawn()",
                        "  say mesh_culled()",
                        "end",
                        "",
                    )
                )
                result, out = build(root, program, name)
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
                return lines, json.loads(lines[-1])

            partial_lines, partial_records = capture("morph_partial_cull", 0)
            whole_lines, whole_records = capture("morph_whole_cull", 300)

        self.assertEqual(partial_lines[:2], ["1", "0"])
        self.assertEqual(
            [record[1] for record in partial_records if record[0] == "triangles"],
            [1],
        )
        self.assertEqual(whole_lines[:2], ["0", "1"])
        self.assertEqual(
            [record[1] for record in whole_records if record[0] == "triangles"],
            [],
        )

    def test_skinned_model_draw_and_ray_mesh_obey_the_shared_triangle_budget(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_skinned_model(root, "skin.gltf", with_clip=False)
            for draw in ("model_draw", "ray_mesh"):
                program = "\n".join(
                    (
                        "scene 3d",
                        "camera perspective 0 0 12",
                        "set var(ok) = 1",
                        "fn(draw)",
                        "  for local(i) = 1 to 16385",
                        f'    set var(ok) = {draw}("skin.gltf", 0, 0, 0, 1, 0, 0, 0)',
                        "  end",
                        "  say var(ok)",
                        "end",
                        "",
                    )
                )
                result, out = build(root, program, f"skinned_{draw}_budget")
                self.assertEqual(result.returncode, 0, result.stderr)
                run = subprocess.run(
                    ["node", str(HOST), "--record", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env={**os.environ, "ANVIL_WASM_FRAMES": "2"},
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                lines = run.stdout.strip().splitlines()
                self.assertEqual(
                    lines[:2], ["0", "0"],
                    f"the over-budget skinned {draw} is refused per frame",
                )
                records = json.loads(lines[-1])
                triangles = [record for record in records if record[0] == "triangles"]
                self.assertEqual([record[1] for record in triangles], [16384, 16384])

    def test_skinned_model_draw_samples_joint_animation_and_weights(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)

            def capture(
                name: str,
                *,
                animation_time: float | None,
                weights: tuple[float, float] = (1.0, 0.0),
                joints: int = 1,
                draw: str = "model_draw",
            ) -> list:
                model_dir = root / name
                model_dir.mkdir()
                model = f"{name}.gltf"
                asset = f"{name}/{model}"
                write_skinned_model(
                    model_dir, model, weights=weights, with_clip=animation_time is not None,
                    joints=joints,
                )
                statements = [
                    "scene 3d",
                    "camera perspective 0 0 12",
                    "fn(draw)",
                ]
                if animation_time is not None:
                    statements.append(
                        f'  set var(t) = model_animate("{asset}", {animation_time})'
                    )
                statements.extend(
                    (
                        f'  set var(ok) = {draw}("{asset}", 0, 0, 0, 1, 0, 0, 0)',
                        "end",
                        "",
                    )
                )
                result, out = build(root, "\n".join(statements), f"{name}.ANVL")
                self.assertEqual(result.returncode, 0, result.stderr)
                run = subprocess.run(
                    ["node", str(HOST), "--record", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                records = json.loads(run.stdout.strip().splitlines()[-1])
                return next(record for record in records if record[0] == "triangles")

            bind_pose = capture("bind_pose", animation_time=None)
            fully_weighted = capture("full_weight", animation_time=0.5)
            skinned_ray_mesh = capture(
                "ray_mesh", animation_time=0.5, draw="ray_mesh"
            )
            half_weighted = capture(
                "half_weight", animation_time=0.5, weights=(0.5, 0.5), joints=2
            )

        full_shift = fully_weighted[2] - bind_pose[2]
        half_shift = half_weighted[2] - bind_pose[2]
        self.assertEqual(skinned_ray_mesh, fully_weighted)
        self.assertGreater(full_shift, 30, (bind_pose, fully_weighted))
        self.assertAlmostEqual(half_shift / full_shift, 0.5, delta=0.12)

    def test_animated_morphed_ray_mesh_applies_all_pose_controls(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            model = write_animated_morph_glb(root)

            def capture(animation_time: float, morph_weight: float, name: str) -> list:
                program = "\n".join(
                    (
                        "scene 3d",
                        "camera perspective 0 0 12",
                        "fn(draw)",
                        f'  set var(t) = model_animate("{model.name}", {animation_time})',
                        f'  set var(w) = model_morph("{model.name}", 0, {morph_weight})',
                        f'  set var(ok) = ray_mesh("{model.name}", 0, 0, 0, 1, 0, 0, 0)',
                        "end",
                        "",
                    )
                )
                result, out = build(root, program, name)
                self.assertEqual(result.returncode, 0, result.stderr)
                run = subprocess.run(
                    ["node", str(HOST), "--record", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                records = json.loads(run.stdout.strip().splitlines()[-1])
                return next(record for record in records if record[0] == "triangles")

            rest = capture(0.0, 0.0, "animated_morph_rest")
            animated = capture(0.5, 0.0, "animated_morph_node")
            morphed = capture(0.0, 1.0, "animated_morph_target")
            combined = capture(0.5, 1.0, "animated_morph_combined")

        self.assertGreater(animated[2], rest[2] + 20, (rest, animated))
        self.assertGreater(morphed[2], rest[2] + 40, (rest, morphed))
        self.assertGreater(combined[2], animated[2] + 40, (animated, combined))

    def test_ray_mesh_requires_a_3d_scene(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                'scene 2d\nfn(draw)\n'
                '  set var(ok) = ray_mesh("missing.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
                'end\n',
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ray_mesh(...) requires scene 3d", result.stderr)

    def test_morphed_ray_mesh_preserves_group_defaults_and_global_override(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            base = root / "base.gltf"
            write_morph_model(root, base.name, defaults=(0.25,))
            document = json.loads(base.read_text(encoding="utf-8"))
            document["nodes"] = [
                {"mesh": 0, "translation": [-3, 0, 0], "weights": [0.0]},
                {"mesh": 0, "translation": [3, 0, 0], "weights": [1.0]},
            ]
            document["scenes"][0]["nodes"] = [0, 1]
            model = write_morph_glb(root, "groups.glb", document)

            def draw(override: bool, name: str) -> list:
                statements = [
                    "scene 3d",
                    "camera perspective 0 0 12",
                    "fn(draw)",
                ]
                if override:
                    statements.append(
                        f'  set var(prev) = model_morph("{model.name}", 0, 1)'
                    )
                statements.extend(
                    [
                        f'  set var(ok) = ray_mesh("{model.name}", 0, 0, 0, 1, 0, 0, 0)',
                        "end",
                        "",
                    ]
                )
                result, out = build(root, "\n".join(statements), name)
                self.assertEqual(result.returncode, 0, result.stderr)
                run = subprocess.run(
                    ["node", str(HOST), "--record", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                records = json.loads(run.stdout.strip().splitlines()[-1])
                return next(record for record in records if record[0] == "triangles")

            per_group = draw(False, "morph_group_defaults")
            overridden = draw(True, "morph_group_override")

        per_group_width = per_group[3] - per_group[2]
        override_width = overridden[3] - overridden[2]
        self.assertGreater(per_group_width, override_width + 50, (per_group, overridden))
        self.assertGreater(overridden[2], per_group[2] + 50, (per_group, overridden))

    def test_morphed_model_draw_applies_static_defaults_and_override(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_morph_model(root, "morph.gltf")

            def capture(override: bool, name: str) -> list:
                statements = ["scene 3d", "camera perspective 0 0 12", "fn(draw)"]
                if override:
                    statements.append(
                        '  set var(previous) = model_morph("morph.gltf", 0, 1)'
                    )
                statements.extend(
                    [
                        '  set var(ok) = model_draw("morph.gltf", 0, 0, 0, 1, 0, 0, 0)',
                        "end",
                        "",
                    ]
                )
                result, out = build(root, "\n".join(statements), name)
                self.assertEqual(result.returncode, 0, result.stderr)
                run = subprocess.run(
                    ["node", str(HOST), "--record", str(out)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                records = json.loads(run.stdout.strip().splitlines()[-1])
                return next(record for record in records if record[0] == "triangles")

            default = capture(False, "morphed_model_draw_default")
            overridden = capture(True, "morphed_model_draw_override")

        self.assertGreater(overridden[2], default[2] + 50, (default, overridden))

    def test_static_ray_mesh_uses_the_depth_tested_triangle_path(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))

            def capture(call: str, name: str) -> tuple[str, list]:
                program = "\n".join(
                    (
                        "scene 3d",
                        "camera perspective 0 0 6",
                        "clear rgba(10, 12, 18, 255)",
                        "fn(draw)",
                        f"  set var(ok) = {call}",
                        "  say var(ok)",
                        "end",
                        "",
                    )
                )
                result, out = build(root, program, name)
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
                records = json.loads(lines[-1])
                triangles = [record for record in records if record[0] == "triangles"]
                self.assertEqual(len(triangles), 1)
                return lines[0], triangles[0]

            ray_result, ray_triangles = capture(
                'ray_mesh("quad.gltf", 0, 0, 0, 1, 0, 0, 0)', "ray_mesh_static"
            )
            draw_result, draw_triangles = capture(
                'model_draw("quad.gltf", 0, 0, 0, 1, 0, 0, 0)', "model_draw_static"
            )
        self.assertEqual(ray_result, "1")
        self.assertEqual(ray_triangles, draw_triangles)
        self.assertEqual(ray_triangles[1], 2, "a quad submits its two GLTF triangles")

    def test_static_ray_mesh_has_a_per_frame_triangle_budget(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 6",
                    "set var(last) = 1",
                    "fn(draw)",
                    "  for local(i) = 1 to 8193",
                    '    set var(last) = ray_mesh("quad.gltf", 0, 0, 0, 1, 0, 0, 0)',
                    "  end",
                    "  say var(last)",
                    "end",
                    "",
                )
            )
            result, out = build(root, program, "ray_mesh_budget")
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "2"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.strip().splitlines()
            self.assertEqual(lines[:2], ["0", "0"], "the over-budget draw is refused each frame")
            records = json.loads(lines[-1])
            triangles = [record for record in records if record[0] == "triangles"]
            self.assertEqual([record[1] for record in triangles], [16384, 16384])

    def test_model_draw_has_a_shared_per_frame_triangle_budget(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 6",
                    "set var(ok) = 0",
                    "fn(draw)",
                    "  for local(i) = 1 to 8193",
                    '    set var(ok) = model_draw("quad.gltf", 0, 0, 0, 1, 0, 0, 0)',
                    "  end",
                    "  say var(ok)",
                    "end",
                    "",
                )
            )
            result, out = build(root, program, "model_draw_budget")
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "2"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.strip().splitlines()
            self.assertEqual(lines[:2], ["0", "0"], "the over-budget draw is refused per frame")
            records = json.loads(lines[-1])
            triangles = [record for record in records if record[0] == "triangles"]
            self.assertEqual([record[1] for record in triangles], [16384, 16384])

    def test_model_draw_budget_is_shared_with_ray_mesh_and_morph_draw(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            write_morph_model(root, "morph.gltf")
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 6",
                    "set var(a) = 0",
                    "set var(b) = 0",
                    "set var(c) = 0",
                    "fn(draw)",
                    "  for local(i) = 1 to 8192",
                    '    set var(a) = model_draw("quad.gltf", 0, 0, 0, 1, 0, 0, 0)',
                    "  end",
                    '  set var(b) = ray_mesh("quad.gltf", 0, 0, 0, 1, 0, 0, 0)',
                    '  set var(c) = model_draw("morph.gltf", 0, 0, 0, 1, 0, 0, 0)',
                    "  say var(b)",
                    "  say var(c)",
                    "end",
                    "",
                )
            )
            result, out = build(root, program, "shared_model_budget")
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
            self.assertEqual(lines[:2], ["0", "0"], "both ray and morph draw are refused over the budget")
            records = json.loads(lines[-1])
            triangles = [record for record in records if record[0] == "triangles"]
            self.assertEqual(triangles[0][1], 16384, "rejected calls leave the exact submitted cap unchanged")

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
    def test_a_streamed_track_reports_its_length_and_uses_sidecar_url(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            _write_tone(root / "song.wav", frames=1600)
            result, out = build(root, _MUSIC_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            sidecars = list(root.glob("program_assets/music-*.wav"))
            self.assertEqual(len(sidecars), 1)
            self.assertEqual(sidecars[0].read_bytes(), (root / "song.wav").read_bytes())
            generated = (root / ".anvil-cache" / "program.wasm.c").read_text(
                encoding="utf-8"
            )
            self.assertIn('"program_assets/music-', generated)
            self.assertIn(", NULL};", generated)
            self.assertNotIn("anvil_baked_music_pcm", generated)
            page = out.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("new Audio()", page)
            self.assertIn("createMediaElementSource(audio)", page)
            self.assertIn('audio.preload = "metadata"', page)
            self.assertIn("music_stream(urlPointer, duration, volume, loop)", page)
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
            stream_ops = [op for op in ops if op[0] == "music_stream"]
            self.assertEqual(len(stream_ops), 1)
            self.assertEqual(stream_ops[0][1], sidecars[0].relative_to(root).as_posix())
            self.assertAlmostEqual(stream_ops[0][2], 0.2)
            self.assertEqual(stream_ops[0][3:], [1, 1])
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



_TRAP_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "",
        "fn(update)",
        "  if var(armed) = 1",
        "    say chr(300)",
        "  end",
        "end",
        "",
        "fn(draw)",
        "  set var(armed) = 1",
        "  display rect(0, 0, 1, 1) -rgb(0, 0, 0)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmSourceMapTests(unittest.TestCase):
    def test_a_trap_names_the_anvil_function_and_line(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _TRAP_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            mapping = json.loads(out.with_suffix(".map.json").read_text(encoding="utf-8"))
            self.assertEqual(mapping["anvil_update"], {"name": "update", "line": 4})
            self.assertEqual(mapping["anvil_draw"], {"name": "draw", "line": 10})
            page = out.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("anvil_update", page)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "3"},
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(run.stdout, "")
            self.assertIn("Anvil runtime error in fn(update) at line 6", run.stderr)
            self.assertIn("Anvil chr out of range", run.stderr)
            page_run = subprocess.run(
                [
                    "node",
                    str(PAGE_HOST),
                    str(out.with_suffix(".html")),
                    json.dumps([["frame"], ["frame"]]),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertNotEqual(page_run.returncode, 0)
            self.assertIn(
                "Anvil runtime error in fn(update) at line 6", page_run.stderr
            )
            self.assertEqual(page_run.stdout, "")



_PHYSICS_PROGRAM = "\n".join(
    (
        "fn(main)",
        "  set var(b) = body_create(0, 10, 0.5, 1)",
        "  set var(f) = body_create_box(0, 0, 10, 1, 0)",
        "  set var(i) = 0",
        "  set var(c) = 0",
        "  while var(i) < 180",
        "    set var(s) = physics_step()",
        "    set var(c) = compute(var(c) + var(s))",
        "    set var(i) = compute(var(i) + 1)",
        "  end",
        "  say round(body_x(var(b)) * 1000)",
        "  say round(body_y(var(b)) * 1000)",
        "  say round(body_vy(var(b)) * 1000)",
        '  say var(c)',
        "end",
        "call fn(main)",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmPhysicsTests(unittest.TestCase):
    def test_a_body_rests_on_a_static_box_like_the_c_backend(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _PHYSICS_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), ["0", "1000", "0", "99"])

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



@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmSceneModeTests(unittest.TestCase):
    def test_a_3d_scene_tells_the_host_to_use_the_depth_renderer(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _THREE_D_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            page = out.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("scene_mode", page)
            self.assertIn("webgl", page.lower())
            self.assertIn('has("painter")', page)
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            ops = json.loads(run.stdout.strip().splitlines()[-1])
            self.assertIn(["scene_mode", 1], ops)


_MAGNITUDE_PROGRAM = "\n".join(
    (
        "fn(main)",
        '  set var(x) = number("1e3")',
        "  say sin(var(x)) * 1000000",
        "  say cos(var(x)) * 1000000",
        '  set var(x) = number("1e6")',
        "  say sin(var(x)) * 1000000",
        "  say cos(var(x)) * 1000000",
        '  set var(x) = number("1e12")',
        "  say sin(var(x)) * 1000000",
        "  say cos(var(x)) * 1000000",
        '  set var(x) = number("1e15")',
        "  say sin(var(x)) * 1000000",
        "  say cos(var(x)) * 1000000",
        '  set var(x) = number("1e17")',
        "  say sin(var(x)) * 1000000",
        "  say cos(var(x)) * 1000000",
        '  set var(x) = number("1e20")',
        "  say sin(var(x)) * 1000000",
        "  say cos(var(x)) * 1000000",
        '  set var(x) = number("1e300")',
        "  say sin(var(x)) * 1000000",
        "  say cos(var(x)) * 1000000",
        '  set var(x) = number("-1e21")',
        "  say sin(var(x)) * 1000000",
        "  say cos(var(x)) * 1000000",
        "end",
        "call fn(main)",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmAngleMagnitudeTests(unittest.TestCase):
    def test_reduction_holds_past_two_to_the_fifty_second_turns(self) -> None:
        """The old single-round subtraction lost the phase once the turn count
        passed 2^52; the double-double reduction must still agree with libm."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _MAGNITUDE_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            values = run.stdout.replace("\r\n", "\n").splitlines()

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
            self.assertEqual(native.returncode, 0, native.stderr)
            # 1e3 through 1e20 inclusive: six printed pairs, within 1e-8
            # radians of libm (the last printed digit can move by one ulp
            # because the Taylor series rounds differently from libm).
            reference = native.stdout.replace("\r\n", "\n").splitlines()
            for index, printed in enumerate(values[:12]):
                self.assertAlmostEqual(
                    float(printed), float(reference[index]), delta=0.01,
                    msg=f"pair {index // 2} ({'sin' if index % 2 == 0 else 'cos'})",
                )
            # Past the documented limit the phase is not recoverable, so the
            # reduction returns 0: sin reads 0 and cos reads 1.
            self.assertEqual(values[12:], ["0", "1000000", "0", "1000000"])


PAGE_HOST = ROOT / "tools" / "wasm_page.mjs"

_INPUT_PROGRAM = "\n".join(
    (
        "scene 2d",
        "fn(update)",
        "  say held(A)",
        "  say pressed(A)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmFocusReleaseTests(unittest.TestCase):
    def run_page(self, root: pathlib.Path, actions: list) -> list[str]:
        result, out = build(root, _INPUT_PROGRAM)
        self.assertEqual(result.returncode, 0, result.stderr)
        page = out.with_suffix(".html")
        run = subprocess.run(
            ["node", str(PAGE_HOST), str(page), json.dumps(actions)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        return run.stdout.replace("\r\n", "\n").splitlines()

    def test_a_blurred_window_releases_held_keys(self) -> None:
        """A keyup delivered to another window never arrives; the page must
        release what it thinks is held and the next press must count again."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            values = self.run_page(
                pathlib.Path(temp),
                [
                    ["frame"],
                    ["keydown", "KeyA"],
                    ["frame"],
                    ["blur"],
                    ["frame"],
                    ["frame"],
                    ["keydown", "KeyA"],
                    ["frame"],
                ],
            )
        # (held, pressed): untouched, down, released by blur, still released,
        # and a fresh press that proves the release was complete.
        self.assertEqual(values, ["0", "0", "1", "1", "0", "0", "0", "0", "1", "1"])

    def test_a_hidden_tab_releases_held_keys(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            values = self.run_page(
                pathlib.Path(temp),
                [
                    ["keydown", "KeyA"],
                    ["frame"],
                    ["visibility", True],
                    ["frame"],
                    ["visibility", False],
                    ["keydown", "KeyA"],
                    ["frame"],
                ],
            )
        self.assertEqual(values, ["1", "1", "0", "0", "1", "1"])


_FADE_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(alpha) = screen_fade(128)",
        "fn(draw)",
        "  display rect(10, 20, 30, 40) -rgb(255, 0, 0)",
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmScreenFadeTests(unittest.TestCase):
    def test_the_host_dims_the_frame_before_the_present(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _FADE_PROGRAM)
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
            names = [op[0] for op in ops]
            self.assertIn("fade", names)
            fade = ops[names.index("fade")]
            self.assertEqual(fade[1], 128)
            # The overlay has to land above the frame's own draws.
            self.assertGreater(names.index("fade"), names.index("rect"))
            self.assertLess(names.index("fade"), names.index("present"))


_PAGE_SAVE_PROGRAM = "\n".join(
    (
        "fn(update)",
        '  say save_number("hp", 42)',
        '  say load_number("hp")',
        '  say save_text("name", "Ada")',
        '  say load_text("name")',
        '  say save_delete("name")',
        '  say save_exists("name")',
        "end",
        "",
    )
)


@unittest.skipUnless(NEEDS, "clang, wasm-ld and node are required")
class WasmPageSaveTests(unittest.TestCase):
    """The generated page stores saves itself, and must do so with no IndexedDB.

    The Node page harness provides localStorage but no IndexedDB, so this exercises
    the page's fallback store - the path a browser in private mode or a locked-down
    context takes. It also pins the synchronous round trip: Anvil's save API
    cannot await, so the store has to answer from memory.
    """

    def test_the_page_round_trips_saves_without_indexeddb(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, _PAGE_SAVE_PROGRAM)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                [
                    "node",
                    str(PAGE_HOST),
                    str(out.with_suffix(".html")),
                    json.dumps([["frame"]]),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(
            run.stdout.replace("\r\n", "\n").splitlines(),
            ["1", "42", "1", "Ada", "1", "0"],
        )

    def test_indexeddb_migration_copies_adjacent_legacy_slots(self) -> None:
        program = "fn(main)\n" + "".join(
            f'  say load_number("slot{index}")\n' for index in range(3)
        ) + "end\ncall fn(main)\n"
        legacy = {
            "anvil:Anvil_Game/slot0": "14045000000000000",
            "anvil:Anvil_Game/slot1": "14045800000000000",
            "anvil:Anvil_Game/slot2": "14046000000000000",
        }
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, out = build(root, program)
            self.assertEqual(result.returncode, 0, result.stderr)
            run = subprocess.run(
                ["node", str(PAGE_HOST), str(out.with_suffix(".html")), "[[\"frame\"]]"],
                capture_output=True,
                text=True,
                timeout=120,
                env={
                    **os.environ,
                    "ANVIL_TEST_INDEXEDDB": "1",
                    "ANVIL_TEST_LOCAL_STORAGE": json.dumps(legacy),
                },
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        lines = run.stdout.replace("\r\n", "\n").splitlines()
        self.assertEqual(lines[:3], ["42", "43", "44"])
        state = json.loads(lines[-1])
        self.assertEqual(state["backend"], "indexedDB")
        self.assertEqual(state["indexed"], legacy)
        self.assertEqual(state["local"], {})


if __name__ == "__main__":
    unittest.main()
