"""Parallax: layers follow the camera pan at different rates (8.14).

The check is a pair of identical rectangles drawn under different parallax
factors with the camera panned 100 px: the world layer (factor 1) lands at
screen x=0, a half-speed layer (factor 0.5) at x=50, and nothing is drawn
beyond them. Pixels are read from a captured frame, not from arguments.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

RED = 0xFF0000
GREEN = 0x00FF00

CLAMP_PROGRAM = "\n".join(
    (
        "fn(main)",
        "  say parallax(0.5)",
        "  say parallax(9)",
        "  say parallax(9)",
        "  say parallax(-2)",
        "  say parallax(-2)",
        "end",
        "call fn(main)",
        "",
    )
)

PIXEL_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(frame) = 0",
        "set var(ok) = camera2d(100, 0, 1)",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  set var(p1) = parallax(1)",
        "  display rect(100, 100, 40, 40) -rgba(255, 0, 0, 255)",
        "  set var(p2) = parallax(0.5)",
        "  display rect(100, 100, 40, 40) -rgba(0, 255, 0, 255)",
        "  set var(p3) = parallax(1)",
        "  if var(frame) = 5",
        "    set var(cap) = frame_capture()",
        '    say "world " & image_pixel(var(cap), 10, 110)',
        '    say "half " & image_pixel(var(cap), 60, 110)',
        '    say "none " & image_pixel(var(cap), 95, 110)',
        "  end",
        "end",
        "",
    )
)


def build(root: pathlib.Path, program: str, name: str) -> pathlib.Path:
    source = root / f"{name}.ANVL"
    source.write_text(program, encoding="utf-8")
    executable = root / f"{name}.exe"
    result = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return executable


class ParallaxTests(unittest.TestCase):
    def test_the_factor_clamps_and_returns_the_previous_value(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            executable = build(pathlib.Path(temp), CLAMP_PROGRAM, "clamp")
            run = subprocess.run(
                [str(executable)], cwd=temp, capture_output=True, text=True, timeout=60
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            # default 1 -> set 0.5 -> 9 clamps to 4 -> -2 clamps to 0 -> 0
            self.assertEqual(run.stdout.splitlines(), ["1", "0.5", "4", "4", "0"])

    def test_layers_move_at_different_rates_under_the_same_camera(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, PIXEL_PROGRAM, "pixels")
            process = subprocess.Popen(
                [str(executable)],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            lines: list[str] = []
            assert process.stdout is not None
            deadline = time.monotonic() + 45
            try:
                for line in process.stdout:
                    lines.append(line.rstrip("\r\n"))
                    if line.startswith("none") or time.monotonic() > deadline:
                        break
            finally:
                process.kill()
                process.wait(timeout=30)
            values: dict[str, int] = {}
            for line in lines:
                key, _, value = line.partition(" ")
                if key in ("world", "half", "none"):
                    values[key] = int(float(value))
            self.assertEqual(sorted(values), ["half", "none", "world"], lines)
            # Camera pan 100 with zoom 1: world layer at x=0, half-speed at x=50.
            self.assertEqual(values["world"] & 0xFFFFFF, RED)
            self.assertEqual(values["half"] & 0xFFFFFF, GREEN)
            self.assertEqual(values["none"] & 0xFFFFFF, 0)


if __name__ == "__main__":
    unittest.main()
