"""Directional light and ambient control for the 3D path (8.13).

The front face of a red cube faces +Z. With the default light it keeps the
ambient floor plus part of the lit range; pointing the light straight at it
(`light(0,0,1)`) reaches the base colour; `light_ambient(1)` flattens every
face; `light_intensity(0)` drops back to the ambient floor.
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

RED = (200, 60, 60)

HEADLESS_PROGRAM = "\n".join(
    (
        "fn(main)",
        "  say light(0, 0, 0)",
        "  say light(0, 1, 0)",
        "  say light_ambient(0.5)",
        "  say light_ambient(9)",
        "  say light_ambient(9)",
        "  say light_intensity(0)",
        "  say light_intensity(0)",
        "  say light_intensity(5)",
        "end",
        "call fn(main)",
        "",
    )
)

PIXEL_PROGRAM = "\n".join(
    (
        "scene 3d",
        "camera perspective 0 3 12",
        "camera fov(70)",
        "clear rgba(11, 16, 27, 255)",
        "set var(frame) = 0",
        "set var(default_px) = -1",
        "set var(lit_px) = -1",
        "set var(flat_px) = -1",
        "set var(dim_px) = -1",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  display cube(0, 3, 0, 1.4) -rgb(200, 60, 60)",
        "  if var(frame) = 5",
        "    set var(cap) = frame_capture()",
        "    set var(default_px) = image_pixel(var(cap), 480, 324)",
        "    set var(l) = light(0, 0, 1)",
        "  end",
        "  if var(frame) = 10",
        "    set var(cap) = frame_capture()",
        "    set var(lit_px) = image_pixel(var(cap), 480, 324)",
        "    set var(a) = light_ambient(1)",
        "  end",
        "  if var(frame) = 15",
        "    set var(cap) = frame_capture()",
        "    set var(flat_px) = image_pixel(var(cap), 480, 324)",
        "    set var(a2) = light_ambient(0.28)",
        "    set var(i) = light_intensity(0)",
        "  end",
        "  if var(frame) = 20",
        "    set var(cap) = frame_capture()",
        "    set var(dim_px) = image_pixel(var(cap), 480, 324)",
        '    say "default " & var(default_px)',
        '    say "lit " & var(lit_px)',
        '    say "flat " & var(flat_px)',
        '    say "dim " & var(dim_px)',
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


def rgb(value: int) -> tuple[int, int, int]:
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


class LightingTests(unittest.TestCase):
    def test_light_values_and_clamping(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            executable = build(pathlib.Path(temp), HEADLESS_PROGRAM, "lights")
            run = subprocess.run(
                [str(executable)], cwd=temp, capture_output=True, text=True, timeout=60
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(
                run.stdout.splitlines(),
                [
                    "0",      # a zero vector is rejected
                    "1",      # any other direction is accepted
                    "0.28",   # default ambient returned
                    "0.5",    # the value just set
                    "1",      # 9 clamps to 1
                    "1",      # default intensity returned
                    "0",      # the value just set
                    "0",      # 5 clamps to 2, previous was 0
                ],
            )

    def test_faces_follow_the_light_and_ambient(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, PIXEL_PROGRAM, "cubelight")
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
                    if line.startswith("dim ") or time.monotonic() > deadline:
                        break
            finally:
                process.kill()
                process.wait(timeout=30)
            values: dict[str, int] = {}
            for line in lines:
                key, _, value = line.partition(" ")
                if key in ("default", "lit", "flat", "dim"):
                    values[key] = int(float(value))
            self.assertEqual(sorted(values), ["default", "dim", "flat", "lit"], lines)
            default = rgb(values["default"])
            # Default light: ambient 0.28 plus 0.72 * 0.55 of the red.
            self.assertLess(default[0], RED[0] - 20)
            self.assertGreater(default[0], 110)
            # Light straight at the face reaches the base colour.
            self.assertEqual(rgb(values["lit"]), RED)
            # Ambient 1 flattens shading entirely.
            self.assertEqual(rgb(values["flat"]), RED)
            # Intensity 0 leaves only the ambient floor.
            dim = rgb(values["dim"])
            self.assertLessEqual(dim[0], 60)
            self.assertGreaterEqual(dim[0], 50)


if __name__ == "__main__":
    unittest.main()
