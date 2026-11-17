"""Scene manager: a timed scene change built on the fade (8.14).

A scene change is a fade out, a swap of the current scene name while the screen
is black, and a fade back in. These tests read the timeline the program sees
(names, progress, the one-frame change flag), the pixels a player sees (black at
the midpoint, the drawn frame afterwards), and the wasm overlay ops.
"""

from __future__ import annotations

import json
import os
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
HOST = ROOT / "tools" / "wasm_host.mjs"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_sprite_draw import WindowReader  # noqa: E402

PROBE = (150, 150)
NEEDS_WASM = all(
    __import__("shutil").which(tool) for tool in ("clang", "node", "wasm-ld")
)


class Runner:
    """Build and run a program in a real window, exposing its output lines."""

    def __init__(self, root: pathlib.Path, program: str):
        self.root = root
        source = root / "scene.ANVL"
        source.write_text(program, encoding="utf-8")
        self.executable = root / "scene.exe"
        self.build = subprocess.run(
            [sys.executable, str(COMPILER), str(source), "-o", str(self.executable)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.process = None
        self.lines: queue.Queue[str] = queue.Queue()

    def __enter__(self) -> "Runner":
        if self.build.returncode != 0:
            if "No C compiler found" in self.build.stderr:
                raise unittest.SkipTest("MSVC is not available")
            raise AssertionError(self.build.stderr)
        self.process = subprocess.Popen(
            [str(self.executable)],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def pump() -> None:
            assert self.process is not None and self.process.stdout is not None
            for line in self.process.stdout:
                self.lines.put(line.strip())

        threading.Thread(target=pump, daemon=True).start()
        return self

    def __exit__(self, *exc) -> None:
        if self.process is not None:
            self.process.kill()
            self.process.wait(timeout=30)

    def until(self, marker: str, timeout: float = 25.0) -> list[str]:
        seen: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(0.1, deadline - time.monotonic()))
            except queue.Empty:
                break
            seen.append(line)
            if line == marker:
                return seen
        raise AssertionError(f"never saw {marker!r}: {seen}")

    def stderr_after_exit(self) -> str:
        assert self.process is not None and self.process.stderr is not None
        return self.process.stderr.read()


class SceneManagerTests(unittest.TestCase):
    def test_an_immediate_change_swaps_the_name_at_once(self) -> None:
        program = "\n".join(
            (
                "scene 2d",
                "set var(step) = 0",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                "  add var(step) 1",
                "  if var(step) = 2",
                '    say "before [" & scene_name() & "]"',
                '    say "change " & scene_change("level2", 0)',
                '    say "after [" & scene_name() & "]"',
                '    say "changing " & scene_changing()',
                '    say "progress " & scene_progress()',
                '    say "flag " & scene_changed()',
                '    say "mark1"',
                "  end",
                "  if var(step) = 3",
                '    say "next " & scene_changed()',
                "  end",
                "  if var(step) = 4",
                '    say "done"',
                "  end",
                "end",
                "",
            )
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            with Runner(pathlib.Path(temp), program) as runner:
                seen = runner.until("done")
        self.assertIn("before []", seen)
        self.assertIn("change 1", seen)
        self.assertIn("after [level2]", seen)
        self.assertIn("changing 0", seen)
        self.assertIn("progress 1", seen)
        # The change flag is set by the call itself, so the frame that made the
        # change sees it; the next frame starts with it cleared.
        self.assertIn("flag 1", seen)
        self.assertIn("next 0", seen)

    def test_a_timed_change_swaps_in_the_black_hold(self) -> None:
        program = "\n".join(
            (
                "scene 2d",
                "set var(step) = 0",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                "  display rect(100, 100, 200, 100) -rgb(255, 255, 255)",
                "  add var(step) 1",
                "  if var(step) = 2",
                '    say "change " & scene_change("level2", 2.0)',
                '    say "name [" & scene_name() & "]"',
                '    say "target [" & scene_target() & "]"',
                '    say "markstart"',
                "  end",
                "  if var(step) = 70",
                '    say "name [" & scene_name() & "]"',
                '    say "progress " & scene_progress()',
                '    say "changing " & scene_changing()',
                '    say "alpha " & screen_fade_alpha()',
                '    say "markmid"',
                "  end",
                "  if var(step) = 150",
                '    say "end [" & scene_name() & "]"',
                '    say "changing " & scene_changing()',
                '    say "alpha " & screen_fade_alpha()',
                '    say "done"',
                "  end",
                "end",
                "",
            )
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            with Runner(pathlib.Path(temp), program) as runner:
                reader = WindowReader(runner.process.pid)
                reader.find(time.monotonic() + 15)
                reader.raise_window()
                time.sleep(0.3)
                start = runner.until("markstart")
                self.assertIn("change 1", start)
                self.assertIn("name []", start)  # nothing changes until the swap
                self.assertIn("target [level2]", start)

                # Somewhere inside the two-second transition the overlay is at
                # full strength, so the white rectangle reads as black.
                reader.settle((0, 0, 0), *PROBE)

                mid = runner.until("markmid")
                self.assertIn("name [level2]", mid)
                self.assertIn("changing 1", mid)
                progress = float(
                    [line for line in mid if line.startswith("progress ")][0].split()[1]
                )
                self.assertGreater(progress, 0.5)
                self.assertLess(progress, 1.0)

                end = runner.until("done")
                self.assertIn("end [level2]", end)
                self.assertIn("changing 0", end)
                self.assertIn("alpha 0", end)
                # The overlay is gone, so the drawn frame is back.
                reader.settle((255, 255, 255), *PROBE)

    def test_a_second_change_is_refused_while_one_runs(self) -> None:
        long_name = "x" * 70
        program = "\n".join(
            (
                "scene 2d",
                "set var(step) = 0",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                "  add var(step) 1",
                "  if var(step) = 2",
                f'    say "too long " & scene_change("{long_name}", 0)',
                '    say "empty " & scene_change("", 0)',
                '    say "start " & scene_change("level2", 0.5)',
                '    say "again " & scene_change("level3", 0.5)',
                '    say "name [" & scene_name() & "]"',
                '    say "target [" & scene_target() & "]"',
                '    say "mark1"',
                "  end",
                "  if var(step) = 45",
                '    say "later " & scene_change("level3", 0)',
                '    say "name [" & scene_name() & "]"',
                '    say "done"',
                "  end",
                "end",
                "",
            )
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            runner = Runner(pathlib.Path(temp), program)
            with runner:
                seen = runner.until("done")
            errors = runner.stderr_after_exit()
        self.assertIn("too long 0", seen)
        self.assertIn("empty 0", seen)
        self.assertIn("start 1", seen)
        self.assertIn("again 0", seen)           # one transition at a time
        self.assertIn("target [level2]", seen)   # the refused call changed nothing
        self.assertIn("later 1", seen)           # refused only while it ran
        self.assertIn("name [level3]", seen)
        self.assertIn("1 to 63 bytes", errors)

    @unittest.skipUnless(NEEDS_WASM, "clang, wasm-ld and node are required")
    def test_the_wasm_target_fades_and_swaps_the_scene(self) -> None:
        program = "\n".join(
            (
                "scene 2d",
                "set var(step) = 0",
                "",
                "fn(draw)",
                "  clear rgba(40, 80, 120, 255)",
                "  if var(step) = 0",
                '    say "change " & scene_change("level2", 0.25)',
                "  end",
                "  add var(step) 1",
                "  if var(step) = 2",
                '    say "early [" & scene_name() & "] target [" & scene_target() & "]"',
                "  end",
                "  if var(step) = 12",
                '    say "late [" & scene_name() & "] changing " & scene_changing()',
                "  end",
                "end",
                "",
            )
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "scene.ANVL"
            source.write_text(program, encoding="utf-8")
            out = root / "scene.wasm"
            build = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "-o",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            script = json.dumps([["frame", 17]] * 20)
            run = subprocess.run(
                ["node", str(HOST), "--record", "--input", script, str(out)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("change 1", run.stdout)
        self.assertIn("early [] target [level2]", run.stdout)
        self.assertIn("late [level2]", run.stdout)
        ops = json.loads(run.stdout.strip().splitlines()[-1])
        fades = [op[1] for op in ops if op[0] == "fade"]
        # The overlay ramps up, holds at 255 and comes back down; a 0.25 s
        # transition at 17 ms per frame is about fifteen frames.
        self.assertGreaterEqual(len(fades), 10)
        self.assertEqual(max(fades), 255)
        self.assertLess(fades[-1], 255)
        # The last frame draws with no overlay at all.
        self.assertNotEqual(ops[-2][0], "fade")


if __name__ == "__main__":
    unittest.main()
