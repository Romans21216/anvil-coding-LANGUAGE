"""Particles: emit, count, clear, fade and lifetime (8.15/2D feature)."""

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


def run_window(program: str, body) -> None:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        root = pathlib.Path(temp)
        source = root / "particles.ANVL"
        source.write_text(program, encoding="utf-8")
        executable = root / "particles.exe"
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
            body(reader, wait_for, lines)
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


class ParticleApiTests(unittest.TestCase):
    def test_invalid_arguments_are_refused(self) -> None:
        source = (
            "fn(main)\n"
            "  say particle_emit(0, 0, 0, 0, 0, 4, 255, 0, 0)\n"
            "  say particle_emit(0, 0, 0, 0, 1, 0, 255, 0, 0)\n"
            "  say particle_emit(0, 0, 0, 0, 1, 4, 255, 0, 0)\n"
            "  say particle_count()\n"
            "  say particle_clear()\n"
            "  say particle_count()\n"
            "end\n"
            "call fn(main)\n"
        )
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        from test_audio import lines_of, run_c

        result = run_c(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines_of(result), ["0", "0", "1", "1", "1", "0"])


class ParticleWindowTests(unittest.TestCase):
    def test_capacity_is_bounded_and_clear_reports_the_count(self) -> None:
        program = "\n".join(
            (
                "scene 2d",
                "clear rgba(0, 0, 0, 255)",
                "set var(frame) = 0",
                "",
                "fn(draw)",
                "  add var(frame) 1",
                "  if var(frame) = 2",
                "    for local(i) = 0 to 4095",
                "      set var(e) = particle_emit(100, 100, 0, 0, 60, 2, 255, 0, 0)",
                "    end",
                "    say particle_count()",
                "    say particle_emit(100, 100, 0, 0, 60, 2, 255, 0, 0)",
                "    say particle_clear()",
                "    say particle_count()",
                "  end",
                "  if var(frame) = 30",
                '    say "done"',
                "    stop",
                "  end",
                "end",
                "",
            )
        )

        def body(reader, wait_for, lines) -> None:
            wait_for("4096")
            self.assertEqual(lines.get(timeout=5), "0")
            self.assertEqual(lines.get(timeout=5), "4096")
            self.assertEqual(lines.get(timeout=5), "0")
            wait_for("done")

        run_window(program, body)

    def test_a_particle_fades_then_disappears(self) -> None:
        program = "\n".join(
            (
                "scene 2d",
                "clear rgba(0, 0, 0, 255)",
                "set var(frame) = 0",
                "",
                "fn(draw)",
                "  add var(frame) 1",
                "  if var(frame) = 2",
                "    set var(e) = particle_emit(480, 300, 0, 0, 1.0, 40, 255, 0, 0)",
                '    say "red"',
                "  end",
                "  if var(frame) = 20",
                '    say "mid"',
                "  end",
                "  if var(frame) = 90",
                '    say "gone"',
                "    say particle_count()",
                "  end",
                "  if var(frame) = 110",
                '    say "done"',
                "    stop",
                "  end",
                "end",
                "",
            )
        )

        def body(reader, wait_for, lines) -> None:
            wait_for("red")
            deadline = time.monotonic() + 3
            bright = 0
            while time.monotonic() < deadline:
                bright = reader.pixel(480, 300)[0]
                if bright > 200:
                    break
                time.sleep(0.02)
            self.assertGreater(bright, 200, "the fresh particle should be nearly solid red")

            wait_for("mid")
            # The marker prints during draw, but the window presents a frame
            # later, so poll briefly instead of reading a possibly stale pixel.
            mid = 0
            mid_deadline = time.monotonic() + 2
            while time.monotonic() < mid_deadline:
                mid = reader.pixel(480, 300)[0]
                if 20 < mid < 250:
                    break
                time.sleep(0.02)
            self.assertGreater(mid, 20, "the particle should still be visible mid-life")
            self.assertLess(mid, 250, "the particle should have faded by mid-life")

            wait_for("gone")
            self.assertEqual(lines.get(timeout=5), "0")
            reader.settle((0, 0, 0), 480, 300)
            wait_for("done")

        run_window(program, body)


if __name__ == "__main__":
    unittest.main()
