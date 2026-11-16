"""Overhead shadows: models and cubes flattened onto a ground plane (8.13)."""

from __future__ import annotations

import pathlib
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_gltf_model import write_quad  # noqa: E402
from test_sprite_draw import WindowReader  # noqa: E402

BACKGROUND = (100, 100, 100)
SHADOW = (41, 41, 41)  # 100 * (255 - 150) / 255


def run_scene(root: pathlib.Path, program: str, body) -> None:
    source = root / "shadows.ANVL"
    source.write_text(program, encoding="utf-8")
    executable = root / "shadows.exe"
    build = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if build.returncode != 0:
        if "No C compiler found" in build.stderr:
            raise unittest.SkipTest("MSVC is not available")
        raise AssertionError(build.stderr)
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: queue.Queue[str] = queue.Queue()

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line.strip())

    threading.Thread(target=pump, daemon=True).start()
    reader = WindowReader(process.pid)

    def wait_for(marker: str) -> None:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                if lines.get(timeout=0.2) == marker:
                    return
            except queue.Empty:
                continue
        raise AssertionError(f"marker {marker!r} never arrived")

    try:
        if reader.find(time.monotonic() + 10) is None:
            raise AssertionError("no window")
        reader.force_client_size(960, 600)
        body(reader, wait_for)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


class ShadowTests(unittest.TestCase):
    def test_a_model_casts_a_shadow_that_moves_with_the_ground(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 8 12",
                    "set var(look) = camera_angle(0, -35)",
                    "camera fov(60)",
                    "clear rgba(100, 100, 100, 255)",
                    "set var(frame) = 0",
                    "",
                    "fn(draw)",
                    "  add var(frame) 1",
                    "  if var(frame) = 2",
                    "    set var(s0) = shadow(0)",
                    '    say "off"',
                    "  end",
                    "  if var(frame) = 40",
                    "    set var(s1) = shadow(1)",
                    "    set var(h) = shadow_height(0)",
                    "    set var(al) = shadow_alpha(150)",
                    '    say "on"',
                    "  end",
                    "  if var(frame) = 80",
                    "    set var(h2) = shadow_height(1)",
                    '    say "raised"',
                    "  end",
                    "  if var(frame) = 120",
                    '    say "done"',
                    "    stop",
                    "  end",
                    '  set var(d) = model_draw("quad.gltf", 0, 2, 0, 2, 90, 0, 0)',
                    "end",
                    "",
                )
            )

            def body(reader, wait_for) -> None:
                wait_for("off")
                reader.settle(BACKGROUND, 480, 340)
                wait_for("on")
                reader.settle(SHADOW, 480, 340)
                wait_for("raised")
                reader.settle(BACKGROUND, 480, 340)
                wait_for("done")

            run_scene(root, program, body)

    def test_a_cube_casts_a_shadow_below_itself(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 8 12",
                    "set var(look) = camera_angle(0, -35)",
                    "camera fov(60)",
                    "clear rgba(100, 100, 100, 255)",
                    "set var(frame) = 0",
                    "",
                    "fn(draw)",
                    "  add var(frame) 1",
                    "  if var(frame) = 2",
                    "    set var(s0) = shadow(0)",
                    '    say "off"',
                    "  end",
                    "  if var(frame) = 40",
                    "    set var(s1) = shadow(1)",
                    "    set var(h) = shadow_height(0)",
                    '    say "on"',
                    "  end",
                    "  if var(frame) = 90",
                    '    say "done"',
                    "    stop",
                    "  end",
                    "  display cube(0, 1, 0, 1) -rgb(255, 0, 0)",
                    "end",
                    "",
                )
            )

            def body(reader, wait_for) -> None:
                wait_for("off")
                reader.settle(BACKGROUND, 480, 312)
                wait_for("on")
                reader.settle(SHADOW, 480, 312)
                wait_for("done")

            run_scene(root, program, body)


if __name__ == "__main__":
    unittest.main()
