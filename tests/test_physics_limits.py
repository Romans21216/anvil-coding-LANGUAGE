"""Measured limits of the fixed-step 2D physics runtime.

Part 8 asks for physics limits to be specified *and tested*: tunneling, stacks,
high speed and long replays. These tests pin the behaviour that
`docs/ENGINE.md` promises, so a solver change that quietly makes a fast body
solid or a stack unstable fails here.
"""

import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"


def build_and_run(source: str, temporary: str) -> list[str]:
    path = pathlib.Path(temporary) / "probe.ANVL"
    path.write_text(source, encoding="utf-8")
    executable = path.with_suffix(".exe")
    build = subprocess.run(
        [sys.executable, str(COMPILER), str(path), "-o", str(executable)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run(
        [str(executable)], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout.replace("\r\n", "\n").splitlines()


class PhysicsLimitTests(unittest.TestCase):
    def test_capacity_limit_rejects_the_body_after_the_capacity(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            lines = build_and_run(
                "fn(main)\n"
                "  set local(cap) = physics_capacity(4)\n"
                "  set local(a) = body_create(0, 0, 1, 1)\n"
                "  set local(b) = body_create(3, 0, 1, 1)\n"
                "  set local(c) = body_create(6, 0, 1, 1)\n"
                "  set local(d) = body_create(9, 0, 1, 1)\n"
                "  set local(e) = body_create(12, 0, 1, 1)\n"
                "  print \"cap=\" + local(cap)\n"
                "  print \"last=\" + local(d) + \" over=\" + local(e)\n"
                "end\n",
                temporary,
            )
        self.assertEqual(lines[0], "cap=4")
        # The fourth body fits; the fifth is refused rather than silently
        # evicting a live body.
        self.assertIn("over=-1", lines[1])
        self.assertNotIn("last=-1", lines[1])

    def test_a_slow_body_is_stopped_by_a_static_wall(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            lines = build_and_run(
                "fn(main)\n"
                "  set local(ok) = physics_gravity(0, 0)\n"
                "  set local(wall) = body_create(0, 0, 1, 0)\n"
                "  set local(b) = body_create(-3, 0, 0.5, 1)\n"
                "  set local(ok) = body_set_velocity(local(b), 120, 0)\n"
                "  for local(i) = 1 to 200\n"
                "    set local(c) = physics_step()\n"
                "  end\n"
                "  print \"x=\" + body_x(local(b)) + \" vx=\" + body_vx(local(b))\n"
                "end\n",
                temporary,
            )
        x_text, vx_text = lines[0].split()
        x = float(x_text.split("=")[1])
        vx = float(vx_text.split("=")[1])
        # Contact is at x = -(1 + 0.5); the body stops there instead of passing
        # through the static wall.
        self.assertLess(x, -1.4)
        self.assertGreater(x, -1.6)
        self.assertEqual(vx, 0.0)

    def test_a_fast_body_tunnels_through_a_thin_wall(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            lines = build_and_run(
                "fn(main)\n"
                "  set local(ok) = physics_gravity(0, 0)\n"
                "  set local(wall) = body_create(0, 0, 1, 0)\n"
                "  set local(b) = body_create(-3, 0, 0.5, 1)\n"
                # 4 units per fixed step clears the 3-unit contact window.
                "  set local(ok) = body_set_velocity(local(b), 240, 0)\n"
                "  for local(i) = 1 to 200\n"
                "    set local(c) = physics_step()\n"
                "  end\n"
                "  print \"x=\" + body_x(local(b))\n"
                "end\n",
                temporary,
            )
        x = float(lines[0].split("=")[1])
        # Documented limitation: there is no continuous collision detection, so
        # a body whose per-step travel exceeds the contact window passes through.
        self.assertGreater(x, 100.0)

    def test_identical_runs_produce_identical_positions(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            path = pathlib.Path(temporary) / "replay.ANVL"
            path.write_text(
                "fn(main)\n"
                "  set local(a) = body_create(0, 4, 0.5, 1)\n"
                "  set local(b) = body_create(0.7, 5, 0.5, 2)\n"
                "  set local(floor) = body_create_box(0, -0.5, 10, 1, 0)\n"
                "  for local(i) = 1 to 400\n"
                "    set local(c) = physics_step()\n"
                "  end\n"
                "  print \"a=\" + body_x(local(a)) + \",\" + body_y(local(a))\n"
                "  print \"b=\" + body_x(local(b)) + \",\" + body_y(local(b))\n"
                "end\n",
                encoding="utf-8",
            )
            executable = path.with_suffix(".exe")
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(path), "-o", str(executable)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            runs = [
                subprocess.run(
                    [str(executable)], capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                )
                for _ in range(2)
            ]
        self.assertEqual(runs[0].returncode, 0, runs[0].stderr)
        self.assertEqual(runs[1].returncode, 0, runs[1].stderr)
        self.assertEqual(runs[0].stdout, runs[1].stdout)

    def test_a_small_stack_settles_without_sinking(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            lines = build_and_run(
                "fn(main)\n"
                "  set local(floor) = body_create_box(0, -0.5, 20, 1, 0)\n"
                "  set local(low) = body_create_box(0, 2, 1, 1, 1)\n"
                "  set local(high) = body_create_box(0, 3.6, 1, 1, 1)\n"
                "  for local(i) = 1 to 600\n"
                "    set local(c) = physics_step()\n"
                "  end\n"
                "  print \"low=\" + body_y(local(low)) + \",\" + body_vy(local(low))\n"
                "  print \"high=\" + body_y(local(high)) + \",\" + body_vy(local(high))\n"
                "  print \"floor=\" + body_y(local(floor))\n"
                "end\n",
                temporary,
            )
        low_y, low_vy = (float(part) for part in lines[0].split("=", 1)[1].split(","))
        high_y, high_vy = (float(part) for part in lines[1].split("=", 1)[1].split(","))
        # The floor's top is y = 0.5; each box is one unit tall.
        self.assertAlmostEqual(low_y, 0.5, delta=0.02)
        self.assertAlmostEqual(high_y, 1.5, delta=0.02)
        self.assertLess(abs(low_vy), 0.05)
        self.assertLess(abs(high_vy), 0.05)
        self.assertEqual(lines[2], "floor=-0.5")

    def test_a_long_replay_stays_finite_and_bounded(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            lines = build_and_run(
                "fn(main)\n"
                "  set local(a) = body_create(0, 6, 0.5, 1)\n"
                "  set local(b) = body_create(0.4, 9, 0.5, 1)\n"
                "  set local(floor) = body_create_box(0, -0.5, 8, 1, 0)\n"
                "  for local(i) = 1 to 5000\n"
                "    set local(c) = physics_step()\n"
                "  end\n"
                "  print \"a=\" + body_x(local(a)) + \",\" + body_y(local(a))\n"
                "end\n",
                temporary,
            )
        x_text, y_text = lines[0].split("=", 1)[1].split(",")
        x, y = float(x_text), float(y_text)
        self.assertEqual(x, x)  # a NaN would have failed the runtime's range check
        self.assertEqual(y, y)
        self.assertLess(abs(x), 1e6)
        self.assertGreater(y, 0.0)


if __name__ == "__main__":
    unittest.main()
