"""Win64 numeric ABI at the boundary of Anvil-owned native functions.

Arguments are already evaluated into distinct RBP-relative slots. This layer
only transports values; source evaluation order and lifetime belong to lowering.
It assumes the caller's current RSP is aligned to 16 bytes before CALL.
"""

import struct


class Win64NumericABI:
    MAX_ARGUMENTS = 16
    SHADOW_BYTES = 32
    REGISTER_ARGUMENTS = 4

    def __init__(self, code):
        self.code = code

    @classmethod
    def _validate(cls, count):
        if not 0 <= count <= cls.MAX_ARGUMENTS:
            raise ValueError("Anvil numeric ABI supports at most sixteen arguments")

    @classmethod
    def outgoing_size(cls, count):
        cls._validate(count)
        return (cls.SHADOW_BYTES + max(0, count - cls.REGISTER_ARGUMENTS) * 8 + 15) & ~15

    def call(self, label, frame_offsets):
        """Call with binary64 arguments saved in the caller's RBP frame."""
        size = self.outgoing_size(len(frame_offsets))
        c = self.code
        c.bytes(b"\x48\x81\xec" + struct.pack("<I", size))
        for index, offset in enumerate(frame_offsets[4:], 4):
            c.scalar_memory(0, 5, offset)
            c.scalar_memory(0, 4, self.SHADOW_BYTES + (index - 4) * 8, store=True)
        for index, offset in enumerate(frame_offsets[:4]):
            c.scalar_memory(index, 5, offset)
        c.call(label)
        c.bytes(b"\x48\x81\xc4" + struct.pack("<I", size))

    def save_parameters(self, frame_offsets):
        """Save incoming arguments after PUSH RBP / MOV RBP,RSP / frame allocation."""
        self._validate(len(frame_offsets))
        c = self.code
        for index, offset in enumerate(frame_offsets):
            if index < self.REGISTER_ARGUMENTS:
                c.scalar_memory(index, 5, offset, store=True)
            else:
                # Saved RBP + return address + caller shadow space precede arg 5.
                c.scalar_memory(0, 5, 16 + self.SHADOW_BYTES + (index - 4) * 8)
                c.scalar_memory(0, 5, offset, store=True)
