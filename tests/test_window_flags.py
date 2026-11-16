"""Window flags: always-on-top toggles and fullscreen restore.

Runs a real windowed program and inspects the live Win32 state after each
phase, so a call that merely returns 1 without doing anything fails the test.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_EX_TOPMOST = 0x00000008
WS_POPUP = 0x80000000
MONITOR_DEFAULTTONEAREST = 2
NL = chr(10)

PROGRAM = NL.join(
    (
        "scene 2d",
        "fn(draw)",
        "  if var(step) = 0",
        "    set var(step) = 1",
        '    say "on-top"',
        "    say window_on_top(1)",
        "    wait 0.8",
        '    say "off-top"',
        "    say window_on_top(0)",
        "    wait 0.8",
        '    say "on-full"',
        "    say window_fullscreen(1)",
        "    wait 0.8",
        '    say "off-full"',
        "    say window_fullscreen(0)",
        "    wait 0.5",
        "    stop",
        "  end",
        "end",
        "",
    )
)


def find_window(pid: int):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def window_state(hwnd):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
    ex_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(info)
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    return style, ex_style, rect, info.rcMonitor


class WindowFlagTests(unittest.TestCase):
    def test_topmost_and_fullscreen_change_real_window_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            source = root / "flags.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            out = root / "flags.exe"
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(out)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if build.returncode != 0:
                if "No C compiler found" in build.stderr:
                    self.skipTest("MSVC is not available")
                self.fail(build.stdout + build.stderr)

            process = subprocess.Popen(
                [str(out)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            lines: list[str] = []
            hwnd = None
            try:
                deadline = time.monotonic() + 8
                while hwnd is None and time.monotonic() < deadline:
                    hwnd = find_window(process.pid)
                    time.sleep(0.02)
                self.assertIsNotNone(hwnd, "window did not appear")

                def read_until(marker: str) -> str:
                    while True:
                        line = process.stdout.readline()
                        self.assertNotEqual(line, "", "program ended early")
                        lines.append(line.strip())
                        if line.strip() == marker:
                            return process.stdout.readline().strip()

                self.assertEqual(read_until("on-top"), "1")
                time.sleep(0.2)
                _style, ex_style, _rect, _monitor = window_state(hwnd)
                self.assertTrue(
                    ex_style & WS_EX_TOPMOST,
                    "window_on_top(1) did not set WS_EX_TOPMOST",
                )

                self.assertEqual(read_until("off-top"), "1")
                time.sleep(0.2)
                _style, ex_style, _rect, _monitor = window_state(hwnd)
                self.assertFalse(
                    ex_style & WS_EX_TOPMOST,
                    "window_on_top(0) did not clear WS_EX_TOPMOST",
                )

                normal_rect = window_state(hwnd)[2]
                self.assertEqual(read_until("on-full"), "1")
                time.sleep(0.3)
                style, _ex, rect, monitor = window_state(hwnd)
                self.assertTrue(style & WS_POPUP, "fullscreen did not switch to WS_POPUP")
                self.assertEqual(
                    (rect.left, rect.top, rect.right, rect.bottom),
                    (monitor.left, monitor.top, monitor.right, monitor.bottom),
                    "fullscreen window does not cover the monitor",
                )

                self.assertEqual(read_until("off-full"), "1")
                time.sleep(0.3)
                style, _ex, rect, _monitor = window_state(hwnd)
                self.assertFalse(style & WS_POPUP, "fullscreen was not reverted")
                self.assertEqual(
                    (rect.left, rect.top, rect.right, rect.bottom),
                    (normal_rect.left, normal_rect.top, normal_rect.right, normal_rect.bottom),
                    "window did not return to its previous rectangle",
                )
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()


if __name__ == "__main__":
    unittest.main()
