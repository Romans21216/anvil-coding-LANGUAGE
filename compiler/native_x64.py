"""Small Anvil-owned x64 encoder and PE32+ image writer."""

from __future__ import annotations

import argparse
import pathlib
import struct
from collections import OrderedDict


FILE_ALIGNMENT = 0x200
SECTION_ALIGNMENT = 0x1000
IMAGE_BASE = 0x140000000
PE_OFFSET = 0x80


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) & ~(boundary - 1)


class X64Code:
    """Byte buffer with labels and signed rel32 fixups for x64 code."""

    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[int, str]] = []

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate machine-code label {name!r}")
        self.labels[name] = len(self.code)

    def bytes(self, payload: bytes) -> None:
        self.code.extend(payload)

    def rip_call_import(self, name: str) -> None:
        self.code.extend(b"\xff\x15")
        self.fixups.append((len(self.code), f"iat:{name}"))
        self.code.extend(b"\0\0\0\0")

    def call(self, label: str) -> None:
        self.code.append(0xE8)
        self.fixups.append((len(self.code), f"label:{label}"))
        self.code.extend(b"\0\0\0\0")

    def jump(self, label: str) -> None:
        self.code.append(0xE9)
        self.fixups.append((len(self.code), f"label:{label}"))
        self.code.extend(b"\0\0\0\0")

    def conditional_jump(self, condition: int, label: str) -> None:
        self.code.extend((0x0F, condition))
        self.fixups.append((len(self.code), f"label:{label}"))
        self.code.extend(b"\0\0\0\0")

    def rip_load_data(self, destination: int, data_offset: int) -> None:
        self.code.extend((0xF2, 0x0F, 0x10, 0x05 | (destination << 3)))
        self.fixups.append((len(self.code), f"data:{data_offset}"))
        self.code.extend(b"\0\0\0\0")

    def rip_store_data(self, source: int, data_offset: int) -> None:
        self.code.extend((0xF2, 0x0F, 0x11, 0x05 | (source << 3)))
        self.fixups.append((len(self.code), f"data:{data_offset}"))
        self.code.extend(b"\0\0\0\0")

    def rip_lea_data(self, destination: int, data_offset: int) -> None:
        """Load a .data address into an integer register using RIP-relative LEA."""
        self._register(destination)
        self.code.extend((0x48 | (4 if destination >= 8 else 0), 0x8D,
                          0x05 | ((destination & 7) << 3)))
        self.fixups.append((len(self.code), f"data:{data_offset}"))
        self.code.extend(b"\0\0\0\0")

    @staticmethod
    def _register(register: int) -> None:
        if not 0 <= register <= 15:
            raise ValueError("x64 register number must be from 0 to 15")

    def mov_imm(self, destination: int, value: int) -> None:
        self._register(destination)
        self.bytes(bytes((0x48 | (destination >> 3), 0xB8 + (destination & 7)))
                   + struct.pack("<Q", value & 0xFFFFFFFFFFFFFFFF))

    def mov_reg(self, destination: int, source: int) -> None:
        self._register(destination)
        self._register(source)
        self.bytes(bytes((0x48 | ((source >> 3) << 2) | (destination >> 3),
                          0x89, 0xC0 | ((source & 7) << 3) | (destination & 7))))

    def rip_int(self, register: int, data_offset: int, *, store: bool = False) -> None:
        self._register(register)
        self.bytes(bytes((0x48 | ((register >> 3) << 2), 0x89 if store else 0x8B,
                          0x05 | ((register & 7) << 3))))
        self.fixups.append((len(self.code), f"data:{data_offset}"))
        self.bytes(b"\0\0\0\0")

    def stack_int(self, register: int, offset: int, *, store: bool = False,
                  address: bool = False) -> None:
        self._register(register)
        opcode = 0x8D if address else (0x89 if store else 0x8B)
        self.bytes(bytes((0x48 | ((register >> 3) << 2), opcode,
                          0x84 | ((register & 7) << 3), 0x24))
                   + struct.pack("<i", offset))

    def rbp_int(self, register: int, offset: int, *, store: bool = False) -> None:
        """Load/store a frame-relative integer or pointer without scratch registers."""
        self._register(register)
        self.bytes(bytes((0x48 | ((register >> 3) << 2),
                          0x89 if store else 0x8B,
                          0x85 | ((register & 7) << 3))) + struct.pack("<i", offset))

    def scalar_memory(self, register: int, base: int, displacement: int,
                      *, store: bool = False) -> None:
        """MOVSD between an XMM register and [base + signed displacement].

        Always encode a displacement, including zero, so RBP/R13 cannot
        accidentally select RIP-relative addressing. RSP/R12 require a SIB.
        """
        self._register(register)
        self._register(base)
        if not -(1 << 31) <= displacement < (1 << 31):
            raise ValueError("x64 memory displacement must fit signed 32 bits")
        short = -128 <= displacement <= 127
        prefix = bytes((0x40 | ((register >> 3) << 2) | (base >> 3),))
        self.bytes(b"\xf2" + (prefix if prefix != b"\x40" else b"")
                   + bytes((0x0F, 0x11 if store else 0x10,
                            (0x40 if short else 0x80) | ((register & 7) << 3) | (base & 7))))
        if base & 7 == 4:
            self.bytes(b"\x24")
        self.bytes(struct.pack("<b" if short else "<i", displacement))

    def rip_lea_label(self, destination: int, label: str) -> None:
        self._register(destination)
        self.bytes(bytes((0x48 | ((destination >> 3) << 2), 0x8D,
                          0x05 | ((destination & 7) << 3))))
        self.fixups.append((len(self.code), f"label:{label}"))
        self.bytes(b"\0\0\0\0")

    def finish(self, import_rvas: dict[str, int], text_rva: int = SECTION_ALIGNMENT) -> bytes:
        result = bytearray(self.code)
        for offset, target in self.fixups:
            if target.startswith("iat:"):
                address = import_rvas[target[4:]]
            elif target.startswith("data:"):
                address = import_rvas["__data_base__"] + int(target[5:])
            else:
                address = text_rva + self.labels[target[6:]]
            origin = text_rva + offset + 4
            displacement = address - origin
            if not -(1 << 31) <= displacement < (1 << 31):
                raise ValueError(f"x64 rel32 target out of range: {target}")
            struct.pack_into("<i", result, offset, displacement)
        return bytes(result)


class Pe32Plus:
    """Create a fixed-base console PE executable from native x64 sections."""

    def __init__(self, text: bytes, imports: list[tuple[str, str]]) -> None:
        if not text:
            raise ValueError("PE executable needs a non-empty .text section")
        self.text = text
        self.imports = imports

    def _import_section(self, rva: int) -> tuple[bytes, dict[str, int]]:
        if not self.imports:
            return b"", {}
        grouped: OrderedDict[str, list[str]] = OrderedDict()
        for dll, function in self.imports:
            grouped.setdefault(dll, []).append(function)
        descriptor_size = 20 * (len(grouped) + 1)
        data = bytearray(descriptor_size)
        imports: dict[str, int] = {}
        library_records = []
        for dll, functions in grouped.items():
            ilt = len(data)
            data.extend(b"\0" * (8 * (len(functions) + 1)))
            iat = len(data)
            data.extend(b"\0" * (8 * (len(functions) + 1)))
            dll_offset = len(data)
            data.extend(dll.encode("ascii") + b"\0")
            library_records.append((dll, functions, ilt, iat, dll_offset))
            for index, function in enumerate(functions):
                if len(data) & 1:
                    data.append(0)
                hint_name = len(data)
                data.extend(b"\0\0" + function.encode("ascii") + b"\0")
                hint_name_rva = rva + hint_name
                struct.pack_into("<Q", data, ilt + index * 8, hint_name_rva)
                struct.pack_into("<Q", data, iat + index * 8, hint_name_rva)
                imports[function] = rva + iat + index * 8
        for descriptor, (_, _, ilt, iat, dll_offset) in enumerate(library_records):
            struct.pack_into(
                "<IIIII", data, descriptor * 20, rva + ilt, 0, 0,
                rva + dll_offset, rva + iat
            )
        return bytes(data), imports

    def fixup_targets(self, text_size: int) -> dict[str, int]:
        text_rva = SECTION_ALIGNMENT
        rdata_rva = text_rva + align(text_size, SECTION_ALIGNMENT)
        rdata, targets = self._import_section(rdata_rva)
        data_rva = rdata_rva + align(max(1, len(rdata)), SECTION_ALIGNMENT)
        targets["__data_base__"] = data_rva
        return targets

    def build(
        self, entry_offset: int = 0, data: bytes = b"\0"
    ) -> bytes:
        section_count = 3
        optional_size = 240
        headers_end = PE_OFFSET + 4 + 20 + optional_size + section_count * 40
        headers_size = align(headers_end, FILE_ALIGNMENT)

        text_rva = SECTION_ALIGNMENT
        rdata_rva = text_rva + align(len(self.text), SECTION_ALIGNMENT)
        rdata, import_rvas = self._import_section(rdata_rva)
        data_rva = rdata_rva + align(max(1, len(rdata)), SECTION_ALIGNMENT)
        sections = [
            (b".text", self.text, text_rva, 0x60000020),
            (b".rdata", rdata, rdata_rva, 0x40000040),
            (b".data", data or b"\0", data_rva, 0xC0000040),
        ]

        file_cursor = headers_size
        section_headers = bytearray()
        section_blobs: list[tuple[int, bytes]] = []
        for name, payload, virtual_address, characteristics in sections:
            virtual_size = max(1, len(payload))
            raw_size = align(virtual_size, FILE_ALIGNMENT)
            section_headers.extend(
                struct.pack(
                    "<8sIIIIIIHHI",
                    name,
                    virtual_size,
                    virtual_address,
                    raw_size,
                    file_cursor,
                    0,
                    0,
                    0,
                    0,
                    characteristics,
                )
            )
            section_blobs.append((file_cursor, payload.ljust(raw_size, b"\0")))
            file_cursor += raw_size

        size_of_image = align(
            sections[-1][2] + max(1, len(sections[-1][1])), SECTION_ALIGNMENT
        )
        size_of_code = align(len(self.text), FILE_ALIGNMENT)
        size_of_init_data = sum(
            align(len(payload), FILE_ALIGNMENT) for _, payload, _, _ in sections[1:]
        )
        optional = bytearray(optional_size)
        struct.pack_into("<HBBIIIII", optional, 0, 0x20B, 14, 0, size_of_code,
                         size_of_init_data, 0, text_rva + entry_offset, text_rva)
        struct.pack_into("<QII", optional, 24, IMAGE_BASE, SECTION_ALIGNMENT,
                         FILE_ALIGNMENT)
        struct.pack_into("<HHHHHH", optional, 40, 6, 0, 0, 0, 6, 0)
        struct.pack_into("<IIIIH", optional, 52, 0, size_of_image, headers_size, 0, 3)
        struct.pack_into("<H", optional, 70, 0x0100)  # NX_COMPAT, fixed image base
        struct.pack_into("<QQQQII", optional, 72, 0x100000, 0x1000, 0x100000,
                         0x1000, 0, 16)
        if self.imports:
            import_count = len({dll for dll, _ in self.imports})
            struct.pack_into("<II", optional, 120, rdata_rva,
                             20 * (import_count + 1))

        coff = struct.pack(
            "<HHIIIHH", 0x8664, section_count, 0, 0, 0, optional_size, 0x0023
        )
        pe_header = b"PE\0\0" + coff + bytes(optional) + bytes(section_headers)
        dos = bytearray(PE_OFFSET)
        dos[0:2] = b"MZ"
        struct.pack_into("<I", dos, 0x3C, PE_OFFSET)
        output = bytearray(headers_size)
        output[:PE_OFFSET] = dos
        output[PE_OFFSET:PE_OFFSET + len(pe_header)] = pe_header
        for offset, payload in section_blobs:
            output.extend(b"\0" * max(0, offset - len(output)))
            output[offset:offset + len(payload)] = payload
        return bytes(output)


def minimal_exit_exe(exit_code: int) -> bytes:
    code = X64Code()
    code.bytes(b"\xb9" + struct.pack("<I", exit_code & 0xFFFFFFFF))  # mov ecx, imm32
    code.bytes(b"\x48\x83\xec\x28")  # reserve shadow space and align the stack
    code.rip_call_import("ExitProcess")
    code.bytes(b"\xcc")
    # PE layout is deterministic, so .rdata begins at the next page after .text.
    text = bytes(code.code)
    rdata_rva = SECTION_ALIGNMENT + align(len(text), SECTION_ALIGNMENT)
    _, import_rvas = Pe32Plus(text, [("KERNEL32.dll", "ExitProcess")])._import_section(rdata_rva)
    return Pe32Plus(code.finish(import_rvas), [("KERNEL32.dll", "ExitProcess")]).build()


def main() -> int:
    parser = argparse.ArgumentParser(description="Anvil native x64 PE writer smoke tool")
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--exit-code", type=int, default=42)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(minimal_exit_exe(args.exit_code))
    print(f"Wrote native x64 PE executable: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
