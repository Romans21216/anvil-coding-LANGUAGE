"""Execute Anvil-emitted Win32 code and inspect its actual client pixels."""

import ctypes
from ctypes import wintypes
import pathlib
import struct
import subprocess
import sys
import tempfile
import time
import unittest

from compiler.common import CompileError
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


@unittest.skipUnless(sys.platform == "win32", "native Win32 runtime")
class NativeWindowTests(unittest.TestCase):
    def test_direct_2d_scene_pixels_resize_and_close(self):
        source = """\
scene 2d
clear rgba(10, 20, 30, 255)
set var(x) = 20
set var(phase) = 0
set var(elapsed) = 0
set var(drawing) = 0
array positions(1)
fn(width)
  output 40
end
fn(update)
  add var(elapsed) delta()
  if time() >= 0.1 and var(elapsed) >= 0.1
    set var(phase) = compute(120)
  end
end
fn(draw)
  set var(drawing) = 1
  for local(delay) = 1 to 200000
  end
  set array(positions, 0) = var(x)
  display rect(array(positions, 0) + 0.5, 20.5, call fn(width), 30.25) -rgb(200, 80, 40)
  display rect(-10, -10, 15, 15) -rgb(5, 100, 200)
  display rect(var(phase), 100, 10, 10) -rgb(10, 240, 80)
  set var(drawing) = 0
end
"""
        user = ctypes.WinDLL("user32", use_last_error=True)
        gdi = ctypes.WinDLL("gdi32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p,
                                            ctypes.c_void_p, ctypes.c_size_t,
                                            ctypes.POINTER(ctypes.c_size_t)]
        user.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        user.GetGuiResources.restype = wintypes.DWORD
        user.GetDC.argtypes = [wintypes.HWND]
        user.GetDC.restype = wintypes.HDC
        user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        gdi.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi.GetPixel.restype = wintypes.DWORD
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user.EnumWindows.argtypes = [enum_proc, wintypes.LPARAM]

        def find_window(pid):
            found = []

            @enum_proc
            def visit(hwnd, unused):
                owner = wintypes.DWORD()
                user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if owner.value == pid:
                    found.append(hwnd)
                return True

            user.EnumWindows(visit, 0)
            return found[0] if found else None

        def pixel(hwnd, x, y):
            dc = user.GetDC(hwnd)
            self.assertTrue(dc)
            try:
                return gdi.GetPixel(dc, x, y)
            finally:
                user.ReleaseDC(hwnd, dc)

        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "scene.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            executable = pathlib.Path(temp) / "scene.exe"
            generator = NativeCodegen(path, functions, top, variables, arrays)
            image = generator.generate()
            self.assertIn(b"USER32.dll", image)
            self.assertIn(b"GDI32.dll", image)
            self.assertNotIn(b"msvcrt", image.lower())
            executable.write_bytes(image)
            process = subprocess.Popen([str(executable)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process_handle = kernel.OpenProcess(0x410, False, process.pid)
            self.assertTrue(process_handle)
            pe = struct.unpack_from("<I", image, 0x3C)[0]
            section_count = struct.unpack_from("<H", image, pe + 6)[0]
            optional_size = struct.unpack_from("<H", image, pe + 20)[0]
            image_base = struct.unpack_from("<Q", image, pe + 48)[0]
            sections = pe + 24 + optional_size
            data_rva = next(
                struct.unpack_from("<I", image, section + 12)[0]
                for section in range(sections, sections + section_count * 40, 40)
                if image[section:section + 8].rstrip(b"\0") == b".data"
            )
            drawing_address = image_base + data_rva + generator._data_offsets["drawing"]
            hwnd = None
            positioned = False
            try:
                deadline = time.monotonic() + 8
                colour = 200 | (80 << 8) | (40 << 16)
                while time.monotonic() < deadline:
                    self.assertIsNone(process.poll(), "native scene terminated before painting")
                    hwnd = find_window(process.pid)
                    if hwnd and not positioned:
                        self.assertTrue(user.SetWindowPos(hwnd, -1, 80, 80, 960, 640, 0x10))
                        positioned = True
                    if hwnd and pixel(hwnd, 20, 20) == colour:
                        break
                    time.sleep(0.05)
                self.assertTrue(hwnd, "native window did not appear")
                self.assertEqual(pixel(hwnd, 20, 20), colour)
                self.assertEqual(pixel(hwnd, 60, 50), colour)  # floor/ceil edges
                background = 10 | (20 << 8) | (30 << 16)
                self.assertEqual(pixel(hwnd, 61, 50), background)
                self.assertEqual(pixel(hwnd, 0, 0), 5 | (100 << 8) | (200 << 16))
                self.assertEqual(pixel(hwnd, 5, 5), background)
                marker = 10 | (240 << 8) | (80 << 16)
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and pixel(hwnd, 120, 100) != marker:
                    time.sleep(0.02)
                self.assertEqual(pixel(hwnd, 120, 100), marker)
                self.assertEqual(pixel(hwnd, 0, 100), background)
                # Inspect a live draw phase rather than relying on a lucky screenshot.
                # The old visible-HDC path showed background here before the rect call.
                samples = 0
                deadline = time.monotonic() + 0.3
                while time.monotonic() < deadline:
                    drawing = ctypes.c_double()
                    size = ctypes.c_size_t()
                    self.assertTrue(kernel.ReadProcessMemory(
                        process_handle, drawing_address, ctypes.byref(drawing),
                        ctypes.sizeof(drawing), ctypes.byref(size)))
                    if drawing.value == 1:
                        self.assertEqual(pixel(hwnd, 20, 20), colour,
                                         "partially drawn frame became visible")
                        samples += 1
                    time.sleep(0.001)
                self.assertGreater(samples, 0, "did not observe the deliberate slow draw")
                gdi_before = user.GetGuiResources(process_handle, 0)
                self.assertGreater(gdi_before, 0)
                # Keep the sampled client pixels visible on the primary display.
                self.assertTrue(user.SetWindowPos(hwnd, -1, 80, 80, 1200, 800, 0x10))
                rect = wintypes.RECT()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    user.GetClientRect(hwnd, ctypes.byref(rect))
                    if rect.right > 1000 and pixel(hwnd, rect.right - 2, rect.bottom - 2) == background:
                        break
                    time.sleep(0.05)
                self.assertGreater(rect.right, 1000)
                self.assertEqual(pixel(hwnd, rect.right - 2, rect.bottom - 2), background)
                self.assertEqual(pixel(hwnd, 20, 20), colour)
                for width, height in ((900, 650), (1100, 700), (850, 600), (1200, 800)):
                    self.assertTrue(user.SetWindowPos(hwnd, -1, 80, 80, width, height, 0x10))
                    time.sleep(0.05)
                self.assertLessEqual(user.GetGuiResources(process_handle, 0), gdi_before + 2,
                                     "resizing leaked GDI bitmaps or device contexts")
                user.PostMessageW(hwnd, 0x10, 0, 0)  # WM_CLOSE
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 0, (stdout, stderr))
                self.assertEqual(stdout, b"")
            finally:
                kernel.CloseHandle(process_handle)
                if process.poll() is None:
                    if hwnd:
                        user.PostMessageW(hwnd, 0x10, 0, 0)
                    try:
                        process.communicate(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.communicate()

    def test_backbuffer_allocation_failure_is_controlled(self):
        source = "scene 2d\nfn(draw)\n display rect(10,10,20,20)\nend\n"
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "failure.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            generator = NativeCodegen(path, functions, top, variables, arrays)
            image = bytearray(generator.generate())
            pe = struct.unpack_from("<I", image, 0x3C)[0]
            sections = pe + 24 + struct.unpack_from("<H", image, pe + 20)[0]
            text_raw = struct.unpack_from("<I", image, sections + 20)[0]
            call = next(offset - 2 for offset, target in generator.code.fixups
                        if target == "iat:CreateCompatibleBitmap")
            # Simulate a NULL allocation result at the emitted API call itself.
            image[text_raw + call:text_raw + call + 6] = b"\x31\xc0\x90\x90\x90\x90"
            executable = pathlib.Path(temp) / "failure.exe"
            executable.write_bytes(image)
            result = subprocess.run([str(executable)], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, b"Anvil native painting error\n")

    def test_unsupported_native_graphics_have_compile_diagnostics(self):
        cases = [
            ("fn(main)\n output held(A)\nend\n", "held() requires native scene 2d"),
            ("scene 2d\nfn(draw)\n output held()\nend\n", "expects one numeric key argument"),
            ("scene 2d\nfn(draw)\n output pressed(A, B)\nend\n", "expects one numeric key argument"),
            ("scene 3d\nfn(draw)\nend\n", "one scene 2d"),
            ("scene 2d\nfn(draw, x)\nend\n", "fn(draw) with no parameters"),
            ("scene 2d\nfn(update, value)\nend\nfn(draw)\nend\n", "fn(update) cannot have parameters"),
            ("scene 2d\nfn(draw)\n display plane(0,0,4,4,5)\nend\n", "display rect, circle or line only"),
            ("scene 2d\nclear rgba(0,0,0,20)\nfn(draw)\nend\n", "alpha 255"),
        ]
        for source, diagnostic in cases:
            with self.subTest(diagnostic=diagnostic), tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp) / "unsupported.ANVL"
                path.write_text(source, encoding="utf-8")
                functions, top, variables, arrays = parse(path, source)
                with self.assertRaisesRegex(CompileError, diagnostic.replace("(", r"\(").replace(")", r"\)")):
                    NativeCodegen(path, functions, top, variables, arrays).generate()
