"""Text glyphs scale with the 2D camera, checked against presented pixels."""

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

from test_sprite_draw import WindowReader  # noqa: E402

# Each phase holds its frame for 2.5 s so the (slow, pixel-by-pixel) bounding
# box scan always reads the frame the marker describes. The frame before the
# marker's frame is the one on screen while the program waits.
PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(frame) = 0",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  if var(frame) = 2",
        '    say "one"',
        "    wait 2.5",
        "  end",
        "  if var(frame) = 6",
        "    set var(c) = camera2d(0, 0, 2)",
        "  end",
        "  if var(frame) = 7",
        '    say "two"',
        "    wait 2.5",
        "  end",
        "  if var(frame) = 9",
        "    set var(c2) = camera2d(0, 0, 1)",
        "  end",
        "  if var(frame) = 10",
        '    say "reset"',
        "    wait 2.5",
        "  end",
        "  if var(frame) = 12",
        '    say "done"',
        "    stop",
        "  end",
        '  display text("MMMM") -l(100, 100) -rgb(255, 255, 255)',
        "end",
        "",
    )
)


class TextZoomTests(unittest.TestCase):
    def test_glyphs_grow_with_camera_zoom(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = root / "text_zoom.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "text_zoom.exe"
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

            def box() -> tuple[int, int, int, int]:
                found = reader.bounding_box(90, 90, 400, 280)
                self.assertIsNotNone(found, "no text pixels were presented")
                assert found is not None
                return found

            try:
                self.assertIsNotNone(reader.find(time.monotonic() + 10), "no window")
                reader.force_client_size(960, 600)

                wait_for("one")
                one = box()
                width_one = one[2] - one[0] + 1
                height_one = one[3] - one[1] + 1

                wait_for("two")
                two = box()
                width_two = two[2] - two[0] + 1
                height_two = two[3] - two[1] + 1

                # 2x zoom doubles the glyph size as well as moving the origin.
                self.assertGreaterEqual(width_two, width_one * 1.6)
                self.assertGreaterEqual(height_two, height_one * 1.6)
                self.assertGreaterEqual(two[0], one[2])

                wait_for("reset")
                back = box()
                self.assertLessEqual(abs(back[0] - one[0]), 1)
                self.assertLessEqual(abs(back[1] - one[1]), 1)
                self.assertLessEqual(abs((back[2] - back[0]) - (one[2] - one[0])), 2)

                wait_for("done")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    unittest.main()
