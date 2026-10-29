"""Execute ABI boundaries and register/addressing combinations in emitted PEs."""

import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

from compiler.native_abi import Win64NumericABI
from compiler.native_x64 import X64Code, Pe32Plus
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


@unittest.skipUnless(sys.platform == "win32", "emitted Windows x64 executables")
class NativeABITests(unittest.TestCase):
    def run_image(self, image):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "abi.exe"
            path.write_bytes(image)
            result = subprocess.run([str(path)], capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout.decode("utf-8")

    def test_scalar_memory_all_registers_bases_and_displacement_boundaries(self):
        c = X64Code()
        data = bytearray(1040)
        struct.pack_into("<d", data, 8, -137.125)
        c.label("entry")
        c.rip_int(4, 0, store=True)  # restore the actual process stack before APIs
        for base in range(16):
            for xmm in range(16):
                for displacement in (-256, -129, -128, 0, 119, 127, 128, 256):
                    source = 512 + displacement
                    destination = source + 8
                    # Reset sentinels each time, independently of the MOVSD encoder.
                    c.mov_imm(0, struct.unpack("<Q", struct.pack("<d", -137.125))[0])
                    c.rip_int(0, source, store=True)
                    c.mov_imm(0, 0)
                    c.rip_int(0, destination, store=True)
                    c.rip_lea_data(base, 512)
                    c.scalar_memory(xmm, base, displacement)
                    c.scalar_memory(xmm, base, displacement + 8, store=True)
                    c.rip_load_data(0, destination)
                    c.rip_load_data(1, 8)
                    c.bytes(b"\x66\x0f\x2e\xc1")  # ucomisd xmm0,xmm1
                    c.conditional_jump(0x85, "failure")
                    c.conditional_jump(0x8A, "failure")  # unordered cannot pass
        c.mov_imm(1, 0)
        c.jump("exit")
        c.label("failure")
        c.mov_imm(1, 2)
        c.label("exit")
        c.rip_int(4, 0)
        c.bytes(b"\x48\x83\xec\x28")
        c.rip_call_import("ExitProcess")
        c.bytes(b"\xcc")
        imports = [("KERNEL32.dll", "ExitProcess")]
        targets = Pe32Plus(bytes(c.code), imports).fixup_targets(len(c.code))
        self.run_image(Pe32Plus(c.finish(targets), imports).build(data=bytes(data)))

    def test_integer_memory_all_registers_bases_widths_and_displacements(self):
        c = X64Code()
        c.label("entry")
        c.rip_int(4,0,store=True)
        sentinel = 0x00007ABC89ABCDEF  # canonical even when exercised as RSP
        for width in (4,8):
            for base in range(16):
                for register in range(16):
                    for displacement in (-129,-128,0,127,128):
                        source,destination = 512+displacement,520+displacement
                        c.mov_imm(0,sentinel)
                        c.rip_int(0,source,store=True)
                        c.rip_lea_data(base,512)
                        c.memory_int(register,base,displacement,width=width)
                        c.rip_int(register,destination,store=True)
                        c.rip_int(4,0)  # RSP as value register is restored before calls
                        c.rip_int(0,destination)
                        c.mov_imm(1,sentinel if width == 8 else sentinel & 0xFFFFFFFF)
                        c.bytes(b"\x48\x39\xc8")
                        c.conditional_jump(0x85,"failure")
                        c.mov_imm(0,0)
                        c.rip_int(0,destination,store=True)
                        c.mov_imm(register,sentinel)
                        c.rip_lea_data(base,512)
                        # When value and base coincide, store the actual base value.
                        c.rip_int(register,8,store=True)
                        c.memory_int(register,base,displacement+8,store=True,width=width)
                        c.rip_int(4,0)
                        c.rip_int(0,destination)
                        c.rip_int(1,8)
                        if width == 4:
                            c.bytes(b"\x89\xc9")
                        c.bytes(b"\x48\x39\xc8")
                        c.conditional_jump(0x85,"failure")
        c.mov_imm(1,0)
        c.jump("exit")
        c.label("failure")
        c.mov_imm(1,2)
        c.label("exit")
        c.rip_int(4,0)
        c.bytes(b"\x48\x83\xec\x28")
        c.rip_call_import("ExitProcess")
        c.bytes(b"\xcc")
        imports = [("KERNEL32.dll","ExitProcess")]
        targets = Pe32Plus(bytes(c.code),imports).fixup_targets(len(c.code))
        self.run_image(Pe32Plus(c.finish(targets),imports).build(data=b"\0"*1040))

    def test_numeric_calls_zero_through_sixteen_arguments_reentrant_frames(self):
        # Each argument is weighted differently, so swapped stack/register arguments
        # cannot hide behind an unchanged sum. Argument evaluation has side effects.
        source = "fn(next)\n add var(sequence) 1\n output var(sequence)\nend\n"
        expected = 0
        for count in range(17):
            params = [f"p{i}" for i in range(count)]
            source += f"fn(f{count}" + (", " + ", ".join(params) if params else "") + ")\n"
            # Push parameter storage across the disp8 boundary.
            source += "".join(f" set local(padding{i}) = {i}\n" for i in range(20))
            source += " output " + (" + ".join(f"var(p{i}) * {i+1}" for i in range(count)) or "7.25") + "\nend\n"
        source += "fn(main)\n set local(total) = 0\n"
        for count in range(17):
            source += " set var(sequence) = 0\n set local(result) = call fn(f" + str(count)
            source += (", " + ", ".join("call fn(next)" for _ in range(count))) if count else ""
            source += ")\n add local(total) local(result) * " + str(count+1) + "\n"
            expected += (sum(i*i for i in range(1, count+1)) if count else 7.25) * (count+1)
        source += " output local(total)\nend\n"
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "calls.ANVL"
            path.write_text(source, encoding="utf-8")
            functions, top, variables, arrays = parse(path, source)
            image = NativeCodegen(path, functions, top, variables, arrays).generate()
        self.assertEqual(self.run_image(image), f"{expected}\n")

    def test_calls_against_independent_stack_and_register_callee(self):
        c = X64Code()
        c.label("entry")
        c.rip_int(4, 0, store=True)
        c.bytes(b"\x55\x48\x89\xe5\x48\x81\xec\x80\x00\x00\x00")
        values = [struct.unpack("<Q", struct.pack("<d", i + 0.125))[0] for i in range(16)]
        offsets = [-8 * (i + 1) for i in range(16)]

        def check_rax(value):
            c.mov_imm(10, value)
            c.bytes(b"\x4c\x39\xd0")  # cmp rax,r10
            c.conditional_jump(0x85, "failure")

        for offset, value in zip(offsets, values):
            c.mov_imm(0, value)
            c.rbp_int(0, offset, store=True)
        for count in range(17):
            Win64NumericABI(c).call(f"callee{count}", offsets[:count])
            # A callee is entitled to overwrite all four shadow slots. None of
            # those writes may overwrite the caller's saved values or RBP.
            for offset, value in zip(offsets, values):
                c.rbp_int(0, offset)
                check_rax(value)
        c.mov_imm(1, 0)
        c.jump("exit")
        for count in range(17):
            c.label(f"callee{count}")
            c.mov_reg(0, 4)
            c.bytes(b"\x48\x83\xe0\x0f")  # return address makes RSP 8 mod 16
            check_rax(8)
            for index in range(count):
                if index < 4:
                    c.bytes(bytes((0x66, 0x48, 0x0F, 0x7E, 0xC0 | (index << 3))))
                else:
                    c.stack_int(0, 40 + (index - 4) * 8)
                check_rax(values[index])
            c.mov_imm(0, 0xDEADBEEF)
            for offset in (8, 16, 24, 32):
                c.stack_int(0, offset, store=True)
            c.bytes(b"\xc3")
        c.label("failure")
        c.mov_imm(1, 2)
        c.label("exit")
        c.rip_int(4, 0)
        c.bytes(b"\x48\x83\xec\x28")
        c.rip_call_import("ExitProcess")
        c.bytes(b"\xcc")
        imports = [("KERNEL32.dll", "ExitProcess")]
        targets = Pe32Plus(bytes(c.code), imports).fixup_targets(len(c.code))
        self.run_image(Pe32Plus(c.finish(targets), imports).build(data=b"\0" * 8))


class NativeABIValidationTests(unittest.TestCase):
    def test_invalid_addressing_and_argument_counts_are_rejected(self):
        for count in (-1, 17):
            with self.assertRaises(ValueError):
                Win64NumericABI.outgoing_size(count)
        for register, base, offset in ((16, 0, 0), (0, -1, 0), (0, 0, 1 << 31), (0, 0, -(1 << 31)-1)):
            with self.assertRaises(ValueError):
                X64Code().scalar_memory(register, base, offset)
