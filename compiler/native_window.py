"""Anvil-owned x64 emission for the first Win32 2D drawing runtime.

All runtime instructions are emitted here; USER32/GDI32 are operating-system
imports, not an external language runtime or compiled shim.
"""

from __future__ import annotations

import struct
import re
from typing import TYPE_CHECKING

from compiler.common import CompileError, Node
from compiler.expressions import split_args

if TYPE_CHECKING:
    from compiler.native_codegen import NativeCodegen


class NativeWindow:
    FRAME = 0x128
    PAINT = 0x60
    RECT = 0xB0
    HWND = 0xC0
    PAINT_DC = 0xC8
    WIDTH = 0xD0
    HEIGHT = 0xD8
    OLD_BITMAP = 0xE0
    CLOCK_IMPORTS = [
        ("KERNEL32.dll", "GetTickCount64"),
        ("USER32.dll", "SetTimer"),
        ("USER32.dll", "KillTimer"),
        ("USER32.dll", "InvalidateRect"),
    ]
    IMPORTS = [
        ("KERNEL32.dll", "GetModuleHandleW"),
        ("USER32.dll", "RegisterClassW"),
        ("USER32.dll", "UnregisterClassW"),
        ("USER32.dll", "CreateWindowExW"),
        ("USER32.dll", "DefWindowProcW"),
        ("USER32.dll", "GetMessageW"),
        ("USER32.dll", "TranslateMessage"),
        ("USER32.dll", "DispatchMessageW"),
        ("USER32.dll", "PostQuitMessage"),
        ("USER32.dll", "BeginPaint"),
        ("USER32.dll", "EndPaint"),
        ("USER32.dll", "GetClientRect"),
        ("USER32.dll", "FillRect"),
        ("USER32.dll", "LoadCursorW"),
        ("GDI32.dll", "CreateSolidBrush"),
        ("GDI32.dll", "DeleteObject"),
        ("GDI32.dll", "CreateCompatibleDC"),
        ("GDI32.dll", "CreateCompatibleBitmap"),
        ("GDI32.dll", "SelectObject"),
        ("GDI32.dll", "DeleteDC"),
        ("GDI32.dll", "BitBlt"),
    ]

    def __init__(self, owner: NativeCodegen, clear: int):
        self.owner = owner
        self.code = owner.code
        self.clear = clear
        from compiler.native_drawing import NativeDrawing
        self.drawing = NativeDrawing(self)
        self.hdc = owner.reserve_data(b"\0" * 8)
        self.instance = owner.reserve_data(b"\0" * 8)
        self.brush = owner.reserve_data(b"\0" * 8)
        self.wndclass = owner.reserve_data(b"\0" * 72)
        self.message = owner.reserve_data(b"\0" * 48)
        self.class_name = owner.reserve_data("AnvilDirect2D\0".encode("utf-16-le"))
        self.title = owner.reserve_data((owner.title + "\0").encode("utf-16-le"))
        self.last_tick = owner.reserve_data(b"\0" * 8)
        self.accumulator = owner.reserve_data(b"\0" * 8)
        self.simulation_time = owner.reserve_data(b"\0" * 8)
        self.clock_requested = False
        self.keyboard = None
        self.mouse = None
        self.window_handle = owner.reserve_data(b"\0" * 8)
        self.back_dc = owner.reserve_data(b"\0" * 8)
        self.back_bitmap = owner.reserve_data(b"\0" * 8)
        self.stock_bitmap = owner.reserve_data(b"\0" * 8)
        self.pending_bitmap = owner.reserve_data(b"\0" * 8)
        self.back_width = owner.reserve_data(b"\0" * 8)
        self.back_height = owner.reserve_data(b"\0" * 8)

    @property
    def clock_enabled(self) -> bool:
        return "update" in self.owner.functions or self.clock_requested or self.keyboard is not None or self.mouse is not None

    def emit_key_query(self, name: str) -> None:
        if self.keyboard is None:
            from compiler.native_input import NativeKeyboard
            self.keyboard = NativeKeyboard(self.owner)
        self.keyboard.emit_query(name)

    def emit_mouse_query(self, name, button=None):
        if self.mouse is None:
            from compiler.native_mouse import NativeMouse
            self.mouse = NativeMouse(self)
        self.mouse.emit_query(name, button)

    @property
    def imports(self) -> list[tuple[str, str]]:
        return (self.IMPORTS + (self.CLOCK_IMPORTS if self.clock_enabled else [])
                + (self.mouse.IMPORTS if self.mouse is not None else []))

    def call(self, name: str) -> None:
        self.code.rip_call_import(name)

    def frame(self, size: int) -> None:
        # Runtime functions have no RBP frame; 8 mod 16 makes calls aligned.
        self.code.bytes(b"\x48\x81\xec" + struct.pack("<I", size))

    def return_frame(self, size: int) -> None:
        self.code.bytes(b"\x48\x81\xc4" + struct.pack("<I", size) + b"\xc3")

    def require_rax(self, failure: str) -> None:
        self.code.bytes(b"\x48\x85\xc0")
        self.code.conditional_jump(0x84, failure)

    def emit(self) -> None:
        self.drawing.emit_pending()
        self._rectangle()
        self._release_buffer()
        if self.keyboard is not None:
            self.keyboard.emit_helpers()
        if self.mouse is not None:
            self.mouse.emit_helpers()
        self._window_proc()
        self._entry()

    def emit_display(self, node: Node, scope: Node | None) -> None:
        raw = node.value.strip()
        location = f"{self.owner.path}:{node.line}"
        match = re.match(r"(rect|circle|line)\(", raw)
        if not match:
            raise CompileError(f"{location}: native 2D graphics currently supports display rect, circle or line only")
        shape = match[1]
        start = match.end()
        depth = 1
        end = start
        while end < len(raw) and depth:
            depth += (raw[end] == "(") - (raw[end] == ")")
            end += 1
        if depth:
            raise CompileError(f"{location}: unclosed native {shape} arguments")
        values = split_args(raw[start:end - 1])
        expected = {"rect": (4,), "circle": (3,), "line": (4, 5)}[shape]
        if len(values) not in expected:
            signature = {"rect": "x,y,width,height", "circle": "x,y,radius",
                         "line": "x1,y1,x2,y2[,thickness]"}[shape]
            raise CompileError(f"{location}: display {shape} expects {signature}")
        if shape == "line" and len(values) == 4:
            values.append("1")
        rest = raw[end:].strip()
        colour = ["255", "255", "255"]
        if rest:
            if rest.startswith("-rgb(") and rest.endswith(")"):
                colour = split_args(rest[5:-1])
            elif rest.startswith("-rgba(") and rest.endswith(")"):
                channels = split_args(rest[6:-1])
                if len(channels) != 4 or channels[3] != "255":
                    raise CompileError(f"{location}: native shapes currently require alpha 255")
                colour = channels[:3]
            else:
                raise CompileError(f"{location}: unsupported native {shape} modifier")
            if len(colour) != 3:
                raise CompileError(f"{location}: native {shape} colour expects three channels")
        if shape != "rect":
            self.drawing.primitive(shape, values + colour, node, scope)
            return
        self.code.bytes(b"\x48\x83\xec\x60")
        for index, expression in enumerate(values + colour):
            self.owner.emit_expression(expression, node.line, scope)
            self.code.bytes(b"\xf2\x0f\x11\x44\x24" + bytes((32 + index * 8,)))
        self.code.stack_int(1, 32, address=True)
        self.code.call("native:rectangle")
        self.code.bytes(b"\x48\x83\xc4\x60")

    def _window_proc(self) -> None:
        c = self.code
        c.label("native:window_proc")
        self.frame(self.FRAME)
        c.stack_int(1, self.HWND, store=True)
        c.rip_int(1, self.window_handle, store=True)
        c.mov_imm(0, 0)
        c.stack_int(0, self.PAINT_DC, store=True)
        paint = self.owner.label("paint")
        destroy = self.owner.label("destroy")
        timer = self.owner.label("timer")
        erase = self.owner.label("erase")
        failure = self.owner.label("paint_failure")
        finish = self.owner.label("paint_finish")
        default = self.owner.label("default_window_message")
        c.bytes(b"\x81\xfa\x0f\x00\x00\x00")  # WM_PAINT
        c.conditional_jump(0x84, paint)
        c.bytes(b"\x81\xfa\x02\x00\x00\x00")  # WM_DESTROY
        c.conditional_jump(0x84, destroy)
        c.bytes(b"\x81\xfa\x14\x00\x00\x00")  # WM_ERASEBKGND
        c.conditional_jump(0x84, erase)
        if self.clock_enabled:
            c.bytes(b"\x81\xfa\x13\x01\x00\x00")  # WM_TIMER
            c.conditional_jump(0x84, timer)
        focus = self.owner.label("input_focus_lost")
        if self.keyboard is not None or self.mouse is not None:
            for message in (0x008, 0x01F):  # WM_KILLFOCUS / WM_CANCELMODE
                c.bytes(b"\x81\xfa" + struct.pack("<I", message))
                c.conditional_jump(0x84, focus)
        if self.keyboard is not None:
            self.keyboard.emit_dispatch()
        if self.mouse is not None:
            self.mouse.emit_dispatch()
        c.label(default)
        self.call("DefWindowProcW")  # original four Win64 argument registers
        self.return_frame(self.FRAME)
        c.label(erase)
        c.mov_imm(0, 1)  # full background is composed offscreen during WM_PAINT
        self.return_frame(self.FRAME)
        c.label(destroy)
        if self.clock_enabled:
            c.mov_imm(2, 1)
            self.call("KillTimer")
        c.call("native:release_buffer")
        c.mov_imm(1, 0)
        self.call("PostQuitMessage")
        c.mov_imm(0, 0)
        self.return_frame(self.FRAME)
        c.label(paint)
        c.stack_int(2, self.PAINT, address=True)
        self.call("BeginPaint")
        self.require_rax(failure)
        c.stack_int(0, self.PAINT_DC, store=True)
        c.stack_int(1, self.HWND)
        c.stack_int(2, self.RECT, address=True)
        self.call("GetClientRect")
        self.require_rax(failure)
        for source, target in ((self.RECT + 8, self.WIDTH),
                               (self.RECT + 12, self.HEIGHT)):
            c.stack_int(0, source)
            c.bytes(b"\x89\xc0\x85\xc0")  # client dimensions are signed int32
            c.conditional_jump(0x8E, finish)  # minimized/empty client
            c.stack_int(0, target, store=True)
        self._prepare_buffer(failure)
        c.rip_int(1, self.hdc)
        c.stack_int(2, self.RECT, address=True)
        c.rip_int(8, self.brush)
        self.call("FillRect")
        self.require_rax(failure)
        c.call("function:draw")
        if self.keyboard is not None and "update" not in self.owner.functions:
            c.call("native:clear_pressed")
        if self.mouse is not None and "update" not in self.owner.functions:
            self.mouse.clear_edges()
        c.stack_int(1, self.PAINT_DC)
        c.mov_imm(2, 0)
        c.mov_imm(8, 0)
        c.stack_int(9, self.WIDTH)
        c.stack_int(0, self.HEIGHT)
        c.stack_int(0, 32, store=True)
        c.rip_int(0, self.back_dc)
        c.stack_int(0, 40, store=True)
        c.mov_imm(0, 0)
        c.stack_int(0, 48, store=True)
        c.stack_int(0, 56, store=True)
        c.mov_imm(0, 0x00CC0020)  # SRCCOPY: one completed frame presentation
        c.stack_int(0, 64, store=True)
        self.call("BitBlt")
        self.require_rax(failure)
        c.label(finish)
        c.mov_imm(0, 0)
        c.rip_int(0, self.hdc, store=True)
        c.stack_int(0, self.PAINT_DC, store=True)
        c.stack_int(1, self.HWND)
        c.stack_int(2, self.PAINT, address=True)
        self.call("EndPaint")
        self.require_rax(failure)
        c.mov_imm(0, 0)
        c.rip_int(0, self.hdc, store=True)
        self.return_frame(self.FRAME)
        if self.clock_enabled:
            c.label(timer)
            self._timer(failure)
            c.mov_imm(0, 0)
            self.return_frame(self.FRAME)
        if self.keyboard is not None:
            self.keyboard.emit_handlers(self, default)
        if self.mouse is not None:
            self.mouse.emit_handlers()
        if self.keyboard is not None or self.mouse is not None:
            c.label(focus)
            if self.keyboard is not None:
                c.call("native:clear_keys")
            if self.mouse is not None:
                self.mouse.clear_focus()
            c.mov_imm(0, 0)
            self.return_frame(self.FRAME)
        c.label(failure)
        no_paint = self.owner.label("failure_without_paint")
        c.stack_int(0, self.PAINT_DC)
        c.bytes(b"\x48\x85\xc0")
        c.conditional_jump(0x84, no_paint)
        c.stack_int(1, self.HWND)
        c.stack_int(2, self.PAINT, address=True)
        self.call("EndPaint")
        c.label(no_paint)
        c.call("native:release_buffer")
        self.owner.emit_runtime_error("Anvil native painting error\n")

    def _prepare_buffer(self, failure: str) -> None:
        c = self.code
        exists = self.owner.label("buffer_dc_exists")
        resize = self.owner.label("resize_buffer")
        ready = self.owner.label("buffer_ready")
        delete_old = self.owner.label("delete_old_bitmap")
        dimensions = self.owner.label("save_buffer_dimensions")
        c.rip_int(0, self.back_dc)
        c.bytes(b"\x48\x85\xc0")
        c.conditional_jump(0x85, exists)
        c.stack_int(1, self.PAINT_DC)
        self.call("CreateCompatibleDC")
        self.require_rax(failure)
        c.rip_int(0, self.back_dc, store=True)
        c.label(exists)
        for local, data in ((self.WIDTH, self.back_width),
                            (self.HEIGHT, self.back_height)):
            c.stack_int(0, local)
            c.rip_int(2, data)
            c.bytes(b"\x48\x39\xd0")
            c.conditional_jump(0x85, resize)
        c.jump(ready)
        c.label(resize)
        c.stack_int(1, self.PAINT_DC)  # use colour display DC, not monochrome memory DC
        c.stack_int(2, self.WIDTH)
        c.stack_int(8, self.HEIGHT)
        self.call("CreateCompatibleBitmap")
        self.require_rax(failure)
        c.rip_int(0, self.pending_bitmap, store=True)
        c.rip_int(1, self.back_dc)
        c.mov_reg(2, 0)
        self.call("SelectObject")
        self.require_rax(failure)
        c.bytes(b"\x48\x83\xf8\xff")
        c.conditional_jump(0x84, failure)
        c.stack_int(0, self.OLD_BITMAP, store=True)
        c.rip_int(0, self.pending_bitmap)
        c.rip_int(0, self.back_bitmap, store=True)
        c.mov_imm(0, 0)
        c.rip_int(0, self.pending_bitmap, store=True)
        c.rip_int(0, self.stock_bitmap)
        c.bytes(b"\x48\x85\xc0")
        c.conditional_jump(0x85, delete_old)
        c.stack_int(0, self.OLD_BITMAP)
        c.rip_int(0, self.stock_bitmap, store=True)
        c.jump(dimensions)
        c.label(delete_old)
        c.stack_int(1, self.OLD_BITMAP)
        self.call("DeleteObject")
        self.require_rax(failure)
        c.label(dimensions)
        for local, data in ((self.WIDTH, self.back_width),
                            (self.HEIGHT, self.back_height)):
            c.stack_int(0, local)
            c.rip_int(0, data, store=True)
        c.label(ready)
        c.rip_int(0, self.back_dc)
        c.rip_int(0, self.hdc, store=True)

    def _release_buffer(self) -> None:
        c = self.code
        c.label("native:release_buffer")
        self.frame(0x28)
        no_pending = self.owner.label("no_pending_bitmap")
        no_dc = self.owner.label("no_buffer_dc")
        no_stock = self.owner.label("no_stock_bitmap")
        no_bitmap = self.owner.label("no_buffer_bitmap")
        c.rip_int(1, self.pending_bitmap)
        c.bytes(b"\x48\x85\xc9")
        c.conditional_jump(0x84, no_pending)
        self.call("DeleteObject")
        c.label(no_pending)
        c.rip_int(1, self.back_dc)
        c.bytes(b"\x48\x85\xc9")
        c.conditional_jump(0x84, no_dc)
        c.rip_int(2, self.stock_bitmap)
        c.bytes(b"\x48\x85\xd2")
        c.conditional_jump(0x84, no_stock)
        self.call("SelectObject")  # deselect owned bitmap before deleting it
        c.label(no_stock)
        c.rip_int(1, self.back_bitmap)
        c.bytes(b"\x48\x85\xc9")
        c.conditional_jump(0x84, no_bitmap)
        self.call("DeleteObject")
        c.label(no_bitmap)
        c.rip_int(1, self.back_dc)
        self.call("DeleteDC")
        c.label(no_dc)
        c.mov_imm(0, 0)
        for data in (self.hdc, self.back_dc, self.back_bitmap, self.pending_bitmap,
                     self.stock_bitmap, self.back_width, self.back_height):
            c.rip_int(0, data, store=True)
        self.return_frame(0x28)

    def _double_xmm1(self, value: float) -> None:
        self.code.mov_imm(0, struct.unpack("<Q", struct.pack("<d", value))[0])
        self.code.bytes(b"\x66\x48\x0f\x6e\xc8")

    def _timer(self, failure: str) -> None:
        c = self.code
        self.call("GetTickCount64")
        c.rip_int(2, self.last_tick)
        c.rip_int(0, self.last_tick, store=True)
        c.bytes(b"\x48\x29\xd0\x48\x3d\xfa\x00\x00\x00")
        elapsed = self.owner.label("elapsed_bounded")
        c.conditional_jump(0x86, elapsed)
        c.mov_imm(0, 250)  # bounded catch-up after a stall
        c.label(elapsed)
        c.bytes(b"\xf2\x48\x0f\x2a\xc0")
        c.rip_load_data(1, self.accumulator)
        c.bytes(b"\xf2\x0f\x58\xc1")
        c.rip_store_data(0, self.accumulator)
        loop = self.owner.label("fixed_update")
        done = self.owner.label("updates_done")
        c.label(loop)
        c.rip_load_data(0, self.accumulator)
        self._double_xmm1(1000.0 / self.owner.fixed_hz)
        c.bytes(b"\x66\x0f\x2e\xc1")
        c.conditional_jump(0x82, done)
        c.bytes(b"\xf2\x0f\x5c\xc1")
        c.rip_store_data(0, self.accumulator)
        c.rip_load_data(0, self.simulation_time)
        self._double_xmm1(1.0 / self.owner.fixed_hz)
        c.bytes(b"\xf2\x0f\x58\xc1")
        c.rip_store_data(0, self.simulation_time)
        if "update" in self.owner.functions:
            c.call("function:update")
            if self.keyboard is not None:
                c.call("native:clear_pressed")
            if self.mouse is not None:
                self.mouse.clear_edges()
        c.jump(loop)
        c.label(done)
        c.stack_int(1, self.HWND)
        c.mov_imm(2, 0)
        c.mov_imm(8, 0)
        self.call("InvalidateRect")
        self.require_rax(failure)

    def _clamp(self, low: float, high: float) -> None:
        for value, opcode in ((low, b"\xf2\x0f\x5f\xc1"),
                              (high, b"\xf2\x0f\x5d\xc1")):
            self.code.mov_imm(0, struct.unpack("<Q", struct.pack("<d", value))[0])
            self.code.bytes(b"\x66\x48\x0f\x6e\xc8" + opcode)

    def _rectangle(self) -> None:
        """RCX points to seven doubles: x,y,width,height,r,g,b."""
        c = self.code
        c.label("native:rectangle")
        self.frame(0x88)
        done = self.owner.label("rectangle_done")
        failure = self.owner.label("rectangle_failure")
        c.rip_int(0, self.hdc)
        c.bytes(b"\x48\x85\xc0")
        c.conditional_jump(0x84, done)
        for index, source in enumerate((0, 8, 0, 8)):
            c.bytes(b"\xf2\x0f\x10\x41" + bytes((source,)))
            if index >= 2:
                c.bytes(b"\xf2\x0f\x58\x41" + bytes((16 if index == 2 else 24,)))
            self._clamp(-1073741824.0, 1073741824.0)
            c.bytes(b"\xf2\x48\x0f\x2c\xc0\xf2\x48\x0f\x2a\xc8")
            c.bytes(b"\x66\x0f\x2e\xc1")  # original versus truncated value
            rounded = self.owner.label("rectangle_edge")
            c.conditional_jump(0x83 if index < 2 else 0x86, rounded)
            c.bytes(b"\x48\xff\xc8" if index < 2 else b"\x48\xff\xc0")
            c.label(rounded)
            c.bytes(b"\x89\x44\x24" + bytes((0x40 + index * 4,)))
        c.bytes(b"\x45\x31\xd2")  # RGB accumulator in R10D
        for index in range(3):
            c.bytes(b"\xf2\x0f\x10\x41" + bytes((32 + index * 8,)))
            self._clamp(0.0, 255.0)
            c.bytes(b"\xf2\x0f\x2c\xc0")
            if index:
                c.bytes(b"\xc1\xe0" + bytes((index * 8,)))
            c.bytes(b"\x41\x09\xc2")
        c.mov_reg(1, 10)
        self.call("CreateSolidBrush")
        self.require_rax(failure)
        c.stack_int(0, 0x58, store=True)
        c.rip_int(1, self.hdc)
        c.stack_int(2, 0x40, address=True)
        c.mov_reg(8, 0)
        self.call("FillRect")
        # Empty or clipped rectangles may return zero; brush lifetime is always ended.
        c.stack_int(1, 0x58)
        self.call("DeleteObject")
        self.require_rax(failure)
        c.label(done)
        c.bytes(b"\x0f\x57\xc0")
        self.return_frame(0x88)
        c.label(failure)
        self.owner.emit_runtime_error("Anvil native rectangle error\n")

    def _entry(self) -> None:
        c = self.code
        c.label("entry")
        self.frame(0x68)  # shadow space plus eight CreateWindowExW stack arguments
        failure = self.owner.label("window_failure")
        loop = self.owner.label("message_loop")
        close = self.owner.label("window_close")
        c.call("native:setup")
        c.mov_imm(1, 0)
        self.call("GetModuleHandleW")
        self.require_rax(failure)
        c.rip_int(0, self.instance, store=True)
        c.rip_int(0, self.wndclass + 24, store=True)
        c.rip_lea_label(0, "native:window_proc")
        c.rip_int(0, self.wndclass + 8, store=True)
        c.rip_lea_data(0, self.class_name)
        c.rip_int(0, self.wndclass + 64, store=True)
        c.mov_imm(0, 3)  # CS_HREDRAW | CS_VREDRAW
        c.rip_int(0, self.wndclass, store=True)
        c.mov_imm(1, 0)
        c.mov_imm(2, 32512)  # IDC_ARROW
        self.call("LoadCursorW")
        c.rip_int(0, self.wndclass + 40, store=True)
        c.rip_lea_data(1, self.wndclass)
        self.call("RegisterClassW")
        c.bytes(b"\x66\x85\xc0")  # ATOM is a 16-bit return value
        c.conditional_jump(0x84, failure)
        c.mov_imm(1, self.clear)
        self.call("CreateSolidBrush")
        self.require_rax(failure)
        c.rip_int(0, self.brush, store=True)
        c.mov_imm(1, 0)
        c.rip_lea_data(2, self.class_name)
        c.rip_lea_data(8, self.title)
        c.mov_imm(9, 0x10CF0000)  # WS_VISIBLE | WS_OVERLAPPEDWINDOW
        for index, value in enumerate((0x80000000, 0x80000000, 960, 640, 0, 0)):
            c.mov_imm(0, value)
            c.stack_int(0, 32 + index * 8, store=True)
        c.rip_int(0, self.instance)
        c.stack_int(0, 80, store=True)
        c.mov_imm(0, 0)
        c.stack_int(0, 88, store=True)
        self.call("CreateWindowExW")
        self.require_rax(failure)
        if self.clock_enabled:
            c.stack_int(0, 96, store=True)
            self.call("GetTickCount64")
            c.rip_int(0, self.last_tick, store=True)
            c.stack_int(1, 96)
            c.mov_imm(2, 1)
            c.mov_imm(8, 10)
            c.mov_imm(9, 0)
            self.call("SetTimer")
            self.require_rax(failure)
        c.label(loop)
        c.rip_lea_data(1, self.message)
        for register in (2, 8, 9):
            c.mov_imm(register, 0)
        self.call("GetMessageW")
        c.bytes(b"\x85\xc0")
        c.conditional_jump(0x88, failure)
        c.conditional_jump(0x84, close)
        c.rip_lea_data(1, self.message)
        self.call("TranslateMessage")
        c.rip_lea_data(1, self.message)
        self.call("DispatchMessageW")
        c.jump(loop)
        c.label(close)
        c.rip_int(1, self.brush)
        self.call("DeleteObject")
        c.rip_lea_data(1, self.class_name)
        c.rip_int(2, self.instance)
        self.call("UnregisterClassW")
        c.mov_imm(1, 0)
        self.call("ExitProcess")
        c.bytes(b"\xcc")
        c.label(failure)
        self.owner.emit_runtime_error("Anvil native window error\n")
