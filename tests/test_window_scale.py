"""Display scaling: the window follows the monitor DPI and can be resized (8.14).

The framebuffer stays 960x600 and is letterboxed, so `window_scale` changes the
client area only. The test checks the reported factor against the DPI the OS
reports for the real window, then watches the client rect shrink to 480x300 at
scale 0.5 and return to 960x600.
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
sys.path.insert(0, str(ROOT / "tests"))

from test_sprite_draw import WindowReader  # noqa: E402

PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(10, 12, 18, 255)",
        "set var(frame) = 0",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  if var(frame) = 3",
        '    say "dpi " & dpi_scale()',
        "  end",
        "  if var(frame) = 30",
        '    say "prev " & window_scale(0.5)',
        "  end",
        "  if var(frame) = 45",
        '    say "same " & window_scale(0.5)',
        "  end",
        "  if var(frame) = 90",
        '    say "back " & window_scale(1)',
        "  end",
        "  if var(frame) = 150",
        "    stop",
        "  end",
        "end",
        "",
    )
)


def window_dpi(hwnd: int) -> float:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        get_dpi = user32.GetDpiForWindow
    except AttributeError:  # pragma: no cover - older Windows
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        hdc = user32.GetDC(wintypes.HWND(hwnd))
        dpi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        user32.ReleaseDC(wintypes.HWND(hwnd), hdc)
        return dpi / 96.0
    get_dpi.argtypes = [wintypes.HWND]
    get_dpi.restype = wintypes.UINT
    dpi = get_dpi(wintypes.HWND(hwnd))
    if not dpi:  # pragma: no cover - pre-1607 or a stale handle
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        hdc = user32.GetDC(wintypes.HWND(hwnd))
        dpi = gdi32.GetDeviceCaps(hdc, 88)
        user32.ReleaseDC(wintypes.HWND(hwnd), hdc)
    return dpi / 96.0


class WindowScaleTests(unittest.TestCase):
    def test_dpi_and_window_scale(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "scale.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "scale.exe"
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)

            process = subprocess.Popen(
                [str(executable)],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            reader = WindowReader(process.pid)
            reader.find(time.monotonic() + 10)
            # Read the DPI while the window is alive; the handle is invalid once
            # the program exits.
            expected_dpi = window_dpi(reader.hwnd)
            seen: list[tuple[int, int]] = []
            start = time.monotonic()
            # Sample until the program exits rather than for a fixed time: the
            # frame clock decides when each resize happens, not the test.
            while process.poll() is None and time.monotonic() - start < 8.0:
                try:
                    left, top, right, bottom = reader.client_rect()
                except Exception:
                    # The window can close between the poll and the query; the
                    # sizes sampled so far are still the evidence.
                    break
                size = (right - left, bottom - top)
                if not seen or seen[-1] != size:
                    seen.append(size)
                time.sleep(0.08)
            out, err = process.communicate(timeout=40)
            self.assertEqual(process.returncode, 0, err)

            values: dict[str, float] = {}
            for line in out.splitlines():
                key, _, value = line.partition(" ")
                if key in ("dpi", "prev", "same", "back"):
                    values[key] = float(value)
            self.assertEqual(sorted(values), ["back", "dpi", "prev", "same"], out)
            # The program's factor must match what Windows reports for its window.
            self.assertAlmostEqual(values["dpi"], expected_dpi, places=3)
            self.assertGreater(values["dpi"], 0.5)
            self.assertEqual(values["prev"], 1.0)
            self.assertEqual(values["same"], 0.5)
            self.assertEqual(values["back"], 0.5)
            # Client area: full size, half size, full size again.
            self.assertEqual(seen, [(960, 600), (480, 300), (960, 600)], seen)


if __name__ == "__main__":
    unittest.main()
