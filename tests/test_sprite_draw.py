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


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


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
        self.gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(BITMAPINFO),
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_void_p),
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        self.gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        self.gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self.gdi32.BitBlt.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
        ]
        self.gdi32.BitBlt.restype = wintypes.BOOL
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

    def raise_window(self) -> None:
        """Bring the window to the top without moving or resizing it."""
        self.user32.SetWindowPos(
            self.hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010
        )

    def pixel(self, x: int, y: int) -> tuple[int, int, int]:
        dc = self.user32.GetDC(self.hwnd)
        if not dc:
            raise AssertionError("GetDC failed")
        try:
            return colourref_to_rgb(self.gdi32.GetPixel(dc, x, y))
        finally:
            self.user32.ReleaseDC(self.hwnd, dc)

    def grab(
        self, left: int, top: int, right: int, bottom: int
    ) -> tuple[int, int, bytes]:
        """Capture a client rectangle as top-down BGRA bytes in one BitBlt."""
        width = right - left
        height = bottom - top
        if width <= 0 or height <= 0:
            raise AssertionError("empty capture rectangle")
        dc = self.user32.GetDC(self.hwnd)
        if not dc:
            raise AssertionError("GetDC failed")
        mem = self.gdi32.CreateCompatibleDC(dc)
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        bitmap = self.gdi32.CreateDIBSection(
            dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0
        )
        if not bitmap:
            self.gdi32.DeleteDC(mem)
            self.user32.ReleaseDC(self.hwnd, dc)
            raise AssertionError("CreateDIBSection failed")
        old = self.gdi32.SelectObject(mem, bitmap)
        try:
            if not self.gdi32.BitBlt(mem, 0, 0, width, height, dc, left, top, 0x00CC0020):
                raise AssertionError("BitBlt failed")
            raw = ctypes.string_at(bits, width * height * 4)
        finally:
            self.gdi32.SelectObject(mem, old)
            self.gdi32.DeleteObject(bitmap)
            self.gdi32.DeleteDC(mem)
            self.user32.ReleaseDC(self.hwnd, dc)
        return width, height, raw

    def bounding_box(
        self,
        left: int,
        top: int,
        right: int,
        bottom: int,
        background: tuple[int, int, int] = (0, 0, 0),
    ) -> tuple[int, int, int, int] | None:
        """Bounding box of pixels that differ from `background` in a region."""
        width, height, raw = self.grab(left, top, right, bottom)
        back_b, back_g, back_r = background[2], background[1], background[0]
        min_x = min_y = None
        max_x = max_y = -1
        for y in range(height):
            row = y * width * 4
            for x in range(width):
                offset = row + x * 4
                if (
                    raw[offset] != back_b
                    or raw[offset + 1] != back_g
                    or raw[offset + 2] != back_r
                ):
                    if min_x is None or x < min_x:
                        min_x = x
                    if min_y is None or y < min_y:
                        min_y = y
                    if x > max_x:
                        max_x = x
                    if y > max_y:
                        max_y = y
        if min_x is None or min_y is None:
            return None
        return (left + min_x, top + min_y, left + max_x, top + max_y)

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
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
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
                reader.settle(GREEN, 12, 10)
                reader.settle(BLUE, 10, 12)
                reader.settle(WHITE, 12, 12)

                wait_for("flip")
                reader.settle(GREEN, 10, 10)
                reader.settle(RED, 12, 10)
                reader.settle(WHITE, 10, 12)
                reader.settle(BLUE, 12, 12)

                wait_for("tint")
                reader.settle((128, 0, 0), 10, 10)
                reader.settle((0, 128, 0), 12, 10)

                wait_for("rot")
                # 90 degrees clockwise: top-left blue, top-right red,
                # bottom-left white, bottom-right green.
                reader.settle(BLUE, 37, 37)
                reader.settle(RED, 43, 37)
                reader.settle(WHITE, 37, 43)
                reader.settle(GREEN, 43, 43)

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
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
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
                reader.settle(RED, 16, 11)

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
