"""Execute pixel blending, bounded writes and GDI/CPU synchronization paths."""

import ctypes
from ctypes import wintypes
import math
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from compiler.native_codegen import NativeCodegen
from compiler.native_surface import NativeSurface
from compiler.native_x64 import X64Code
from compiler.parser import parse
from tests.native_app import NativeApp
from tests import test_native_drawing as drawing_tests


@unittest.skipUnless(sys.platform == "win32", "Anvil native pixel surfaces")
class NativeSurfaceTests(unittest.TestCase):
    @staticmethod
    def blend(source, destination, alpha):
        return tuple((s*alpha+d*(255-alpha))//255 for s,d in zip(source,destination))

    @staticmethod
    def colour(rgb):
        return rgb[0] | (rgb[1]<<8) | (rgb[2]<<16)

    def test_every_alpha_and_source_byte_against_integer_reference(self):
        source = '''scene 2d
clear rgba(17,83,211,255)
fn(draw)
 for local(a) = 0 to 255
  for local(s) = 0 to 255
   display rect(local(s),local(a),1,1) -rgba(local(s),255-local(s),floor(local(s)/2),local(a))
  end
 end
 display rect(0,260,256,1) -rgb(255,255,255)
 for local(a) = 0 to 255
  display rect(local(a),260,1,1) -rgba(255,255,255,local(a))
 end
end
'''
        with NativeApp(source) as app:
            gdi = drawing_tests.NativeDrawingTests.prepare_pixels(self,app)
            self.assertTrue(app.user.SetWindowPos(app.hwnd,-1,80,80,380,400,0x10))
            app.user.InvalidateRect(app.hwnd,None,False)
            app.send(0xF)
            dc = app.user.GetDC(app.hwnd)
            try:
                for a in range(256):
                    for s in range(256):
                        expected = self.blend((s,255-s,s//2),(17,83,211),a)
                        self.assertEqual(gdi.GetPixel(dc,s,a),self.colour(expected),(s,a,expected))
                    self.assertEqual(gdi.GetPixel(dc,a,260),0xFFFFFF,a)
            finally:
                app.user.ReleaseDC(app.hwnd,dc)
            self.assertIn(b"CreateDIBSection",app.image)
            self.assertNotIn(b"CreateCompatibleBitmap",app.image)
        self.assertEqual(app.result[0],0)

    def test_text_then_alpha_shapes_then_text_and_overlapping_line_stamps(self):
        source = '''scene 2d
clear rgba(3,5,7,255)
set var(phase) = 0
fn(update)
 if pressed(SPACE)
  set var(phase) = 1
 end
end
fn(draw)
 display rect(0,0,260,160) -rgb(30,60,90)
 display text("Alpha native \\u03bb") -l(10,12) -rgb(210,180,100)
 if var(phase) = 1
  display rect(-0.25,10.5,161,40.25) -rgba(200,40,100,127.9)
  display circle(40.5,30.25,15.5) -rgba(20,230,80,63)
  display line(-30,80,250,80) -rgba(240,20,30,51)
 end
 display text("After") -l(10,110) -rgb(100,200,250)
end
'''
        with NativeApp(source) as app:
            gdi = drawing_tests.NativeDrawingTests.prepare_pixels(self,app)
            def read_pixels():
                dc = app.user.GetDC(app.hwnd)
                try:
                    return [gdi.GetPixel(dc,x,y) for y in range(140) for x in range(260)]
                finally:
                    app.user.ReleaseDC(app.hwnd,dc)
            initial = read_pixels()
            app.send(0x100,32)
            app.wait(lambda: app.read("phase") == 1)
            app.user.InvalidateRect(app.hwnd,None,False)
            app.send(0xF)
            final = read_pixels()
            for y in range(140):
                for x in range(260):
                    old = initial[y*260+x]
                    rgb = (old&255,(old>>8)&255,(old>>16)&255)
                    if x < 161 and 10 <= y < 51:
                        rgb = self.blend((200,40,100),rgb,127)
                    if (x-40.5)**2+(y-30.25)**2 <= 15.5**2:
                        rgb = self.blend((20,230,80),rgb,63)
                    if 79 <= y <= 81:
                        stamps = sum(0 <= center <= 250 for center in (x-1,x,x+1))
                        for _ in range(stamps):
                            rgb = self.blend((240,20,30),rgb,51)
                    self.assertEqual(final[y*260+x],self.colour(rgb),(x,y))
        self.assertEqual(app.result[0],0)

    def test_clipped_writes_preserve_guards_and_nonvolatile_registers_without_a_window(self):
        width,height = 17,13
        cases = [(0,0,17,13,20,40,60,255),(-1e9,-1e9,2e9,2e9,120,200,30,127.8),
                 (16.5,12.5,10,10,255,0,30,254),(17,13,100,100,1,2,3,255),
                 (-100,-100,101,101,255,255,255,0.5),(10,10,-20,-20,1,2,3,128),
                 (-1e308,-1e308,1.5e308,1.5e308,300,-5,1e308,12),
                 (1e308,1e308,1e308,1e308,20,30,40,255),
                 (1,2,8,7,40,50,60,-1),(1,2,8,7,10,20,30,1000)]
        expected = [(0,0,0)]*(width*height)
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp)/"guard.ANVL"
            source = "scene 2d\nfn(draw)\nend\n"
            path.write_text(source,encoding="utf-8")
            generator = NativeCodegen(path,*parse(path,source))
            generator.generate()
            c,w = generator.code,generator._window
            guard = generator.reserve_data(struct.pack("<I",0xDEADC0DE)+b"\0"*(width*height*4)+struct.pack("<I",0xCAFEBABE))
            c.labels["entry"] = len(c.code)
            w.frame(0x28)
            c.mov_reg(12,4)
            for register,number in ((3,123456),(6,789012),(7,345678)):
                c.mov_imm(register,number)
            c.mov_imm(0,1)
            c.rip_int(0,w.hdc,store=True)
            for number,data in ((width,w.back_width),(height,w.back_height)):
                c.mov_imm(0,number)
                c.rip_int(0,data,store=True)
            c.rip_lea_data(0,guard+4)
            c.rip_int(0,w.surface.pixels,store=True)
            for values in cases:
                data = generator.reserve_data(struct.pack("<8d",*values))
                c.rip_lea_data(1,data)
                c.call("native:rectangle")
                x,y,rw,rh,*rgba = values
                clamp = lambda value,limit: max(0,min(limit,value))
                left,top = math.floor(clamp(x,width)),math.floor(clamp(y,height))
                right,bottom = math.ceil(clamp(x+rw,width)),math.ceil(clamp(y+rh,height))
                red,green,blue,alpha = [int(clamp(v,255)) for v in rgba]
                for py in range(top,bottom):
                    for px in range(left,right):
                        i = py*width+px
                        expected[i] = self.blend((red,green,blue),expected[i],alpha)
            for register,number in ((3,123456),(6,789012),(7,345678)):
                c.mov_reg(0,register)
                c.mov_imm(2,number)
                c.bytes(b"\x48\x39\xd0")
                c.conditional_jump(0x85,"test:failure")
            c.bytes(b"\x4c\x39\xe4")  # RSP == saved R12
            c.conditional_jump(0x85,"test:failure")
            values = [0xDEADC0DE]+[(r<<16)|(g<<8)|b for r,g,b in expected]+[0xCAFEBABE]
            for i,value in enumerate(values):
                c.rip_int(0,guard+i*4)
                c.bytes(b"\x89\xc0")
                c.mov_imm(2,value)
                c.bytes(b"\x48\x39\xd0")
                c.conditional_jump(0x85,"test:failure")
            c.mov_imm(1,0)
            c.jump("test:exit")
            c.label("test:failure")
            c.mov_imm(1,2)
            c.label("test:exit")
            c.rip_call_import("ExitProcess")
            c.bytes(b"\xcc")
            exe = path.with_suffix(".exe")
            exe.write_bytes(generator._build(generator.IMPORTS+w.imports))
            result = subprocess.run([str(exe)],capture_output=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_dib_null_bits_budget_and_sync_failures_are_controlled(self):
        source = "scene 2d\nfn(draw)\n display rect(1,1,20,20) -rgba(100,200,40,128)\nend\n"
        original = X64Code.rip_call_import
        for failed in ("CreateDIBSection","null_bits","budget","GdiFlush"):
            with self.subTest(failed=failed), tempfile.TemporaryDirectory() as temp:
                path = pathlib.Path(temp)/"failure.ANVL"
                path.write_text(source,encoding="utf-8")
                generator = NativeCodegen(path,*parse(path,source))
                def call(code,name):
                    if name == failed:
                        code.mov_imm(0,0)
                    else:
                        original(code,name)
                        if name == "CreateDIBSection" and failed == "null_bits":
                            code.mov_reg(10,0)
                            code.mov_imm(0,0)
                            code.rip_int(0,generator._window.surface.pending_pixels,store=True)
                            code.mov_reg(0,10)
                with mock.patch.object(X64Code,"rip_call_import",call), mock.patch.object(
                        NativeSurface,"MAX_PIXELS",1 if failed == "budget" else NativeSurface.MAX_PIXELS):
                    image = generator.generate()
                exe = path.with_suffix(".exe")
                exe.write_bytes(image)
                result = subprocess.run([str(exe)],capture_output=True,timeout=5)
                self.assertEqual(result.returncode,2)
                error = b"Anvil native rectangle error\n" if failed == "GdiFlush" else b"Anvil native painting error\n"
                self.assertEqual(result.stdout,error)
