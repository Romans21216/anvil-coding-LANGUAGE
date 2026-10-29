"""Pixel and lifetime evidence for Anvil-written native drawing kernels."""

import ctypes
from ctypes import wintypes
import pathlib
import subprocess
import sys
import tempfile
import unittest

from compiler.common import CompileError
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse
from tests.native_app import NativeApp


@unittest.skipUnless(sys.platform == "win32", "own-window native rendering")
class NativeDrawingTests(unittest.TestCase):
    def prepare_pixels(self, app):
        app.user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        app.user.InvalidateRect.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.BOOL]
        app.user.GetDC.argtypes = [wintypes.HWND]
        app.user.GetDC.restype = wintypes.HDC
        app.user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        gdi = ctypes.WinDLL("gdi32")
        gdi.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi.GetPixel.restype = wintypes.DWORD
        self.assertTrue(app.user.SetWindowPos(app.hwnd, -1, 80, 80, 300, 220, 0x10))
        self.assertTrue(app.user.InvalidateRect(app.hwnd, None, False))
        app.send(0xF)
        return gdi

    def test_circle_pixels_match_membership_with_fractional_zero_negative_and_clipped_radii(self):
        cases = [(20, 18, 9), (20.25, 18.75, 9.125), (3.5, 2.25, -8.5),
                 (20, 18, 0), (20.25, 18, 0), (1e-200, 1e-200, 0),
                 (-30, 18, 9), (20, 18, 0.25), (1073741824, 0, 1073741824),
                 (0, 0, 1073741824)]
        foreground, background = 220 | (80 << 8) | (40 << 16), 3 | (5 << 8) | (7 << 16)
        for x, y, radius in cases:
            x, y, radius = float(x), float(y), float(radius)
            with self.subTest(x=x, y=y, radius=radius):
                source = f"scene 2d\nclear rgba(3,5,7,255)\nfn(draw)\n display circle({x},{y},{radius}) -rgb(220,80,40)\nend\n"
                with NativeApp(source) as app:
                    gdi = self.prepare_pixels(app)
                    dc = app.user.GetDC(app.hwnd)
                    self.assertTrue(dc)
                    try:
                        for py in range(38):
                            for px in range(42):
                                inside = (px-x)*(px-x) + (py-y)*(py-y) <= radius*radius
                                self.assertEqual(gdi.GetPixel(dc, px, py), foreground if inside else background,
                                                 (x, y, radius, px, py))
                    finally:
                        app.user.ReleaseDC(app.hwnd, dc)
                self.assertEqual(app.result[0], 0)

    def test_evaluation_order_array_inputs_composition_resize_and_resource_reuse(self):
        source = '''scene 2d
clear rgba(3,5,7,255)
array values(6)
set var(sequence) = 0
fn(next)
 add var(sequence) 1
 output array(values,var(sequence)-1)
end
fn(draw)
 array local_values(1)
 set array(local_values,0) = 14
 set array(values,0) = 240
 set array(values,1) = 80
 set array(values,2) = array(local_values,0)
 set array(values,3) = 300
 set array(values,4) = -5
 set array(values,5) = 40.9
 set var(sequence) = 0
 display circle(call fn(next),call fn(next),call fn(next)) -rgb(call fn(next),call fn(next),call fn(next))
 display rect(240,80,3,3) -rgb(10,20,30)
 display circle(40,40,3)
end
'''
        with NativeApp(source) as app:
            gdi = self.prepare_pixels(app)
            self.assertEqual(app.read("sequence"), 6)
            dc = app.user.GetDC(app.hwnd)
            try:
                self.assertEqual(gdi.GetPixel(dc, 240, 80), 10 | (20 << 8) | (30 << 16))
                self.assertEqual(gdi.GetPixel(dc, 239, 80), 255 | (40 << 16))
                self.assertEqual(gdi.GetPixel(dc, 40, 40), 0xFFFFFF)
            finally:
                app.user.ReleaseDC(app.hwnd, dc)
            app.user.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            count = app.user.GetGuiResources(app.process_handle, 0)
            for frame in range(60):
                width = 180 if frame % 2 else 300
                self.assertTrue(app.user.SetWindowPos(app.hwnd, -1, 80, 80, width, 220, 0x10))
                self.assertTrue(app.user.InvalidateRect(app.hwnd, None, False))
                app.send(0xF)
            self.assertLessEqual(app.user.GetGuiResources(app.process_handle, 0), count + 2)
        self.assertEqual(app.result[0], 0)

    def test_line_pixels_clipping_rounding_thickness_and_degenerate_segments(self):
        cases = [(2,2,34,25,0), (34,25,2,2,0), (5.5,5.5,5.5,5.5,0),
                 (0.5,0.5,35.5,20.5,1), (10,2,10,34,-2), (2,10,35,10,2.2),
                 (-100,12,10000,12,2.2), (-1e9,-1e9,1e9,1e9,0),
                 (-30,-10,-1,-10,3), (1e-310,-1e-310,1e-310,1e-310,0),
                 (20,20,21,22,1e308)]
        foreground, background = 220 | (80 << 8) | (40 << 16), 3 | (5 << 8) | (7 << 16)
        for values in cases:
            with self.subTest(values=values):
                source = "scene 2d\nclear rgba(3,5,7,255)\nfn(draw)\n display line(" + ",".join(map(str,values)) + ") -rgb(220,80,40)\nend\n"
                with NativeApp(source) as app:
                    gdi = self.prepare_pixels(app)
                    rectangle = wintypes.RECT()
                    app.user.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
                    self.assertTrue(app.user.GetClientRect(app.hwnd, ctypes.byref(rectangle)))
                    pixels = self.reference_line(values, rectangle.right, rectangle.bottom)
                    dc = app.user.GetDC(app.hwnd)
                    try:
                        for py in range(38):
                            for px in range(42):
                                self.assertEqual(gdi.GetPixel(dc, px, py), foreground if (px,py) in pixels else background,
                                                 (values, px, py))
                    finally:
                        app.user.ReleaseDC(app.hwnd, dc)
                self.assertEqual(app.result[0], 0)

    @staticmethod
    def reference_line(values, width, height):
        import math
        x1,y1,x2,y2,thickness = map(float, values)
        dx,dy = x2-x1,y2-y1
        enter,leave = 0.0,1.0
        for p,q in ((-dx,x1), (dx,width-1-x1), (-dy,y1), (dy,height-1-y1)):
            if p == 0:
                if q < 0:
                    return set()
            else:
                ratio = q/p
                if p < 0:
                    enter = max(enter,ratio)
                else:
                    leave = min(leave,ratio)
                if enter > leave:
                    return set()
        ax,ay = max(0,min(width-1,x1+dx*enter)),max(0,min(height-1,y1+dy*enter))
        bx,by = max(0,min(width-1,x1+dx*leave)),max(0,min(height-1,y1+dy*leave))
        x,y,target_x,target_y = round(ax),round(ay),round(bx),round(by)
        dx,dy,sx,sy = abs(target_x-x),-abs(target_y-y),1 if ax<bx else -1,1 if ay<by else -1
        error = dx+dy
        radius = min(width,max(0,math.ceil(thickness*0.5)))
        pixels = set()
        while True:
            # Only sampled pixels are needed, including very large thicknesses.
            for py in range(max(0,y-radius),min(37,y+radius)+1):
                for px in range(max(0,x-radius),min(41,x+radius)+1):
                    pixels.add((px,py))
            if (x,y) == (target_x,target_y):
                return pixels
            twice = 2*error
            if twice >= dy:
                error += dy
                x += sx
            if twice <= dx:
                error += dx
                y += sy

    def test_line_default_thickness_and_circle_line_composition(self):
        source = '''scene 2d
fn(draw)
 display circle(30,30,10) -rgb(200,0,0)
 display line(20,30,40,30) -rgb(0,200,0)
 display circle(30,30,0) -rgb(0,0,200)
end
'''
        with NativeApp(source) as app:
            gdi = self.prepare_pixels(app)
            dc = app.user.GetDC(app.hwnd)
            try:
                self.assertEqual(gdi.GetPixel(dc, 30,30), 200 << 16)
                self.assertEqual(gdi.GetPixel(dc, 30,31), 200 << 8)
                self.assertEqual(gdi.GetPixel(dc, 30,32), 200)
            finally:
                app.user.ReleaseDC(app.hwnd,dc)
        self.assertEqual(app.result[0],0)

    def test_invalid_ranges_report_actual_unicode_include_location(self):
        cases = [("circle", [0,0,1], 3), ("line", [0,0,1,1], 4)]
        for primitive, initial, count in cases:
            for index in range(count):
                for value in (-1073741825,1073741825):
                    with self.subTest(primitive=primitive,index=index,value=value), tempfile.TemporaryDirectory() as temp:
                        root = pathlib.Path(temp)
                        library = root / "shapes_\u03bb.ANVL"
                        arguments = list(initial)
                        arguments[index] = value
                        library.write_text("fn(draw)\n display " + primitive + "(" + ",".join(map(str,arguments)) + ")\nend\n", encoding="utf-8")
                        path = root / "main.ANVL"
                        source = 'scene 2d\ninclude "shapes_\u03bb.ANVL"\n'
                        path.write_text(source, encoding="utf-8")
                        image = NativeCodegen(path, *parse(path, source)).generate()
                        exe = root / "test.exe"
                        exe.write_bytes(image)
                        result = subprocess.run([str(exe)], capture_output=True, timeout=5)
                        self.assertEqual(result.returncode, 2)
                        self.assertEqual(result.stdout.decode("utf-8"), f"Anvil native {primitive} range error at line 2 ({library})\n")

    def test_invalid_shapes_have_source_diagnostics_and_unused_kernel_is_omitted(self):
        for drawing, message in [("circle(0,0)", "expects x,y,radius"),
                                 ("circle(0,0,1) -rgba(0,0,0)", "rgba expects four channels"),
                                 ("circle(0,0,1) -rot(0,0,0)", "unsupported native circle modifier"),
                                 ("line(1,2,3)", "expects x1,y1,x2,y2"),
                                 ("line(1,2,3,4,5,6)", "expects x1,y1,x2,y2")]:
            with self.subTest(drawing=drawing), tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp) / "input.ANVL"
                source = f"scene 2d\nfn(draw)\n display {drawing}\nend\n"
                path.write_text(source, encoding="utf-8")
                with self.assertRaisesRegex(CompileError, message):
                    NativeCodegen(path, *parse(path, source)).generate()
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "rect.ANVL"
            source = "scene 2d\nfn(draw)\n display rect(1,1,1,1)\nend\n"
            path.write_text(source, encoding="utf-8")
            generator = NativeCodegen(path, *parse(path, source))
            generator.generate()
            self.assertNotIn("function:_anvil_native_circle", generator.code.labels)
            self.assertNotIn("function:_anvil_native_line", generator.code.labels)
