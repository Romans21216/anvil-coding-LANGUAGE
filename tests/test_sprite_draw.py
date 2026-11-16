"""Sprite tint, flip and rotation, checked against real window pixels.

The runtime letterboxes its 960x600 framebuffer into the client area, so the
test resizes the window until the client is exactly 960x600; the framebuffer
then maps 1:1 and GetPixel reads the pixel the program drew.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import pathlib
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)


def quadrant_bmp() -> bytes:
    """A 2x2, 32-bit BMP: TL red, TR green, BL blue, BR white."""
    width = height = 2
    header = bytearray(54)
    header[0:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + width * height * 4)
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<i", header, 18, width)
    struct.pack_into("<i", header, 22, height)
    struct.pack_into("<H", header, 26, 1)
    struct.pack_into("<H", header, 28, 32)
    struct.pack_into("<I", header, 34, width * height * 4)
    # BMP rows are bottom-up: bottom row (blue, white) first.
    bottom = bytes((255, 0, 0, 255)) + bytes((255, 255, 255, 255))
    top = bytes((0, 0, 255, 255)) + bytes((0, 255, 0, 255))
    return bytes(header) + bottom + top


def quadrant4_bmp() -> bytes:
    """A 4x4, 32-bit BMP with 2x2 quadrants: TL red, TR green, BL blue, BR white."""
    width = height = 4
    header = bytearray(54)
    header[0:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + width * height * 4)
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<i", header, 18, width)
    struct.pack_into("<i", header, 22, height)
    struct.pack_into("<H", header, 26, 1)
    struct.pack_into("<H", header, 28, 32)
    struct.pack_into("<I", header, 34, width * height * 4)

    def rgba(colour: tuple[int, int, int]) -> bytes:
        b, g, r = colour[2], colour[1], colour[0]
        return bytes((b, g, r, 255))

    red, green, blue, white = RED, GREEN, BLUE, WHITE
    rows = []
    for _ in range(2):  # bottom two rows: blue | white
        rows.append(rgba(blue) * 2 + rgba(white) * 2)
    for _ in range(2):  # top two rows: red | green
        rows.append(rgba(red) * 2 + rgba(green) * 2)
    return bytes(header) + b"".join(rows)


PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        'set var(img) = image_load("quad.bmp")',
        "set var(frame) = 0",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  if var(frame) = 5",
        '    say "plain"',
        "  end",
        "  if var(frame) = 35",
        "    set var(f) = image_flip(var(img), 1, 0)",
        '    say "flip"',
        "  end",
        "  if var(frame) = 65",
        "    set var(f2) = image_flip(var(img), 0, 0)",
        "    set var(t) = image_tint(var(img), 128, 128, 128)",
        '    say "tint"',
        "  end",
        "  if var(frame) = 95",
        "    set var(t2) = image_tint(var(img), 255, 255, 255)",
        '    say "rot"',
        "  end",
        "  if var(frame) = 140",
        '    say "done"',
        "    stop",
        "  end",
        "  if var(frame) < 95",
        "    set var(d) = image_draw_scaled(var(img), 10, 10, 4, 4)",
        "  end",
        "  if var(frame) >= 95",
        "    set var(d2) = image_draw_rotated(var(img), 40, 40, 90, 4)",
        "  end",
        "end",
        "",
    )
)


def colourref_to_rgb(value: int) -> tuple[int, int, int]:
    return value & 255, (value >> 8) & 255, (value >> 16) & 255


class WindowReader:
    def __init__(self, pid: int):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        self.user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        self.user32.GetDC.argtypes = [wintypes.HWND]
        self.user32.GetDC.restype = wintypes.HDC
        self.user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        self.gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        self.gdi32.GetPixel.restype = wintypes.DWORD
        self.pid = pid
        self.hwnd = None

    def find(self, deadline: float):
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        @enum_proc
        def visit(hwnd, _unused):
            owner = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == self.pid and self.user32.IsWindowVisible(hwnd):
                found.append(hwnd)
                return False
            return True

        while time.monotonic() < deadline:
            found: list[int] = []
            self.user32.EnumWindows(visit, 0)
            if found:
                self.hwnd = found[0]
                return found[0]
            time.sleep(0.05)
        return None

    def force_client_size(self, width: int, height: int) -> None:
        window_rect = wintypes.RECT()
        client_rect = wintypes.RECT()
        self.user32.GetWindowRect(self.hwnd, ctypes.byref(window_rect))
        self.user32.GetClientRect(self.hwnd, ctypes.byref(client_rect))
        border_x = (window_rect.right - window_rect.left) - (
            client_rect.right - client_rect.left
        )
        border_y = (window_rect.bottom - window_rect.top) - (
            client_rect.bottom - client_rect.top
        )
        self.user32.SetWindowPos(
            self.hwnd,
            ctypes.c_void_p(-1),  # HWND_TOPMOST: an occluded window reads wrong pixels
            60,
            60,
            width + border_x,
            height + border_y,
            0x0004 | 0x0010,  # SWP_NOZORDER is deliberately NOT set
        )
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.user32.GetClientRect(self.hwnd, ctypes.byref(client_rect))
            if (
                client_rect.right - client_rect.left == width
                and client_rect.bottom - client_rect.top == height
            ):
                return
            time.sleep(0.05)
        raise AssertionError(
            f"could not force a {width}x{height} client area; got "
            f"{client_rect.right - client_rect.left}x"
            f"{client_rect.bottom - client_rect.top}"
        )

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        dc = self.user32.GetDC(self.hwnd)
        if not dc:
            raise AssertionError("GetDC failed")
        try:
            return colourref_to_rgb(self.gdi32.GetPixel(dc, x, y))
        finally:
            self.user32.ReleaseDC(self.hwnd, dc)

    def settle(self, expected: tuple[int, int, int], x: int, y: int) -> None:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.pixel(x, y) == expected:
                return
            time.sleep(0.05)
        raise AssertionError(
            f"pixel ({x},{y}) was {self.pixel(x, y)}, expected {expected}"
        )


class SpriteDrawTests(unittest.TestCase):
    def test_tint_flip_and_rotation_paint_expected_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "quad.bmp").write_bytes(quadrant_bmp())
            source = root / "sprite.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "sprite.exe"
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
            try:
                self.assertIsNotNone(reader.find(time.monotonic() + 10), "no window")
                reader.force_client_size(960, 600)

                def wait_for(marker: str) -> None:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        try:
                            if lines.get(timeout=0.2) == marker:
                                return
                        except queue.Empty:
                            continue
                    self.fail(f"marker {marker!r} never arrived")

                wait_for("plain")
                reader.settle(RED, 10, 10)
                self.assertEqual(reader.pixel(12, 10), GREEN)
                self.assertEqual(reader.pixel(10, 12), BLUE)
                self.assertEqual(reader.pixel(12, 12), WHITE)

                wait_for("flip")
                reader.settle(GREEN, 10, 10)
                self.assertEqual(reader.pixel(12, 10), RED)
                self.assertEqual(reader.pixel(10, 12), WHITE)
                self.assertEqual(reader.pixel(12, 12), BLUE)

                wait_for("tint")
                reader.settle((128, 0, 0), 10, 10)
                self.assertEqual(reader.pixel(12, 10), (0, 128, 0))

                wait_for("rot")
                # 90 degrees clockwise: top-left blue, top-right red,
                # bottom-left white, bottom-right green.
                reader.settle(BLUE, 37, 37)
                self.assertEqual(reader.pixel(43, 37), RED)
                self.assertEqual(reader.pixel(37, 43), WHITE)
                self.assertEqual(reader.pixel(43, 43), GREEN)

                wait_for("done")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


REGION_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        'set var(img) = image_load("quad4.bmp")',
        "set var(frame) = 0",
        "set var(rx) = 0",
        "set var(ry) = 0",
        "set var(rw) = 2",
        "set var(rh) = 2",
        "set var(dw) = 4",
        "set var(dh) = 4",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  if var(frame) = 5",
        '    say "tl"',
        "  end",
        "  if var(frame) = 35",
        "    set var(rx) = 2",
        '    say "tr"',
        "  end",
        "  if var(frame) = 65",
        "    set var(ry) = 2",
        '    say "br"',
        "  end",
        "  if var(frame) = 95",
        "    set var(rx) = 0",
        '    say "bl"',
        "  end",
        "  if var(frame) = 125",
        "    set var(ry) = 0",
        "    set var(rw) = 4",
        "    set var(rh) = 2",
        "    set var(dw) = 8",
        "    set var(dh) = 4",
        "    set var(f) = image_flip(var(img), 1, 0)",
        '    say "flip"',
        "  end",
        "  if var(frame) = 155",
        "    set var(f2) = image_flip(var(img), 0, 0)",
        "    set var(bad) = image_draw_region(var(img), 3, 3, 3, 3, 10, 10, 4, 4)",
        '    say "bad"',
        "    say var(bad)",
        "  end",
        "  if var(frame) = 180",
        '    say "done"',
        "    stop",
        "  end",
        "  set var(d) = image_draw_region(var(img), var(rx), var(ry), var(rw), var(rh), 10, 10, var(dw), var(dh))",
        "end",
        "",
    )
)


class SpriteRegionTests(unittest.TestCase):
    def test_atlas_regions_draw_the_requested_cell(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "quad4.bmp").write_bytes(quadrant4_bmp())
            source = root / "region.ANVL"
            source.write_text(REGION_PROGRAM, encoding="utf-8")
            executable = root / "region.exe"
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

                wait_for("tl")
                reader.settle(RED, 11, 11)
                wait_for("tr")
                reader.settle(GREEN, 11, 11)
                wait_for("br")
                reader.settle(WHITE, 11, 11)
                wait_for("bl")
                reader.settle(BLUE, 11, 11)

                wait_for("flip")
                # The top half (red | green) is mirrored inside its region.
                reader.settle(GREEN, 11, 11)
                self.assertEqual(reader.pixel(16, 11), RED)

                wait_for("bad")
                self.assertEqual(next_line(), "0")
                wait_for("done")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    unittest.main()
