"""Native numeric primitives and demand-loaded Anvil procedural routines."""

from pathlib import Path
import re
import struct

from compiler.common import CompileError


class NativeMath:
    ARITY = {"abs": 1, "sqrt": 1, "floor": 1, "ceil": 1,
             "min": 2, "max": 2, "rnd": 2, "noise": 3, "fbm": 6,
             "_anvil_native_hash": 3}
    PREFIX = "_anvil_native_"
    DEFAULT_SEED = 0x9E3779B97F4A7C15

    def __init__(self, owner):
        self.owner = owner
        self.code = owner.code
        self.state = None
        self.library = None
        self.pending = []
        self.constants = {}

    def random_state(self):
        if self.state is None:
            self.state = self.owner.reserve_data(struct.pack("<Q", self.DEFAULT_SEED))
        return self.state

    def constant(self, register, number):
        payload = struct.pack("<d", number)
        if payload not in self.constants:
            self.constants[payload] = self.owner.reserve_data(payload)
        offset = self.constants[payload]
        self.code.rip_load_data(register, offset)

    def round(self, ceiling=False):
        """SSE2 rounding without an int64 conversion for already integral doubles."""
        c = self.code
        done = self.owner.label("rounded")
        c.bytes(b"\x66\x48\x0f\x7e\xc0")  # bits -> rax
        c.mov_imm(1, 0x7FFFFFFFFFFFFFFF)
        c.bytes(b"\x48\x21\xc8")
        c.mov_imm(1, 0x4330000000000000)  # all finite |x| >= 2^52 are integral
        c.bytes(b"\x48\x39\xc8")
        c.conditional_jump(0x83, done)
        c.bytes(b"\xf2\x48\x0f\x2c\xc0\xf2\x48\x0f\x2a\xc8")
        c.bytes(b"\x66\x0f\x2e\xc1")  # original vs truncation
        adjust = self.owner.label("round_adjust")
        c.conditional_jump(0x87 if ceiling else 0x82, adjust)
        c.bytes(b"\x66\x0f\x28\xc1")
        c.jump(done)
        c.label(adjust)
        c.bytes(b"\x66\x0f\x28\xc1")
        self.constant(1, 1)
        c.bytes(b"\xf2\x0f\x58\xc1" if ceiling else b"\xf2\x0f\x5c\xc1")
        c.label(done)

    def seed(self, line):
        c = self.code
        failure = self.owner.label("seed_range")
        high = self.owner.label("seed_unsigned_high")
        ready = self.owner.label("seed_ready")
        nonzero = self.owner.label("seed_nonzero")
        done = self.owner.label("seed_done")
        self.constant(1, 0)
        c.bytes(b"\x66\x0f\x2e\xc1")
        c.conditional_jump(0x82, failure)
        self.constant(1, float(1 << 64))
        c.bytes(b"\x66\x0f\x2e\xc1")
        c.conditional_jump(0x83, failure)
        self.constant(1, float(1 << 63))
        c.bytes(b"\x66\x0f\x2e\xc1")
        c.conditional_jump(0x83, high)
        c.bytes(b"\xf2\x48\x0f\x2c\xc0")
        c.jump(ready)
        c.label(high)
        c.bytes(b"\xf2\x0f\x5c\xc1\xf2\x48\x0f\x2c\xc0")
        c.mov_imm(1, 1 << 63)
        c.bytes(b"\x48\x09\xc8")
        c.label(ready)
        c.bytes(b"\x48\x85\xc0")
        c.conditional_jump(0x85, nonzero)
        c.mov_imm(0, self.DEFAULT_SEED)
        c.label(nonzero)
        c.rip_int(0, self.random_state(), store=True)
        c.jump(done)
        c.label(failure)
        self.owner.emit_runtime_error(f"Anvil seed range error at line {line} ({self.owner.path})\n")
        c.label(done)

    def rnd(self, load, line):
        c = self.code
        failure = self.owner.label("random_range")
        done = self.owner.label("random_done")
        singleton = self.owner.label("random_singleton")
        # Keep the inclusive result within the exactly representable integer range.
        for index in range(2):
            load(index, 0)
            self.constant(1, -9007199254740991.0)
            c.bytes(b"\x66\x0f\x2e\xc1")
            c.conditional_jump(0x82, failure)
            self.constant(1, 9007199254740991.0)
            c.bytes(b"\x66\x0f\x2e\xc1")
            c.conditional_jump(0x87, failure)
        for ceiling, destination, opcode in ((True, 8, b"\xf2\x0f\x5d\xc1"),
                                              (False, 9, b"\xf2\x0f\x5f\xc1")):
            load(0, 0)
            load(1, 1)
            c.bytes(opcode)
            self.round(ceiling)
            c.bytes(b"\xf2\x48\x0f\x2c\xc0")
            c.mov_reg(destination, 0)
        c.bytes(b"\x4d\x39\xc1")  # cmp r9, r8: hi <= lo returns ceil(lo)
        c.conditional_jump(0x8E, singleton)
        c.mov_reg(10, 9)
        c.bytes(b"\x4d\x29\xc2\x49\xff\xc2")  # inclusive span
        c.rip_int(0, self.random_state())
        for shift, opcode in ((12, b"\x48\xc1\xea"), (25, b"\x48\xc1\xe2"),
                              (27, b"\x48\xc1\xea")):
            c.mov_reg(2, 0)
            c.bytes(opcode + bytes((shift,)) + b"\x48\x31\xd0")
        c.rip_int(0, self.random_state(), store=True)
        c.mov_imm(1, 2685821657736338717)
        c.bytes(b"\x48\x0f\xaf\xc1\x31\xd2\x49\xf7\xf2")
        c.mov_reg(0, 2)
        c.bytes(b"\x4c\x01\xc0\xf2\x48\x0f\x2a\xc0")
        c.jump(done)
        c.label(singleton)
        c.bytes(b"\xf2\x49\x0f\x2a\xc0")  # r8 -> xmm0
        c.jump(done)
        c.label(failure)
        self.owner.emit_runtime_error(f"Anvil random range error at line {line} ({self.owner.path})\n")
        c.label(done)

    def emit_builtin(self, parser, name):
        owner = self.owner
        c = self.code
        count = self.ARITY[name]
        base = owner._scratch_depth
        slots = []
        for index in range(count):
            if index:
                parser._expect(",")
            parser._require_number(parser.emit())
            slot = owner.push_temp()
            owner.store_local(slot)
            slots.append(slot)
        parser._expect(")")

        def load(index, register):
            offset = owner._temporary_offset(slots[index])
            c.bytes(owner._memory_operand(register, 5, offset))

        if name in ("noise", "fbm"):
            if name == "noise":
                failure = owner.label("noise_coordinate_error")
                ready = owner.label("noise_coordinate_ready")
                for index in range(3):
                    load(index, 0)
                    self.constant(1, -2147483648.0)
                    c.bytes(b"\x66\x0f\x2e\xc1")
                    c.conditional_jump(0x82, failure)
                    self.constant(1, 2147483647.0)
                    c.bytes(b"\x66\x0f\x2e\xc1")
                    c.conditional_jump(0x83, failure)
                c.jump(ready)
                c.label(failure)
                location = ("in procedural runtime" if parser.scope is not None and
                            parser.scope.name.startswith(self.PREFIX) else f"at line {parser.line}")
                owner.emit_runtime_error(f"Anvil noise coordinate range error {location} ({owner.path})\n")
                c.label(ready)
            helper = self.require(name)
            # Calls reuse already evaluated slots, including the stack parameters.
            owner.emit_saved_call(helper, slots)
        elif name == "rnd":
            self.rnd(load, parser.line)
        else:
            load(0, 0)
            if name in ("min", "max"):
                load(1, 1)
                c.bytes(b"\xf2\x0f\x5d\xc1" if name == "min" else b"\xf2\x0f\x5f\xc1")
            elif name in ("floor", "ceil"):
                self.round(name == "ceil")
            elif name == "sqrt":
                c.bytes(b"\xf2\x0f\x51\xc0")
                owner.emit_finite_check(parser.line)
            elif name == "abs":
                c.bytes(b"\x66\x48\x0f\x7e\xc0")
                c.mov_imm(0x1, 0x7FFFFFFFFFFFFFFF)
                c.bytes(b"\x48\x21\xc8\x66\x48\x0f\x6e\xc0")
            else:
                if parser.scope is None or not parser.scope.name.startswith(self.PREFIX):
                    raise CompileError(f"{owner.path}:{parser.line}: reserved native runtime intrinsic")
                for index in (1, 2):
                    load(index, index)
                self.hash()
        owner._scratch_depth = base

    def hash(self):
        c = self.code
        c.bytes(b"\xf2\x0f\x2c\xc0\x69\xc0" + struct.pack("<I", 374761393))
        for register, multiplier in ((1, 668265263), (2, 2147483647)):
            c.bytes(b"\xf2\x0f\x2c" + bytes((0xD0 | register,)))
            c.bytes(b"\x69\xd2" + struct.pack("<I", multiplier) + b"\x01\xd0")
        c.bytes(b"\x89\xc2\xc1\xea\x0d\x31\xd0\x69\xc0" + struct.pack("<I", 1274126177))
        c.bytes(b"\x89\xc2\xc1\xea\x10\x31\xd0\x83\xe0\x0f\xf2\x0f\x2a\xc0")

    def require(self, public_name):
        if self.library is None:
            from compiler.parser import parse
            path = Path(__file__).resolve().parents[1] / "runtime" / "native" / "procedural.ANVL"
            self.library = parse(path, path.read_text(encoding="utf-8"))[0]
        name = self.PREFIX + public_name
        self._require_function(name)
        return name

    def _require_function(self, name):
        if name in self.owner.functions:
            return
        function = self.library[name]
        self.owner.functions[name] = function
        self.pending.append(name)

        def visit(nodes):
            for node in nodes:
                for text in [node.value] + node.params:
                    for dependency in re.findall(r"call\s+fn\((_anvil_native_\w+)", text):
                        self._require_function(dependency)
                visit(node.body)
                visit(node.otherwise)

        visit(function.body)

    def emit_pending(self):
        while self.pending:
            name = self.pending.pop(0)
            self.owner._emit_function(name, self.owner.functions[name])
