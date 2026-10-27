import pathlib
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


class CompilerTests(unittest.TestCase):
    def test_language_version_header_and_legacy_default(self):
        with tempfile.TemporaryDirectory() as temp:
            for name, source_text in {
                "explicit-v1": "# Header comments are ignored\n\nlanguage version 1\nfn(main)\n  output 7\nend\ncall fn(main)\n",
                "implicit-v1": "fn(main)\n  output 7\nend\ncall fn(main)\n",
            }.items():
                with self.subTest(name=name):
                    source = pathlib.Path(temp) / f"{name}.ANVL"
                    source.write_text(source_text, encoding="utf-8")
                    result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / f"{name}.c")], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_language_version_errors_are_source_located(self):
        cases = {
            "unsupported": ("language version 2\nfn(main)\nend\n", "unsupported Anvil language version 2; compiler supports version 1", 1),
            "malformed": ("language version next\nfn(main)\nend\n", "language version declaration must use 'language version N'", 1),
            "duplicate": ("language version 1\nlanguage version 1\nfn(main)\nend\n", "language version may only be declared once", 2),
            "late": ("fn(main)\nend\nlanguage version 1\n", "language version declaration must appear before all other source code", 3),
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, (source_text, expected, line) in cases.items():
                with self.subTest(name=name):
                    source = pathlib.Path(temp) / f"{name}.ANVL"
                    source.write_text(source_text, encoding="utf-8")
                    result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / f"{name}.c")], capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"{source}:{line}: {expected}", result.stderr)

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

    def test_ray_backend_builtins_select_and_report_available_backends(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "ray-backend.ANVL"
            out = pathlib.Path(temp) / "ray-backend.exe"
            generated = out.with_suffix(".generated.c")
            source.write_text(
                'fn(main)\n'
                '  if ray_backend_available("bvh") = false\n'
                '    output 0\n'
                '  end\n'
                '  if ray_backend("bvh") = false\n'
                '    output 0\n'
                '  end\n'
                '  if ray_backend_available("dxr") = true\n'
                '    output 0\n'
                '  end\n'
                '  if ray_backend("dxr") = true\n'
                '    output 0\n'
                '  end\n'
                '  if ray_backend_available("embree") = true\n'
                '    output 0\n'
                '  end\n'
                '  if ray_backend("embree") = true\n'
                '    output 0\n'
                '  end\n'
                '  if ray_backend("unknown") = true\n'
                '    output 0\n'
                '  end\n'
                '  if ray_backend_available("unknown") = true\n'
                '    output 0\n'
                '  end\n'
                '  output 1\n'
                'end\n'
                'call fn(main)\n',
                encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(generated), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), "1")
            self.assertIn("ray backend 'dxr' is unavailable", result.stderr)
            self.assertIn("ray backend 'embree' is unavailable", result.stderr)
            self.assertIn("unknown ray backend 'unknown'", result.stderr)
            self.assertIn('anvil_ray_backend_available ( "bvh" )', generated.read_text(encoding="utf-8"))

    def test_ray_backend_builtin_requires_a_string(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "ray-backend-type.ANVL"
            source.write_text("fn(main)\n  output ray_backend(3)\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("expected a string, got a number", result.stderr)

    def test_starter_game_links_native_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / "world.exe"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "first_world.ANVL"), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertGreater(out.stat().st_size, 100_000)

    def test_multiplayer_sample_links_winsock_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / "network.exe"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "network_counter.ANVL"), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertGreater(out.stat().st_size, 100_000)

    def test_multiplayer_client_links_winsock_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / "client.exe"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "network_client.ANVL"), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertGreater(out.stat().st_size, 100_000)

    def test_2d_circle_physics_step_collision_and_stale_handles(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics.ANVL"
            out = pathlib.Path(temp) / "physics.exe"
            source.write_text(
                "fn(main)\n"
                "  set local(first) = body_create(0, 0, 0.5, 1)\n"
                "  set local(second) = body_create(0.95, 0, 0.5, 1)\n"
                "  set local(fixed) = body_create(100, 0, 1, 0)\n"
                "  if body_active(local(first)) != 1\n"
                "    output 0\n"
                "  end\n"
                "  if body_collision(local(first), local(second)) != 1\n"
                "    output 0\n"
                "  end\n"
                "  set local(ok) = body_restitution(local(first), 1)\n"
                "  set local(ok) = body_restitution(local(second), 1)\n"
                "  set local(ok) = body_set_velocity(local(first), 1, 0)\n"
                "  if body_set_velocity(local(fixed), 5, 5) != 0 or body_force(local(fixed), 1, 1) != 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(ok) = physics_gravity(0, 0)\n"
                "  set local(contacts) = physics_step()\n"
                "  if local(contacts) < 1\n"
                "    output 0\n"
                "  end\n"
                "  if body_vx(local(first)) > 0.05 or body_vx(local(second)) < 0.9\n"
                "    output 0\n"
                "  end\n"
                "  if body_x(local(fixed)) != 100 or body_y(local(fixed)) != 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(ok) = body_force(local(first), 0, -10)\n"
                "  set local(ok) = physics_step()\n"
                "  if body_vy(local(first)) >= 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(old) = local(first)\n"
                "  set local(ok) = body_destroy(local(old))\n"
                "  set local(replacement) = body_create(4, 0, 0.5, 1)\n"
                "  if body_active(local(old)) != 0 or body_active(local(replacement)) != 1\n"
                "    output 0\n"
                "  end\n"
                "  if local(old) = local(replacement)\n"
                "    output 0\n"
                "  end\n"
                "  if body_create(0, 0, 0, 1) >= 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(index) = 0\n"
                "  set local(result) = 0\n"
                "  for local(index) = 1 to 125\n"
                "    set local(result) = body_create(local(index) * 3, 0, 0.25, 1)\n"
                "  end\n"
                "  if local(result) < 0\n"
                "    output 0\n"
                "  end\n"
                "  if body_create(0, 0, 1, 1) >= 0\n"
                "    output 0\n"
                "  end\n"
                "  output 1\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "1")

    def test_2d_box_and_mixed_shape_physics_contacts(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics-boxes.ANVL"
            out = pathlib.Path(temp) / "physics-boxes.exe"
            source.write_text(
                "fn(main)\n"
                "  set local(ok) = physics_gravity(0, 0)\n"
                "  set local(floor) = body_create_box(0, -1, 4, 2, 0)\n"
                "  set local(ball) = body_create(0, 0.4, 0.5, 1)\n"
                "  set local(left_box) = body_create_box(10, 0, 2, 2, 0)\n"
                "  set local(right_box) = body_create_box(11.75, 0, 2, 2, 1)\n"
                "  set local(container) = body_create_box(20, 0, 2, 2, 0)\n"
                "  set local(embedded) = body_create(20, 0, 0.25, 1)\n"
                "  if body_collision(local(floor), local(ball)) != 1\n"
                "    output 0\n"
                "  end\n"
                "  if body_collision(local(left_box), local(right_box)) != 1\n"
                "    output 0\n"
                "  end\n"
                "  if body_collision(local(container), local(embedded)) != 1\n"
                "    output 0\n"
                "  end\n"
                "  if body_create_box(0, 0, -1, 2, 1) >= 0\n"
                "    output 0\n"
                "  end\n"
                "  if physics_step() < 3\n"
                "    output 0\n"
                "  end\n"
                "  if body_y(local(ball)) < 0.45\n"
                "    output 0\n"
                "  end\n"
                "  if body_x(local(right_box)) < 11.9\n"
                "    output 0\n"
                "  end\n"
                "  if abs(body_x(local(embedded)) - 20) < 1.2\n"
                "    output 0\n"
                "  end\n"
                "  output 1\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "1")

    def test_box_physics_builtin_arity_is_validated(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics-box-arity.ANVL"
            source.write_text("fn(main)\n  output body_create_box(0, 0, 2, 2)\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("body_create_box() expects 5 argument(s), got 4", result.stderr)

    def test_physics_friction_slows_sliding_body_and_validates_values(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics-friction.ANVL"
            out = pathlib.Path(temp) / "physics-friction.exe"
            source.write_text(
                "fn(main)\n"
                "  set local(ok) = physics_gravity(0, -9.81)\n"
                "  set local(floor) = body_create_box(0, 0, 100, 2, 0)\n"
                "  set local(ball) = body_create(0, 1.5, 0.5, 1)\n"
                "  if body_friction(local(floor), 1) != 1 or body_friction(local(ball), 1) != 1\n"
                "    output 0\n"
                "  end\n"
                "  if body_friction(local(ball), -0.01) != 0 or body_friction(local(ball), 1.01) != 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(ok) = body_set_velocity(local(ball), 5, 0)\n"
                "  set local(step) = 0\n"
                "  while local(step) < 180\n"
                "    set local(ok) = physics_step()\n"
                "    set local(step) = local(step) + 1\n"
                "  end\n"
                "  if abs(body_vx(local(ball))) > 0.000001\n"
                "    output 0\n"
                "  end\n"
                "  output 1\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "1")

    def test_physics_friction_zero_and_geometric_mean(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics-friction-edges.ANVL"
            out = pathlib.Path(temp) / "physics-friction-edges.exe"
            source.write_text(
                "fn(main)\n"
                "  set local(ok) = physics_gravity(0, -9.81)\n"
                "  set local(floor_zero) = body_create_box(0, 0, 10, 2, 0)\n"
                "  set local(ball_zero) = body_create(0, 1.5, 0.5, 1)\n"
                "  set local(floor_mix) = body_create_box(100, 0, 10, 2, 0)\n"
                "  set local(ball_mix) = body_create(100, 1.5, 0.5, 1)\n"
                "  set local(ok) = body_friction(local(floor_zero), 1)\n"
                "  set local(ok) = body_friction(local(ball_zero), 0)\n"
                "  set local(ok) = body_friction(local(floor_mix), 1)\n"
                "  set local(ok) = body_friction(local(ball_mix), 0.25)\n"
                "  set local(ok) = body_set_velocity(local(ball_zero), 5, 0)\n"
                "  set local(ok) = body_set_velocity(local(ball_mix), 0.12, 0)\n"
                "  set local(ok) = physics_step()\n"
                "  if abs(body_vx(local(ball_zero)) - 5) > 0.000001\n"
                "    output 0\n"
                "  end\n"
                "  if abs(body_vx(local(ball_mix)) - 0.03825) > 0.001\n"
                "    output 0\n"
                "  end\n"
                "  output 1\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "1")

    def test_physics_body_capacity_can_grow_and_safely_shrink(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics-capacity.ANVL"
            out = pathlib.Path(temp) / "physics-capacity.exe"
            source.write_text(
                "fn(main)\n"
                "  if physics_capacity(4) != 4\n"
                "    output 0\n"
                "  end\n"
                "  if physics_capacity(0) >= 0 or physics_capacity(1.5) >= 0 or physics_capacity(129) >= 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(a) = body_create(-20, 0, 0.5, 1)\n"
                "  set local(b) = body_create(-10, 0, 0.5, 1)\n"
                "  set local(c) = body_create(10, 0, 0.5, 1)\n"
                "  set local(d) = body_create(20, 0, 0.5, 1)\n"
                "  if body_create(30, 0, 0.5, 1) >= 0 or physics_capacity(3) >= 0\n"
                "    output 0\n"
                "  end\n"
                "  if physics_capacity(5) != 5\n"
                "    output 0\n"
                "  end\n"
                "  set local(e) = body_create(30, 0, 0.5, 1)\n"
                "  if local(e) < 0 or physics_capacity(4) >= 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(ok) = body_destroy(local(d))\n"
                "  set local(ok) = body_destroy(local(e))\n"
                "  if physics_capacity(3) != 3\n"
                "    output 0\n"
                "  end\n"
                "  if body_create(30, 0, 0.5, 1) >= 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(ok) = body_destroy(local(c))\n"
                "  if body_create(30, 0, 0.5, 1) < 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(ok) = physics_gravity(0, 0)\n"
                "  set local(ok) = body_set_velocity(local(a), 6, 0)\n"
                "  set local(ok) = physics_step()\n"
                "  if body_x(local(a)) <= -19.95\n"
                "    output 0\n"
                "  end\n"
                "  output 1\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "1")

    def test_physics_capacity_builtin_arity_is_validated(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics-capacity-arity.ANVL"
            source.write_text("fn(main)\n  output physics_capacity()\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("physics_capacity() expects 1 argument(s), got 0", result.stderr)

    def test_physics_builtin_arity_is_validated_before_c_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics-arity.ANVL"
            source.write_text("fn(main)\n  output body_create(0, 0, 1)\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("physics-arity.ANVL:2:", result.stderr)
            self.assertIn("body_create() expects 4 argument(s), got 3", result.stderr)

    def test_physics_contact_timing_bounds_and_repeatability(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "physics-bounds.ANVL"
            out = pathlib.Path(temp) / "physics-bounds.exe"
            source.write_text(
                "fn(main)\n"
                "  set local(ok) = physics_gravity(0, 0)\n"
                "  set local(a) = body_create(0, 0, 1, 1)\n"
                "  set local(b) = body_create(2.01, 0, 1, 1)\n"
                "  set local(ok) = body_restitution(local(a), 1)\n"
                "  set local(ok) = body_restitution(local(b), 1)\n"
                "  set local(ok) = body_set_velocity(local(a), 1, 0)\n"
                "  set local(ok) = body_set_velocity(local(b), -1, 0)\n"
                "  if physics_step() != 0\n"
                "    output 0\n"
                "  end\n"
                "  if body_vx(local(a)) >= 0 or body_vx(local(b)) <= 0\n"
                "    output 0\n"
                "  end\n"
                "  set local(heavy) = body_create(-500000, 0, 1000000, 1000000000)\n"
                "  set local(light) = body_create(500000, 0, 1000000, 0.000001)\n"
                "  set local(ok) = body_restitution(local(heavy), 1)\n"
                "  set local(ok) = body_restitution(local(light), 1)\n"
                "  set local(ok) = body_set_velocity(local(heavy), 1000000, 0)\n"
                "  set local(ok) = body_set_velocity(local(light), -1000000, 0)\n"
                "  set local(edge_a) = body_create(999999999, 0, 1000000, 1)\n"
                "  set local(edge_b) = body_create(999999999, 0, 1000000, 1)\n"
                "  set local(ok) = physics_step()\n"
                "  if body_vx(local(light)) > 1000000 or body_vx(local(light)) < -1000000\n"
                "    output 0\n"
                "  end\n"
                "  if body_x(local(edge_b)) > 1000000000\n"
                "    output 0\n"
                "  end\n"
                "  output body_vx(local(light)) + body_x(local(edge_b))\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            first = subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip()
            second = subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip()
            self.assertEqual(first, second)

    def test_numeric_program_builds_and_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            out = pathlib.Path(temp) / "numeric.exe"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "numeric_demo.ANVL"), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip(), "17")

    def test_division_by_zero_reports_source_location(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "divide-zero.ANVL"
            out = pathlib.Path(temp) / "divide-zero.exe"
            source.write_text(
                "fn(main)\n"
                "  output 1 / (3 - 3)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn(f"{source}:2: division by zero", result.stderr)

    def test_regular_division_remains_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "division.ANVL"
            out = pathlib.Path(temp) / "division.exe"
            source.write_text(
                "fn(main)\n"
                "  output 7 / 2\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "3.5")

    def test_non_finite_numeric_results_report_source_location(self):
        cases = {
            "overflow": "1e308 * 1e308",
            "comparison-overflow": "1e308 * 1e308 > 0",
            "invalid-math": "sqrt(-1)",
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, expression in cases.items():
                with self.subTest(name=name):
                    source = pathlib.Path(temp) / f"{name}.ANVIL"
                    out = pathlib.Path(temp) / f"{name}.exe"
                    source.write_text(
                        f"fn(main)\n  output {expression}\nend\ncall fn(main)\n",
                        encoding="utf-8",
                    )
                    subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
                    result = subprocess.run([str(out)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn(f"{source}:2: numeric overflow or non-finite result", result.stderr)

    def test_accumulation_and_for_step_overflow_report_source_location(self):
        cases = {
            "local-add": "  set local(value) = 1e308\n  add local(value) 1e308\n  output local(value)\n",
            "local-sub": "  set local(value) = -1e308\n  sub local(value) 1e308\n  output local(value)\n",
            "for-step": "  set local(counter) = 0\n  for local(index) = 1e308 to 1e308 step 1e308\n    add local(counter) 1\n  end\n  output local(counter)\n",
        }
        with tempfile.TemporaryDirectory() as temp:
            for name, body in cases.items():
                with self.subTest(name=name):
                    source = pathlib.Path(temp) / f"{name}.ANVIL"
                    out = pathlib.Path(temp) / f"{name}.exe"
                    source.write_text(f"fn(main)\n{body}end\ncall fn(main)\n", encoding="utf-8")
                    subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
                    result = subprocess.run([str(out)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn("numeric overflow or non-finite result", result.stderr)

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
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
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
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "120")

    def test_while_loop_runs_and_updates_locals(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "while.ANVL"
            out = pathlib.Path(temp) / "while.exe"
            source.write_text(
                "fn(sum_to, limit)\n"
                "  set local(index) = 1\n"
                "  set local(total) = 0\n"
                "  while local(index) <= var(limit)\n"
                "    add local(total) local(index)\n"
                "    add local(index) 1\n"
                "  end\n"
                "  output local(total)\n"
                "end\n"
                "fn(main)\n"
                "  output call fn(sum_to, 5)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "15")

    def test_while_loop_requires_condition(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "bad.ANVL"
            source.write_text("fn(main)\n  while\n  end\nend\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("while needs a condition", result.stderr)

    def test_for_loop_ascending_descending_steps_and_nesting(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "for.ANVL"
            out = pathlib.Path(temp) / "for.exe"
            source.write_text(
                "fn(sum_range, first, last, step)\n"
                "  set local(total) = 0\n"
                "  for local(index) = var(first) to var(last) step var(step)\n"
                "    add local(total) local(index)\n"
                "  end\n"
                "  output local(total)\n"
                "end\n"
                "fn(nested)\n"
                "  set local(total) = 0\n"
                "  for local(row) = 1 to 2\n"
                "    for local(column) = 1 to 3\n"
                "      add local(total) 1\n"
                "    end\n"
                "  end\n"
                "  output local(total)\n"
                "end\n"
                "fn(main)\n"
                "  output call fn(sum_range, 1, 5, 2) + call fn(sum_range, 5, 1, -2) + call fn(sum_range, 1, 5, 0) + call fn(nested)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "24")

    def test_for_loop_evaluates_bounds_and_step_once(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "for_calls.ANVL"
            out = pathlib.Path(temp) / "for_calls.exe"
            source.write_text(
                "set var(calls) = 0\n"
                "fn(next-bound)\n"
                "  add var(calls) 1\n"
                "  output 2\n"
                "end\n"
                "fn(main)\n"
                "  set local(total) = 0\n"
                "  for local(index) = call fn(next-bound) to call fn(next-bound) step call fn(next-bound)\n"
                "    add local(total) local(index)\n"
                "  end\n"
                "  output var(calls)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "3")

    def test_nested_for_loop_rejects_reused_control_variable(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "bad_nested_for.ANVL"
            source.write_text(
                "fn(main)\n"
                "  for local(index) = 1 to 2\n"
                "    for local(index) = 1 to 3\n"
                "    end\n"
                "  end\n"
                "end\n",
                encoding="utf-8",
            )
            result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("nested for loops must use different local variables", result.stderr)

    def test_fixed_numeric_arrays_support_dynamic_reads_and_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "arrays.ANVL"
            out = pathlib.Path(temp) / "arrays.exe"
            source.write_text(
                "array values(4)\n"
                "fn(double, value)\n"
                "  output var(value) * 2\n"
                "end\n"
                "fn(main)\n"
                "  for local(index) = 0 to 3\n"
                "    set array(values, local(index)) = call fn(double, local(index))\n"
                "  end\n"
                "  output array(values, 2) + array(values, 3)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "10")

    def test_array_index_is_checked_at_runtime(self):
        for index in ("-1", "2", "0.5"):
            with self.subTest(index=index), tempfile.TemporaryDirectory() as temp:
                source = pathlib.Path(temp) / "array-bounds.ANVL"
                out = pathlib.Path(temp) / "array-bounds.exe"
                source.write_text(
                    "array values(2)\n"
                    "fn(main)\n"
                    f"  output array(values, {index})\n"
                    "end\n"
                    "call fn(main)\n",
                    encoding="utf-8",
                )
                subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
                result = subprocess.run([str(out)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn("array index", result.stderr)
                self.assertIn("array-bounds.ANVL:3:", result.stderr)

    def test_array_index_side_effect_evaluates_once(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "array-once.ANVL"
            out = pathlib.Path(temp) / "array-once.exe"
            source.write_text(
                "array values(3)\n"
                "set var(calls) = 0\n"
                "fn(next-index)\n"
                "  add var(calls) 1\n"
                "  output 1\n"
                "end\n"
                "fn(next-value)\n"
                "  add var(calls) 1\n"
                "  output 7\n"
                "end\n"
                "fn(main)\n"
                "  set array(values, call fn(next-index)) = call fn(next-value)\n"
                "  output array(values, 1) + var(calls)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "9")

    def test_array_declarations_and_references_are_validated(self):
        cases = (
            ("array values(0)\nfn(main)\n output 0\nend\n", "array size must be"),
            ("array values(2)\narray values(3)\nfn(main)\n output 0\nend\n", "duplicate array 'values'"),
            ("array values(1048577)\nfn(main)\n output 0\nend\n", "array size must be"),
            ("fn(main)\n array values(8193)\n output 0\nend\n", "local arrays in a function may contain at most 8192 elements total"),
            ("fn(main)\n output array(missing, 0)\nend\n", "unknown array 'missing'"),
            ("if 1\n array values(2)\nend\nfn(main)\n output 0\nend\n", "global arrays must be declared at top level"),
            ("array values(2)\nfn(values)\n output 0\nend\n", "conflicts with another declaration"),
            ("fn(array_get)\n output 0\nend\n", "conflicts with a reserved runtime name"),
        )
        for program, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic), tempfile.TemporaryDirectory() as temp:
                source = pathlib.Path(temp) / "bad-array.ANVL"
                source.write_text(program, encoding="utf-8")
                result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)

    def test_function_local_arrays_are_zeroed_and_isolated_per_call(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "local-arrays.ANVL"
            out = pathlib.Path(temp) / "local-arrays.exe"
            source.write_text(
                "set var(return_value) = 7\n"
                "fn(sum-offset, offset)\n"
                "  array values(3)\n"
                "  for local(index) = 0 to 2\n"
                "    set array(values, local(index)) = var(offset) + local(index)\n"
                "  end\n"
                "  output array(values, 0) + array(values, 1) + array(values, 2)\n"
                "end\n"
                "fn(zero-local-array)\n"
                "  array empty(2)\n"
                "  output array(empty, 0) + array(empty, 1)\n"
                "end\n"
                "fn(recursive-sum, count)\n"
                "  array frame(1)\n"
                "  set array(frame, 0) = var(count)\n"
                "  if var(count) <= 1\n"
                "    output array(frame, 0)\n"
                "  else\n"
                "    output array(frame, 0) + call fn(recursive-sum, var(count) - 1)\n"
                "  end\n"
                "end\n"
                "fn(discard-array)\n"
                "  array spare(8192)\n"
                "  set array(spare, 0) = 1\n"
                "end\n"
                "fn(main)\n"
                "  set local(repeated) = 0\n"
                "  for local(pass) = 1 to 300\n"
                "    call fn(discard-array)\n"
                "    add local(repeated) call fn(sum-offset, 0)\n"
                "  end\n"
                "  output call fn(zero-local-array) + call fn(sum-offset, 2) + call fn(sum-offset, 5) + call fn(recursive-sum, 3) + local(repeated) + var(return_value)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            generated = pathlib.Path(temp) / "local-arrays.generated.c"
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(generated), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "940")
            generated_c = generated.read_text(encoding="utf-8")
            self.assertIn("double *anvil_sum_offset__values = anvil_local_array_alloc(3,", generated_c)
            self.assertIn("double *anvil_recursive_sum__frame = anvil_local_array_alloc(1,", generated_c)
            self.assertIn("double *anvil_zero_local_array__empty = anvil_local_array_alloc(2,", generated_c)
            self.assertIn("calloc(count, sizeof(double))", generated_c)
            self.assertIn("anvil_local_array_free(anvil_sum_offset__values, 3);", generated_c)

    def test_recursive_local_array_budget_fails_with_source_diagnostic(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "local-array-budget.ANVL"
            out = pathlib.Path(temp) / "local-array-budget.exe"
            source.write_text(
                "fn(recurse, count)\n"
                "  array frame(8192)\n"
                "  if var(count) > 0\n"
                "    output 1 + call fn(recurse, var(count) - 1)\n"
                "  else\n"
                "    output 0\n"
                "  end\n"
                "end\n"
                "fn(main)\n"
                "  output call fn(recurse, 1000)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(pathlib.Path(temp) / "local-array-budget.generated.c"), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("active local arrays exceed the 16 MiB Anvil memory limit", result.stderr)
            self.assertIn("local-array-budget.ANVL:2:", result.stderr)

    def test_function_local_array_bounds_are_checked_at_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "local-array-bounds.ANVL"
            out = pathlib.Path(temp) / "local-array-bounds.exe"
            source.write_text(
                "fn(main)\n"
                "  array values(1)\n"
                "  output array(values, 1)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(pathlib.Path(temp) / "local-array-bounds.generated.c"), "--output", str(out)], check=True, capture_output=True, text=True)
            result = subprocess.run([str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("array index", result.stderr)
            self.assertIn("local-array-bounds.ANVL:3:", result.stderr)

    def test_local_array_references_are_function_scoped_and_name_checked(self):
        cases = (
            ("fn(first)\n array hidden(1)\n set array(hidden, 0) = 3\n output 0\nend\nfn(second)\n output array(hidden, 0)\nend\n", "unknown array 'hidden'"),
            ("fn(main)\n array items(2)\n set local(items) = 1\n output array(items, 0)\nend\n", "conflicts with a local variable or parameter"),
            ("fn(main, items)\n array items(2)\n output array(items, 0)\nend\n", "conflicts with a local variable or parameter"),
        )
        for program, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic), tempfile.TemporaryDirectory() as temp:
                source = pathlib.Path(temp) / "bad-local-array.ANVL"
                source.write_text(program, encoding="utf-8")
                result = subprocess.run([sys.executable, str(COMPILER), str(source), "--emit-c", str(pathlib.Path(temp) / "bad.c")], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, result.stderr)

    def test_network_api_emits_native_udp_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            c_file = pathlib.Path(temp) / "network.c"
            subprocess.run([sys.executable, str(COMPILER), str(ROOT / "examples" / "network_counter.ANVL"), "--emit-c", str(c_file)], check=True, capture_output=True, text=True)
            generated = c_file.read_text(encoding="utf-8")
            self.assertIn("anvil_net_host(7777)", generated)
            self.assertIn("anvil_net_send(anvil_local_count)", generated)
            self.assertIn("anvil_net_receive ( )", generated)

    def test_udp_nan_receive_reports_source_location(self):
        with tempfile.TemporaryDirectory() as temp:
            port_probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]
            port_probe.close()

            source = pathlib.Path(temp) / "non-finite-network.ANVL"
            out = pathlib.Path(temp) / "non-finite-network.exe"
            source.write_text(
                f"net host({port})\n"
                "fn(main)\n"
                "  while 1\n"
                "    set local(value) = receive()\n"
                "  end\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)

            process = subprocess.Popen([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                payload = struct.pack("<d", float("nan"))
                deadline = time.monotonic() + 5
                while process.poll() is None and time.monotonic() < deadline:
                    sender.sendto(payload, ("127.0.0.1", port))
                    time.sleep(0.01)
                stdout, stderr = process.communicate(timeout=1)
            finally:
                sender.close()
                if process.poll() is None:
                    process.terminate()
                    process.communicate()

            self.assertEqual(process.returncode, 2, stdout + stderr)
            self.assertIn(f"{source}:4: numeric overflow or non-finite result", stderr)

    def test_udp_finite_receive_and_missing_socket_remain_supported(self):
        with tempfile.TemporaryDirectory() as temp:
            no_socket_source = pathlib.Path(temp) / "no-network.ANVL"
            no_socket_out = pathlib.Path(temp) / "no-network.exe"
            no_socket_source.write_text("fn(main)\n  output receive()\nend\ncall fn(main)\n", encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(no_socket_source), "--release", "--output", str(no_socket_out)], check=True, capture_output=True, text=True)
            no_socket_result = subprocess.run([str(no_socket_out)], check=True, capture_output=True, text=True)
            self.assertEqual(no_socket_result.stdout.strip(), "0")

            port_probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            port_probe.bind(("127.0.0.1", 0))
            port = port_probe.getsockname()[1]
            port_probe.close()
            source = pathlib.Path(temp) / "finite-network.ANVL"
            out = pathlib.Path(temp) / "finite-network.exe"
            source.write_text(
                f"net host({port})\n"
                "fn(main)\n"
                "  set local(value) = 0\n"
                "  while local(value) = 0\n"
                "    set local(value) = receive()\n"
                "  end\n"
                "  output local(value)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--output", str(out)], check=True, capture_output=True, text=True)
            process = subprocess.Popen([str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                payload = struct.pack("<d", 42.5)
                deadline = time.monotonic() + 5
                while process.poll() is None and time.monotonic() < deadline:
                    sender.sendto(payload, ("127.0.0.1", port))
                    time.sleep(0.01)
                stdout, stderr = process.communicate(timeout=1)
            finally:
                sender.close()
                if process.poll() is None:
                    process.terminate()
                    process.communicate()
            self.assertEqual(process.returncode, 0, stdout + stderr)
            self.assertEqual(stdout.strip(), "42.5")

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
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip(), "5")

    def test_expression_precedence_builds_expected_result(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "precedence.ANVL"
            out = pathlib.Path(temp) / "precedence.exe"
            source.write_text("fn(main)\n  output 2 + 3 * 4\nend\ncall fn(main)\n", encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip(), "14")

    def test_and_or_short_circuit_side_effecting_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "short-circuit.ANVL"
            out = pathlib.Path(temp) / "short-circuit.exe"
            source.write_text(
                "set var(calls) = 0\n"
                "fn(mark)\n"
                "  add var(calls) 1\n"
                "  output 1\n"
                "end\n"
                "fn(main)\n"
                "  set local(a) = false and call fn(mark)\n"
                "  set local(b) = true or call fn(mark)\n"
                "  set local(c) = true and call fn(mark)\n"
                "  set local(d) = false or call fn(mark)\n"
                "  output var(calls)\n"
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
            self.assertEqual(subprocess.run([str(out)], check=True, capture_output=True, text=True).stdout.strip(), "2")

    def test_remainder_operator_compiles_and_runs_for_numbers(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "remainder.ANVL"
            out = pathlib.Path(temp) / "remainder.exe"
            source.write_text("fn(main)\n  output 7 % 4\nend\ncall fn(main)\n", encoding="utf-8")
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
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
            subprocess.run([sys.executable, str(COMPILER), str(source), "--release", "--generated-c", str(out.with_suffix(".generated.c")), "--output", str(out)], check=True, capture_output=True, text=True)
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

