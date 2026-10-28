"""Direct x64 code generation for the first native Anvil compiler milestone."""

from __future__ import annotations

import math
import pathlib
import re
import struct
from dataclasses import dataclass

from compiler.common import CompileError, KEY_CODES, Node
from compiler.expressions import ExpressionParser, MAX_EXPRESSION_DEPTH, split_args
from compiler.lexer import strip_comment
from compiler.native_x64 import Pe32Plus, X64Code


@dataclass(frozen=True)
class _Value:
    kind: str
    text: str


class _Expression:
    PRECEDENCE = {
        "or": 1,
        "and": 2,
        "=": 3,
        "==": 3,
        "!=": 3,
        "<": 4,
        "<=": 4,
        ">": 4,
        ">=": 4,
        "+": 5,
        "-": 5,
        "*": 6,
        "/": 6,
        "%": 6,
    }

    def __init__(self, owner: "NativeCodegen", line: int, raw: str, scope: Node | None):
        self.owner = owner
        self.line = line
        self.scope = scope
        self.tokens = ExpressionParser(
            owner.path, line, raw, owner.functions, scope, owner.arrays
        ).tokens
        self.index = 0

    def _peek(self, value: str | None = None) -> bool:
        return self.index < len(self.tokens) and (
            value is None or self.tokens[self.index][1] == value
        )

    def _take(self) -> tuple[str, str]:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def emit(self, minimum: int = 0) -> _Value:
        self.owner._expression_depth += 1
        try:
            if self.owner._expression_depth > MAX_EXPRESSION_DEPTH:
                raise CompileError(f"{self.owner.path}:{self.line}: expression nesting exceeds {MAX_EXPRESSION_DEPTH} parser levels")
            return self._emit_impl(minimum)
        finally:
            self.owner._expression_depth -= 1

    def _emit_impl(self, minimum: int = 0) -> _Value:
        if not self._peek():
            raise CompileError(f"{self.owner.path}:{self.line}: expected expression")
        kind, value = self._take()
        if kind == "number":
            number = float(value)
            if not math.isfinite(number):
                raise CompileError(f"{self.owner.path}:{self.line}: numeric literal must be finite")
            self.owner.emit_float(number)
            left = _Value("number", value)
        elif kind == "variable":
            name = value[4:-1]
            self.owner.load_variable(name, self.scope, self.line)
            left = _Value("number", name)
        elif kind == "local":
            name = value[6:-1]
            self.owner.load_local(name, self.scope, self.line)
            left = _Value("number", name)
        elif kind == "op" and value in ("+", "-"):
            operand = self.emit(7)
            self._require_number(operand)
            if value == "-":
                self.owner.emit_negate()
            left = _Value("number", "unary")
        elif kind == "op" and value == "(":
            left = self.emit()
            self._expect(")")
        elif kind == "word" and value in ("true", "false"):
            self.owner.emit_float(1.0 if value == "true" else 0.0)
            left = _Value("number", value)
        elif kind == "word" and value in KEY_CODES:
            self.owner.emit_float(float(KEY_CODES[value]))
            left = _Value("number", value)
        elif kind == "call":
            self._emit_user_call(value)
            left = _Value("number", "call")
        elif kind == "word" and value in self.owner.BUILTIN_NAMES:
            self._emit_builtin(value)
            left = _Value("number", value)
        elif kind == "array":
            contents = value[value.index("array(") + 6:-1]
            parts = split_args(contents)
            if len(parts) != 2:
                raise CompileError(
                    f"{self.owner.path}:{self.line}: array access expects array(name, index)"
                )
            self.owner.emit_array_read(parts[0], parts[1], self.line, self.scope)
            left = _Value("number", "array")
        elif kind == "string":
            raise CompileError(
                f"{self.owner.path}:{self.line}: string expressions are not available in the native numeric backend"
            )
        else:
            raise CompileError(f"{self.owner.path}:{self.line}: unsupported native expression token {value!r}")

        while self._peek():
            operator = self.tokens[self.index][1]
            precedence = self.PRECEDENCE.get(operator, -1)
            if precedence < minimum:
                break
            self.index += 1
            self._require_number(left)
            if operator in ("and", "or"):
                short = self.owner.label("logic_short")
                done = self.owner.label("logic_done")
                self.owner.code.bytes(b"\x66\x0f\xef\xc9\x66\x0f\x2e\xc1")
                self.owner.code.conditional_jump(0x84 if operator == "and" else 0x85, short)
                right = self.emit(precedence + 1)
                self._require_number(right)
                self.owner.code.bytes(b"\x66\x0f\xef\xc9\x66\x0f\x2e\xc1")
                self.owner.code.bytes(b"\x0f\x95\xc0\x0f\xb6\xc0\xf2\x48\x0f\x2a\xc0")
                self.owner.code.jump(done)
                self.owner.code.label(short)
                self.owner.emit_float(0.0 if operator == "and" else 1.0)
                self.owner.code.label(done)
                left = _Value("number", operator)
                continue
            temp = self.owner.push_temp()
            self.owner.store_local(temp)
            right = self.emit(precedence + 1)
            self._require_number(right)
            self.owner.emit_binary(operator, temp, self.line)
            self.owner.pop_temp()
            left = _Value("number", operator)
        return left

    def compile(self) -> None:
        result = self.emit()
        self._require_number(result)
        if self._peek():
            raise CompileError(
                f"{self.owner.path}:{self.line}: unexpected token {self.tokens[self.index][1]!r}"
            )

    def _emit_user_call(self, token: str) -> None:
        contents = token[token.index("fn(") + 3:-1]
        parts = split_args(contents)
        if not parts:
            raise CompileError(f"{self.owner.path}:{self.line}: empty function call")
        name, raw_args = parts[0], parts[1:]
        target = self.owner.functions.get(name)
        if target is None:
            raise CompileError(f"{self.owner.path}:{self.line}: unknown function {name!r}")
        if len(raw_args) != len(target.params):
            raise CompileError(
                f"{self.owner.path}:{self.line}: function {name!r} expects "
                f"{len(target.params)} argument(s), got {len(raw_args)}"
            )
        self.owner.emit_call(name, raw_args, self.scope, self.line)

    def _emit_builtin(self, name: str) -> None:
        self._expect("(")
        if name in self.owner._math.ARITY:
            self.owner._math.emit_builtin(self, name)
            return
        if name == "compute":
            self._require_number(self.emit())
            self._expect(")")
            return
        if name.startswith("mouse_"):
            button = None
            if name in ("mouse_held", "mouse_pressed"):
                if not self._peek() or self.tokens[self.index][0] != "string":
                    raise CompileError(f"{self.owner.path}:{self.line}: {name}() expects a literal mouse button: left, right or middle")
                raw = self._take()[1][1:-1].lower()
                if raw not in ("left", "right", "middle"):
                    raise CompileError(f"{self.owner.path}:{self.line}: unknown mouse button {raw!r}; choose left, right or middle")
                button = ("left", "right", "middle").index(raw)
            self._expect(")")
            if self.owner._window is None:
                raise CompileError(f"{self.owner.path}:{self.line}: {name}() requires native scene 2d")
            self.owner._window.emit_mouse_query(name, button)
            return
        if name in ("held", "pressed"):
            if self._peek(")"):
                raise CompileError(f"{self.owner.path}:{self.line}: {name}() expects one numeric key argument")
            self._require_number(self.emit())
            if self._peek(","):
                raise CompileError(f"{self.owner.path}:{self.line}: {name}() expects one numeric key argument")
            self._expect(")")
            if self.owner._window is None:
                raise CompileError(f"{self.owner.path}:{self.line}: {name}() requires native scene 2d")
            self.owner._window.emit_key_query(name)
            return
        self._expect(")")
        if self.owner._window is None:
            raise CompileError(f"{self.owner.path}:{self.line}: {name}() requires native scene 2d")
        if name == "delta":
            self.owner.emit_float(1.0 / 60.0)
        else:
            self.owner._window.clock_requested = True
            self.owner.code.rip_load_data(0, self.owner._window.simulation_time)

    def _peek_expected(self, value: str) -> bool:
        return self._peek(value)

    def _expect(self, value: str) -> None:
        if not self._peek_expected(value):
            raise CompileError(f"{self.owner.path}:{self.line}: expected {value!r}")
        self.index += 1

    def _require_number(self, value: _Value) -> None:
        if value.kind != "number":
            raise CompileError(f"{self.owner.path}:{self.line}: expected a number")


class NativeCodegen:
    """Emit native x64 instructions and a PE executable without C/Rust output."""

    IMPORTS = [("KERNEL32.dll", "GetStdHandle"),
               ("KERNEL32.dll", "WriteFile"),
               ("KERNEL32.dll", "ExitProcess")]
    BUILTIN_NAMES = {"compute", "time", "delta", "held", "pressed",
                     "mouse_x", "mouse_y", "mouse_held", "mouse_pressed", "mouse_wheel",
                     "abs", "sqrt", "floor", "ceil", "min", "max", "rnd", "noise", "fbm",
                     "_anvil_native_hash"}
    MAX_DATA_BYTES = 16 * 1024 * 1024
    MAX_FRAME_BYTES = 4096

    def __init__(self, path, functions, top, variables, arrays=None):
        self.path = path
        if any(name.startswith("_anvil_native_") for name in functions):
            raise CompileError(f"{path}: function prefix _anvil_native_ is reserved for the native runtime")
        self.functions = dict(functions)
        self.top = top
        self.variables = variables
        self.arrays = arrays or {}
        self.code = X64Code()
        self._error_messages = {}
        self._expression_depth = 0
        self._label_counter = 0
        self._frame_slots: dict[str, int] = {}
        self._scratch_base = 0
        self._scratch_depth = 0
        self._frame_size = 0
        self._scope: Node | None = None
        self._data_offsets = {
            name: index * 8 for index, name in enumerate(sorted(variables))
        }
        next_offset = len(self._data_offsets) * 8
        self._array_offsets: dict[str, int] = {}
        try:
            source_lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
        except (OSError, TypeError):
            source_lines = []
        for name in sorted(self.arrays):
            size = self.arrays[name]
            if next_offset + size * 8 > self.MAX_DATA_BYTES:
                declaration = re.compile(
                    rf"array\s+{re.escape(name)}\s*\(\s*\d+\s*\)"
                )
                line = next(
                    (
                        number
                        for number, text in enumerate(source_lines, 1)
                        if declaration.fullmatch(strip_comment(text).strip())
                    ),
                    None,
                )
                declared = getattr(self.arrays, "locations", {}).get(name)
                location = (f"{declared[0]}:{declared[1]}" if declared else
                            (f"{self.path}:{line}" if line is not None else str(self.path)))
                required = next_offset + size * 8
                raise CompileError(
                    f"{location}: direct native global data needs {required} bytes; "
                    f"the limit is {self.MAX_DATA_BYTES} bytes"
                )
            self._array_offsets[name] = next_offset
            next_offset += size * 8
        if next_offset > self.MAX_DATA_BYTES:
            raise CompileError(
                f"{self.path}: direct native global data needs {next_offset} bytes; "
                f"the limit is {self.MAX_DATA_BYTES} bytes"
            )
        self._data_size = max(8, next_offset)
        self._data = bytearray(self._data_size)
        self._window = None
        from compiler.native_math import NativeMath
        self._math = NativeMath(self)

    def reserve_data(self, payload: bytes) -> int:
        offset = (len(self._data) + 7) & ~7
        end = offset + len(payload)
        if end > self.MAX_DATA_BYTES:
            raise CompileError(f"{self.path}: native program data exceeds the 16 MiB limit")
        self._data.extend(b"\0" * (offset - len(self._data)))
        self._data.extend(payload)
        return offset

    def label(self, stem: str) -> str:
        self._label_counter += 1
        return f"{stem}_{self._label_counter}"

    def emit_float(self, value: float) -> None:
        self.code.bytes(b"\x48\xb8" + struct.pack("<Q", struct.unpack("<Q", struct.pack("<d", value))[0]))
        self.code.bytes(b"\x66\x48\x0f\x6e\xc0")  # movq xmm0, rax

    @staticmethod
    def _memory_operand(register: int, base: int, displacement: int) -> bytes:
        return NativeCodegen._xmm_rbp_operand(0x10, register, displacement)

    @staticmethod
    def _store_xmm_operand(register: int, displacement: int) -> bytes:
        return NativeCodegen._xmm_rbp_operand(0x11, register, displacement)

    @staticmethod
    def _xmm_rbp_operand(opcode: int, register: int, displacement: int) -> bytes:
        if -128 <= displacement <= 127:
            return bytes((0xF2, 0x0F, opcode, 0x45 | (register << 3), displacement & 0xFF))
        return bytes((0xF2, 0x0F, opcode, 0x85 | (register << 3))) + struct.pack("<i", displacement)

    def load_local(self, name: str, scope: Node | None, line: int) -> None:
        if name.startswith("_temporary_"):
            index = int(name.rsplit("_", 1)[1])
            displacement = -(self._scratch_base + index * 8)
        elif scope is None or name not in self._frame_slots:
            raise CompileError(f"{self.path}:{line}: unknown local variable {name!r}")
        else:
            displacement = -self._frame_slots[name]
        self.code.bytes(self._memory_operand(0, 5, displacement))

    def store_local(self, name: str) -> None:
        if name.startswith("_temporary_"):
            index = int(name.rsplit("_", 1)[1])
            if index > 16:
                raise CompileError(f"{self.path}: native expression needs more than 16 temporary slots")
            offset = -(self._scratch_base + index * 8)
        elif name in self._frame_slots:
            offset = -self._frame_slots[name]
        else:
            raise CompileError(f"native compiler internal error: local slot {name!r} missing")
        self.code.bytes(self._store_xmm_operand(0, offset))

    def load_variable(self, name: str, scope: Node | None, line: int) -> None:
        if scope is not None and name in self._frame_slots:
            self.load_local(name, scope, line)
            return
        offset = self._data_offsets.get(name)
        if offset is None:
            raise CompileError(f"{self.path}:{line}: unknown global variable {name!r}")
        self.code.rip_load_data(0, offset)

    def store_variable(self, name: str, scope: Node | None, line: int) -> None:
        if scope is not None and name in self._frame_slots:
            self.store_local(name)
            return
        offset = self._data_offsets.get(name)
        if offset is None:
            raise CompileError(f"{self.path}:{line}: unknown global variable {name!r}")
        self.code.rip_store_data(0, offset)

    def _emit_array_index(
        self, name: str, raw_index: str, line: int, scope: Node | None
    ) -> str:
        """Evaluate a global array index once, validate it, and save its int64 slot."""
        if scope is not None and name in scope.local_arrays:
            raise CompileError(
                f"{self.path}:{line}: native local arrays are not implemented yet"
            )
        size = self.arrays.get(name)
        offset = self._array_offsets.get(name)
        if size is None or offset is None:
            raise CompileError(f"{self.path}:{line}: unknown array {name!r}")
        self.emit_expression(raw_index, line, scope)
        self.emit_finite_check(line)
        self.code.bytes(b"\xf2\x48\x0f\x2c\xc0")  # cvttsd2si rax,xmm0
        self.code.bytes(b"\xf2\x48\x0f\x2a\xc8\x66\x0f\x2e\xc1")
        failure = self.label("array_index_error")
        done = self.label("array_index_valid")
        self.code.conditional_jump(0x8A, failure)  # jp: not integral/unordered
        self.code.conditional_jump(0x85, failure)  # jne: not integral
        self.code.bytes(b"\x48\x85\xc0")  # test rax,rax
        self.code.conditional_jump(0x88, failure)  # js: negative
        self.code.bytes(b"\x48\x3d" + struct.pack("<I", size))
        self.code.conditional_jump(0x83, failure)  # jae: index >= size
        slot = self.push_temp()
        displacement = -(self._scratch_base + int(slot.rsplit("_", 1)[1]) * 8)
        self._store_rax_rbp(displacement)
        self.code.jump(done)
        self.code.label(failure)
        self.emit_runtime_error(f"Anvil array index error at line {line} ({self.path})\n")
        self.code.label(done)
        return slot

    def emit_array_read(
        self, name: str, raw_index: str, line: int, scope: Node | None
    ) -> None:
        slot = self._emit_array_index(name, raw_index, line, scope)
        displacement = -(self._scratch_base + int(slot.rsplit("_", 1)[1]) * 8)
        self._load_rax_rbp(displacement)
        self.code.rip_lea_data(2, self._array_offsets[name])  # lea rdx,[array]
        self.code.bytes(b"\xf2\x0f\x10\x04\xc2")  # movsd xmm0,[rdx+rax*8]
        self.pop_temp()

    def emit_array_write(
        self,
        name: str,
        raw_index: str,
        raw_value: str,
        line: int,
        scope: Node | None,
    ) -> None:
        slot = self._emit_array_index(name, raw_index, line, scope)
        self.emit_expression(raw_value, line, scope)
        displacement = -(self._scratch_base + int(slot.rsplit("_", 1)[1]) * 8)
        self._load_rax_rbp(displacement)
        self.code.rip_lea_data(2, self._array_offsets[name])
        self.code.bytes(b"\xf2\x0f\x11\x04\xc2")  # movsd [rdx+rax*8],xmm0
        self.pop_temp()

    def emit_runtime_error(self, message_text: str) -> None:
        """Write pooled UTF-8 diagnostic data and terminate with status 2."""
        message = message_text.encode("utf-8")
        if message not in self._error_messages:
            self._error_messages[message] = self.reserve_data(message)
        self.code.mov_imm(1, -11)  # STD_OUTPUT_HANDLE, preserving existing CLI behavior
        self.code.rip_call_import("GetStdHandle")
        self.code.mov_reg(1, 0)
        self.code.rip_lea_data(2, self._error_messages[message])
        self.code.mov_imm(8, len(message))
        self.code.stack_int(9, 0x28, address=True)
        self.code.mov_imm(0, 0)
        self.code.stack_int(0, 0x20, store=True)
        self.code.rip_call_import("WriteFile")
        self.code.mov_imm(1, 2)
        self.code.rip_call_import("ExitProcess")
        self.code.bytes(b"\xcc")

    def _store_rax_rbp(self, displacement: int) -> None:
        if -128 <= displacement <= 127:
            self.code.bytes(b"\x48\x89\x45" + bytes((displacement & 0xFF,)))
        else:
            self.code.bytes(b"\x48\x89\x85" + struct.pack("<i", displacement))

    def _load_rax_rbp(self, displacement: int) -> None:
        if -128 <= displacement <= 127:
            self.code.bytes(b"\x48\x8b\x45" + bytes((displacement & 0xFF,)))
        else:
            self.code.bytes(b"\x48\x8b\x85" + struct.pack("<i", displacement))

    def push_temp(self) -> str:
        self._scratch_depth += 1
        if self._scratch_depth > 16:
            raise CompileError(f"{self.path}: native expression needs more than 16 temporary slots")
        return f"_temporary_{self._scratch_depth}"

    def pop_temp(self) -> None:
        self._scratch_depth -= 1

    def _alloc_slot(self, name: str) -> None:
        if name not in self._frame_slots:
            self._frame_slots[name] = (len(self._frame_slots) + 1) * 8

    def emit_binary(self, operator: str, left_slot: str | None = None, line: int = 0) -> None:
        if left_slot is not None:
            temp_index = int(left_slot.rsplit("_", 1)[1])
            displacement = -(self._scratch_base + temp_index * 8)
            # movapd xmm1, xmm0; load the saved left operand into xmm0.
            self.code.bytes(b"\x66\x0f\x28\xc8")
            self.code.bytes(self._memory_operand(0, 5, displacement))
        opcodes = {
            "+": b"\xf2\x0f\x58\xc1",
            "-": b"\xf2\x0f\x5c\xc1",
            "*": b"\xf2\x0f\x59\xc1",
            "/": b"\xf2\x0f\x5e\xc1",
        }
        if operator in opcodes:
            self.code.bytes(opcodes[operator])
            if line:
                self.emit_finite_check(line)
            return
        if operator in ("=", "==", "!=", "<", "<=", ">", ">="):
            self.code.bytes(b"\x66\x0f\x2e\xc1")  # ucomisd xmm0, xmm1
            setcc = {"=": 0x94, "==": 0x94, "!=": 0x95,
                     "<": 0x92, "<=": 0x96, ">": 0x97, ">=": 0x93}[operator]
            self.code.bytes(bytes((0x0F, setcc, 0xC0)))  # setcc al
            self.code.bytes(b"\x0f\xb6\xc0\xf2\x48\x0f\x2a\xc0")
            return
        if operator in ("and", "or"):
            self.code.bytes(b"\x66\x0f\xef\xd2")  # zero xmm2
            self.code.bytes(b"\x66\x0f\x2e\xc2\x0f\x95\xc0")  # left != 0 -> al
            self.code.bytes(b"\x66\x0f\x2e\xca\x0f\x95\xc1")  # right != 0 -> cl
            self.code.bytes(b"\x20\xc8" if operator == "and" else b"\x08\xc8")
            self.code.bytes(b"\x0f\xb6\xc0\xf2\x48\x0f\x2a\xc0")
            return
        raise CompileError(f"{self.path}:{line}: operator {operator!r} is not supported by native x64 yet")

    def emit_negate(self) -> None:
        self.code.bytes(b"\x66\x48\x0f\x7e\xc0")
        self.code.bytes(b"\x48\xb9\x00\x00\x00\x00\x00\x00\x00\x80")
        self.code.bytes(b"\x48\x31\xc8\x66\x48\x0f\x6e\xc0")

    def emit_finite_check(self, line: int) -> None:
        failure = self.label("nonfinite")
        done = self.label("finite")
        self.code.bytes(b"\x66\x48\x0f\x7e\xc0")  # movq rax, xmm0
        self.code.bytes(b"\x48\xc1\xe8\x34\x25\xff\x07\x00\x00")
        self.code.bytes(b"\x3d\xff\x07\x00\x00")  # cmp eax, 0x7ff
        self.code.conditional_jump(0x84, failure)  # je
        self.code.jump(done)
        self.code.label(failure)
        self.emit_runtime_error(f"Anvil numeric error at line {line} ({self.path})\n")
        self.code.label(done)

    def emit_call(self, name: str, raw_args: list[str], scope: Node | None, line: int) -> None:
        target = self.functions.get(name)
        if target is None:
            raise CompileError(f"{self.path}:{line}: unknown function {name!r}")
        if len(raw_args) != len(target.params):
            raise CompileError(
                f"{self.path}:{line}: function {name!r} expects "
                f"{len(target.params)} argument(s), got {len(raw_args)}"
            )
        if len(raw_args) > 16:
            raise CompileError(f"{self.path}:{line}: native x64 backend supports at most sixteen parameters")
        base_depth = self._scratch_depth
        slots = []
        for argument in raw_args:
            self.emit_expression(argument, line, scope)
            slot = self.push_temp()
            self.store_local(slot)
            slots.append(slot)
        self.emit_saved_call(name, slots)
        self._scratch_depth = base_depth

    def emit_saved_call(self, name: str, slots: list[str]) -> None:
        # First four doubles use XMM0-3; later doubles use Win64 stack slots.
        shadow = (32 + max(0, len(slots) - 4) * 8 + 15) & ~15
        self.code.bytes(b"\x48\x81\xec" + struct.pack("<I", shadow))
        for index in range(4, len(slots)):
            self.load_local(slots[index], self._scope, 0)
            self.code.bytes(b"\xf2\x0f\x11\x84\x24" + struct.pack("<i", 32 + (index - 4) * 8))
        for index, slot in enumerate(slots[:4]):
            displacement = -(self._scratch_base + int(slot.rsplit("_", 1)[1]) * 8)
            self.code.bytes(self._memory_operand(index, 5, displacement))
        self.code.call(f"function:{name}")
        self.code.bytes(b"\x48\x81\xc4" + struct.pack("<I", shadow))

    def emit_expression(self, raw: str, line: int, scope: Node | None) -> None:
        _Expression(self, line, raw, scope).compile()

    def emit_nodes(self, nodes: list[Node], scope: Node | None) -> None:
        for node in nodes:
            previous = self.path
            self.path = node.source or previous
            try:
                self._emit_nodes([node], scope)
            finally:
                self.path = previous

    def _emit_nodes(self, nodes: list[Node], scope: Node | None) -> None:
        for node in nodes:
            if node.kind == "seed":
                self.emit_expression(node.value, node.line, scope)
                self.emit_finite_check(node.line)
                self._math.seed(node.line)
            elif node.kind == "set":
                self.emit_expression(node.value, node.line, scope)
                self.store_variable(node.name, scope, node.line)
            elif node.kind == "local_set":
                self.emit_expression(node.value, node.line, scope)
                self.store_local(node.name)
            elif node.kind == "array_set":
                self.emit_array_write(
                    node.name, node.params[0], node.value, node.line, scope
                )
            elif node.kind == "display" and self._window is not None:
                self._window.emit_display(node, scope)
            elif node.kind in ("add", "sub", "local_add", "local_sub"):
                name = node.name
                self.load_variable(name, scope, node.line)
                temp = self.push_temp()
                self.store_local(temp)
                self.emit_expression(node.value, node.line, scope)
                self.emit_binary("+" if node.kind in ("add", "local_add") else "-", temp, node.line)
                self.pop_temp()
                self.store_variable(name, scope, node.line)
            elif node.kind == "output":
                self.emit_expression(node.value, node.line, scope)
                self.code.bytes(b"\xc9\xc3")  # leave; ret
            elif node.kind == "if":
                else_label = self.label("else")
                end_label = self.label("endif")
                self.emit_expression(node.value, node.line, scope)
                self.code.bytes(b"\x66\x0f\xef\xc9\x66\x0f\x2e\xc1")
                self.code.conditional_jump(0x84, else_label)
                self.emit_nodes(node.body, scope)
                if node.otherwise:
                    self.code.jump(end_label)
                self.code.label(else_label)
                if node.otherwise:
                    self.emit_nodes(node.otherwise, scope)
                    self.code.label(end_label)
            elif node.kind == "while":
                start = self.label("while_start")
                end = self.label("while_end")
                self.code.label(start)
                self.emit_expression(node.value, node.line, scope)
                self.code.bytes(b"\x66\x0f\xef\xc9\x66\x0f\x2e\xc1")
                self.code.conditional_jump(0x84, end)
                self.emit_nodes(node.body, scope)
                self.code.jump(start)
                self.code.label(end)
            elif node.kind == "for":
                if scope is None:
                    raise CompileError(f"{self.path}:{node.line}: native for loops require a function")
                start_slot = self.push_temp()
                end_slot = self.push_temp()
                step_slot = self.push_temp()
                self.emit_expression(node.params[0], node.line, scope)
                self.store_local(node.name)
                self.emit_expression(node.params[1], node.line, scope)
                self.store_local(end_slot)
                self.emit_expression(node.params[2], node.line, scope)
                self.store_local(step_slot)
                check_step = self.label("for_step_check")
                positive = self.label("for_positive")
                body = self.label("for_body")
                end = self.label("for_end")
                self.code.label(check_step)
                self.load_local(step_slot, scope, node.line)
                self.code.bytes(b"\x66\x0f\xef\xc9\x66\x0f\x2e\xc1")
                self.code.conditional_jump(0x84, end)  # a zero step performs no iterations
                self.code.conditional_jump(0x87, positive)  # step > 0
                self.load_local(node.name, scope, node.line)
                self.code.bytes(self._memory_operand(1, 5, -(self._scratch_base + int(end_slot.rsplit("_", 1)[1]) * 8)))
                self.code.bytes(b"\x66\x0f\x2e\xc1")
                self.code.conditional_jump(0x82, end)  # current < end for negative step
                self.code.jump(body)
                self.code.label(positive)
                self.load_local(node.name, scope, node.line)
                self.code.bytes(self._memory_operand(1, 5, -(self._scratch_base + int(end_slot.rsplit("_", 1)[1]) * 8)))
                self.code.bytes(b"\x66\x0f\x2e\xc1")
                self.code.conditional_jump(0x87, end)  # current > end for positive step
                self.code.label(body)
                self.emit_nodes(node.body, scope)
                self.load_local(node.name, scope, node.line)
                self.store_local(start_slot)
                self.load_local(step_slot, scope, node.line)
                self.emit_binary("+", start_slot, node.line)
                self.store_local(node.name)
                self.code.jump(check_step)
                self.code.label(end)
                self.pop_temp()
                self.pop_temp()
                self.pop_temp()
            elif node.kind == "call":
                self.emit_call(node.name, split_args(node.value), scope, node.line)
            else:
                raise CompileError(
                    f"{self.path}:{node.line}: statement {node.kind!r} is not supported by the native x64 backend yet"
                )

    def _emit_function(self, name: str, fn: Node) -> None:
        previous = self.path
        self.path = fn.source or previous
        try:
            self._emit_function_body(name, fn)
        finally:
            self.path = previous

    def _emit_function_body(self, name: str, fn: Node) -> None:
        if fn.local_arrays:
            raise CompileError(f"{self.path}:{fn.line}: native local arrays are not implemented yet")
        self._scope = fn
        self._frame_slots = {}
        for local in sorted(fn.locals | set(fn.params)):
            self._alloc_slot(local)
        self._scratch_base = len(self._frame_slots) * 8
        self._frame_size = ((self._scratch_base + 128 + 15) // 16) * 16
        if self._frame_size > self.MAX_FRAME_BYTES:
            raise CompileError(f"{self.path}:{fn.line}: native function frame exceeds 4096 bytes; split the function into smaller functions")
        self._scratch_depth = 0
        self.code.label(f"function:{name}")
        self.code.bytes(b"\x55\x48\x89\xe5")  # push rbp; mov rbp,rsp
        self.code.bytes(b"\x48\x81\xec" + struct.pack("<I", self._frame_size))
        for index, param in enumerate(fn.params):
            if index < 4:
                offset = -self._frame_slots[param]
                self.code.bytes(self._store_xmm_operand(index, offset))
            elif index < 16:
                self.code.bytes(self._memory_operand(0, 5, 48 + (index - 4) * 8))
                self.code.bytes(self._store_xmm_operand(0, -self._frame_slots[param]))
            else:
                raise CompileError(f"{self.path}:{fn.line}: native backend supports at most sixteen parameters")
        self.emit_nodes(fn.body, fn)
        self.code.bytes(b"\x0f\x57\xc0\xc9\xc3")  # zero return; leave; ret

    def _emit_print_helper(self) -> None:
        """Write a signed number with up to six fractional digits via Kernel32."""
        self.code.label("function:anvil_print_number")
        self.code.bytes(b"\x48\x83\xec\x58")  # shadow space and aligned locals
        self.code.bytes(b"\x66\x48\x0f\x7e\xc0")  # movq rax,xmm0
        self.code.bytes(b"\x48\xc1\xe8\x3f\x41\x89\xc3")  # sign bit -> r11d
        self.code.bytes(b"\x66\x0f\x28\xc8")  # movapd xmm1,xmm0
        nonnegative = self.label("print_nonnegative")
        range_error = self.label("print_range_error")
        self.code.bytes(b"\x45\x85\xdb")
        self.code.conditional_jump(0x84, nonnegative)
        self.code.bytes(b"\x66\x0f\x57\xc0\xf2\x0f\x5c\xc1")  # abs(x) via 0-x
        self.code.label(nonnegative)
        self.code.bytes(b"\x48\xb8\x00\x00\x00\x00\x00\x00\xe0\x43")  # 2^63
        self.code.bytes(b"\x66\x48\x0f\x6e\xd0\x66\x0f\x2e\xc2")  # compare abs(value)
        self.code.conditional_jump(0x8A, range_error)  # jp: NaN
        self.code.conditional_jump(0x87, range_error)  # ja: outside magnitude limit
        format_value = self.label("print_format_value")
        signed_min = self.label("print_signed_min")
        self.code.conditional_jump(0x85, format_value)  # jne: strictly within range
        self.code.bytes(b"\x45\x85\xdb")  # equal 2^63 is valid only for negative input
        self.code.conditional_jump(0x85, signed_min)
        self.code.jump(range_error)
        self.code.label(signed_min)
        self.code.bytes(b"\x66\x0f\x28\xc1")  # restore -2^63 so signed conversion is exact
        self.code.label(format_value)
        self.code.bytes(b"\xf2\x48\x0f\x2c\xc0")  # cvttsd2si rax,xmm0
        self.code.bytes(b"\x48\x89\x44\x24\x28")  # save integer part
        self.code.bytes(b"\xf2\x48\x0f\x2a\xc8")  # cvtsi2sd xmm1,rax
        self.code.bytes(b"\x66\x0f\x28\xd0\xf2\x0f\x5c\xd1")  # fraction in xmm2
        self.code.bytes(b"\x48\xb8\x40\x42\x0f\x00\x00\x00\x00\x00")  # 1,000,000
        self.code.bytes(b"\xf2\x48\x0f\x2a\xc8\xf2\x0f\x59\xd1")  # scale fraction
        self.code.bytes(b"\x48\xb8\x00\x00\x00\x00\x00\x00\xe0\x3f")  # 0.5
        self.code.bytes(b"\x66\x48\x0f\x6e\xc8\xf2\x0f\x58\xd1")  # round to nearest
        self.code.bytes(b"\xf2\x48\x0f\x2c\xc2")  # cvttsd2si rax,xmm2
        fraction_carry = self.label("print_fraction_carry")
        fraction_ready = self.label("print_fraction_ready")
        self.code.bytes(b"\x48\x3d\x40\x42\x0f\x00")  # cmp rax,1,000,000
        self.code.conditional_jump(0x84, fraction_carry)
        self.code.jump(fraction_ready)
        self.code.label(fraction_carry)
        self.code.bytes(b"\x48\xff\x44\x24\x28\x31\xc0")  # carry into integer; fraction = 0
        self.code.label(fraction_ready)
        self.code.bytes(b"\x44\x89\x5c\x24\x20")  # preserve negative flag
        self.code.bytes(b"\x45\x31\xdb")  # r11d = fraction-started flag
        self.code.bytes(b"\x4c\x8d\x54\x24\x50")  # lea r10,[rsp+50h]
        self.code.bytes(b"\xc6\x44\x24\x50\x0a")  # newline
        self.code.bytes(b"\x49\xb8\x0a\x00\x00\x00\x00\x00\x00\x00")  # divisor 10
        self.code.bytes(b"\x41\xb9\x06\x00\x00\x00")  # six decimal digits
        fraction_loop = self.label("print_fraction_digit")
        fraction_write = self.label("print_fraction_write")
        fraction_done = self.label("print_fraction_done")
        self.code.label(fraction_loop)
        self.code.bytes(b"\x31\xd2\x49\xf7\xf0")  # div r8; remainder in edx
        self.code.bytes(b"\x45\x85\xdb")
        self.code.conditional_jump(0x85, fraction_write)
        self.code.bytes(b"\x85\xd2")
        self.code.conditional_jump(0x84, fraction_done)
        self.code.bytes(b"\x41\xbb\x01\x00\x00\x00")  # first nonzero digit
        self.code.label(fraction_write)
        self.code.bytes(b"\x80\xc2\x30\x49\xff\xca\x41\x88\x12")  # store digit backwards
        self.code.label(fraction_done)
        self.code.bytes(b"\x41\xff\xc9")  # dec r9d
        self.code.conditional_jump(0x85, fraction_loop)
        no_decimal = self.label("print_no_decimal")
        self.code.bytes(b"\x45\x85\xdb")
        self.code.conditional_jump(0x84, no_decimal)
        self.code.bytes(b"\x49\xff\xca\x41\xc6\x02\x2e")  # decimal point
        self.code.label(no_decimal)
        self.code.bytes(b"\x48\x8b\x44\x24\x28")  # restore integer part
        self.code.bytes(b"\x48\x85\xc0")  # test rax,rax
        nonzero = self.label("print_nonzero")
        positive = self.label("print_positive")
        digits = self.label("print_digits")
        have_digits = self.label("print_have_digits")
        have_sign = self.label("print_have_sign")
        self.code.conditional_jump(0x85, nonzero)
        self.code.bytes(b"\x49\xff\xca\x41\xc6\x02\x30")  # zero digit
        self.code.jump(have_digits)
        self.code.label(nonzero)
        self.code.bytes(b"\x48\x85\xc0")
        self.code.conditional_jump(0x89, positive)  # jns
        self.code.bytes(b"\x49\xff\xc3\x48\xf7\xd8")  # negative flag; abs(value)
        self.code.label(positive)
        self.code.label(digits)
        self.code.bytes(b"\x31\xd2\x49\xb8\x0a\x00\x00\x00\x00\x00\x00\x00")
        self.code.bytes(b"\x49\xf7\xf0")  # div r8
        self.code.bytes(b"\x80\xc2\x30\x49\xff\xca\x41\x88\x12")  # store digit backwards
        self.code.bytes(b"\x48\x85\xc0")
        self.code.conditional_jump(0x85, digits)
        self.code.label(have_digits)
        self.code.bytes(b"\x44\x8b\x5c\x24\x20\x45\x85\xdb")  # restore/test sign
        self.code.conditional_jump(0x84, have_sign)
        self.code.bytes(b"\x49\xff\xca\x41\xc6\x02\x2d")  # minus sign
        self.code.label(have_sign)
        self.code.bytes(b"\x4c\x89\x54\x24\x20")  # start pointer in local
        self.code.bytes(b"\x48\x8d\x54\x24\x51\x4c\x29\xd2\x89\x54\x24\x28")  # length
        self.code.bytes(b"\xb9\xf5\xff\xff\xff")  # STD_OUTPUT_HANDLE
        self.code.rip_call_import("GetStdHandle")
        self.code.bytes(b"\x48\x89\xc1\x48\x8b\x54\x24\x20")
        self.code.bytes(b"\x8b\x44\x24\x28\x49\x89\xc0\x4c\x8d\x4c\x24\x30")
        self.code.bytes(b"\x48\xc7\x44\x24\x20\x00\x00\x00\x00")
        self.code.rip_call_import("WriteFile")
        self.code.bytes(b"\x48\x83\xc4\x58\xc3")
        self.code.label(range_error)
        message = b"Anvil output out of range\n"
        for offset in range(0, len(message), 8):
            chunk = message[offset:offset + 8].ljust(8, b"\0")
            self.code.bytes(b"\x48\xb8" + chunk)  # mov rax, immediate text
            self.code.bytes(b"\x48\x89\x44\x24" + bytes((0x30 + offset,)))
        self.code.bytes(b"\xb9\xf5\xff\xff\xff")  # STD_OUTPUT_HANDLE
        self.code.rip_call_import("GetStdHandle")
        self.code.bytes(b"\x48\x89\xc1\x48\x8d\x54\x24\x30")
        self.code.bytes(b"\x41\xb8" + struct.pack("<I", len(message)))
        self.code.bytes(b"\x4c\x8d\x4c\x24\x28")
        self.code.bytes(b"\x48\xc7\x44\x24\x20\x00\x00\x00\x00")
        self.code.rip_call_import("WriteFile")
        self.code.bytes(b"\xb9\x02\x00\x00\x00")  # controlled runtime error
        self.code.rip_call_import("ExitProcess")
        self.code.bytes(b"\xcc")

    def generate(self) -> bytes:
        if any(node.kind == "scene" for node in self.top):
            return self._generate_window()
        calls = [node for node in self.top if node.kind == "call"]
        if any(node.kind not in ("call", "seed") for node in self.top):
            unsupported = next(node for node in self.top if node.kind not in ("call", "seed"))
            raise CompileError(
                f"{unsupported.source or self.path}:{unsupported.line}: top-level configuration is not implemented by the native x64 backend yet"
            )
        from compiler.modules import reachable_functions
        for name, fn in reachable_functions(self.functions, self.top, graphical=False):
            self._emit_function(name, fn)
        setup = [node for node in self.top if node.kind == "seed"]
        if setup:
            self._emit_function("native:console_setup", Node("function", 1, body=setup))
        if calls:
            if len(calls) != 1 or calls[0].name not in self.functions or calls[0].name != "main":
                raise CompileError(f"{calls[0].source or self.path}:{calls[0].line}: direct native entry currently accepts only call fn(main)")
            arguments = (", " + calls[0].value) if calls[0].value.strip() else ""
            expression = f"call fn(main{arguments})"
            self._emit_function("native:entry_main", Node(
                "function", calls[0].line, name="native:entry_main", source=calls[0].source,
                body=[Node("output", calls[0].line, value=expression, source=calls[0].source)],
            ))
        self._math.emit_pending()
        self._emit_print_helper()
        self.code.label("entry")
        self.code.bytes(b"\x48\x83\xec\x28")
        if setup:
            self.code.call("function:native:console_setup")
        if calls:
            self.code.call("function:native:entry_main")
        elif "main" in self.functions:
            if self.functions["main"].params:
                raise CompileError(f"{self.functions['main'].source or self.path}:{self.functions['main'].line}: main cannot have parameters")
            self.code.call("function:main")
        else:
            raise CompileError(f"{self.path}: native executable needs fn(main)")
        self.code.call("function:anvil_print_number")
        self.code.bytes(b"\x31\xc9")
        self.code.rip_call_import("ExitProcess")
        self.code.bytes(b"\xcc")
        return self._build(list(self.IMPORTS))

    def _generate_window(self) -> bytes:
        from compiler.native_window import NativeWindow

        scenes = [node for node in self.top if node.kind == "scene"]
        if len(scenes) != 1 or scenes[0].value != "2d":
            raise CompileError(f"{scenes[0].source or self.path}:{scenes[0].line}: native graphics currently requires one scene 2d declaration")
        draw = self.functions.get("draw")
        if draw is None or draw.params:
            raise CompileError(f"{draw.source or self.path}:{draw.line}: native scene 2d requires fn(draw) with no parameters" if draw else f"{self.path}: native scene 2d requires fn(draw) with no parameters")
        if "update" in self.functions and self.functions["update"].params:
            raise CompileError(f"{self.functions['update'].source or self.path}:{self.functions['update'].line}: native fn(update) cannot have parameters")
        clear = [11, 16, 27, 255]
        setup = []
        for node in self.top:
            if node.kind == "scene":
                continue
            if node.kind == "clear":
                parts = split_args(node.value[1:-1])
                if (len(parts) != 4 or any(not re.fullmatch(r"[0-9]{1,3}", part) for part in parts)
                        or any(int(part) > 255 for part in parts) or parts[3] != "255"):
                    raise CompileError(f"{node.source or self.path}:{node.line}: native clear requires four literal channels in 0..255 and alpha 255")
                clear = [int(part) for part in parts]
            elif node.kind in ("set", "add", "sub", "call", "seed"):
                setup.append(node)
            else:
                raise CompileError(f"{node.source or self.path}:{node.line}: native scene setup does not support {node.kind!r}")
        self._window = NativeWindow(self, clear[0] | (clear[1] << 8) | (clear[2] << 16))
        from compiler.modules import reachable_functions
        for name, function in reachable_functions(self.functions, self.top, graphical=True):
            self._emit_function(name, function)
        self.code.label("native:setup")
        self._emit_function("native:setup", Node("function", 1, name="native:setup", body=setup))
        self._math.emit_pending()
        self._window.emit()
        return self._build(list(self.IMPORTS) + self._window.imports)

    def _build(self, imports: list[tuple[str, str]]) -> bytes:
        pe = Pe32Plus(bytes(self.code.code), imports)
        targets = pe.fixup_targets(len(self.code.code))
        text = self.code.finish(targets)
        return Pe32Plus(text, imports).build(
            entry_offset=self.code.labels["entry"], data=bytes(self._data)
        )
