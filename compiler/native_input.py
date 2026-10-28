"""Anvil x64 keyboard state and Win32 key-message lowering."""

from __future__ import annotations

import struct


class NativeKeyboard:
    KEY_COUNT = 256

    def __init__(self, owner):
        self.owner = owner
        self.code = owner.code
        self.held = owner.reserve_data(b"\0" * (self.KEY_COUNT * 2))
        self.pressed = self.held + self.KEY_COUNT
        self.down_label = owner.label("key_down")
        self.up_label = owner.label("key_up")

    def emit_query(self, name: str) -> None:
        """Convert the numeric key once, returning false outside the byte table."""
        c = self.code
        invalid = self.owner.label("invalid_key")
        done = self.owner.label("key_result")
        c.bytes(b"\xf2\x48\x0f\x2c\xc0\x48\x85\xc0")
        c.conditional_jump(0x88, invalid)
        c.bytes(b"\x48\x3d" + struct.pack("<I", self.KEY_COUNT))
        c.conditional_jump(0x83, invalid)
        c.rip_lea_data(2, self.held if name == "held" else self.pressed)
        c.bytes(b"\x0f\xb6\x04\x02\xf2\x48\x0f\x2a\xc0")
        c.jump(done)
        c.label(invalid)
        c.bytes(b"\x0f\x57\xc0")
        c.label(done)

    def emit_helpers(self) -> None:
        for label, offset, size in (
            ("native:clear_keys", self.held, self.KEY_COUNT * 2),
            ("native:clear_pressed", self.pressed, self.KEY_COUNT),
        ):
            self.code.label(label)
            self.code.bytes(b"\x57")  # preserve Win64 nonvolatile RDI
            self.code.rip_lea_data(7, offset)
            self.code.mov_imm(0, 0)
            self.code.mov_imm(1, size // 8)
            self.code.bytes(b"\xfc\xf3\x48\xab\x5f\xc3")  # cld; rep stosq; pop rdi; ret

    def emit_dispatch(self) -> None:
        for message, label in (
            (0x100, self.down_label), (0x104, self.down_label),
            (0x101, self.up_label), (0x105, self.up_label),
        ):
            self.code.bytes(b"\x81\xfa" + struct.pack("<I", message))
            self.code.conditional_jump(0x84, label)

    def emit_handlers(self, window, default_label: str) -> None:
        c = self.code
        held_already = self.owner.label("key_already_held")
        c.label(self.down_label)
        c.bytes(b"\x49\x81\xf8" + struct.pack("<I", self.KEY_COUNT))
        c.conditional_jump(0x83, default_label)
        c.rip_lea_data(0, self.held)
        c.bytes(b"\x42\x80\x3c\x00\x00")  # cmp byte [rax+r8],0
        c.conditional_jump(0x85, held_already)
        c.rip_lea_data(0, self.pressed)
        c.bytes(b"\x42\xc6\x04\x00\x01")
        c.label(held_already)
        c.rip_lea_data(0, self.held)
        c.bytes(b"\x42\xc6\x04\x00\x01")
        # Original RCX/RDX/R8/R9 remain intact, including SYSKEY context.
        c.jump(default_label)
        c.label(self.up_label)
        c.bytes(b"\x49\x81\xf8" + struct.pack("<I", self.KEY_COUNT))
        c.conditional_jump(0x83, default_label)
        c.rip_lea_data(0, self.held)
        c.bytes(b"\x42\xc6\x04\x00\x00")
        c.jump(default_label)
