"""Actual native text pixels against an independent GDI reference surface."""

import ctypes
from ctypes import wintypes
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from compiler.common import CompileError
from compiler.native_codegen import NativeCodegen
from compiler.native_x64 import X64Code
from compiler.parser import parse
from tests.native_app import NativeApp
from tests import test_native_drawing as drawing_tests


@unittest.skipUnless(sys.platform == "win32", "own-window native Unicode text")
class NativeTextTests(unittest.TestCase):
    def reference(self, app, gdi, text):
        gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi.CreateCompatibleDC.restype = wintypes.HDC
        gdi.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        gdi.SelectObject.restype = wintypes.HANDLE
        gdi.CreateSolidBrush.argtypes = [wintypes.DWORD]
        gdi.CreateSolidBrush.restype = wintypes.HBRUSH
        gdi.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi.DeleteDC.argtypes = [wintypes.HDC]
        gdi.CreateFontW.argtypes = [ctypes.c_int]*5 + [wintypes.DWORD]*8 + [wintypes.LPCWSTR]
        gdi.CreateFontW.restype = wintypes.HANDLE
        gdi.SetTextColor.argtypes = [wintypes.HDC,wintypes.DWORD]
        gdi.SetBkMode.argtypes = [wintypes.HDC,ctypes.c_int]
        gdi.TextOutW.argtypes = [wintypes.HDC,ctypes.c_int,ctypes.c_int,wintypes.LPCWSTR,ctypes.c_int]
        app.user.FillRect.argtypes = [wintypes.HDC,ctypes.POINTER(wintypes.RECT),wintypes.HBRUSH]
        visible = app.user.GetDC(app.hwnd)
        dc = gdi.CreateCompatibleDC(visible)
        bitmap = gdi.CreateCompatibleBitmap(visible,280,160)
        self.assertTrue(dc and bitmap)
        old_bitmap = gdi.SelectObject(dc,bitmap)
        font = gdi.CreateFontW(20,0,0,0,600,0,0,0,1,0,0,5,0,"Segoe UI")
        self.assertTrue(font)
        old_font = gdi.SelectObject(dc,font)
        brushes = []
        try:
            for rect,colour in [((0,0,280,160),3 | (5<<8) | (7<<16)),
                                ((10,10,250,70),30 | (60<<8) | (90<<16))]:
                brush = gdi.CreateSolidBrush(colour)
                brushes.append(brush)
                self.assertTrue(app.user.FillRect(dc,ctypes.byref(wintypes.RECT(*rect)),brush))
            self.assertTrue(gdi.SetBkMode(dc,1))
            gdi.SetTextColor(dc,220 | (170<<8) | (80<<16))
            self.assertTrue(gdi.TextOutW(dc,20,20,text,len(text.encode("utf-16-le"))//2))
            changed = 0
            for y in range(90):
                for x in range(260):
                    actual, expected = gdi.GetPixel(visible,x,y),gdi.GetPixel(dc,x,y)
                    self.assertEqual(actual,expected,(text,x,y))
                    if 20 <= x < 240 and 20 <= y < 45 and expected != (30 | (60<<8) | (90<<16)):
                        changed += 1
            self.assertGreater(changed,0,"reference and native text must both draw visible glyphs")
        finally:
            gdi.SelectObject(dc,old_font)
            gdi.SelectObject(dc,old_bitmap)
            gdi.DeleteObject(font)
            gdi.DeleteObject(bitmap)
            for brush in brushes:
                gdi.DeleteObject(brush)
            gdi.DeleteDC(dc)
            app.user.ReleaseDC(app.hwnd,visible)

    def test_unicode_quoted_modifier_literals_and_transparent_pixels(self):
        for text in ["Anvil \u03bb \u03a9", 'A ") -rgb(1,2,3) # fn(fake) \\"', "Anvil \U0001f642"]:
            with self.subTest(text=text):
                source = ('scene 2d\nclear rgba(3,5,7,255)\nfn(draw)\n'
                          ' display rect(10,10,240,60) -rgb(30,60,90)\n'
                          f' display text({json.dumps(text,ensure_ascii=False)}) -rgb(220,170,80) -l(20.75,20.25)\nend\n')
                with NativeApp(source) as app:
                    gdi = drawing_tests.NativeDrawingTests.prepare_pixels(self,app)
                    self.reference(app,gdi,text)
                self.assertEqual(app.result[0],0)

    def test_argument_order_empty_extreme_positions_and_font_reuse(self):
        source = '''scene 2d
set var(sequence) = 0
set var(before_mode) = 0
set var(before_colour) = 0
set var(before_font) = 0
set var(after_mode) = 0
set var(after_colour) = 0
set var(after_font) = 0
array args(5)
fn(next)
 add var(sequence) 1
 output array(args,var(sequence)-1)
end
fn(draw)
set array(args,0) = 20
set array(args,1) = 20
set array(args,2) = 300
set array(args,3) = -5
set array(args,4) = 40.75
 set var(sequence) = 0
 display text("Anvil") -l(call fn(next),call fn(next)) -rgb(call fn(next),call fn(next),call fn(next))
 display text("") -l(0,0)
 display text("offscreen") -l(1073741824,-1073741824)
end
'''
        def inspect_state(generator):
            # Only this test PE gains telemetry around the real draw function.
            c,w = generator.code,generator._window
            c.labels["test:actual_draw"] = c.labels.pop("function:draw")
            c.label("function:draw")
            w.frame(0x28)
            for phase in ("before","after"):
                for api,field in (("GetBkMode","mode"),("GetTextColor","colour"),("GetCurrentObject","font")):
                    c.rip_int(1,w.hdc)
                    if field == "font":
                        c.mov_imm(2,6)  # OBJ_FONT
                    c.rip_call_import(api)
                    c.bytes(b"\xf2\x48\x0f\x2a\xc0")
                    c.rip_store_data(0,generator._data_offsets[f"{phase}_{field}"])
                if phase == "before":
                    c.call("test:actual_draw")
            w.return_frame(0x28)
            imports = generator.IMPORTS+w.imports+[("GDI32.dll",name) for name in
                                                 ("GetBkMode","GetTextColor","GetCurrentObject")]
            return generator._build(imports)
        with NativeApp(source,instrument=inspect_state) as app:
            gdi = drawing_tests.NativeDrawingTests.prepare_pixels(self,app)
            self.assertEqual(app.read("sequence"),5)
            for field in ("mode","colour","font"):
                self.assertEqual(app.read(f"before_{field}"),app.read(f"after_{field}"),field)
            self.assertEqual(app.read("before_mode"),2)
            self.assertGreater(app.read("before_font"),0)
            app.user.GetGuiResources.argtypes = [wintypes.HANDLE,wintypes.DWORD]
            before = app.user.GetGuiResources(app.process_handle,0)
            self.assertGreater(before,0)
            for frame in range(80):
                app.user.InvalidateRect(app.hwnd,None,False)
                app.send(0xF)
            self.assertLessEqual(app.user.GetGuiResources(app.process_handle,0),before+1)
            dc = app.user.GetDC(app.hwnd)
            try:
                self.assertTrue(any(gdi.GetPixel(dc,x,y) != 11 | (16<<8) | (27<<16)
                                    for y in range(20,40) for x in range(20,70)))
            finally:
                app.user.ReleaseDC(app.hwnd,dc)
        self.assertEqual(app.result[0],0)

    def test_font_and_draw_failures_are_controlled(self):
        source = 'scene 2d\nfn(draw)\n display text("Anvil") -l(10,10)\nend\n'
        original = X64Code.rip_call_import
        for failed in ("CreateFontW","TextOutW"):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp)/"text.ANVL"
                path.write_text(source,encoding="utf-8")
                def call(code,name):
                    if name == failed:
                        code.mov_imm(0,0)
                    else:
                        original(code,name)
                with mock.patch.object(X64Code,"rip_call_import",call):
                    image = NativeCodegen(path,*parse(path,source)).generate()
                exe = path.with_suffix(".exe")
                exe.write_bytes(image)
                result = subprocess.run([str(exe)],capture_output=True,timeout=5)
                self.assertEqual(result.returncode,2)
                self.assertEqual(result.stdout,b"Anvil native text error\n")

    def test_literal_limits_modifiers_and_unsupported_strings_have_locations(self):
        cases = [('text("hello")','requires -l'),
                 ('text("hello") -l(1)','-l expects x,y'),
                 ('text("hello") -l(1,2) -l(3,4)','repeated native text l'),
                 ('text("hello") -l(1,2) -rgba(1,2,3,4)','alpha 255'),
                 ('text("hello") -l(1,2) -rgb(1,2,3) -rgba(1,2,3,255)','repeated native text colour'),
                 ('text("hello") -l(1,2) -rotate(0,0,0)','expects one string literal'),
                 ('text("value" + 2) -l(1,2)','dynamic strings'),
                 ('text("\\n") -l(1,2)','control characters'),
                 ('text("\\ud800") -l(1,2)','invalid native text literal'),
                 ('text("'+('a'*8193)+'") -l(1,2)','exceeds 8192'),
                 ('text('+json.dumps("\U0001f642"*4097)+') -l(1,2)','exceeds 8192')]
        for command,message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp)/"invalid.ANVL"
                source = f"scene 2d\nfn(draw)\n display {command}\nend\n"
                path.write_text(source,encoding="utf-8")
                with self.assertRaises(CompileError) as caught:
                    NativeCodegen(path,*parse(path,source)).generate()
                self.assertIn(f"{path}:3:",str(caught.exception))
                self.assertIn(message,str(caught.exception))

    def test_range_errors_keep_unicode_include_location_and_literal_boundary_works(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            library = root / "labels_\u03bb.ANVL"
            path = root / "main.ANVL"
            source = 'scene 2d\ninclude "labels_\u03bb.ANVL"\n'
            path.write_text(source,encoding="utf-8")
            for x,y in ((1073741825,0),(-1073741825,0),(0,1073741825),(0,-1073741825)):
                library.write_text(f'fn(draw)\n display text("hello") -l({x},{y})\nend\n',encoding="utf-8")
                exe = root / "text.exe"
                exe.write_bytes(NativeCodegen(path,*parse(path,source)).generate())
                result = subprocess.run([str(exe)],capture_output=True,timeout=5)
                self.assertEqual(result.returncode,2)
                self.assertEqual(result.stdout.decode("utf-8"),f"Anvil native text range error at line 2 ({library})\n")
        source = 'scene 2d\nfn(draw)\n display text("'+('a'*8192)+'") -l(1,1)\nend\n'
        with NativeApp(source) as app:
            drawing_tests.NativeDrawingTests.prepare_pixels(self,app)
        self.assertEqual(app.result[0],0)

    def test_unused_imports_and_duplicate_utf16_pool(self):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp)/"pool.ANVL"
            source = 'scene 2d\nfn(draw)\n display text("same") -l(1,1)\n display text("same") -l(2,2)\nend\n'
            path.write_text(source,encoding="utf-8")
            generator = NativeCodegen(path,*parse(path,source))
            image = generator.generate()
            self.assertEqual(len(generator._window.text.literals),1)
            self.assertIn(b"TextOutW",image)
            plain = 'scene 2d\nfn(draw)\n display rect(1,1,1,1)\nend\n'
            path.write_text(plain,encoding="utf-8")
            self.assertNotIn(b"TextOutW",NativeCodegen(path,*parse(path,plain)).generate())
