import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


class CompilerTests(unittest.TestCase):
    def test_game_source_emits_native_renderer_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            c_file = pathlib.Path(temp) / "world.c"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "first_world.ANVL"), "--emit-c", str(c_file)], check=True, capture_output=True, text=True)
            generated = c_file.read_text(encoding="utf-8")
            self.assertIn("anvil_run(anvil_update, anvil_draw", generated)
            self.assertIn("anvil_cube(", generated)
            self.assertIn("anvil_text_number(", generated)
            self.assertIn("anvil_pressed ( ANVIL_KEY_SPACE )", generated)
            self.assertIn("anvil_trace_sphere(", generated)
            self.assertIn("anvil_camera_fov(70.0)", generated)
            self.assertIn("anvil_camera_control(4.0, 80.0)", generated)

    def test_ray_tracing_batch_flushes_before_hud_drawing(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "trace.ANVL"
            c_file = pathlib.Path(temp) / "trace.c"
            source.write_text(
                "scene 3d\ncamera perspective 0 0 6\ncamera fov(75)\n"
                "camera control(3, 90)\nfn(draw)\n"
                "  display ray_sphere(0, 0, 0, 1) -rgb(180, 90, 230)\n"
                "  display text(\"HUD\") -l(10, 10)\nend\n",
                encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(c_file)], check=True, capture_output=True, text=True)
            generated = c_file.read_text(encoding="utf-8")
            self.assertIn("anvil_camera_fov(75.0)", generated)
            self.assertIn("anvil_camera_control(3.0, 90.0)", generated)
            self.assertIn("anvil_trace_sphere(0.0, 0.0, 0.0, 1.0", generated)
            self.assertLess(generated.index("anvil_trace_sphere("), generated.index("anvil_trace_finish();", generated.index("anvil_trace_sphere(")))

    def test_starter_game_links_native_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / "world.exe"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "first_world.ANVL"), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertGreater(out.stat().st_size, 100_000)

    def test_multiplayer_sample_links_winsock_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / "network.exe"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "network_counter.ANVL"), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertGreater(out.stat().st_size, 100_000)

    def test_multiplayer_client_links_winsock_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / "client.exe"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "network_client.ANVL"), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertGreater(out.stat().st_size, 100_000)

    def test_numeric_program_builds_and_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / "numeric.exe"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "numeric_demo.ANVL"), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip(), "17")

    def test_function_parameters_returns_and_local_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "functions.ANVL"
            out = pathlib.Path(temp) / "functions.exe"
            source.write_text(
                "fn(double, value)\n"
                "  output var(value) * 2\n"
                "end\n"
                "fn(add, left, right)\n"
                "  output call fn(double, var(left)) + var(right)\n"
                "end\n"
                "fn(main)\n"
                "  set local(result) = call fn(add, 4, 5)\n"
                "  add local(result) 0\n"
                "  output local(result)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "13")

    def test_function_call_arity_is_validated(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "bad-arity.ANVL"
            source.write_text("fn(double, value)\n  output var(value) * 2\nend\nfn(main)\n  output call fn(double)\nend\ncall fn(main)\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("bad-arity.ANVL:5:", result.stderr)
            self.assertIn("expects 1 argument(s), got 0", result.stderr)

    def test_local_variables_are_not_visible_outside_their_function(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "local-scope.ANVL"
            source.write_text("fn(first)\n  set local(value) = 2\n  output local(value)\nend\nfn(second)\n  output var(value)\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("local-scope.ANVL:6:", result.stderr)
            self.assertIn("unknown variable 'value'", result.stderr)

    def test_recursive_function_calls_compile_and_run(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "recursive.ANVL"
            out = pathlib.Path(temp) / "recursive.exe"
            source.write_text(
                "fn(factorial, value)\n"
                "  if var(value) <= 1\n"
                "    output 1\n"
                "  else\n"
                "    output var(value) * call fn(factorial, var(value) - 1)\n"
                "  end\n"
                "end\n"
                "fn(main)\n"
                "  output call fn(factorial, 5)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "120")

    def test_network_api_emits_native_udp_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            c_file = pathlib.Path(temp) / "network.c"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "network_counter.ANVL"), "--emit-c", str(c_file)], check=True, capture_output=True, text=True)
            generated = c_file.read_text(encoding="utf-8")
            self.assertIn("anvil_net_host(7777)", generated)
            self.assertIn("anvil_net_send(anvil_local_count)", generated)
            self.assertIn("anvil_net_receive ( )", generated)

    def test_unknown_statement_has_source_location(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "broken.ANVL"
            source.write_text("fn(main)\n  frobnicate\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "broken.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("broken.ANVL:2:", result.stderr)

    def test_unknown_function_expression_has_source_location(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "unknown-call.ANVL"
            source.write_text("fn(main)\n  output call fn(missing)\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unknown-call.ANVL:2:", result.stderr)

    def test_nested_branches_build_and_run(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "nested.ANVL"
            out = pathlib.Path(temp) / "nested.exe"
            source.write_text("fn(main)\n  set var(value) = 5\n  if var(value) > 0\n    if var(value) < 10\n      output var(value)\n    else\n      output 0\n    end\n  else\n    output 0\n  end\nend\ncall fn(main)\n", encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip(), "5")

    def test_expression_precedence_builds_expected_result(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "precedence.ANVL"
            out = pathlib.Path(temp) / "precedence.exe"
            source.write_text("fn(main)\n  output 2 + 3 * 4\nend\ncall fn(main)\n", encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip(), "14")

    def test_remainder_operator_compiles_and_runs_for_numbers(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "remainder.ANVL"
            out = pathlib.Path(temp) / "remainder.exe"
            source.write_text("fn(main)\n  output 7 % 4\nend\ncall fn(main)\n", encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip(), "3")

    def test_string_value_is_rejected_in_numeric_context(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "type-error.ANVL"
            source.write_text('fn(main)\n  output "not a number"\nend\n', encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("type-error.ANVL:2:", result.stderr)
            self.assertIn("expected number, got string", result.stderr)

    def test_malformed_expression_is_rejected_by_anvil_parser(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "malformed.ANVL"
            source.write_text("fn(main)\n  output 1 2\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("malformed.ANVL:2:", result.stderr)
            self.assertIn("unexpected token '2'", result.stderr)

    def test_builtin_arity_is_validated_before_c_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "arity.ANVL"
            source.write_text("fn(main)\n  output sqrt()\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("arity.ANVL:2:", result.stderr)
            self.assertIn("sqrt() expects 1 argument(s), got 0", result.stderr)

    def test_undefined_variable_has_source_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "undefined.ANVL"
            source.write_text("fn(main)\n  output var(missing)\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("undefined.ANVL:2:", result.stderr)
            self.assertIn("unknown variable 'missing'", result.stderr)

    def test_identifiers_that_normalize_to_same_c_name_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "collision.ANVL"
            source.write_text("fn(main)\n  set var(foo-bar) = 1\n  set var(foo_bar) = 2\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("both map to C name 'anvil_foo_bar'", result.stderr)

    def test_seeded_random_and_noise_are_repeatable(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "random.ANVL"
            out = pathlib.Path(temp) / "random.exe"
            source.write_text("fn(main)\n  seed(42)\n  set var(roll) = rnd(1, 100)\n  output var(roll) + noise(0.1, 0.2, 0.3)\nend\ncall fn(main)\n", encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            first = subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip()
            second = subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(first, second)

    def test_project_manifest_resolves_entry_inside_project(self):
        with tempfile.TemporaryDirectory() as temp:
            c_file = pathlib.Path(temp) / "project.c"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "game.ANVLproj"), "--emit-c", str(c_file)], check=True, capture_output=True, text=True)
            generated = c_file.read_text(encoding="utf-8")
            self.assertIn("anvil_run(anvil_update, anvil_draw", generated)
            self.assertIn("anvil_set_fixed_hz(60)", generated)
            self.assertIn('"First World"', generated)

    def test_project_manifest_rejects_invalid_fixed_rate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "main.ANVL").write_text("fn(main)\nend\n", encoding="utf-8")
            project = root / "invalid-rate.ANVLproj"
            project.write_text('name = "invalid"\nentry = "main.ANVL"\n[engine]\nfixed_hz = 0\n', encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(project), "--emit-c", str(root / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("engine.fixed_hz must be an integer from 1 to 240", result.stderr)

    def test_project_manifest_rejects_unimplemented_settings(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "main.ANVL").write_text("fn(main)\nend\n", encoding="utf-8")
            project = root / "unknown-setting.ANVLproj"
            project.write_text('name = "unsupported"\nentry = "main.ANVL"\n[target]\nplatform = "windows"\n', encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(project), "--emit-c", str(root / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported project setting(s): target", result.stderr)

    def test_project_manifest_rejects_entry_outside_project(self):
        with tempfile.TemporaryDirectory() as temp:
            project = pathlib.Path(temp) / "escape.ANVLproj"
            project.write_text('name = "escape"\nentry = "../outside.ANVL"\n', encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(project), "--emit-c", str(pathlib.Path(temp) / "escape.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("entry must resolve inside the project folder", result.stderr)

    def test_malformed_project_manifest_returns_clean_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            project = pathlib.Path(temp) / "malformed.ANVLproj"
            project.write_text('name = "unterminated\nentry = "missing.ANVL"\n', encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(project), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("malformed.ANVLproj", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_network_port_range_is_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "bad-port.ANVL"
            source.write_text("net host(70000)\nfn(main)\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad-port.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("UDP port must be between 1 and 65535", result.stderr)


if __name__ == "__main__":
    unittest.main()

