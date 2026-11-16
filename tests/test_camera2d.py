"""2D camera pan and zoom, checked against presented pixels."""

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

from test_sprite_draw import RED, WindowReader  # noqa: E402

BLACK = (0, 0, 0)

PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(frame) = 0",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  if var(frame) = 5",
        '    say "default"',
        "  end",
        "  if var(frame) = 35",
        "    set var(c) = camera2d(50, 50, 1)",
        '    say "pan"',
        "  end",
        "  if var(frame) = 65",
        "    set var(c2) = camera2d(0, 0, 2)",
        '    say "zoom"',
        "  end",
        "  if var(frame) = 95",
        "    set var(bad) = camera2d(0, 0, 0)",
        '    say "bad"',
        "    say var(bad)",
        "  end",
        "  if var(frame) = 110",
        "    set var(c3) = camera2d(0, 0, 1)",
        '    say "reset"',
        "  end",
        "  if var(frame) = 140",
        '    say "done"',
        "    stop",
        "  end",
        "  display rect(100, 100, 10, 10) -rgb(255, 0, 0)",
        "end",
        "",
    )
)


class Camera2DTests(unittest.TestCase):
    def test_pan_and_zoom_move_the_world_rect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = root / "camera.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "camera.exe"
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if build.returncode != 0:
                if "No C compiler found" in build.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(build.stderr)

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
                self.fail(f"marker {marker!r} never arrived")

            def next_line(timeout: float = 5.0) -> str:
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        return lines.get(timeout=0.2)
                    except queue.Empty:
                        continue
                self.fail("expected another output line")

            try:
                self.assertIsNotNone(reader.find(time.monotonic() + 10), "no window")
                reader.force_client_size(960, 600)

                wait_for("default")
                reader.settle(RED, 105, 105)
                self.assertEqual(reader.pixel(50, 50), BLACK)
                self.assertEqual(reader.pixel(210, 210), BLACK)

                wait_for("pan")
                reader.settle(RED, 55, 55)
                self.assertEqual(reader.pixel(105, 105), BLACK)

                wait_for("zoom")
                reader.settle(RED, 210, 210)
                self.assertEqual(reader.pixel(105, 105), BLACK)

                wait_for("bad")
                self.assertEqual(next_line(), "0")
                # A rejected camera call leaves the previous camera in place.
                self.assertEqual(reader.pixel(210, 210), RED)

                wait_for("reset")
                reader.settle(RED, 105, 105)
                wait_for("done")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    unittest.main()
