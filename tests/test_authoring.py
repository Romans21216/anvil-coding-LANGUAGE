"""End-to-end C compiler coverage for the new Anvil authoring syntax."""

from __future__ import annotations

import json
import pathlib
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

from compiler.build import build_c, find_compiler

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


class AuthoringSyntaxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_default_c_build_keeps_generated_source_temporary(self):
        entry = self.root / "temporary-source.ANVL"
        executable = self.root / "temporary-source.exe"
        generated = entry.with_suffix(".generated.c")
        object_dir = self.root / "temporary-source_obj"
        helper = self.root / "temporary-source.build.cmd"
        helper_contents = b"@echo preserve this user file\r\n"
        helper.write_bytes(helper_contents)
        entry.write_text(
            "fn(main)\n  output 23\nend\ncall fn(main)\n", encoding="utf-8"
        )

        build = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--output", str(executable)],
            capture_output=True,
            text=True,
        )

        self.assertEqual(build.returncode, 0, build.stderr)
        self.assertTrue(executable.is_file())
        self.assertFalse(generated.exists())
        self.assertFalse(object_dir.exists())
        self.assertEqual(helper.read_bytes(), helper_contents)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip(), "23")

    def test_missing_c_compiler_only_preserves_requested_generated_source(self):
        entry = self.root / "missing-compiler.ANVL"
        default_c = entry.with_suffix(".generated.c")
        preserved_c = self.root / "preserved.c"
        entry.write_text("fn(main)\n  output 23\nend\ncall fn(main)\n", encoding="utf-8")

        failed_default = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--cc", "anvil-no-such-compiler"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(failed_default.returncode, 2)
        self.assertFalse(default_c.exists())
        self.assertIn("--generated-c PATH or --emit-c PATH", failed_default.stderr)

        failed_preserved = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                str(entry),
                "--cc",
                "anvil-no-such-compiler",
                "--generated-c",
                str(preserved_c),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(failed_preserved.returncode, 2)
        self.assertTrue(preserved_c.is_file())
        self.assertIn("return 23.0;", preserved_c.read_text(encoding="utf-8"))

    def test_console_c_does_not_root_engine_or_optional_runtime_subsystems(self):
        entry = self.root / "console-roots.ANVL"
        generated = self.root / "console-roots.c"
        entry.write_text(
            'name "anvil_net_host()"\n'
            "fn(main)\n output 23\nend\n"
            "fn(unused_network_feature)\n net host(7777)\n output 0\nend\n"
            "fn(unused_physics_feature)\n output body_create(0, 0, 1, 1)\nend\n"
            "call fn(main)\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--emit-c", str(generated)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        c_source = generated.read_text(encoding="utf-8")
        self.assertNotIn("anvil_set_fixed_hz(", c_source)
        self.assertNotIn("anvil_net_close();", c_source)
        self.assertNotIn("ANVIL_RUNTIME_MODULE: networking", c_source)
        self.assertNotIn("ANVIL_RUNTIME_MODULE: physics", c_source)

    def test_c_network_cleanup_root_follows_reachable_network_calls(self):
        entry = self.root / "network-roots.ANVL"
        generated = self.root / "network-roots.c"
        entry.write_text(
            'name "anvil_net_host()"\n'
            "fn(main)\n net host(7777)\n output 0\nend\ncall fn(main)\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--emit-c", str(generated)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        c_source = generated.read_text(encoding="utf-8")
        self.assertIn("anvil_net_host(7777)", c_source)
        self.assertIn("anvil_net_close();", c_source)
        self.assertIn("ANVIL_RUNTIME_MODULE: networking", c_source)

    def test_reachable_physics_builtin_selects_physics_runtime_module(self):
        entry = self.root / "physics-module.ANVL"
        generated = self.root / "physics-module.c"
        entry.write_text(
            "fn(main)\n output body_create(0, 0, 1, 1)\nend\ncall fn(main)\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--emit-c", str(generated)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "ANVIL_RUNTIME_MODULE: physics",
            generated.read_text(encoding="utf-8"),
        )

    def test_reachable_receive_builtin_selects_network_runtime_module(self):
        entry = self.root / "receive-module.ANVL"
        generated = self.root / "receive-module.c"
        entry.write_text(
            "fn(main)\n output receive()\nend\ncall fn(main)\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--emit-c", str(generated)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "ANVIL_RUNTIME_MODULE: networking",
            generated.read_text(encoding="utf-8"),
        )

    def test_network_api_text_does_not_select_network_runtime(self):
        entry = self.root / "network-name.ANVL"
        generated = self.root / "network-name.c"
        entry.write_text(
            'scene 2d\nfn(draw)\n display text("anvil_net_host() body_create()") -l(1, 1)\nend\n',
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--emit-c", str(generated)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        c_source = generated.read_text(encoding="utf-8")
        self.assertIn('"anvil_net_host() body_create()"', c_source)
        self.assertNotIn("anvil_net_close();", c_source)
        self.assertNotIn("ANVIL_RUNTIME_MODULE: networking", c_source)
        self.assertNotIn("ANVIL_RUNTIME_MODULE: physics", c_source)

    def test_c_build_elides_dead_functions_and_keeps_callback_targets(self):
        entry = self.root / "tree-shake.ANVL"
        generated = self.root / "tree-shake.c"
        executable = self.root / "tree-shake.exe"
        entry.write_text(
            "set varl(callback) = fnref(target)\n"
            "fn(main)\n output call fn(used) + call varl(callback)\nend\n"
            "fn(used)\n output call fn(helper)\nend\n"
            "fn(helper)\n output 3\nend\n"
            "fn(target)\n output 4\nend\n"
            "fn(unused)\n output 999\nend\n"
            "call fn(main)\n",
            encoding="utf-8",
        )

        build = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                str(entry),
                "--generated-c",
                str(generated),
                "--output",
                str(executable),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(build.returncode, 0, build.stderr)
        c_source = generated.read_text(encoding="utf-8")
        self.assertIn("anvil_helper", c_source)
        self.assertIn("anvil_target", c_source)
        self.assertIn("anvil__anvil_callable_dispatch_", c_source)
        self.assertNotIn("anvil_unused", c_source)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stdout.strip()), (0, "7"), run.stderr)

    def test_c_build_elides_unreachable_global_storage(self):
        entry = self.root / "storage-tree-shake.ANVL"
        generated = self.root / "storage-tree-shake.c"
        executable = self.root / "storage-tree-shake.exe"
        entry.write_text(
            "array live_array(2)\n"
            "array dead_array(200000)\n"
            "set varl(initialized) = 5\n"
            "fn(main)\n"
            " set array(live_array, 0) = varl(initialized)\n"
            " output array(live_array, 0)\n"
            "end\n"
            "fn(unused)\n"
            " set varl(dead_value) = array(dead_array, 0)\n"
            " output varl(dead_value)\n"
            "end\n"
            "call fn(main)\n",
            encoding="utf-8",
        )

        build = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                str(entry),
                "--generated-c",
                str(generated),
                "--output",
                str(executable),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(build.returncode, 0, build.stderr)
        c_source = generated.read_text(encoding="utf-8")
        self.assertIn("static double anvil_live_array[2];", c_source)
        self.assertIn("static double anvil_initialized;", c_source)
        self.assertNotIn("anvil_dead_array", c_source)
        self.assertNotIn("anvil_dead_value", c_source)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual((run.returncode, run.stdout.strip()), (0, "5"), run.stderr)

    def test_explicit_top_level_entry_omits_unreachable_main(self):
        compiler = find_compiler(None)
        if not compiler:
            self.skipTest("MSVC required")
        entry = self.root / "explicit-entry.ANVL"
        generated = self.root / "explicit-entry.c"
        executable = self.root / "explicit-entry.exe"
        entry.write_text(
            "set varl(result) = 0\n"
            "fn(main)\n set varl(result) = 999\n output 999\nend\n"
            "fn(actual)\n set varl(result) = 7\n output 7\nend\n"
            "call fn(actual)\n",
            encoding="utf-8",
        )

        emit = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                str(entry),
                "--emit-c",
                str(generated),
            ],
            capture_output=True,
            text=True,
        )

        self.assertEqual(emit.returncode, 0, emit.stderr)
        c_source = generated.read_text(encoding="utf-8")
        self.assertIn("anvil_actual", c_source)
        self.assertNotIn("anvil_main", c_source)
        harness = self.root / "entry_harness.c"
        harness.write_text(
            '#define main anvil_generated_main\n'
            '#include "explicit-entry.c"\n'
            '#undef main\n'
            'int main(void) { anvil_generated_main(); return anvil_result == 7.0 ? 0 : 1; }\n',
            encoding="utf-8",
        )
        build_c(compiler[1], harness, executable, release=True)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def build_and_run(self, source: str, name: str = "game"):
        entry = self.root / f"{name}.ANVL"
        generated = self.root / f"{name}.generated.c"
        executable = self.root / f"{name}.exe"
        entry.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--generated-c", str(generated), "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        return entry, generated, executable, run.stdout.strip()

    def test_v2_var_is_local_and_varl_is_global(self):
        _, generated, _, output = self.build_and_run(
            """language version 2
set varl(score) = 5
fn(adjust, value)
  set var(value) = var(value) + 2
  set varl(score) = varl(score) + 1
  output var(value) + varl(score)
end
fn(main)
  set var(score) = 99
  output call fn(adjust, 10) + var(score) + varl(score)
end
call fn(main)
"""
        )
        self.assertEqual(output, "123")
        text = generated.read_text(encoding="utf-8")
        self.assertIn("main__score", text)
        self.assertIn("score", text)

    def test_metadata_round_trips_through_compiled_executable(self):
        entry, _, executable, output = self.build_and_run(
            'name "Anvil 🙂 Project"\nauthor("Romans21216")\nversion("0.2.1")\n'
            "fn(main)\n  output 23\nend\ncall fn(main)\n",
            "metadata",
        )
        self.assertEqual(output, "23")
        inspected = subprocess.run(
            [sys.executable, str(COMPILER), str(executable), "--inspect-metadata"],
            capture_output=True,
        )
        self.assertEqual(inspected.returncode, 0, inspected.stderr.decode("utf-8", "replace"))
        self.assertEqual(
            json.loads(inspected.stdout.decode("utf-8")),
            {"name": "Anvil 🙂 Project", "author": "Romans21216", "version": "0.2.1"},
        )

    def test_metadata_inspection_ignores_same_marker_in_program_text(self):
        entry = self.root / "marker-text.ANVL"
        executable = self.root / "marker-text.exe"
        entry.write_text(
            'scene 2d\nfn(draw)\n  display text("ANVL-METADATA-1") -l(0, 0)\nend\n',
            encoding="utf-8",
        )
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        inspected = subprocess.run(
            [sys.executable, str(COMPILER), str(executable), "--inspect-metadata"],
            capture_output=True,
        )
        self.assertEqual(inspected.returncode, 0, inspected.stderr.decode("utf-8", "replace"))
        self.assertEqual(json.loads(inspected.stdout.decode("utf-8")), {})

    def test_callback_invocation_evaluates_arguments_in_source_order(self):
        _, generated, _, output = self.build_and_run(
            """language version 2
set varl(counter) = 0
fn(next)
  add varl(counter) 1
  output varl(counter)
end
fn(pair, left, right)
  output var(left) * 10 + var(right)
end
fn(main)
  set var(callback) = fnref(pair)
  output call var(callback, call fn(next), call fn(next))
end
call fn(main)
""",
            "callbacks",
        )
        self.assertEqual(output, "12")
        self.assertIn("_anvil_callable_dispatch_1", generated.read_text(encoding="utf-8"))

    def test_global_callback_uses_explicit_varl_storage(self):
        _, _, _, output = self.build_and_run(
            "language version 2\n"
            "fn(double_value, value)\n  output var(value) * 2\nend\n"
            "set varl(callback) = fnref(double_value)\n"
            "fn(main)\n  output call varl(callback, 12)\nend\n"
            "call fn(main)\n",
            "global-callback",
        )
        self.assertEqual(output, "24")

    def test_double_dash_selective_import_and_qualified_callback(self):
        library = self.root / "lib" / "player.ANVL"
        library.parent.mkdir()
        library.write_text(
            "fn(move, distance)\n  output var(distance) + 3\nend\n", encoding="utf-8"
        )
        _, _, _, output = self.build_and_run(
            'include fn(move) -- "lib/player.ANVL"\n'
            "fn(main)\n"
            "  set var(callback) = fnref(move -- player)\n"
            "  output call var(callback, 10)\n"
            "end\ncall fn(main)\n",
            "qualified",
        )
        self.assertEqual(output, "13")

    def test_selective_import_private_zero_arg_callback_expression_v1_var(self):
        library = self.root / "lib" / "player.ANVL"
        library.parent.mkdir()
        library.write_text(
            "fn(target)\n  output 73\nend\n"
            "set var(cb) = fnref(target)\n"
            "fn(move)\n  output 1 + call var(cb) * 2\nend\n",
            encoding="utf-8",
        )
        _, _, _, output = self.build_and_run(
            'include fn(move) -- "lib/player.ANVL"\n'
            "fn(main)\n  output call fn(move -- player)\nend\ncall fn(main)\n",
            "private-callback-v1-var",
        )
        self.assertEqual(output, "147")

    def test_selective_import_private_zero_arg_callback_expression_v1_varl(self):
        library = self.root / "lib" / "player.ANVL"
        library.parent.mkdir()
        library.write_text(
            "fn(target)\n  output 73\nend\n"
            "set varl(cb) = fnref(target)\n"
            "fn(move)\n  output 1 + call varl(cb) * 2\nend\n",
            encoding="utf-8",
        )
        _, _, _, output = self.build_and_run(
            'include fn(move) -- "lib/player.ANVL"\n'
            "fn(main)\n  output call fn(move -- player)\nend\ncall fn(main)\n",
            "private-callback-v1-varl",
        )
        self.assertEqual(output, "147")

    def test_selective_import_private_zero_arg_callback_expression_v2(self):
        library = self.root / "lib" / "player.ANVL"
        library.parent.mkdir()
        library.write_text(
            "language version 2\n"
            "fn(target)\n  output 73\nend\n"
            "set varl(cb) = fnref(target)\n"
            "fn(move)\n  output 1 + call varl(cb) * 2\nend\n",
            encoding="utf-8",
        )
        _, _, _, output = self.build_and_run(
            'include fn(move) -- "lib/player.ANVL"\n'
            "fn(main)\n  output call fn(move -- player)\nend\ncall fn(main)\n",
            "private-callback-v2",
        )
        self.assertEqual(output, "147")

    def assert_callback_temporary_collision_is_rejected(self, source, name):
        entry = self.root / f"{name}.ANVL"
        generated = self.root / f"{name}.generated.c"
        executable = self.root / f"{name}.exe"
        entry.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--generated-c", str(generated), "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0, "colliding compiler temporary must not build")
        self.assertIn("compiler-generated C name", result.stderr)
        self.assertFalse(executable.exists())

    def test_callback_temporary_cannot_capture_explicit_v2_global(self):
        self.assert_callback_temporary_collision_is_rejected(
            "language version 2\n"
            "set varl(main___anvil_callable_dispatch_1_arg_0) = 999\n"
            "fn(identity, x)\n  output var(x)\nend\n"
            "fn(main)\n"
            "  set var(cb) = fnref(identity)\n"
            "  output call var(cb, 5) + varl(main___anvil_callable_dispatch_1_arg_0)\n"
            "end\ncall fn(main)\n",
            "callback-global-shadow-v2",
        )

    def test_callback_temporary_collisions_cover_v1_slots_sites_and_arrays(self):
        cases = (
            (
                "callback-slot-v1",
                "set var(main___anvil_callable_dispatch_1_arg_1) = 999\n"
                "fn(sum, left, right)\n  output var(left) + var(right)\nend\n"
                "fn(main)\n  set var(cb) = fnref(sum)\n"
                "  output call var(cb, 5, 6) + var(main___anvil_callable_dispatch_1_arg_1)\n"
                "end\ncall fn(main)\n",
            ),
            (
                "callback-second-site-array-v2",
                "language version 2\n"
                "array main___anvil_callable_dispatch_2_arg_0(1)\n"
                "fn(target)\n  output 5\nend\n"
                "fn(main)\n  set var(cb) = fnref(target)\n"
                "  output call var(cb)\n"
                "  output call var(cb) + array(main___anvil_callable_dispatch_2_arg_0, 0)\n"
                "end\ncall fn(main)\n",
            ),
        )
        for name, source in cases:
            with self.subTest(name=name):
                self.assert_callback_temporary_collision_is_rejected(source, name)

    def test_top_level_callback_arguments_run_in_source_order(self):
        source = (
            "set var(counter) = 0\n"
            "set var(result) = 0\n"
            "fn(next)\n  add var(counter) 1\n  output var(counter)\nend\n"
            "fn(pair, left, right)\n"
            "  set var(result) = var(left) * 10 + var(right)\n"
            "  output var(result)\nend\n"
            "set var(callback) = fnref(pair)\n"
            "call var(callback, call fn(next), call fn(next))\n"
            "fn(main)\n  output var(result)\nend\ncall fn(main)\n"
        )
        for mode, flags in (("default", []), ("release", ["--release"])):
            with self.subTest(mode=mode):
                entry = self.root / f"top-callback-order-{mode}.ANVL"
                executable = self.root / f"top-callback-order-{mode}.exe"
                entry.write_text(source, encoding="utf-8")
                build = subprocess.run(
                    [sys.executable, str(COMPILER), str(entry), *flags, "--output", str(executable)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(build.returncode, 0, build.stderr)
                run = subprocess.run([str(executable)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), "12")

    def test_top_level_callback_captures_handle_before_side_effecting_arguments(self):
        source = (
            "language version 2\n"
            "set varl(result) = 0\n"
            "fn(pair, left, right)\n"
            "  set varl(result) = var(left) * 10 + var(right)\n"
            "  output varl(result)\nend\n"
            "fn(replacement, left, right)\n"
            "  set varl(result) = var(left) * 100 + var(right)\n"
            "  output varl(result)\nend\n"
            "fn(switch_callback)\n"
            "  set varl(callback) = fnref(replacement)\n"
            "  output 5\nend\n"
            "fn(next)\n  output 6\nend\n"
            "set varl(callback) = fnref(pair)\n"
            "call varl(callback, call fn(switch_callback), call fn(next))\n"
            "fn(main)\n  output varl(result)\nend\ncall fn(main)\n"
        )
        for mode, flags in (("default", []), ("release", ["--release"])):
            with self.subTest(mode=mode):
                entry = self.root / f"top-callback-handle-{mode}.ANVL"
                executable = self.root / f"top-callback-handle-{mode}.exe"
                entry.write_text(source, encoding="utf-8")
                build = subprocess.run(
                    [sys.executable, str(COMPILER), str(entry), *flags, "--output", str(executable)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(build.returncode, 0, build.stderr)
                run = subprocess.run([str(executable)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), "56")

    def test_ordinary_function_expression_arguments_run_left_to_right(self):
        source = (
            "set varl(counter) = 0\n"
            "fn(next)\n  add varl(counter) 1\n  output varl(counter)\nend\n"
            "fn(pair, left, right)\n  output var(left) * 10 + var(right)\nend\n"
            "fn(main)\n"
            "  output call fn(pair, call fn(next), call fn(next))\n"
            "end\ncall fn(main)\n"
        )
        for version, prefix in ((1, ""), (2, "language version 2\n")):
            for mode, flags in (("default", []), ("release", ["--release"])):
                with self.subTest(version=version, mode=mode):
                    entry = self.root / f"function-order-v{version}-{mode}.ANVL"
                    executable = self.root / f"function-order-v{version}-{mode}.exe"
                    entry.write_text(prefix + source, encoding="utf-8")
                    build = subprocess.run(
                        [sys.executable, str(COMPILER), str(entry), *flags, "--output", str(executable)],
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(build.returncode, 0, build.stderr)
                    run = subprocess.run([str(executable)], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(run.stdout.strip(), "12")

    def test_ordinary_function_top_level_arguments_run_left_to_right(self):
        source = (
            "set varl(counter) = 0\n"
            "set varl(result) = 0\n"
            "fn(next)\n  add varl(counter) 1\n  output varl(counter)\nend\n"
            "fn(pair, left, right)\n"
            "  set varl(result) = var(left) * 10 + var(right)\n"
            "  output varl(result)\nend\n"
            "call fn(pair, call fn(next), call fn(next))\n"
            "fn(main)\n  output varl(result)\nend\ncall fn(main)\n"
        )
        for mode, flags in (("default", []), ("release", ["--release"])):
            with self.subTest(mode=mode):
                entry = self.root / f"function-order-top-{mode}.ANVL"
                executable = self.root / f"function-order-top-{mode}.exe"
                entry.write_text(source, encoding="utf-8")
                build = subprocess.run(
                    [sys.executable, str(COMPILER), str(entry), *flags, "--output", str(executable)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(build.returncode, 0, build.stderr)
                run = subprocess.run([str(executable)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout.strip(), "12")

    def test_generated_expression_temporary_collision_is_rejected(self):
        self.assert_callback_temporary_collision_is_rejected(
            "set varl(main___anvil_expr_arg_0) = 999\n"
            "fn(identity, value)\n  output var(value)\nend\n"
            "fn(main)\n  output call fn(identity, 5)\nend\ncall fn(main)\n",
            "ordinary-call-temporary-collision",
        )

    def test_cleared_callback_reports_its_original_call_site(self):
        entry = self.root / "cleared.ANVL"
        executable = self.root / "cleared.exe"
        entry.write_text(
            "language version 2\n"
            "fn(target, value)\n  output var(value) + 1\nend\n"
            "fn(main)\n"
            "  set var(callback) = fnref(target)\n"
            "  set var(callback) = null\n"
            "  output call var(callback, 4)\n"
            "end\ncall fn(main)\n",
            encoding="utf-8",
        )
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 2)
        self.assertIn(f"{entry}:8: function reference is unset or invalid", run.stderr)

    def test_version_one_null_cleanup_remains_a_noop(self):
        _, _, _, output = self.build_and_run(
            "set var(score) = 21\n"
            "set var(score) = null\n"
            "fn(main)\n  set var(score) = null\n  output var(score)\nend\n"
            "call fn(main)\n",
            "legacy-null",
        )
        self.assertEqual(output, "21")

    def test_compact_local_host_uses_loopback_and_receives_udp(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        entry = self.root / "local-network.ANVL"
        executable = self.root / "local-network.exe"
        entry.write_text(
            f'netip("192.0.2.23")\nnethost({port}) --local\n'
            "fn(main)\n"
            "  set local(value) = 0\n"
            "  while local(value) = 0\n"
            "    set local(value) = receive()\n"
            "  end\n"
            "  output local(value)\n"
            "end\ncall fn(main)\n",
            encoding="utf-8",
        )
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(entry), "--release", "--output", str(executable)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        process = subprocess.Popen([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < deadline:
                sender.sendto(struct.pack("<d", 27.0), ("127.0.0.1", port))
                time.sleep(0.01)
            stdout, stderr = process.communicate(timeout=1)
        finally:
            sender.close()
            if process.poll() is None:
                process.terminate()
                process.communicate()
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(stdout.strip(), "27")


if __name__ == "__main__":
    unittest.main()
