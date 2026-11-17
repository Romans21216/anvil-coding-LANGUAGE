"""UI keyboard focus and accessible labels (8.14).

A custom-drawn UI has no window controls for the OS to focus, so the runtime
keeps a registry of focusable rectangles. `ui_focus_add` declares one with the
label a screen reader should read; the engine owns click hit-testing,
registration-order traversal and Enter/Space activation, and `ui_accessible(1)`
announces the focused label - through an MSAA child window on Windows and an
aria-live region in the browser.
"""

from __future__ import annotations

import ctypes
import json
import os
import pathlib
import queue
import subprocess
import sys
import threading
import time
import unittest
from ctypes import wintypes

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
HOST = ROOT / "tools" / "wasm_host.mjs"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_sprite_draw import WindowReader  # noqa: E402

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
NEEDS_WASM = all(
    __import__("shutil").which(tool) for tool in ("clang", "node", "wasm-ld")
)


def lparam(x: int, y: int) -> int:
    return (y << 16) | (x & 0xFFFF)


class Probe:
    """A built Anvil program running in a real window."""

    def __init__(self, root: pathlib.Path, program: str):
        self.root = root
        source = root / "probe.ANVL"
        source.write_text(program, encoding="utf-8")
        self.executable = root / "probe.exe"
        self.build = subprocess.run(
            [sys.executable, str(COMPILER), str(source), "-o", str(self.executable)],
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.process = None
        self.lines: queue.Queue[str] = queue.Queue()
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)

    def __enter__(self) -> "Probe":
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

    def next_line(self, timeout: float = 15.0) -> str:
        return self.lines.get(timeout=timeout)

    def wait_for(self, marker: str, timeout: float = 20.0) -> list[str]:
        seen: list[str] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = self.next_line(max(0.1, deadline - time.monotonic()))
            seen.append(line)
            if line == marker:
                return seen
        raise AssertionError(f"{marker!r} never printed; saw {seen}")

    def window(self, timeout: float = 20.0) -> int:
        assert self.process is not None
        reader = WindowReader(self.process.pid)
        handle = reader.find(time.monotonic() + timeout)
        if not handle:
            raise AssertionError("the program never created a window")
        return handle

    def click(self, handle: int, x: int, y: int) -> None:
        self.user32.PostMessageW(handle, WM_MOUSEMOVE, 0, lparam(x, y))
        self.user32.PostMessageW(handle, WM_LBUTTONDOWN, MK_LBUTTON, lparam(x, y))
        self.user32.PostMessageW(handle, WM_LBUTTONUP, 0, lparam(x, y))

    def child_texts(self, parent: int) -> list[str]:
        found: list[str] = []
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @enum_proc
        def visit(hwnd, _unused):
            buffer = ctypes.create_unicode_buffer(256)
            self.user32.GetWindowTextW(hwnd, buffer, 256)
            found.append(buffer.value)
            return True

        self.user32.EnumChildWindows(parent, visit, 0)
        return found


class UiFocusTests(unittest.TestCase):
    def test_the_registry_traverses_sets_and_clears(self) -> None:
        program = "\n".join(
            (
                "scene 2d",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                "  if ui_focus_count() = 0",
                '    set var(a) = ui_focus_add(10, 10, 100, 40, "Play")',
                '    set var(b) = ui_focus_add(120, 10, 100, 40, "Quit")',
                '    say "count " & ui_focus_count()',
                '    say "next " & ui_focus_next()',
                '    say "label " & ui_focus_label()',
                '    say "at " & ui_focus_at(150, 20)',
                '    say "outside " & ui_focus_at(500, 400)',
                '    say "previous " & ui_focus_set(var(b))',
                '    say "label " & ui_focus_label()',
                '    say "bad " & ui_focus_set(99)',
                '    say "still " & ui_focus_label()',
                '    say "accessible " & ui_accessible(1)',
                '    say "activated " & ui_focus_activate()',
                '    say "cleared " & ui_focus_clear()',
                '    say "count " & ui_focus_count()',
                '    say "done"',
                "  end",
                "end",
                "",
            )
        )
        import tempfile

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            with Probe(pathlib.Path(temp), program) as probe:
                seen = probe.wait_for("done")
        self.assertEqual(
            seen,
            [
                "count 2",
                "next 1",
                "label Play",
                # 150,20 is inside the second region: the later handle wins.
                "at 2",
                "outside 0",
                # ui_focus_set returns what was focused before the call.
                "previous 1",
                "label Quit",
                # An unknown handle leaves the focus alone and returns it.
                "bad 2",
                "still Quit",
                "accessible 1",
                "activated 0",
                "cleared 2",
                "count 0",
                "done",
            ],
        )

    def test_a_click_focuses_and_activates_the_region_under_the_pointer(self) -> None:
        program = "\n".join(
            (
                "scene 2d",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                "  if ui_focus_count() = 0",
                '    set var(all) = ui_focus_add(0, 0, 960, 600, "Canvas")',
                '    say "ready"',
                "  end",
                "  if ui_focus_activate() > 0",
                '    say "activate " & ui_focus_activate()',
                '    say "label " & ui_focus_label()',
                '    say "done"',
                "  end",
                "end",
                "",
            )
        )
        import tempfile

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            with Probe(pathlib.Path(temp), program) as probe:
                handle = probe.window()
                probe.wait_for("ready")
                reader = WindowReader(probe.process.pid)
                reader.hwnd = handle
                left, top, right, bottom = reader.client_rect()
                probe.click(handle, (right - left) // 2, (bottom - top) // 2)
                seen = probe.wait_for("done")
        self.assertIn("activate 1", seen)
        self.assertIn("label Canvas", seen)

    def test_the_focused_label_reaches_the_accessibility_channel(self) -> None:
        program = "\n".join(
            (
                "scene 2d",
                'set var(a) = ui_focus_add(10, 10, 100, 40, "Play")',
                'set var(b) = ui_focus_add(120, 10, 100, 40, "Quit")',
                "set var(on) = ui_accessible(1)",
                # Focus the second region before the first frame: the frame
                # update announces a label the moment focus differs from the
                # last announced one.
                "set var(focus) = ui_focus_next()",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                '  say "ready"',
                "end",
                "",
            )
        )
        import tempfile

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            with Probe(pathlib.Path(temp), program) as probe:
                handle = probe.window()
                texts: list[str] = []
                deadline = time.monotonic() + 20.0
                while time.monotonic() < deadline:
                    texts = probe.child_texts(handle)
                    if "Play" in texts:
                        break
                    time.sleep(0.05)
        self.assertIn("Play", texts, f"child windows: {texts}")

    def test_a_label_past_the_limit_is_refused(self) -> None:
        long_label = "x" * 200
        program = "\n".join(
            (
                "scene 2d",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                "  if ui_focus_count() = 0",
                f'    set var(a) = ui_focus_add(10, 10, 100, 40, "{long_label}")',
                '    say "count " & ui_focus_count()',
                '    say "done"',
                "  end",
                "end",
                "",
            )
        )
        import tempfile

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            probe = Probe(pathlib.Path(temp), program)
            with probe:
                seen = probe.wait_for("done")
            # Read stderr after the probe is killed, so read() sees EOF.
            assert probe.process is not None and probe.process.stderr is not None
            errors = probe.process.stderr.read()
        self.assertIn("count 0", seen)
        self.assertIn("longer than 95 bytes", errors)

    @unittest.skipUnless(NEEDS_WASM, "clang, wasm-ld and node are required")
    def test_the_wasm_target_activates_a_clicked_region(self) -> None:
        import tempfile

        program = "\n".join(
            (
                "scene 2d",
                'set var(all) = ui_focus_add(0, 0, 960, 600, "Canvas")',
                "set var(on) = ui_accessible(1)",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                "  if ui_focus_activate() > 0",
                '    say "activate " & ui_focus_activate()',
                '    say "label " & ui_focus_label()',
                '    say "done"',
                "  end",
                "end",
                "",
            )
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "click.ANVL"
            source.write_text(program, encoding="utf-8")
            out = root / "click.wasm"
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
            script = json.dumps(
                [
                    ["frame", 16],
                    ["mouse", 480, 300],
                    ["button", 0, 1],
                    ["frame", 16],
                ]
            )
            run = subprocess.run(
                ["node", str(HOST), "--record", "--input", script, str(out)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("activate 1", run.stdout)
        self.assertIn("label Canvas", run.stdout)
        ops = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertIn(["announce", "Canvas"], ops)

    @unittest.skipUnless(NEEDS_WASM, "clang, wasm-ld and node are required")
    def test_the_wasm_target_announces_the_focused_label(self) -> None:
        import tempfile

        program = "\n".join(
            (
                "scene 2d",
                'set var(a) = ui_focus_add(10, 10, 100, 40, "Play")',
                'set var(b) = ui_focus_add(120, 10, 100, 40, "Quit")',
                "set var(on) = ui_accessible(1)",
                "set var(focus) = ui_focus_set(var(b))",
                "",
                "fn(draw)",
                "  clear rgba(0, 0, 0, 255)",
                '  say "label " & ui_focus_label()',
                '  say "done"',
                "end",
                "",
            )
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "focus.ANVL"
            source.write_text(program, encoding="utf-8")
            out = root / "focus.wasm"
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
            run = subprocess.run(
                ["node", str(HOST), "--record", str(out)],
                capture_output=True,
                text=True,
                timeout=120,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("label Quit", run.stdout)
        ops = json.loads(run.stdout.strip().splitlines()[-1])
        announce = [op for op in ops if op[0] == "announce"]
        # One announcement for the focus change, not one per frame.
        self.assertEqual(announce, [["announce", "Quit"]])


if __name__ == "__main__":
    unittest.main()
