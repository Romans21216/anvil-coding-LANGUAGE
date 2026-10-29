"""Direct Win32 text emission with pooled UTF-16 literals and an owned font."""

import json
import re

from compiler.common import CompileError
from compiler.display_syntax import take_display_modifiers
from compiler.expressions import split_args


class NativeText:
    IMPORTS = [("GDI32.dll", name) for name in
               ("CreateFontW", "SetBkMode", "SetTextColor", "TextOutW")]
    FRAME = 0xD8
    RECORD, OLD_FONT, OLD_MODE, OLD_COLOUR = 0x70, 0x78, 0x80, 0x88
    RESULT, X, Y, COLOUR, STRING, LENGTH = 0x90, 0x98, 0xA0, 0xA8, 0xB0, 0xB8
    MAX_UNITS = 8192

    def __init__(self, window):
        self.window = window
        self.owner = window.owner
        self.code = window.code
        self.font = self.owner.reserve_data(b"\0" * 8)
        self.face = self.owner.reserve_data("Segoe UI\0".encode("utf-16-le"))
        self.literals = {}

    def display(self, node, scope):
        o, c = self.owner, self.code
        location = f"{o.path}:{node.line}"
        modifiers, command = take_display_modifiers(
            node.value, {"l", "rgb", "rgba"}, o.path, node.line)
        match = re.fullmatch(r'text\(\s*("(?:\\.|[^"\\])*")\s*\)', command.strip())
        if not match:
            raise CompileError(f"{location}: native text expects one string literal; dynamic strings are not implemented")
        try:
            value = json.loads(match[1])
            payload = value.encode("utf-16-le")
        except (ValueError, UnicodeEncodeError) as exc:
            raise CompileError(f"{location}: invalid native text literal: {exc}") from exc
        if any(ord(char) < 32 for char in value):
            raise CompileError(f"{location}: native text is single-line; control characters are unsupported")
        units = len(payload) // 2
        if units > self.MAX_UNITS:
            raise CompileError(f"{location}: native text exceeds {self.MAX_UNITS} UTF-16 units")
        position, colour = None, ["255", "255", "255"]
        seen = set()
        for name, raw in modifiers:
            key = "colour" if name in ("rgb", "rgba") else name
            if key in seen:
                raise CompileError(f"{location}: repeated native text {key} modifier")
            seen.add(key)
            arguments = split_args(raw)
            if name == "l":
                if len(arguments) != 2:
                    raise CompileError(f"{location}: text -l expects x,y")
                position = arguments
            else:
                count = 3 if name == "rgb" else 4
                if len(arguments) != count:
                    raise CompileError(f"{location}: text -{name} expects {count} channels")
                if name == "rgba" and arguments[3] != "255":
                    raise CompileError(f"{location}: native text currently requires alpha 255")
                colour = arguments[:3]
        if position is None:
            raise CompileError(f"{location}: native text requires -l(x,y)")
        if payload not in self.literals:
            self.literals[payload] = o.reserve_data(payload + b"\0\0")
        c.bytes(b"\x48\x83\xec\x60")
        for index, expression in enumerate(position + colour):
            o.emit_expression(expression, node.line, scope)
            c.scalar_memory(0, 4, 32 + index * 8, store=True)
        # Validate before int conversion; preserve the physical source location.
        failure, ready = o.label("text_range"), o.label("text_ready")
        for index in (0, 1):
            c.scalar_memory(0, 4, 32 + index * 8)
            for limit, condition in ((1073741824.0, 0x87), (-1073741824.0, 0x82)):
                o._math.constant(1, limit)
                c.bytes(b"\x66\x0f\x2e\xc1")
                c.conditional_jump(condition, failure)
        c.jump(ready)
        c.label(failure)
        o.emit_runtime_error(f"Anvil native text range error at line {node.line} ({o.path})\n")
        c.label(ready)
        c.rip_lea_data(0, self.literals[payload])
        c.stack_int(0, 72, store=True)
        c.mov_imm(0, units)
        c.stack_int(0, 80, store=True)
        c.stack_int(1, 32, address=True)
        c.call("native:text")
        c.bytes(b"\x48\x83\xc4\x60")

    def emit(self):
        w, c, o = self.window, self.code, self.owner
        c.label("native:text")
        w.frame(self.FRAME)
        done, font_ready, failure = o.label("text_done"), o.label("text_font_ready"), o.label("text_failure")
        c.stack_int(1, self.RECORD, store=True)
        c.rip_int(0, w.hdc)
        c.bytes(b"\x48\x85\xc0")
        c.conditional_jump(0x84, done)
        c.bytes(b"\x48\x83\x79\x30\x00")  # zero UTF-16 units: no allocation/drawing
        c.conditional_jump(0x84, done)
        c.rip_int(0, self.font)
        c.bytes(b"\x48\x85\xc0")
        c.conditional_jump(0x85, font_ready)
        for register, value in ((1,20),(2,0),(8,0),(9,0)):
            c.mov_imm(register,value)
        for index, value in enumerate((600,0,0,0,1,0,0,5,0)):
            c.mov_imm(0,value)
            c.stack_int(0,32 + index*8,store=True)
        c.rip_lea_data(0,self.face)
        c.stack_int(0,104,store=True)
        w.call("CreateFontW")
        w.require_rax(failure)
        c.rip_int(0,self.font,store=True)
        c.label(font_ready)
        c.stack_int(1,self.RECORD)
        for source, target in ((0,self.X),(8,self.Y)):
            c.scalar_memory(0,1,source)
            c.bytes(b"\xf2\x48\x0f\x2c\xc0")
            c.stack_int(0,target,store=True)
        c.bytes(b"\x45\x31\xd2")
        for index in range(3):
            c.scalar_memory(0,1,16+index*8)
            w._clamp(0.0,255.0)
            c.bytes(b"\xf2\x0f\x2c\xc0")
            if index:
                c.bytes(b"\xc1\xe0" + bytes((index*8,)))
            c.bytes(b"\x41\x09\xc2")
        c.stack_int(10,self.COLOUR,store=True)
        for source, target in ((40,self.STRING),(48,self.LENGTH)):
            c.bytes(b"\x48\x8b\x41"+bytes((source,)))
            c.stack_int(0,target,store=True)
        c.rip_int(1,w.hdc)
        c.mov_imm(2,1)  # TRANSPARENT
        w.call("SetBkMode")
        c.bytes(b"\x85\xc0")
        c.conditional_jump(0x84,failure)
        c.stack_int(0,self.OLD_MODE,store=True)
        c.rip_int(1,w.hdc)
        c.stack_int(2,self.COLOUR)
        w.call("SetTextColor")
        self.check_colour(failure)
        c.stack_int(0,self.OLD_COLOUR,store=True)
        c.rip_int(1,w.hdc)
        c.rip_int(2,self.font)
        w.call("SelectObject")
        self.check_object(failure)
        c.stack_int(0,self.OLD_FONT,store=True)
        c.rip_int(1,w.hdc)
        c.stack_int(2,self.X)
        c.stack_int(8,self.Y)
        c.stack_int(9,self.STRING)
        c.stack_int(0,self.LENGTH)
        c.stack_int(0,32,store=True)
        w.call("TextOutW")
        c.stack_int(0,self.RESULT,store=True)
        c.rip_int(1,w.hdc)
        c.stack_int(2,self.OLD_FONT)
        w.call("SelectObject")
        self.check_object(failure)
        c.rip_int(1,w.hdc)
        c.stack_int(2,self.OLD_COLOUR)
        w.call("SetTextColor")
        self.check_colour(failure)
        c.rip_int(1,w.hdc)
        c.stack_int(2,self.OLD_MODE)
        w.call("SetBkMode")
        c.bytes(b"\x85\xc0")
        c.conditional_jump(0x84,failure)
        c.stack_int(0,self.RESULT)
        c.bytes(b"\x85\xc0")
        c.conditional_jump(0x84,failure)
        w.surface.mark_gdi()
        c.label(done)
        c.bytes(b"\x0f\x57\xc0")
        w.return_frame(self.FRAME)
        c.label(failure)
        o.emit_runtime_error("Anvil native text error\n")

    def check_colour(self, failure):
        self.code.bytes(b"\x83\xf8\xff")  # CLR_INVALID, not valid black (zero)
        self.code.conditional_jump(0x84,failure)

    def check_object(self, failure):
        self.window.require_rax(failure)
        self.code.bytes(b"\x48\x83\xf8\xff")
        self.code.conditional_jump(0x84,failure)

    def release(self, failure):
        c, w = self.code, self.window
        done = self.owner.label("text_font_released")
        c.rip_int(1,self.font)
        c.bytes(b"\x48\x85\xc9")
        c.conditional_jump(0x84,done)
        w.call("DeleteObject")
        c.bytes(b"\x85\xc0")
        c.conditional_jump(0x84,failure)
        c.mov_imm(0,0)
        c.rip_int(0,self.font,store=True)
        c.label(done)
