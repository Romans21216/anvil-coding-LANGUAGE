import ctypes
from ctypes import wintypes
import pathlib
import sys
import unittest

from compiler.common import CompileError
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse
from tests.native_app import NativeApp


def point(x, y):
    return (x & 0xFFFF) | ((y & 0xFFFF) << 16)


def atomic_coordinate_probe(generator):
    """Instrument only the test PE: dispatch a message and sample its state
    synchronously, before unrelated posted mouse messages can replace it.
    The production mouse handler and query code are executed unchanged.
    """
    code = generator.code
    window = generator._window
    code.labels["test:original_window_proc"] = code.labels["native:window_proc"]
    code.labels["native:window_proc"] = len(code.code)
    code.bytes(b"\x81\xfa\x01\x80\x00\x00")
    code.conditional_jump(0x85, "test:original_window_proc")
    window.frame(0x28)
    code.mov_reg(2, 8)  # requested message in test WPARAM
    code.mov_imm(8, 0)
    code.call("test:original_window_proc")
    code.call("function:probe")
    code.mov_imm(0, 0)
    window.return_frame(0x28)
    return generator._build(list(generator.IMPORTS) + window.imports)


@unittest.skipUnless(sys.platform == "win32", "native Win32 mouse runtime")
class NativeMouseTests(unittest.TestCase):
    def capture(self, app):
        class GuiThreadInfo(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("flags", wintypes.DWORD)] + [
                (name, wintypes.HWND) for name in
                ("active", "focus", "capture", "menu", "move", "caret")
            ] + [("rect", wintypes.RECT)]

        info = GuiThreadInfo()
        info.size = ctypes.sizeof(info)
        app.user.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GuiThreadInfo)]
        thread = app.user.GetWindowThreadProcessId(app.hwnd, None)
        self.assertTrue(app.user.GetGUIThreadInfo(thread, ctypes.byref(info)))
        return info.capture

    def test_coordinates_buttons_wheel_and_focus_in_actual_pe(self):
        source = '''scene 2d
set var(left-edges) = 0
set var(right-edges) = 0
set var(middle-edges) = 0
set var(same-frame) = 0
set var(wheel-total) = 0
set var(wheel-repeat) = 0
set var(ticks) = 0
fn(probe)
  set var(x) = mouse_x()
  set var(y) = mouse_y()
end
fn(update)
  add var(ticks) 1
  set var(left) = mouse_held("left")
  set var(right) = mouse_held("RIGHT")
  set var(middle) = mouse_held("middle")
  set var(key) = held(A)
  if mouse_pressed("left")
    add var(left-edges) 1
    if mouse_pressed("left")
      add var(same-frame) 1
    end
  end
  if mouse_pressed("right")
    add var(right-edges) 1
  end
  if mouse_pressed("middle")
    add var(middle-edges) 1
  end
  add var(wheel-total) mouse_wheel()
  add var(wheel-repeat) mouse_wheel()
end
fn(draw)
  # Retain the test probe in the static call graph; the wrapper invokes it.
  if false
    call fn(probe)
  end
  display rect(10,10,30,30)
end
'''
        with NativeApp(source, instrument=atomic_coordinate_probe) as app:
            app.wait(lambda: app.read("ticks") >= 2)
            app.send(0x8001, 0x200, point(123, 234))
            app.wait(lambda: app.read("x") == 123 and app.read("y") == 234)
            for x, y in ((-1, 50), (50, -2), (30000, 10), (10, 30000)):
                app.send(0x8001, 0x200, point(x, y))
                app.wait(lambda: app.read("x") == -1 and app.read("y") == -1)
            app.send(0x8001, 0x200, point(5, 6))
            app.wait(lambda: app.read("x") == 5)
            app.send(0x8001, 0x2A3)  # mouse-leave invalidates both coordinates
            app.wait(lambda: app.read("x") == -1 and app.read("y") == -1)
            for down, up, name in ((0x201, 0x202, "left"),
                                    (0x204, 0x205, "right"),
                                    (0x207, 0x208, "middle")):
                app.send(down, 0, point(10, 20))
                app.wait(lambda: app.read(name) == 1 and app.read(name + "-edges") == 1)
                self.assertEqual(self.capture(app), app.hwnd)
                app.send(down, 0, point(10, 20))
                tick = app.read("ticks")
                app.wait(lambda: app.read("ticks") >= tick + 3)
                self.assertEqual(app.read(name + "-edges"), 1)
                app.send(up, 0, point(-5, -5))  # captured outside-client release
                app.wait(lambda: app.read(name) == 0)
                self.assertFalse(self.capture(app))
            self.assertEqual(app.read("same-frame"), 1)
            for delta in (60, 240, -120):
                app.send(0x20A, (delta & 0xFFFF) << 16, point(-300, -200))
            app.wait(lambda: app.read("wheel-total") == 1.5)
            tick = app.read("ticks")
            app.wait(lambda: app.read("ticks") >= tick + 3)
            self.assertEqual(app.read("wheel-total"), 1.5)
            self.assertEqual(app.read("wheel-repeat"), 1.5)
            app.send(0x201, 0, point(20, 30))
            app.send(0x204, 0, point(20, 30))
            app.send(0x100, 65)
            app.wait(lambda: app.read("left") == app.read("right") == app.read("key") == 1)
            app.send(0x202)
            app.wait(lambda: app.read("left") == 0 and app.read("right") == 1)
            self.assertEqual(self.capture(app), app.hwnd)
            app.send(0x008)
            app.wait(lambda: app.read("left") == app.read("right") == app.read("key") == 0)
            self.assertFalse(self.capture(app))
            app.send(0x207)
            app.wait(lambda: app.read("middle") == 1)
            app.send(0x215, 0, 0)  # capture transferred away
            app.wait(lambda: app.read("middle") == 0)
            app.send(0x01F)  # release actual capture after the simulated transfer
            # A client resize changes the coordinate bounds immediately.
            app.user.MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, wintypes.BOOL]
            self.assertTrue(app.user.MoveWindow(app.hwnd, 80, 80, 300, 250, True))
            tick = app.read("ticks")
            app.wait(lambda: app.read("ticks") >= tick + 3)
            app.send(0x8001, 0x200, point(400, 20))
            app.wait(lambda: app.read("x") == -1)
            app.send(0x8001, 0x200, point(100, 100))
            app.wait(lambda: app.read("x") == app.read("y") == 100)
        self.assertEqual(app.result[0], 0, app.result)

    def test_draw_only_edges_taps_capture_and_cancel(self):
        source = '''scene 2d
set var(edges) = 0
set var(draws) = 0
set var(wheel-total) = 0
fn(draw)
  add var(draws) 1
  if mouse_pressed("left")
    add var(edges) 1
  end
  set var(held-now) = mouse_held("left")
  add var(wheel-total) mouse_wheel()
  display rect(10,10,30,30)
end
'''
        with NativeApp(source) as app:
            app.wait(lambda: app.read("draws") >= 2)
            app.send(0x00B, 0)
            app.send(0x201)
            app.send(0x202)
            app.send(0x20A, 60 << 16)
            app.send(0x20A, 60 << 16)
            app.send(0x00B, 1)
            app.wait(lambda: app.read("edges") == 1 and app.read("wheel-total") == 1)
            draw = app.read("draws")
            app.wait(lambda: app.read("draws") >= draw + 3)
            self.assertEqual(app.read("edges"), 1)
            self.assertEqual(app.read("wheel-total"), 1)
            self.assertEqual(app.read("held-now"), 0)
            app.send(0x00B, 0)
            app.send(0x201)
            app.send(0x20A, 120 << 16)
            app.send(0x01F)  # WM_CANCELMODE discards pending input too
            app.send(0x00B, 1)
            draw = app.read("draws")
            app.wait(lambda: app.read("draws") >= draw + 3)
            self.assertEqual(app.read("edges"), 1)
            self.assertEqual(app.read("wheel-total"), 1)
            self.assertEqual(app.read("held-now"), 0)
        self.assertEqual(app.result[0], 0, app.result)


class NativeMouseDiagnosticsTests(unittest.TestCase):
    def test_unsupported_arguments_have_source_diagnostics(self):
        for expression in ('mouse_held(1)', 'mouse_pressed("unknown")',
                           'mouse_x(1)', 'mouse_wheel(1)', 'mouse_y(1,2)'):
            source = f'scene 2d\nfn(draw)\n set var(x) = {expression}\nend\n'
            functions, top, variables, arrays = parse(pathlib.Path("mouse.ANVL"), source)
            with self.subTest(expression=expression), self.assertRaisesRegex(CompileError, r"mouse.ANVL:3:"):
                NativeCodegen(pathlib.Path("mouse.ANVL"), functions, top, variables, arrays).generate()
        source = 'fn(main)\n set var(x) = mouse_x()\nend\n'
        functions, top, variables, arrays = parse(pathlib.Path("mouse.ANVL"), source)
        with self.assertRaisesRegex(CompileError, "requires native scene 2d"):
            NativeCodegen(pathlib.Path("mouse.ANVL"), functions, top, variables, arrays).generate()
