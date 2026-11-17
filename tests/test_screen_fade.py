"""Screen fade: a transition overlay applied after the frame's own draws (8.14).

The fade has to land after every draw and before the present, because that is
where a scene transition sits. That also means frame_capture() cannot see it -
the capture runs inside the draw callback - so these tests read the real window
the way a player would, and separately check the return/clamp sequence and the
timed ramp through screen_fade_alpha().
"""

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

PROBE = (150, 150)  # inside the white rectangle, away from the caption

PROGRAM = "\n".join(
    (
        "scene 2d",
        "set var(step) = 0",
        "",
        "fn(draw)",
        "  clear rgba(0, 0, 0, 255)",
        "  display rect(100, 100, 200, 100) -rgb(255, 255, 255)",
        "  add var(step) 1",
        "  if var(step) = 2",
        '    say "neg " & screen_fade(-7)',
        '    say "alpha0 " & screen_fade_alpha()',
        '    say "mark0"',
        "  end",
        "  if var(step) = 120",
        '    say "prev128 " & screen_fade(128)',
        '    say "mark128"',
        "  end",
        "  if var(step) = 240",
        '    say "prev255 " & screen_fade(300)',
        '    say "clamped " & screen_fade_alpha()',
        '    say "mark255"',
        "  end",
        "  if var(step) = 360",
        '    say "prevto " & screen_fade_to(0, 0.5)',
        '    say "markto"',
        "  end",
        "  if var(step) = 362",
        '    say "mid " & screen_fade_alpha()',
        "  end",
        "  if var(step) = 430",
        '    say "end " & screen_fade_alpha()',
        '    say "markend"',
        "  end",
        "end",
        "",
    )
)


class ScreenFadeTests(unittest.TestCase):
    def test_fade_clamps_and_the_window_dims(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "fade.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "fade.exe"
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
            reader.find(time.monotonic() + 10)
            # GetPixel reads what is on screen, so the window must be on top.
            reader.raise_window()
            time.sleep(0.3)

            def read() -> str:
                try:
                    return lines.get(timeout=15)
                except queue.Empty:
                    self.fail("the program did not reach the next marker")

            def until(marker: str) -> list[str]:
                seen: list[str] = []
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    line = read()
                    seen.append(line)
                    if line == marker:
                        return seen
                self.fail(f"never saw {marker}: {seen}")

            try:
                seen = until("mark0")
                self.assertIn("neg 0", seen)      # non-finite/clamped in, previous out
                self.assertIn("alpha0 0", seen)
                reader.settle((255, 255, 255), *PROBE)

                seen = until("mark128")
                self.assertIn("prev128 0", seen)
                # 255 * (255 - 128) / 255 == 127
                reader.settle((127, 127, 127), *PROBE)

                seen = until("mark255")
                self.assertIn("prev255 128", seen)
                self.assertIn("clamped 255", seen)  # 300 clamps to 255
                reader.settle((0, 0, 0), *PROBE)

                seen = until("markto")
                self.assertIn("prevto 255", seen)

                # One pass to the end marker: the mid ramp lands two frames in,
                # and the ramp must finish exactly on its target.
                seen = until("markend")
                mid = [line for line in seen if line.startswith("mid ")]
                self.assertEqual(len(mid), 1, mid)
                ramp = float(mid[0].split()[1])
                # 0.5 s from 255 at 60 Hz is about 8.5 units per frame, so two
                # frames after the start the alpha must be high but not done.
                self.assertGreater(ramp, 200.0)
                self.assertLess(ramp, 255.0)
                self.assertIn("end 0", seen)
                reader.settle((255, 255, 255), *PROBE)
            finally:
                process.kill()
                process.wait(timeout=30)

    def test_zero_seconds_sets_the_value_immediately(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "quick.ANVL"
            source.write_text(
                "\n".join(
                    (
                        "fn(main)",
                        '  say "prev " & screen_fade_to(180, 0)',
                        '  say "now " & screen_fade_alpha()',
                        '  say "back " & screen_fade_to(-4, 0)',
                        '  say "after " & screen_fade_alpha()',
                        "end",
                        "",
                        "call fn(main)",
                        "",
                    )
                ),
                encoding="utf-8",
            )
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(root / "quick.exe")],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if build.returncode != 0:
                if "No C compiler found" in build.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(build.stderr)
            run = subprocess.run(
                [str(root / "quick.exe")], cwd=root, capture_output=True, text=True, timeout=60
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(
            run.stdout.splitlines(), ["prev 0", "now 180", "back 180", "after 0"]
        )


if __name__ == "__main__":
    unittest.main()
