"""Per-invocation native array storage using the Windows process heap."""

import struct
from compiler.common import MAX_ACTIVE_LOCAL_ARRAY_BYTES


class NativeArrays:
    IMPORTS = [('KERNEL32.dll', name) for name in ('GetProcessHeap','HeapAlloc','HeapFree')]

    def __init__(self, owner):
        self.owner = owner
        self.active = None
        self.total = 0
        self.offsets = {}

    def plan(self, fn):
        self.offsets = {}
        self.total = 0
        for name, size in sorted(fn.local_arrays.items()):
            self.offsets[name] = self.total
            self.total += size * 8
        if self.total and self.active is None:
            self.active = self.owner.reserve_data(b'\0' * 8)
        count = len(self.owner._frame_slots)
        self.pointer = -(count + 1) * 8
        self.result = -(count + 2) * 8
        self.return_label = self.owner.label('array_return')
        return 2 if self.total else 0

    def address(self, name):
        c = self.owner.code
        c.rbp_int(2, self.pointer)
        if self.offsets[name]:
            c.bytes(b'\x48\x81\xc2' + struct.pack('<I', self.offsets[name]))

    def enter(self, fn):
        if not self.total:
            return
        o, c = self.owner, self.owner.code
        failure, ready = o.label('array_allocation_error'), o.label('array_allocated')
        c.rip_int(0, self.active)
        c.bytes(b'\x48\x3d' + struct.pack('<I', MAX_ACTIVE_LOCAL_ARRAY_BYTES-self.total))
        c.conditional_jump(0x87, failure)
        c.bytes(b'\x48\x83\xec\x30')
        c.rip_call_import('GetProcessHeap')
        c.mov_reg(1, 0)
        c.mov_imm(2, 8)  # HEAP_ZERO_MEMORY
        c.mov_imm(8, self.total)
        c.rip_call_import('HeapAlloc')
        c.bytes(b'\x48\x83\xc4\x30\x48\x85\xc0')
        c.conditional_jump(0x84, failure)
        o._store_rax_rbp(self.pointer)
        c.rip_int(0, self.active)
        c.bytes(b'\x48\x05' + struct.pack('<I', self.total))
        c.rip_int(0, self.active, store=True)
        c.jump(ready)
        c.label(failure)
        o.emit_runtime_error(f'Anvil local array allocation/budget error at line {fn.line} ({o.path})\n')
        c.label(ready)

    def leave(self, fn):
        if not self.total:
            self.owner.code.bytes(b'\xc9\xc3')
            return
        o, c = self.owner, self.owner.code
        c.scalar_memory(0, 5, self.result, store=True)
        c.bytes(b'\x48\x83\xec\x30')
        c.rip_call_import('GetProcessHeap')
        c.mov_reg(1, 0)
        c.mov_imm(2, 0)
        c.rbp_int(8, self.pointer)
        c.rip_call_import('HeapFree')
        c.bytes(b'\x48\x83\xc4\x30\x85\xc0')
        ready = o.label('array_released')
        c.conditional_jump(0x85, ready)
        o.emit_runtime_error(f'Anvil local array release error at line {fn.line} ({o.path})\n')
        c.label(ready)
        c.rip_int(0, self.active)
        c.bytes(b'\x48\x2d' + struct.pack('<I', self.total))
        c.rip_int(0, self.active, store=True)
        c.scalar_memory(0, 5, self.result)
        c.bytes(b'\xc9\xc3')
