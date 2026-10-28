"""Anvil-owned x64 emission for the first Win32 2D drawing runtime.

All runtime instructions are emitted here; USER32/GDI32 are operating-system
imports, not an external language runtime or compiled shim.
"""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from compiler.common import CompileError, Node
from compiler.expressions import split_args

if TYPE_CHECKING:
    from compiler.native_codegen import NativeCodegen


class NativeWindow:
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
    ]

    def __init__(self, owner: NativeCodegen, clear: int):
        self.owner = owner
        self.code = owner.code
        self.clear = clear
        self.hdc = owner.reserve_data(b"\0" * 8)
        self.instance = owner.reserve_data(b"\0" * 8)
        self.brush = owner.reserve_data(b"\0" * 8)
        self.wndclass = owner.reserve_data(b"\0" * 72)
        self.message = owner.reserve_data(b"\0" * 48)
        self.class_name = owner.reserve_data("AnvilDirect2D\0".encode("utf-16-le"))
        self.title = owner.reserve_data("Anvil Native 2D\0".encode("utf-16-le"))
        self.last_tick = owner.reserve_data(b"\0" * 8)
        self.accumulator = owner.reserve_data(b"\0" * 8)
        self.simulation_time = owner.reserve_data(b"\0" * 8)
        self.clock_requested = False

    @property
    def clock_enabled(self) -> bool:
        return "update" in self.owner.functions or self.clock_requested

    @property
    def imports(self) -> list[tuple[str, str]]:
        return self.IMPORTS + (self.CLOCK_IMPORTS if self.clock_enabled else [])

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
        self._rectangle()
        self._window_proc()
        self._entry()

    def emit_display(self, node: Node, scope: Node | None) -> None:
        raw = node.value.strip()
        location = f"{self.owner.path}:{node.line}"
        if not raw.startswith("rect("):
            raise CompileError(f"{location}: native 2D graphics currently supports display rect only")
        depth = 1
        end = 5
        while end < len(raw) and depth:
            depth += (raw[end] == "(") - (raw[end] == ")")
            end += 1
        if depth:
            raise CompileError(f"{location}: unclosed native rectangle arguments")
        values = split_args(raw[5:end - 1])
        if len(values) != 4:
            raise CompileError(f"{location}: display rect expects x,y,width,height")
        rest = raw[end:].strip()
        colour = ["255", "255", "255"]
        if rest:
            if rest.startswith("-rgb(") and rest.endswith(")"):
                colour = split_args(rest[5:-1])
            elif rest.startswith("-rgba(") and rest.endswith(")"):
                channels = split_args(rest[6:-1])
                if len(channels) != 4 or channels[3] != "255":
                    raise CompileError(f"{location}: native rectangles currently require alpha 255")
                colour = channels[:3]
            else:
                raise CompileError(f"{location}: unsupported native rectangle modifier")
            if len(colour) != 3:
                raise CompileError(f"{location}: native rectangle colour expects three channels")
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
        self.frame(0xC8)
        c.stack_int(1, 0xA0, store=True)  # HWND survives paint API calls
        paint = self.owner.label("paint")
        destroy = self.owner.label("destroy")
        timer = self.owner.label("timer")
        failure = self.owner.label("paint_failure")
        c.bytes(b"\x81\xfa\x0f\x00\x00\x00")  # WM_PAINT
        c.conditional_jump(0x84, paint)
        c.bytes(b"\x81\xfa\x02\x00\x00\x00")  # WM_DESTROY
        c.conditional_jump(0x84, destroy)
        if self.clock_enabled:
            c.bytes(b"\x81\xfa\x13\x01\x00\x00")  # WM_TIMER
            c.conditional_jump(0x84, timer)
        self.call("DefWindowProcW")  # original four Win64 argument registers
        self.return_frame(0xC8)
        c.label(destroy)
        if self.clock_enabled:
            c.mov_imm(2, 1)
            self.call("KillTimer")
        c.mov_imm(1, 0)
        self.call("PostQuitMessage")
        c.mov_imm(0, 0)
        self.return_frame(0xC8)
        c.label(paint)
        c.stack_int(2, 0x40, address=True)  # PAINTSTRUCT (72 bytes)
        self.call("BeginPaint")
        self.require_rax(failure)
        c.rip_int(0, self.hdc, store=True)
        c.stack_int(1, 0xA0)
        c.stack_int(2, 0x90, address=True)  # client RECT
        self.call("GetClientRect")
        self.require_rax(failure)
        c.rip_int(1, self.hdc)
        c.stack_int(2, 0x90, address=True)
        c.rip_int(8, self.brush)
        self.call("FillRect")
        self.require_rax(failure)
        c.call("function:draw")
        c.stack_int(1, 0xA0)
        c.stack_int(2, 0x40, address=True)
        self.call("EndPaint")
        self.require_rax(failure)
        c.mov_imm(0, 0)
        c.rip_int(0, self.hdc, store=True)
        self.return_frame(0xC8)
        if self.clock_enabled:
            c.label(timer)
            self._timer(failure)
            c.mov_imm(0, 0)
            self.return_frame(0xC8)
        c.label(failure)
        self.owner.emit_runtime_error("Anvil native painting error\n")

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
        self._double_xmm1(1000.0 / 60.0)
        c.bytes(b"\x66\x0f\x2e\xc1")
        c.conditional_jump(0x82, done)
        c.bytes(b"\xf2\x0f\x5c\xc1")
        c.rip_store_data(0, self.accumulator)
        c.rip_load_data(0, self.simulation_time)
        self._double_xmm1(1.0 / 60.0)
        c.bytes(b"\xf2\x0f\x58\xc1")
        c.rip_store_data(0, self.simulation_time)
        if "update" in self.owner.functions:
            c.call("function:update")
        c.jump(loop)
        c.label(done)
        c.stack_int(1, 0xA0)
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
