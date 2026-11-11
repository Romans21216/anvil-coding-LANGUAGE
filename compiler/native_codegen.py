"""Direct x64 code generation for the first native Anvil compiler milestone."""

from __future__ import annotations

import math
import pathlib
import re
import struct
from dataclasses import dataclass

from compiler.common import CompileError, KEY_CODES, Node, decode_string
from compiler.expressions import BUILTINS, LISTS, NAME_SUGGESTIONS, STRING_VARIABLES, set_string_variables
from compiler.expressions import ExpressionParser, MAX_EXPRESSION_DEPTH, split_amp, split_args
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
        "&": 5,
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
            if name in STRING_VARIABLES:
                offset = self.owner.reserve_string_buffer(f"var:{name}")
                self.owner.code.rip_lea_data(0, offset)
                left = _Value("text", name)
            else:
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
        elif kind == "word" and value == "not":
            operand = self.emit(3)
            self._require_number(operand)
            self.owner.code.bytes(b"\x66\x0f\xef\xc9")        # xorpd xmm1, xmm1
            self.owner.code.bytes(b"\x66\x0f\x2e\xc8")        # ucomisd xmm1, xmm0
            self.owner.code.bytes(b"\x0f\x94\xc0")            # sete al (equal; NaN sets ZF)
            self.owner.code.bytes(b"\x0f\x9b\xc1")            # setnp cl (ordered only)
            self.owner.code.bytes(b"\x20\xc8")                # and al, cl -> NaN counts as true
            self.owner.code.bytes(b"\x0f\xb6\xc0")            # movzx eax, al
            self.owner.code.bytes(b"\xf2\x48\x0f\x2a\xc0")    # cvtsi2sd xmm0, rax
            left = _Value("number", "not")
        elif kind == "word" and value in ("true", "false"):
            self.owner.emit_float(1.0 if value == "true" else 0.0)
            left = _Value("number", value)
        elif kind == "word" and value in KEY_CODES:
            self.owner.emit_float(float(KEY_CODES[value]))
            left = _Value("number", value)
        elif kind == "call":
            self._emit_user_call(value)
            contents = value[value.index("fn(") + 3 : -1]
            name = split_args(contents)[0] if split_args(contents) else ""
            target = self.owner.functions.get(name)
            result_kind = (
                "text" if getattr(target, "returns_text", False) else "number"
            )
            left = _Value(result_kind, "call")
        elif kind == "word" and value in self.owner.BUILTIN_NAMES:
            left = _Value(self._emit_builtin(value), value)
        elif kind == "count":
            contents = value[value.index("count(") + 6:-1].strip()
            if contents not in LISTS:
                raise CompileError(
                    f"{self.owner.path}:{self.line}: unknown list {contents!r}; "
                    f"declare it with list {contents}"
                )
            self.owner.load_variable(f"{contents}__count", self.scope, self.line)
            left = _Value("number", "count")
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
            payload = decode_string(value).encode("utf-8")
            if payload not in self.owner._text_cache:
                # Join/append helpers read until a NUL, so every literal keeps one.
                self.owner._text_cache[payload] = self.owner.reserve_data(
                    payload + b"\x00"
                )
            self.owner.code.rip_lea_data(0, self.owner._text_cache[payload])
            left = _Value("text", "literal")
        else:
            if value in BUILTINS:
                raise CompileError(
                    f"{self.owner.path}:{self.line}: {value}() is not available in "
                    "the native x64 backend yet; build with --backend c"
                )
            suggestion = NAME_SUGGESTIONS.get(value.lower())
            if suggestion is not None:
                raise CompileError(
                    f"{self.owner.path}:{self.line}: unknown name {value!r}; "
                    f"did you mean {suggestion}?"
                )
            hint = ""
            if value in self.owner.variables:
                hint = f"; it is a variable, so write var({value})"
            raise CompileError(
                f"{self.owner.path}:{self.line}: unknown name {value!r}{hint}"
            )

        while self._peek():
            operator = self.tokens[self.index][1]
            precedence = self.PRECEDENCE.get(operator, -1)
            if precedence < minimum:
                break
            self.index += 1
            if operator == "&":
                self.owner._needs_string_helpers = True
                if left.kind == "number":
                    _render_number(self.owner)
                    left = _Value("text", "number")
                left_slot = self.owner.push_temp()
                left_disp = -(
                    self.owner._scratch_base + int(left_slot.rsplit("_", 1)[1]) * 8
                )
                self.owner._store_rax_rbp(left_disp)
                right = self.emit(precedence + 1)
                if right.kind == "number":
                    _render_number(self.owner)
                right_slot = self.owner.push_temp()
                right_disp = -(
                    self.owner._scratch_base + int(right_slot.rsplit("_", 1)[1]) * 8
                )
                self.owner._store_rax_rbp(right_disp)
                destination = self.owner.reserve_string_buffer(
                    f"scratch:{self.owner._join_counter}"
                )
                self.owner._join_counter += 1
                # copy left into dst, then append right; every call uses the
                # same argument shape as the proven set-variable copy.
                self.owner.code.rip_lea_data(1, destination)          # rcx = dst
                self.owner.code.bytes(b"\x48\x8b\x95")              # mov rdx,[rbp+d32]
                self.owner.code.bytes(struct.pack("<i", left_disp))
                self.owner.code.call("function:anvil_str_copy")
                self.owner.code.rip_lea_data(1, destination)          # rcx = dst
                self.owner.code.bytes(b"\x48\x8b\x95")              # mov rdx,[rbp+d32]
                self.owner.code.bytes(struct.pack("<i", right_disp))
                self.owner.code.call("function:anvil_str_append")
                self.owner.code.rip_lea_data(0, destination)          # rax = dst
                self.owner.pop_temp()
                self.owner.pop_temp()
                left = _Value("text", "join")
                continue
            if (
                operator in ("=", "==", "!=", "<", "<=", ">", ">=")
                and left.kind == "text"
            ):
                self.owner._needs_string_helpers = True
                self.owner._needs_equal_helper = True
                if operator in ("<", "<=", ">", ">="):
                    self.owner._needs_compare_helper = True
                left_slot = self.owner.push_temp()
                left_disp = -(
                    self.owner._scratch_base + int(left_slot.rsplit("_", 1)[1]) * 8
                )
                self.owner._store_rax_rbp(left_disp)
                right = self.emit(precedence + 1)
                if right.kind != "text":
                    raise CompileError(
                        f"{self.owner.path}:{self.line}: cannot compare text with a number"
                    )
                right_slot = self.owner.push_temp()
                right_disp = -(
                    self.owner._scratch_base + int(right_slot.rsplit("_", 1)[1]) * 8
                )
                self.owner._store_rax_rbp(right_disp)
                self.owner.code.mov_reg(1, 1)                     # rcx = a
                self.owner.code.bytes(b"\x48\x8b\x8d")           # mov rcx,[rbp+d32]
                self.owner.code.bytes(struct.pack("<i", left_disp))
                self.owner.code.bytes(b"\x48\x8b\x95")           # mov rdx,[rbp+d32]
                self.owner.code.bytes(struct.pack("<i", right_disp))
                if operator in ("<", "<=", ">", ">="):
                    self.owner.code.call("function:anvil_str_compare")
                    self.owner.code.bytes(b"\x48\x85\xc0")      # test rax, rax
                    self.owner.code.bytes(
                        {
                            "<": b"\x0f\x9c\xc0",   # setl al
                            "<=": b"\x0f\x9e\xc0",  # setle al
                            ">": b"\x0f\x9f\xc0",   # setg al
                            ">=": b"\x0f\x9d\xc0",  # setge al
                        }[operator]
                    )
                    self.owner.code.bytes(b"\x0f\xb6\xc0")      # movzx eax, al
                else:
                    self.owner.code.call("function:anvil_str_equal")
                    if operator == "!=":
                        self.owner.code.bytes(b"\x48\x83\xf0\x01")  # xor rax, 1
                self.owner.code.bytes(b"\xf2\x48\x0f\x2a\xc0") # cvtsi2sd xmm0, rax
                self.owner.pop_temp()
                self.owner.pop_temp()
                left = _Value("number", "textcmp")
                continue
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

    def compile(self, expected: str = "number") -> None:
        result = self.emit()
        if expected == "number":
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
        if name in ("upper", "lower"):
            argument = self.emit()
            if argument.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: {name}() expects a text value"
                )
            self._expect(")")
            self.owner._needs_string_helpers = True
            self.owner._needs_case_helper = True
            destination = self.owner.reserve_string_buffer(
                f"case:{name}:{self.owner._join_counter}"
            )
            self.owner._join_counter += 1
            self.owner.code.rip_lea_data(1, destination)   # rcx = destination
            self.owner.code.mov_reg(2, 0)                  # rdx = source
            self.owner.code.mov_imm(8, 0 if name == "upper" else 1)  # r8d = mode
            self.owner.code.call("function:anvil_text_case")
            self.owner.code.rip_lea_data(0, destination)   # rax = the text result
            return "text"
        if name == "ord":
            argument = self.emit()
            if argument.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: ord() expects a text value"
                )
            self._expect(")")
            self.owner.code.bytes(b"\x0f\xb6\x00")            # movzx eax, byte [rax]
            self.owner.code.bytes(b"\xf2\x48\x0f\x2a\xc0")  # cvtsi2sd xmm0, rax
            return "number"
        if name == "chr":
            self._require_number(self.emit())
            self._expect(")")
            self.owner._needs_text_helper = True
            self.owner._needs_chr_error = True
            error = "chr_range_error"
            self.owner._math.constant(2, 0.0)
            self.owner.code.bytes(b"\x66\x0f\x2e\xc2")       # ucomisd xmm0, xmm2
            self.owner.code.conditional_jump(0x82, error)        # jb: n < 0
            self.owner._math.constant(2, 255.0)
            self.owner.code.bytes(b"\x66\x0f\x2e\xc2")       # ucomisd xmm0, xmm2
            self.owner.code.conditional_jump(0x87, error)        # ja: n > 255
            self.owner.code.bytes(b"\xf2\x48\x0f\x2c\xc0")  # cvttsd2si rax, xmm0
            destination = self.owner.reserve_string_buffer(
                f"chr:{self.owner._join_counter}"
            )
            self.owner._join_counter += 1
            self.owner.code.rip_lea_data(2, destination)         # rdx = destination
            self.owner.code.bytes(b"\x88\x02")                  # mov [rdx], al
            self.owner.code.bytes(b"\xc6\x42\x01\x00")        # mov byte [rdx+1], 0
            self.owner.code.rip_lea_data(0, destination)         # rax = the text result
            return "text"
        if name in ("starts_with", "ends_with"):
            first = self.emit()
            if first.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: {name}() expects text values"
                )
            left_slot = self.owner.push_temp()
            left_disp = -(
                self.owner._scratch_base + int(left_slot.rsplit("_", 1)[1]) * 8
            )
            self.owner._store_rax_rbp(left_disp)
            self._expect(",")
            second = self.emit()
            if second.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: {name}() expects text values"
                )
            self._expect(")")
            self.owner._needs_string_helpers = True
            self.owner._needs_edge_helpers = True
            self.owner.code.mov_reg(2, 0)                     # rdx = the second text
            self.owner.code.bytes(b"\x48\x8b\x8d")          # rcx = the saved first text
            self.owner.code.bytes(struct.pack("<i", left_disp))
            self.owner.code.call(
                "function:anvil_str_starts"
                if name == "starts_with"
                else "function:anvil_str_ends"
            )
            self.owner.pop_temp()
            self.owner.code.bytes(b"\xf2\x48\x0f\x2a\xc0")  # cvtsi2sd xmm0, rax
            return "number"
        if name == "contains":
            first = self.emit()
            if first.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: contains() expects text values"
                )
            left_slot = self.owner.push_temp()
            left_disp = -(
                self.owner._scratch_base + int(left_slot.rsplit("_", 1)[1]) * 8
            )
            self.owner._store_rax_rbp(left_disp)
            self._expect(",")
            second = self.emit()
            if second.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: contains() expects text values"
                )
            self._expect(")")
            self.owner._needs_string_helpers = True
            self.owner._needs_contains_helper = True
            self.owner.code.mov_reg(2, 0)                     # rdx = the second text
            self.owner.code.bytes(b"\x48\x8b\x8d")          # rcx = the saved first text
            self.owner.code.bytes(struct.pack("<i", left_disp))
            self.owner.code.call("function:anvil_str_contains")
            self.owner.pop_temp()
            self.owner.code.bytes(b"\xf2\x48\x0f\x2a\xc0")  # cvtsi2sd xmm0, rax
            return "number"
        if name in ("left", "right"):
            argument = self.emit()
            if argument.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: {name}() expects a text value"
                )
            left_slot = self.owner.push_temp()
            left_disp = -(
                self.owner._scratch_base + int(left_slot.rsplit("_", 1)[1]) * 8
            )
            self.owner._store_rax_rbp(left_disp)
            self._expect(",")
            self._require_number(self.emit())              # xmm0 = count
            count_slot = self.owner.push_temp()
            self.owner.store_local(count_slot)
            count_disp = -(
                self.owner._scratch_base + int(count_slot.rsplit("_", 1)[1]) * 8
            )
            self._expect(")")
            self.owner._needs_string_helpers = True
            self.owner._needs_mid_helper = True
            destination = self.owner.reserve_string_buffer(
                f"{name}:{self.owner._join_counter}"
            )
            self.owner._join_counter += 1
            if name == "right":
                # length of the source, then start = max(0, length - count)
                self.owner.code.bytes(b"\x48\x8b\x8d")          # rcx = the saved text
                self.owner.code.bytes(struct.pack("<i", left_disp))
                self.owner.code.call("function:anvil_str_len")    # rax = length
                self.owner.code.bytes(b"\xf2\x48\x0f\x2a\xd0")  # cvtsi2sd xmm2, rax
                self.owner.code.bytes(
                    self.owner._memory_operand(1, 5, count_disp)  # xmm1 = count
                )
                self.owner.code.bytes(b"\xf2\x48\x0f\x2c\xc1")  # rax = (int)count
                self.owner.code.bytes(b"\xf2\x48\x0f\x2a\xc8")  # cvtsi2sd xmm1, rax
                self.owner.code.bytes(b"\xf2\x0f\x5c\xd1")      # subsd xmm2, xmm1
                start_ok = self.owner.label("right_start_ok")
                self.owner.code.bytes(b"\x0f\x57\xdb")           # xorps xmm3, xmm3
                self.owner.code.bytes(b"\x66\x0f\x2e\xd3")      # ucomisd xmm2, xmm3
                self.owner.code.conditional_jump(0x83, start_ok)    # jae: start >= 0
                self.owner.code.bytes(b"\x0f\x57\xd2")           # xorps xmm2, xmm2
                self.owner.code.label(start_ok)
                self.owner.code.bytes(b"\x66\x0f\x28\xc2")      # movapd xmm0, xmm2
                self.owner.code.rip_lea_data(1, destination)        # rcx = destination
                self.owner.code.bytes(b"\x48\x8b\x95")          # rdx = the saved text
                self.owner.code.bytes(struct.pack("<i", left_disp))
            else:
                self.owner.code.bytes(b"\x0f\x57\xc0")           # xorps xmm0, xmm0
                self.owner.code.bytes(
                    self.owner._memory_operand(1, 5, count_disp)   # xmm1 = count
                )
                self.owner.code.rip_lea_data(1, destination)        # rcx = destination
                self.owner.code.bytes(b"\x48\x8b\x95")          # rdx = the saved text
                self.owner.code.bytes(struct.pack("<i", left_disp))
            self.owner.code.call("function:anvil_text_mid")
            self.owner.pop_temp()
            self.owner.pop_temp()
            self.owner.code.rip_lea_data(0, destination)      # rax = the text result
            return "text"
        if name == "mid":
            argument = self.emit()
            if argument.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: mid() expects a text value"
                )
            left_slot = self.owner.push_temp()
            left_disp = -(
                self.owner._scratch_base + int(left_slot.rsplit("_", 1)[1]) * 8
            )
            self.owner._store_rax_rbp(left_disp)
            self._expect(",")
            self._require_number(self.emit())              # xmm0 = start
            start_slot = self.owner.push_temp()
            self.owner.store_local(start_slot)
            start_disp = -(
                self.owner._scratch_base + int(start_slot.rsplit("_", 1)[1]) * 8
            )
            self._expect(",")
            self._require_number(self.emit())              # xmm0 = count
            count_slot = self.owner.push_temp()
            self.owner.store_local(count_slot)
            count_disp = -(
                self.owner._scratch_base + int(count_slot.rsplit("_", 1)[1]) * 8
            )
            self._expect(")")
            self.owner._needs_string_helpers = True
            self.owner._needs_mid_helper = True
            destination = self.owner.reserve_string_buffer(
                f"mid:{self.owner._join_counter}"
            )
            self.owner._join_counter += 1
            self.owner.code.rip_lea_data(1, destination)          # rcx = destination
            self.owner.code.bytes(b"\x48\x8b\x95")              # rdx = the saved text
            self.owner.code.bytes(struct.pack("<i", left_disp))
            self.owner.code.bytes(
                self.owner._memory_operand(0, 5, start_disp)      # xmm0 = start
            )
            self.owner.code.bytes(
                self.owner._memory_operand(1, 5, count_disp)      # xmm1 = count
            )
            self.owner.code.call("function:anvil_text_mid")
            self.owner.pop_temp()
            self.owner.pop_temp()
            self.owner.pop_temp()
            self.owner.code.rip_lea_data(0, destination)          # rax = the text result
            return "text"
        if name == "char":
            argument = self.emit()
            if argument.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: char() expects a text value"
                )
            left_slot = self.owner.push_temp()
            left_disp = -(
                self.owner._scratch_base + int(left_slot.rsplit("_", 1)[1]) * 8
            )
            self.owner._store_rax_rbp(left_disp)
            self._expect(",")                          # between the two args
            self._require_number(self.emit())          # xmm0 = the index
            self._expect(")")
            self.owner._needs_char_at_helper = True
            destination = self.owner.reserve_string_buffer(
                f"charat:{self.owner._join_counter}"
            )
            self.owner._join_counter += 1
            self.owner.code.rip_lea_data(1, destination)          # rcx = destination
            self.owner.code.bytes(b"\x48\x8b\x95")              # rdx = the saved text
            self.owner.code.bytes(struct.pack("<i", left_disp))
            self.owner.code.call("function:anvil_text_char")      # xmm0 = the index
            self.owner.pop_temp()
            self.owner.code.rip_lea_data(0, destination)          # rax = the text result
            return "text"
        if name == "number":
            argument = self.emit()
            if argument.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: number() expects a text value"
                )
            self._expect(")")
            self.owner._needs_parse_number = True
            self.owner.code.mov_reg(1, 0)   # rcx = text pointer
            self.owner.code.call("function:anvil_parse_number")   # xmm0 = value
            return "number"
        if name == "trim":
            argument = self.emit()
            if argument.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: trim() expects a text value"
                )
            self._expect(")")
            self.owner._needs_string_helpers = True
            self.owner._needs_trim_helper = True
            destination = self.owner.reserve_string_buffer(
                f"trim:{self.owner._join_counter}"
            )
            self.owner._join_counter += 1
            self.owner.code.rip_lea_data(1, destination)   # rcx = destination
            self.owner.code.mov_reg(2, 0)                  # rdx = source
            self.owner.code.call("function:anvil_text_trim")
            self.owner.code.rip_lea_data(0, destination)   # rax = the text result
            return "text"
        if name == "len":
            argument = self.emit()
            if argument.kind != "text":
                raise CompileError(
                    f"{self.owner.path}:{self.line}: len() expects a text value"
                )
            self._expect(")")
            self.owner._needs_string_helpers = True
            self.owner.code.mov_reg(1, 0)   # rcx = text pointer
            self.owner.code.call("function:anvil_str_len")   # rax = length
            self.owner.code.bytes(b"\xf2\x48\x0f\x2a\xc0")  # cvtsi2sd xmm0, rax
            return "number"
        if name in self.owner._math.ARITY:
            self.owner._math.emit_builtin(self, name)
            return "number"
        if name == "compute":
            self._require_number(self.emit())
            self._expect(")")
            return "number"
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
            return "number"
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
            return "number"
        self._expect(")")
        if self.owner._window is None:
            raise CompileError(f"{self.owner.path}:{self.line}: {name}() requires native scene 2d")
        if name == "delta":
            self.owner.emit_float(1.0 / 60.0)
        else:
            self.owner._window.clock_requested = True
            self.owner.code.rip_load_data(0, self.owner._window.simulation_time)
        return "number"

    def _peek_expected(self, value: str) -> bool:
        return self._peek(value)

    def _expect(self, value: str) -> None:
        if not self._peek_expected(value):
            raise CompileError(f"{self.owner.path}:{self.line}: expected {value!r}")
        self.index += 1

    def _require_number(self, value: _Value) -> None:
        if value.kind != "number":
            raise CompileError(f"{self.owner.path}:{self.line}: expected a number")


_NATIVE_VAR = __import__("re").compile(r"var\(([A-Za-z_][\w-]*)\)")
_TEXT_BUILTIN_CALL = __import__("re").compile(
    r"(upper|lower|chr|trim|char|mid|left|right)\s*\(.*\)", __import__("re").DOTALL
)


def _render_number(owner) -> None:
    """Render xmm0 into a fresh scratch buffer and leave its pointer in rax."""
    slot = owner.reserve_string_buffer(f"scratch:{owner._join_counter}")
    owner._join_counter += 1
    owner.code.rip_lea_data(2, slot)
    owner.code.mov_imm(1, 2)  # buffer mode: no newline
    owner.code.call("function:anvil_print_number")
    owner.code.rip_lea_data(0, slot)


_COMPARISON = __import__("re").compile(r"<=|>=|!=|==|[<>=]")


def _has_comparison(part: str) -> bool:
    """True when `part` compares values; the result is a number, not text."""
    stripped = __import__("re").sub(r'"(?:[^"\\]|\\.)*"', '""', part)
    return _COMPARISON.search(stripped) is not None


def _is_native_string_var(part: str) -> bool:
    match = _NATIVE_VAR.fullmatch(part.strip())
    return match is not None and match.group(1) in STRING_VARIABLES


_NATIVE_CALL = __import__("re").compile(r"call\s+fn\(([^,)]*)")


def _is_native_text_call(part: str, functions) -> bool:
    """True when `part` is a call to a function that returns text."""
    match = _NATIVE_CALL.match(part.strip())
    if match is None:
        return False
    target = functions.get(match.group(1).strip())
    return bool(target is not None and getattr(target, "returns_text", False))


def _walk_native_nodes(top, functions):
    def statements(nodes):
        for node in nodes:
            yield node
            yield from statements(node.body)
            yield from statements(node.otherwise)

    yield from statements(top)
    for function in functions.values():
        yield from statements(function.body)


def _walk_native_kinds(nodes):
    for node in nodes:
        yield node.kind
        for branch in (node.body, node.otherwise):
            if branch:
                yield from _walk_native_kinds(branch)


class NativeCodegen:
    """Emit native x64 instructions and a PE executable without C/Rust output."""

    IMPORTS = [("KERNEL32.dll", "GetStdHandle"),
               ("KERNEL32.dll", "WriteFile"),
               ("KERNEL32.dll", "Sleep"),
               ("KERNEL32.dll", "ReadFile"),
               ("KERNEL32.dll", "ExitProcess")]
    BUILTIN_NAMES = {"len", "round", "upper", "lower", "ord", "chr", "trim", "number", "char", "contains", "mid", "left", "right", "starts_with", "ends_with", "sin", "cos", "compute", "time", "delta", "held", "pressed",
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
        self._text_cache: dict[bytes, int] = {}
        self._needs_text_helper = False
        self._needs_input_helper = False
        self._needs_string_helpers = False
        self._needs_read_line = False
        self._needs_read_line = False
        self._needs_parse_number = False
        self._needs_case_helper = False
        self._needs_trim_helper = False
        self._needs_char_at_helper = False
        self._needs_mid_helper = False
        self._needs_contains_helper = False
        self._needs_edge_helpers = False
        self._needs_compare_helper = False
        self._needs_chr_error = False
        self._needs_equal_helper = False
        self._join_counter = 0
        self._string_offsets: dict[str, int] = {}
        # STRING_VARIABLES is already populated by validate_program during
        # parsing (set-node classification plus ask targets); do not reset it.
        self._expression_depth = 0
        self._label_counter = 0
        self._frame_slots: dict[str, int] = {}
        self._scratch_base = 0
        self._scratch_depth = 0
        self._frame_size = 0
        self._scope: Node | None = None
        self._local_array_slots: dict[str, tuple[int, int]] = {}
        self._loop_stack: list[tuple[str, str]] = []
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
        if not payload:
            # An empty reservation must still own one NUL byte so pointers
            # into .data always read a terminated (empty) string.
            payload = b"\0"
        offset = (len(self._data) + 7) & ~7
        end = offset + len(payload)
        if end > self.MAX_DATA_BYTES:
            raise CompileError(f"{self.path}: native program data exceeds the 16 MiB limit")
        self._data.extend(b"\0" * (offset - len(self._data)))
        self._data.extend(payload)
        return offset

    def reserve_string_buffer(self, key: str) -> int:
        """Dedicated 256-byte text buffer in .data for a variable or scratch slot."""
        if key not in self._string_offsets:
            self._string_offsets[key] = self.reserve_data(bytes(256))
        return self._string_offsets[key]

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
        local = self._local_array_slots.get(name) if scope is not None else None
        if local is not None:
            size = local[1]
        else:
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

    def _lea_rbp(self, register: int, displacement: int) -> None:
        """lea register, [rbp+disp32] for any integer register."""
        if not 0 <= register <= 15:
            raise ValueError("x64 register number must be from 0 to 15")
        rex = 0x48 | (0x04 if register >= 8 else 0)
        modrm = 0x80 | ((register & 7) << 3) | 0x05
        self.code.bytes(bytes((rex, 0x8D, modrm)) + struct.pack("<i", displacement))

    def _lea_array_base(self, register: int, name: str, scope: Node | None) -> None:
        """Load the address of an array's first element into a register."""
        local = self._local_array_slots.get(name) if scope is not None else None
        if local is not None:
            self._lea_rbp(register, local[0])
        else:
            self.code.rip_lea_data(register, self._array_offsets[name])

    def emit_array_read(
        self, name: str, raw_index: str, line: int, scope: Node | None
    ) -> None:
        slot = self._emit_array_index(name, raw_index, line, scope)
        displacement = -(self._scratch_base + int(slot.rsplit("_", 1)[1]) * 8)
        self._load_rax_rbp(displacement)
        self._lea_array_base(2, name, scope)  # lea rdx,[array base]
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
        self._lea_array_base(2, name, scope)
        self.code.bytes(b"\xf2\x0f\x11\x04\xc2")  # movsd [rdx+rax*8],xmm0
        self.pop_temp()

    def emit_runtime_error(self, message_text: str) -> None:
        """Write pooled UTF-8 diagnostic data and terminate with status 2."""
        message = message_text.encode("utf-8")
        if message not in self._error_messages:
            self._error_messages[message] = self.reserve_data(message)
        # Own frame: the WriteFile arguments live at [rsp+0x20]/[rsp+0x28], which
        # inside a frameless helper is the saved return address — writing there
        # corrupted the stack and crashed after the message printed. Align first:
        # callers reach this path with rsp at 0 or 8 mod 16, and a fixed `sub`
        # cannot fix both. We never return, so clobbering rsp is safe.
        self.code.bytes(b"\x48\x83\xe4\xf0")  # and rsp, -16
        self.code.bytes(b"\x48\x83\xec\x30")  # sub rsp, 0x30
        self.code.mov_imm(1, -12)  # STD_ERROR_HANDLE: diagnostics stay off stdout
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
        if operator == "%":
            # fmod(x, y) = x - trunc(x / y) * y, with a non-finite quotient rejected
            self.code.bytes(bytes.fromhex("660f28d0"))        # movapd xmm2, xmm0
            self.code.bytes(bytes.fromhex("f20f5ec1"))        # divsd xmm0, xmm1
            if line:
                self.emit_finite_check(line)
            self.code.bytes(bytes.fromhex("f2480f2cc0"))      # cvttsd2si rax, xmm0
            self.code.bytes(bytes.fromhex("f2480f2ac0"))      # cvtsi2sd xmm0, rax
            self.code.bytes(bytes.fromhex("f20f59c1"))        # mulsd xmm0, xmm1
            self.code.bytes(bytes.fromhex("f20f5cd0"))        # subsd xmm2, xmm0
            self.code.bytes(bytes.fromhex("660f28c2"))        # movapd xmm0, xmm2
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
        for argument in raw_args:
            if self._argument_is_text(argument):
                raise CompileError(
                    f"{self.path}:{line}: text arguments to functions are not "
                    "available yet; functions take numbers on both backends"
                )
        base_depth = self._scratch_depth
        slots = []
        for argument in raw_args:
            self.emit_expression(argument, line, scope)
            slot = self.push_temp()
            self.store_local(slot)
            slots.append(slot)
        self.emit_saved_call(name, slots)
        self._scratch_depth = base_depth

    def _argument_is_text(self, argument: str) -> bool:
        """True when a call argument is text, which the native ABI cannot pass."""
        value = argument.strip()
        if not value:
            return False
        if value.startswith('"') or len(split_amp(value)) > 1:
            return True
        if re.match(r"(upper|lower|chr|trim|char|mid|left|right)\s*\(", value):
            return True
        match = re.fullmatch(r"var\(([A-Za-z_][\w-]*)\)", value)
        if match is not None:
            return match.group(1) in STRING_VARIABLES
        return _is_native_text_call(value, self.functions)

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

    def emit_expression(
        self, raw: str, line: int, scope: Node | None, expected: str = "number"
    ) -> None:
        _Expression(self, line, raw, scope).compile(expected)

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
                if node.string:
                    self._needs_string_helpers = True
                    self.emit_expression(node.value, node.line, scope, expected="text")
                    destination = self.reserve_string_buffer(f"var:{node.name}")
                    self.code.rip_lea_data(1, destination)  # rcx = dest
                    self.code.bytes(b"\x48\x89\xc2")       # mov rdx, rax = src
                    self.code.call("function:anvil_str_copy")
                else:
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
                if scope is not None and getattr(scope, "returns_text", False):
                    self.emit_expression(node.value, node.line, scope, expected="text")
                else:
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
                self._loop_stack.append((start, end))
                try:
                    self.emit_nodes(node.body, scope)
                finally:
                    self._loop_stack.pop()
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
                continue_at = self.label("for_continue")
                self._loop_stack.append((continue_at, end))
                try:
                    self.emit_nodes(node.body, scope)
                finally:
                    self._loop_stack.pop()
                self.code.label(continue_at)
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
            elif node.kind in ("break", "continue"):
                if not self._loop_stack:
                    raise CompileError(
                        f"{self.path}:{node.line}: {node.kind} must be inside a loop"
                    )
                target = self._loop_stack[-1][1 if node.kind == "break" else 0]
                self.code.jump(target)
            elif node.kind == "stop":
                self.code.mov_imm(1, 0)                    # exit code 0
                self.code.rip_call_import("ExitProcess")
                return
            elif node.kind in ("say", "write"):
                parts = split_args(node.value)
                if not parts:
                    raise CompileError(f"{self.path}:{node.line}: say expects text or a value")
                for part in parts:
                    part = part.strip()
                    if not part:
                        raise CompileError(f"{self.path}:{node.line}: say has an empty part")
                    if _has_comparison(part):
                        self.emit_expression(part, node.line, scope)
                        self.code.mov_imm(1, 0)  # no newline mid-line
                        self.code.call("function:anvil_print_number")
                    elif (
                        len(split_amp(part)) > 1
                        or _is_native_string_var(part)
                        or _is_native_text_call(part, self.functions)
                        or _TEXT_BUILTIN_CALL.fullmatch(part)
                    ):
                        self._needs_string_helpers = True
                        self.emit_expression(part, node.line, scope, expected="text")
                        temp = self.push_temp()
                        displacement = -(
                            self._scratch_base + int(temp.rsplit("_", 1)[1]) * 8
                        )
                        self._store_rax_rbp(displacement)
                        self.code.mov_reg(1, 0)   # rcx = text pointer
                        self.code.call("function:anvil_str_len")
                        self.code.mov_reg(2, 0)   # rdx = length
                        self._load_rax_rbp(displacement)
                        self.code.mov_reg(1, 0)   # rcx = text pointer
                        self.code.call("function:anvil_print_text")
                        self.pop_temp()
                    elif part.startswith('"'):
                        payload = decode_string(part).encode("utf-8")
                        if payload not in self._text_cache:
                            self._text_cache[payload] = self.reserve_data(payload)
                        self._needs_text_helper = True
                        self.code.rip_lea_data(1, self._text_cache[payload])
                        self.code.mov_imm(2, len(payload))
                        self.code.call("function:anvil_print_text")
                    else:
                        self.emit_expression(part, node.line, scope)
                        self.code.mov_imm(1, 0)  # no newline mid-line
                        self.code.call("function:anvil_print_number")
                if node.kind == "say":
                    if b"\n" not in self._text_cache:
                        self._text_cache[b"\n"] = self.reserve_data(b"\n")
                    self._needs_text_helper = True
                    self.code.rip_lea_data(1, self._text_cache[b"\n"])
                    self.code.mov_imm(2, 1)
                    self.code.call("function:anvil_print_text")
            elif node.kind == "wait":
                self.emit_expression(node.value, node.line, scope)
                self.emit_finite_check(node.line)
                self._math.constant(1, 1000.0)
                self.code.bytes(b"\xf2\x0f\x59\xc1")       # mulsd xmm0, xmm1
                self.code.bytes(b"\xf2\x48\x0f\x2c\xc0")   # cvttsd2si rax, xmm0
                nonnegative = self.label("wait_nonnegative")
                self.code.bytes(b"\x48\x85\xc0")            # test rax, rax
                self.code.conditional_jump(0x89, nonnegative)  # jns
                self.code.bytes(b"\x31\xc0")                 # clamp negatives to 0
                self.code.label(nonnegative)
                self.code.bytes(b"\x48\x89\xc1")             # mov rcx, rax
                self.code.rip_call_import("Sleep")
            elif node.kind == "press_enter":
                prompt = b"Press Enter to continue...\n"
                if prompt not in self._text_cache:
                    self._text_cache[prompt] = self.reserve_data(prompt)
                self._needs_text_helper = True
                self.code.rip_lea_data(1, self._text_cache[prompt])
                self.code.mov_imm(2, len(prompt))
                self.code.call("function:anvil_print_text")
                # The helper itself is emitted out-of-line with the other
                # runtime helpers; an inline body would execute on fall-through.
                self._needs_input_helper = True
                self.code.call("function:anvil_press_enter")
            elif node.kind == "ask":
                self._needs_text_helper = True
                prompt = node.value.strip()
                if not node.string:
                    self._needs_read_line = True
                    self._needs_parse_number = True
                    if prompt:
                        self._needs_string_helpers = True
                        self.emit_expression(prompt, node.line, scope, expected="text")
                        temp = self.push_temp()
                        displacement = -(
                            self._scratch_base + int(temp.rsplit("_", 1)[1]) * 8
                        )
                        self._store_rax_rbp(displacement)
                        self.code.mov_reg(1, 0)   # rcx = prompt pointer
                        self.code.call("function:anvil_str_len")
                        self.code.mov_reg(2, 0)   # rdx = prompt length
                        self._load_rax_rbp(displacement)
                        self.code.mov_reg(1, 0)   # rcx = prompt pointer
                        self.code.call("function:anvil_print_text")
                        self.pop_temp()
                    buffer = self.reserve_string_buffer(f"asknum:{node.params[0]}")
                    self.code.rip_lea_data(1, buffer)    # rcx = line buffer
                    self.code.call("function:anvil_read_line")
                    self.code.rip_lea_data(1, buffer)    # rcx = line buffer
                    self.code.call("function:anvil_parse_number")  # xmm0 = value
                    self.store_variable(node.params[0], scope, node.line)
                else:
                    self._needs_string_helpers = True
                    if prompt:
                        self.emit_expression(prompt, node.line, scope, expected="text")
                        temp = self.push_temp()
                        displacement = -(
                            self._scratch_base + int(temp.rsplit("_", 1)[1]) * 8
                        )
                        self._store_rax_rbp(displacement)
                        self.code.mov_reg(1, 0)   # rcx = prompt pointer
                        self.code.call("function:anvil_str_len")
                        self.code.mov_reg(2, 0)   # rdx = prompt length
                        self._load_rax_rbp(displacement)
                        self.code.mov_reg(1, 0)   # rcx = prompt pointer
                        self.code.call("function:anvil_print_text")
                        self.pop_temp()
                    destination = self.reserve_string_buffer(f"var:{node.params[0]}")
                    self._needs_read_line = True
                    self.code.rip_lea_data(1, destination)   # rcx = answer buffer
                    self.code.call("function:anvil_read_line")
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
        self._scope = fn
        self._frame_slots = {}
        for local in sorted(fn.locals | set(fn.params)):
            self._alloc_slot(local)
        self._scratch_base = len(self._frame_slots) * 8
        self._frame_size = ((self._scratch_base + 128 + 15) // 16) * 16
        self._local_array_slots: dict[str, tuple[int, int]] = {}
        if fn.local_arrays:
            # Arrays live above the scratch window inside the same frame, so a
            # recursive call gets its own copy. Displacement addresses the last
            # element; index 0 is the lowest address.
            cursor = self._scratch_base + 128
            for array_name, array_size in sorted(fn.local_arrays.items()):
                self._local_array_slots[array_name] = (-(cursor + array_size * 8), array_size)
                cursor += array_size * 8
            if cursor - (self._scratch_base + 128) > 4096:
                raise CompileError(
                    f"{self.path}:{fn.line}: native local arrays are limited to "
                    "4096 bytes per function until stack probing lands"
                )
            self._frame_size = ((cursor + 15) // 16) * 16
        if self._frame_size > self.MAX_FRAME_BYTES:
            if fn.local_arrays:
                raise CompileError(
                    f"{self.path}:{fn.line}: native local arrays do not fit in one "
                    "4 KB stack frame; use a smaller array or declare it at the "
                    "top level of the file"
                )
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
        if getattr(fn, "returns_text", False):
            empty = self.reserve_data(b"\x00")
            self.code.rip_lea_data(0, empty)      # rax = the empty text
            self.code.bytes(b"\xc9\xc3")          # leave; ret
        else:
            self.code.bytes(b"\x0f\x57\xc0\xc9\xc3")  # zero return; leave; ret

    def _emit_print_helper(self) -> None:
        """Write a signed number with up to six fractional digits via Kernel32."""
        self.code.label("function:anvil_print_number")
        self.code.bytes(b"\x48\x83\xec\x68")  # shadow space, locals, saved destination
        self.code.bytes(b"\x48\x89\x54\x24\x58")  # save rdx: destination when ecx==2
        self.code.bytes(b"\x66\x48\x0f\x7e\xc0")  # movq rax,xmm0
        self.code.bytes(b"\x48\xc1\xe8\x3f\x41\x89\xc3")  # sign bit -> r11d
        self.code.bytes(b"\x66\x0f\x28\xc8")  # movapd xmm1,xmm0
        # -0.0 has the sign bit set, but the C formatter prints it as 0. Drop the
        # minus when the magnitude is zero so both backends agree.
        keep_sign = self.label("print_keep_sign")
        self.code.bytes(b"\x66\x0f\x57\xd2")  # xorpd xmm2,xmm2
        self.code.bytes(b"\x66\x0f\x2e\xc2")  # ucomisd xmm0,xmm2
        self.code.conditional_jump(0x8A, keep_sign)  # jp: NaN, leave the sign
        self.code.conditional_jump(0x85, keep_sign)  # jne: nonzero, keep the sign
        self.code.bytes(b"\x45\x31\xdb")  # xor r11d,r11d
        self.code.label(keep_sign)
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
        # A value that renders as zero must not keep its minus: -1e-7 prints "0"
        # on the C backend because %.6f rounds it away and trims to "-0", which
        # the formatter maps to "0". r11d still holds the sign here.
        self.code.bytes(b"\x48\x8b\x54\x24\x28")  # rdx = integer part
        self.code.bytes(b"\x48\x09\xc2")  # or rdx, rax (fraction)
        keep_sign = self.label("print_keep_sign_after_round")
        self.code.conditional_jump(0x85, keep_sign)  # nonzero: keep the sign
        self.code.bytes(b"\x45\x31\xdb")  # xor r11d, r11d
        self.code.label(keep_sign)
        self.code.bytes(b"\x44\x89\x5c\x24\x20")  # preserve negative flag
        self.code.bytes(b"\x45\x31\xdb")  # r11d = fraction-started flag
        self.code.bytes(b"\x4c\x8d\x54\x24\x50")  # lea r10,[rsp+50h]
        # ECX carries the newline flag: 1 = output appends '\n', 0 = say parts.
        newline_skip = self.label("print_newline_skip")
        self.code.bytes(b"\x83\xf9\x01")  # cmp ecx, 1: only output mode appends \n
        self.code.conditional_jump(0x85, newline_skip)
        self.code.bytes(b"\xc6\x44\x24\x50\x0a")  # newline
        self.code.label(newline_skip)
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
        newline_end = self.label("print_end_newline")
        after_end = self.label("print_end_done")
        self.code.bytes(b"\x83\xf9\x01")  # cmp ecx, 1
        self.code.conditional_jump(0x84, newline_end)
        self.code.bytes(b"\x48\x8d\x54\x24\x50")  # end excludes the newline
        self.code.jump(after_end)
        self.code.label(newline_end)
        self.code.bytes(b"\x48\x8d\x54\x24\x51")  # end includes the newline
        self.code.label(after_end)
        self.code.bytes(b"\x4c\x29\xd2\x89\x54\x24\x28")  # length
        # ecx==2: copy the rendered text to [rsp+0x48] and null-terminate it
        # instead of writing to stdout (anvil_str_from_number's backend).
        buffer_copy = self.label("print_buffer_copy")
        stdout_path = self.label("print_stdout_path")
        self.code.bytes(b"\x83\xf9\x02")  # cmp ecx, 2
        self.code.conditional_jump(0x85, stdout_path)
        self.code.bytes(b"\x4c\x8b\x54\x24\x20")  # r10 = start
        self.code.bytes(b"\x44\x8b\x4c\x24\x28")  # r9d = length
        self.code.bytes(b"\x48\x8b\x4c\x24\x58")  # rcx = destination
        copy_loop = self.label("print_buffer_loop")
        copy_done = self.label("print_buffer_done")
        self.code.label(copy_loop)
        self.code.bytes(b"\x45\x85\xc9")  # test r9d, r9d
        self.code.conditional_jump(0x84, copy_done)
        self.code.bytes(b"\x41\x0f\xb6\x02")  # movzx eax, byte [r10]
        self.code.bytes(b"\x88\x01")  # mov [rcx], al
        self.code.bytes(b"\x48\xff\xc1\x49\xff\xc2\x41\xff\xc9")
        self.code.jump(copy_loop)
        self.code.label(copy_done)
        self.code.bytes(b"\xc6\x01\x00")  # terminate
        self.code.jump("print_epilogue")
        self.code.label(stdout_path)
        self.code.bytes(b"\xb9\xf5\xff\xff\xff")  # STD_OUTPUT_HANDLE
        self.code.rip_call_import("GetStdHandle")
        self.code.bytes(b"\x48\x89\xc1\x48\x8b\x54\x24\x20")
        self.code.bytes(b"\x8b\x44\x24\x28\x49\x89\xc0\x4c\x8d\x4c\x24\x30")
        self.code.bytes(b"\x48\xc7\x44\x24\x20\x00\x00\x00\x00")
        self.code.rip_call_import("WriteFile")
        self.code.label("print_epilogue")
        self.code.bytes(b"\x48\x83\xc4\x68\xc3")
        self.code.label(range_error)
        message = b"Anvil output out of range (the native backend prints up to 9.2e18)\n"
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

    def _emit_input_helper(self) -> None:
        """Consume one line of console input (Enter) before returning."""
        self.code.label("function:anvil_press_enter")
        # 0xB8 bytes: 0x20 shadow + 8 written + the 128-byte input buffer,
        # keeping rsp 16-byte aligned for the call.
        self.code.bytes(b"\x48\x81\xec\xb8\x00\x00\x00")
        self.code.mov_imm(1, -10)                          # STD_INPUT_HANDLE
        self.code.rip_call_import("GetStdHandle")
        self.code.bytes(b"\x48\x89\xc1")                  # rcx = handle
        self.code.bytes(b"\x48\x8d\x54\x24\x30")        # rdx = input buffer
        self.code.mov_imm(8, 128)                          # r8d = capacity
        self.code.bytes(b"\x4c\x8d\x4c\x24\x28")        # r9 = &bytes-read
        self.code.bytes(b"\x48\xc7\x44\x24\x20\x00\x00\x00\x00")  # overlapped = NULL
        self.code.rip_call_import("ReadFile")
        self.code.bytes(b"\x48\x81\xc4\xb8\x00\x00\x00")  # add rsp,0xB8
        self.code.bytes(b"\xc3")                            # ret

    def _emit_parse_number_helper(self) -> None:
        """rcx = text: xmm0 = the leading number (optional -, digits, .digits)."""
        self.code.label("function:anvil_parse_number")
        self.code.bytes(b"\x48\x83\xec\x38")           # frame
        self.code.bytes(b"\x48\x89\x4c\x24\x20")      # [rsp+20] = cursor
        intloop = self.label("num_int_loop")
        frac = self.label("num_frac_check")
        fracloop = self.label("num_frac_loop")
        nofrac = self.label("num_nofrac")
        finish = self.label("num_finish")
        positive = self.label("num_positive_value")
        done = self.label("num_done")
        exp_check = self.label("num_exp_check")
        self.code.bytes(b"\x31\xc0")                    # xor eax, eax (value)
        self.code.bytes(b"\x45\x31\xc0")               # xor r8d, r8d (sign)
        skip = self.label("num_skip_space")
        sign = self.label("num_sign")
        advance = self.label("num_skip_advance")
        self.code.label(skip)
        self.code.bytes(b"\x80\x39\x20")               # cmp byte [rcx], ' '
        self.code.conditional_jump(0x84, advance)        # je: skip a space
        self.code.bytes(b"\x80\x39\x09")               # cmp byte [rcx], tab
        self.code.conditional_jump(0x85, sign)           # jne: not whitespace
        self.code.label(advance)
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.jump(skip)
        self.code.label(sign)
        plus_check = self.label("num_plus_check")
        self.code.bytes(b"\x80\x39\x2d")               # cmp byte [rcx], '-'
        self.code.conditional_jump(0x85, plus_check)     # jne: maybe '+'
        self.code.mov_imm(8, 1)                          # r8d = 1 (negative)
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.jump(intloop)
        self.code.label(plus_check)
        self.code.bytes(b"\x80\x39\x2b")               # cmp byte [rcx], '+'
        self.code.conditional_jump(0x85, intloop)        # jne: no sign
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.label(intloop)
        self.code.bytes(b"\x0f\xb6\x11")               # movzx edx, byte [rcx]
        self.code.bytes(b"\x80\xea\x30")               # sub dl, '0'
        self.code.bytes(b"\x80\xfa\x09")               # cmp dl, 9
        self.code.conditional_jump(0x87, frac)           # ja: not a digit
        self.code.bytes(b"\x48\x6b\xc0\x0a")          # imul rax, rax, 10
        self.code.bytes(b"\x44\x0f\xb6\xca")          # movzx r9d, dl
        self.code.bytes(b"\x4c\x01\xc8")               # add rax, r9
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.jump(intloop)
        self.code.label(frac)
        self.code.bytes(b"\x80\x39\x2e")               # cmp byte [rcx], '.'
        self.code.conditional_jump(0x85, nofrac)         # jne: no fraction
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.bytes(b"\x45\x31\xc9")               # xor r9d, r9d (fraction)
        self.code.mov_imm(10, 1)                         # r10d = scale
        self.code.label(fracloop)
        self.code.bytes(b"\x0f\xb6\x11")               # movzx edx, byte [rcx]
        self.code.bytes(b"\x80\xea\x30")               # sub dl, '0'
        self.code.bytes(b"\x80\xfa\x09")               # cmp dl, 9
        self.code.conditional_jump(0x87, finish)         # ja
        self.code.bytes(b"\x45\x6b\xc9\x0a")          # imul r9d, r9d, 10
        self.code.bytes(b"\x44\x0f\xb6\xda")          # movzx r11d, dl
        self.code.bytes(b"\x45\x01\xd9")               # add r9d, r11d
        self.code.bytes(b"\x45\x6b\xd2\x0a")          # imul r10d, r10d, 10
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.bytes(b"\x41\x81\xfa\x00\xca\x9a\x3b")  # cmp r10d, 1e9
        self.code.conditional_jump(0x82, fracloop)       # jb: keep reading digits
        self.code.jump(finish)
        self.code.label(nofrac)
        self.code.bytes(b"\x45\x31\xc9")               # xor r9d, r9d
        self.code.bytes(b"\x45\x31\xd2")               # xor r10d, r10d
        self.code.label(finish)
        self.code.bytes(b"\x48\x89\x44\x24\x10")      # [rsp+10] = rax (int)
        self.code.bytes(b"\x44\x89\x4c\x24\x18")      # [rsp+18] = r9d (fraction)
        self.code.bytes(b"\x44\x89\x54\x24\x1c")      # [rsp+1c] = r10d (scale)
        self.code.bytes(b"\x44\x89\x44\x24\x28")      # [rsp+28] = r8d (sign)
        # real logic, entirely from slots
        self.code.bytes(b"\x48\x8b\x44\x24\x10")      # rax = int
        self.code.bytes(b"\x44\x8b\x44\x24\x28")      # r8d = sign
        self.code.bytes(b"\x45\x85\xc0")               # test r8d, r8d
        self.code.conditional_jump(0x84, positive)       # je: positive
        self.code.bytes(b"\x48\xf7\xd8")               # neg rax
        self.code.label(positive)
        self.code.bytes(b"\xf2\x48\x0f\x2a\xc0")     # cvtsi2sd xmm0, rax
        self.code.bytes(b"\x44\x8b\x4c\x24\x1c")      # r9d = scale
        self.code.bytes(b"\x45\x85\xc9")               # test r9d, r9d
        self.code.conditional_jump(0x84, exp_check)      # je: no fraction
        self.code.bytes(b"\xf2\x0f\x2a\x4c\x24\x18")  # cvtsi2sd xmm1, [rsp+18]
        self.code.bytes(b"\xf2\x0f\x2a\x54\x24\x1c")  # cvtsi2sd xmm2, [rsp+1c]
        self.code.bytes(b"\xf2\x0f\x5e\xca")          # divsd xmm1, xmm2
        negative_frac = self.label("num_frac_negative")
        add_frac = self.label("num_frac_add")
        self.code.bytes(b"\x45\x85\xc0")               # test r8d, r8d (sign)
        self.code.conditional_jump(0x85, negative_frac)  # jne: negative value
        self.code.label(add_frac)
        self.code.bytes(b"\xf2\x0f\x58\xc1")          # addsd xmm0, xmm1
        self.code.jump(exp_check)
        self.code.label(negative_frac)
        self.code.bytes(b"\xf2\x0f\x5c\xc1")          # subsd xmm0, xmm1
        # --- optional exponent: 1e3, -2.5E-2 (only after a mantissa) ---
        self.code.label(exp_check)
        exp_begin = self.label("num_exp_begin")
        exp_plus = self.label("num_exp_plus")
        exp_digits = self.label("num_exp_digits")
        exp_loop = self.label("num_exp_loop")
        exp_apply = self.label("num_exp_apply")
        exp_div = self.label("num_exp_div")
        exp_mul = self.label("num_exp_mul")
        self.code.bytes(b"\x0f\xb6\x11")               # movzx edx, byte [rcx]
        self.code.bytes(b"\x80\xfa\x65")               # cmp dl, 'e'
        self.code.conditional_jump(0x84, exp_begin)
        self.code.bytes(b"\x80\xfa\x45")               # cmp dl, 'E'
        self.code.conditional_jump(0x85, done)
        self.code.label(exp_begin)
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.bytes(b"\x45\x31\xd2")               # r10d = 0 (exp sign)
        self.code.bytes(b"\x80\x39\x2d")               # cmp byte [rcx], '-'
        self.code.conditional_jump(0x85, exp_plus)
        self.code.mov_imm(10, 1)                        # r10d = 1 (divide)
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.jump(exp_digits)
        self.code.label(exp_plus)
        self.code.bytes(b"\x80\x39\x2b")               # cmp byte [rcx], '+'
        self.code.conditional_jump(0x85, exp_digits)
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.label(exp_digits)
        self.code.bytes(b"\x45\x31\xc9")               # r9d = 0 (exponent)
        self.code.label(exp_loop)
        self.code.bytes(b"\x0f\xb6\x11")               # movzx edx, byte [rcx]
        self.code.bytes(b"\x80\xea\x30")               # sub dl, '0'
        self.code.bytes(b"\x80\xfa\x09")               # cmp dl, 9
        self.code.conditional_jump(0x87, exp_apply)      # ja: exponent done
        self.code.bytes(b"\x45\x6b\xc9\x0a")          # imul r9d, r9d, 10
        self.code.bytes(b"\x44\x0f\xb6\xda")          # movzx r11d, dl
        self.code.bytes(b"\x45\x01\xd9")               # add r9d, r11d
        self.code.bytes(b"\x48\xff\xc1")               # inc rcx
        self.code.bytes(b"\x41\x81\xf9\x34\x01\x00\x00")  # cmp r9d, 308
        self.code.conditional_jump(0x86, exp_loop)       # jbe: keep reading
        self.code.label(exp_apply)
        self.code.bytes(b"\x45\x85\xc9")               # test r9d, r9d
        self.code.conditional_jump(0x84, done)           # je: no exponent
        self.code.mov_imm(0, 0x4024000000000000)        # rax = 10.0
        self.code.bytes(b"\x66\x48\x0f\x6e\xc8")      # movq xmm1, rax
        self.code.bytes(b"\x45\x85\xd2")               # test r10d, r10d
        self.code.conditional_jump(0x85, exp_div)        # jne: negative exponent
        self.code.label(exp_mul)
        self.code.bytes(b"\xf2\x0f\x59\xc1")          # mulsd xmm0, xmm1
        self.code.bytes(b"\x41\xff\xc9")               # dec r9d
        self.code.conditional_jump(0x85, exp_mul)        # jne: keep scaling
        self.code.jump(done)
        self.code.label(exp_div)
        self.code.bytes(b"\xf2\x0f\x5e\xc1")          # divsd xmm0, xmm1
        self.code.bytes(b"\x41\xff\xc9")               # dec r9d
        self.code.conditional_jump(0x85, exp_div)        # jne: keep scaling
        self.code.label(done)
        self.code.bytes(b"\x48\x83\xc4\x38\xc3")      # add rsp,0x38; ret

    def _emit_equal_helper(self) -> None:
        """rcx = text a, rdx = text b: rax = 1 when the bytes are identical."""
        self.code.label("function:anvil_str_equal")
        loop = self.label("str_equal_scan")
        yes = self.label("str_equal_yes")
        no = self.label("str_equal_no")
        self.code.label(loop)
        self.code.bytes(b"\x44\x0f\xb6\x01")           # movzx r8d, byte [rcx]
        self.code.bytes(b"\x44\x0f\xb6\x0a")           # movzx r9d, byte [rdx]
        self.code.bytes(b"\x45\x38\xc8")               # cmp r8b, r9b
        self.code.conditional_jump(0x85, no)             # jne: differ
        self.code.bytes(b"\x45\x84\xc0")               # test r8b, r8b
        self.code.conditional_jump(0x84, yes)            # je: both NUL -> equal
        self.code.bytes(b"\x48\xff\xc1\x48\xff\xc2")  # inc rcx; inc rdx
        self.code.jump(loop)
        self.code.label(yes)
        self.code.bytes(b"\xb8\x01\x00\x00\x00")       # eax = 1
        self.code.bytes(b"\xc3")
        self.code.label(no)
        self.code.bytes(b"\x31\xc0")                    # eax = 0
        self.code.bytes(b"\xc3")

    def _emit_text_helper(self) -> None:
        """rcx = destination text, rdx = source text: append source at the
        destination's terminator. Built only from the proven str_copy shape."""
        self.code.label("function:anvil_str_append")
        self.code.bytes(b"\x48\x83\xec\x28")           # locals
        self.code.mov_reg(10, 2)                         # r10 = src
        self.code.mov_reg(9, 1)                          # r9 = dst
        self.code.call("function:anvil_str_len")         # rax = len(dst)
        self.code.bytes(b"\x4b\x8d\x0c\x01")           # lea rcx, [r9+rax] = dst+len(dst)
        self.code.mov_reg(2, 10)                         # rdx = src
        self.code.call("function:anvil_str_copy")        # copy src at dst+len
        self.code.mov_reg(0, 9)                          # rax = dst
        self.code.bytes(b"\x48\x83\xc4\x28\xc3")      # add rsp,0x28; ret

    def _emit_string_helpers(self) -> None:
        """strlen / copy / append over 256-byte text buffers in .data."""
        self.code.label("function:anvil_str_len")
        self.code.bytes(b"\x31\xc0")                    # xor eax, eax
        scan = self.label("str_len_scan")
        reached = self.label("str_len_done")
        self.code.label(scan)
        self.code.bytes(b"\x80\x39\x00")               # cmp byte [rcx], 0
        self.code.conditional_jump(0x84, reached)
        self.code.bytes(b"\x48\xff\xc0\x48\xff\xc1")  # inc rax; inc rcx
        self.code.jump(scan)
        self.code.label(reached)
        self.code.bytes(b"\xc3")

        self.code.label("function:anvil_str_copy")
        self.code.mov_reg(10, 1)                         # r10 = dst
        self.code.mov_reg(11, 2)                         # r11 = src
        self.code.mov_reg(1, 11)                         # rcx = src
        self.code.call("function:anvil_str_len")         # rax = length
        overflow_copy = self.label("str_copy_overflow")
        done_copy = self.label("str_copy_done")
        loop_copy = self.label("str_copy_loop")
        self.code.bytes(b"\x48\x3d\xff\x00\x00\x00")  # cmp rax, 255
        self.code.conditional_jump(0x87, overflow_copy)  # ja: too long
        self.code.mov_reg(9, 0)                          # r9 = length
        self.code.mov_reg(8, 9)                          # r8 = original length
        self.code.label(loop_copy)
        self.code.bytes(b"\x4d\x85\xc9")               # test r9, r9
        self.code.conditional_jump(0x84, done_copy)
        self.code.bytes(b"\x41\x0f\xb6\x03")          # movzx eax, byte [r11]
        self.code.bytes(b"\x41\x88\x02")               # mov byte [r10], al
        self.code.bytes(b"\x49\xff\xc2\x49\xff\xc3\x49\xff\xc9")
        self.code.jump(loop_copy)
        self.code.label(done_copy)
        self.code.bytes(b"\x41\xc6\x02\x00")          # store terminator
        self.code.bytes(b"\x4c\x89\xd0")               # rax = r10 (end)
        self.code.bytes(b"\x4c\x29\xc0")               # rax -= r8: original dst
        self.code.bytes(b"\xc3")
        self.code.label(overflow_copy)
        self.emit_runtime_error("Anvil text is limited to 255 characters\n")

        self.code.label("function:anvil_str_append")
        self.code.bytes(b"\x48\x83\xec\x28")           # locals
        self.code.mov_reg(10, 2)                         # r10 = src
        self.code.mov_reg(9, 1)                          # r9 = dst
        self.code.call("function:anvil_str_len")         # rax = len(dst)
        self.code.bytes(b"\x4b\x8d\x0c\x01")           # lea rcx, [r9+rax] = dst+len
        self.code.mov_reg(2, 10)                         # rdx = src
        self.code.call("function:anvil_str_copy")        # copy src at dst+len
        self.code.mov_reg(0, 9)                          # rax = dst
        self.code.bytes(b"\x48\x83\xc4\x28\xc3")      # add rsp,0x28; ret

    def _emit_read_line_helper(self) -> None:
        """rcx = destination buffer: hand back one console line, strip CR/LF.

        A single bulk ReadFile swallows every line that arrived in the same
        write, so a second `ask` saw an empty string. The chunk now lands in a
        static stash and each call copies out one line, remembering where the
        next one starts.
        """
        stash = self.reserve_data(b"\x00" * 256)
        length = self.reserve_data(b"\x00" * 8)
        position = self.reserve_data(b"\x00" * 8)
        self.code.label("function:anvil_read_line")
        self.code.bytes(b"\x48\x83\xec\x38")            # locals + written count
        self.code.bytes(b"\x48\x89\x4c\x24\x30")        # [rsp+30] = dst
        copy = self.label("ask_copy")
        self.code.rip_int(0, position)                   # rax = stash position
        self.code.rip_int(2, length)                     # rdx = stash length
        self.code.bytes(b"\x48\x39\xd0")                 # cmp rax, rdx
        self.code.conditional_jump(0x82, copy)           # jb: bytes are waiting
        self.code.mov_imm(1, -10)                        # STD_INPUT_HANDLE
        self.code.rip_call_import("GetStdHandle")
        self.code.bytes(b"\x48\x89\xc1")                 # rcx = handle
        self.code.rip_lea_data(2, stash)                 # rdx = stash
        self.code.mov_imm(8, 255)                        # capacity minus terminator
        self.code.bytes(b"\x4c\x8d\x4c\x24\x28")         # r9 = &bytes-read
        self.code.bytes(b"\x48\xc7\x44\x24\x20\x00\x00\x00\x00")  # overlapped
        self.code.rip_call_import("ReadFile")
        self.code.bytes(b"\x48\x8b\x44\x24\x28")         # rax = bytes read
        self.code.rip_int(0, length, store=True)         # stash length = rax
        self.code.bytes(b"\x31\xc0")                     # xor eax, eax
        self.code.rip_int(0, position, store=True)       # stash position = 0
        self.code.label(copy)
        self.code.bytes(b"\x45\x31\xc0")                 # xor r8d, r8d (out index)
        loop = self.label("ask_loop")
        finish = self.label("ask_finish")
        self.code.label(loop)
        self.code.rip_int(0, position)                   # rax = position
        self.code.rip_int(2, length)                     # rdx = length
        self.code.bytes(b"\x48\x39\xd0")                 # cmp rax, rdx
        self.code.conditional_jump(0x83, finish)         # jae: stash drained
        self.code.rip_lea_data(9, stash)                 # r9 = stash
        self.code.bytes(b"\x41\x0f\xb6\x0c\x01")         # movzx ecx, byte [r9+rax]
        self.code.bytes(b"\x48\xff\xc0")                 # inc rax
        self.code.rip_int(0, position, store=True)       # position = rax
        self.code.bytes(b"\x80\xf9\x0a")                 # cmp cl, 10
        self.code.conditional_jump(0x84, finish)         # newline ends the line
        self.code.bytes(b"\x80\xf9\x0d")                 # cmp cl, 13
        self.code.conditional_jump(0x84, loop)           # drop the carriage return
        self.code.bytes(b"\x48\x8b\x54\x24\x30")         # rdx = dst
        self.code.bytes(b"\x42\x88\x0c\x02")             # mov byte [rdx+r8], cl
        self.code.bytes(b"\x49\xff\xc0")                 # inc r8
        self.code.bytes(b"\x49\x81\xf8\xff\x00\x00\x00") # cmp r8, 255
        self.code.conditional_jump(0x83, finish)         # jae: buffer full
        self.code.jump(loop)
        self.code.label(finish)
        self.code.bytes(b"\x48\x8b\x54\x24\x30")         # rdx = dst
        self.code.bytes(b"\x42\xc6\x04\x02\x00")         # mov byte [rdx+r8], 0
        self.code.bytes(b"\x48\x83\xc4\x38\xc3")         # add rsp,0x38; ret

    def _emit_text_helper(self) -> None:
        """rcx = destination text, rdx = source text: append source at the
        destination's terminator. Built only from the proven str_copy shape."""
        self.code.label("function:anvil_str_append")
        self.code.bytes(b"\x48\x83\xec\x28")           # locals
        self.code.mov_reg(10, 2)                         # r10 = src
        self.code.mov_reg(9, 1)                          # r9 = dst
        self.code.call("function:anvil_str_len")         # rax = len(dst)
        self.code.bytes(b"\x4b\x8d\x0c\x01")           # lea rcx, [r9+rax] = dst+len(dst)
        self.code.mov_reg(2, 10)                         # rdx = src
        self.code.call("function:anvil_str_copy")        # copy src at dst+len
        self.code.mov_reg(0, 9)                          # rax = dst
        self.code.bytes(b"\x48\x83\xc4\x28\xc3")      # add rsp,0x28; ret

    def _emit_string_helpers(self) -> None:
        """strlen / copy / append over 256-byte text buffers in .data."""
        self.code.label("function:anvil_str_len")
        self.code.bytes(b"\x31\xc0")                    # xor eax, eax
        scan = self.label("str_len_scan")
        reached = self.label("str_len_done")
        self.code.label(scan)
        self.code.bytes(b"\x80\x39\x00")               # cmp byte [rcx], 0
        self.code.conditional_jump(0x84, reached)
        self.code.bytes(b"\x48\xff\xc0\x48\xff\xc1")  # inc rax; inc rcx
        self.code.jump(scan)
        self.code.label(reached)
        self.code.bytes(b"\xc3")

        self.code.label("function:anvil_str_copy")
        self.code.mov_reg(10, 1)                         # r10 = dst
        self.code.mov_reg(11, 2)                         # r11 = src
        self.code.mov_reg(1, 11)                         # rcx = src
        self.code.call("function:anvil_str_len")         # rax = length
        overflow_copy = self.label("str_copy_overflow")
        done_copy = self.label("str_copy_done")
        loop_copy = self.label("str_copy_loop")
        self.code.bytes(b"\x48\x3d\xff\x00\x00\x00")  # cmp rax, 255
        self.code.conditional_jump(0x87, overflow_copy)  # ja: too long
        self.code.mov_reg(9, 0)                          # r9 = length
        self.code.mov_reg(8, 9)                          # r8 = original length
        self.code.label(loop_copy)
        self.code.bytes(b"\x4d\x85\xc9")               # test r9, r9
        self.code.conditional_jump(0x84, done_copy)
        self.code.bytes(b"\x41\x0f\xb6\x03")          # movzx eax, byte [r11]
        self.code.bytes(b"\x41\x88\x02")               # mov byte [r10], al
        self.code.bytes(b"\x49\xff\xc2\x49\xff\xc3\x49\xff\xc9")
        self.code.jump(loop_copy)
        self.code.label(done_copy)
        self.code.bytes(b"\x41\xc6\x02\x00")          # store terminator
        self.code.bytes(b"\x4c\x89\xd0")               # rax = r10 (end)
        self.code.bytes(b"\x4c\x29\xc0")               # rax -= r8: original dst
        self.code.bytes(b"\xc3")
        self.code.label(overflow_copy)
        self.emit_runtime_error("Anvil text is limited to 255 characters\n")

        self.code.label("function:anvil_str_append")
        self.code.bytes(b"\x48\x83\xec\x28")           # locals
        self.code.mov_reg(10, 2)                         # r10 = src
        self.code.mov_reg(9, 1)                          # r9 = dst
        self.code.call("function:anvil_str_len")         # rax = len(dst)
        self.code.bytes(b"\x4b\x8d\x0c\x01")           # lea rcx, [r9+rax] = dst+len
        self.code.mov_reg(2, 10)                         # rdx = src
        self.code.call("function:anvil_str_copy")        # copy src at dst+len
        self.code.mov_reg(0, 9)                          # rax = dst
        self.code.bytes(b"\x48\x83\xc4\x28\xc3")      # add rsp,0x28; ret

    def _emit_text_helper(self) -> None:
        """rcx = destination text, rdx = source text: append source at the
        destination's terminator. Built only from the proven str_copy shape."""
        self.code.label("function:anvil_str_append")
        self.code.bytes(b"\x48\x83\xec\x28")           # locals
        self.code.mov_reg(10, 2)                         # r10 = src
        self.code.mov_reg(9, 1)                          # r9 = dst
        self.code.call("function:anvil_str_len")         # rax = len(dst)
        self.code.bytes(b"\x4b\x8d\x0c\x01")           # lea rcx, [r9+rax] = dst+len(dst)
        self.code.mov_reg(2, 10)                         # rdx = src
        self.code.call("function:anvil_str_copy")        # copy src at dst+len
        self.code.mov_reg(0, 9)                          # rax = dst
        self.code.bytes(b"\x48\x83\xc4\x28\xc3")      # add rsp,0x28; ret

    def _emit_mid_helper(self) -> None:
        """rcx = dst, rdx = src, xmm0 = start, xmm1 = count: bounded slice."""
        self.code.label("function:anvil_text_mid")
        self.code.mov_reg(10, 1)                          # r10 = destination
        self.code.mov_reg(11, 2)                          # r11 = source
        self.code.bytes(b"\xf2\x48\x0f\x2c\xc0")      # rax = start
        self.code.bytes(b"\xf2\x4c\x0f\x2c\xc9")      # r9 = count
        empty = self.label("mid_empty")
        start_ok = self.label("mid_start_ok")
        self.code.bytes(b"\x48\x85\xc0")                 # test rax, rax
        self.code.conditional_jump(0x89, start_ok)         # jns: start fine
        self.code.bytes(b"\x31\xc0")                     # clamp: start = 0
        self.code.label(start_ok)
        self.code.bytes(b"\x4d\x85\xc9")                 # test r9, r9
        self.code.conditional_jump(0x8c, empty)            # jl: negative count
        self.code.bytes(b"\x45\x31\xc0")                 # r8d = 0 (length)
        len_loop = self.label("mid_len_loop")
        have_len = self.label("mid_have_len")
        copy_init = self.label("mid_copy_init")
        copy_loop = self.label("mid_copy_loop")
        copy_done = self.label("mid_copy_done")
        self.code.label(len_loop)
        self.code.bytes(b"\x43\x0f\xb6\x0c\x03")       # movzx ecx, [r11+r8]
        self.code.bytes(b"\x85\xc9")                     # test ecx, ecx
        self.code.conditional_jump(0x84, have_len)
        self.code.bytes(b"\x41\xff\xc0")                 # ++r8d
        self.code.jump(len_loop)
        self.code.label(have_len)
        self.code.bytes(b"\x4c\x39\xc0")                 # cmp rax, r8
        self.code.conditional_jump(0x87, empty)            # ja: start past the end
        self.code.bytes(b"\x4a\x8d\x0c\x08")            # rcx = start + count
        self.code.bytes(b"\x4c\x39\xc1")                 # cmp rcx, r8
        self.code.conditional_jump(0x86, copy_init)        # jbe: end within bounds
        self.code.mov_reg(1, 8)                            # rcx = r8 (clamp)
        self.code.label(copy_init)
        self.code.bytes(b"\x45\x31\xc9")                 # r9d = 0 (the copy index)
        self.code.label(copy_loop)
        self.code.bytes(b"\x48\x39\xc8")                 # cmp rax, rcx
        self.code.conditional_jump(0x83, copy_done)        # jae: sliced everything
        self.code.bytes(b"\x45\x0f\xb6\x04\x03")       # movzx r8d, [r11+rax]
        self.code.bytes(b"\x47\x88\x04\x0a")            # mov [r10+r9], r8b
        self.code.bytes(b"\x48\xff\xc0")                 # ++rax
        self.code.bytes(b"\x41\xff\xc1")                 # ++r9d
        self.code.jump(copy_loop)
        self.code.label(copy_done)
        self.code.bytes(b"\x43\xc6\x04\x0a\x00")       # mov byte [r10+r9], 0
        self.code.mov_reg(0, 10)
        self.code.bytes(b"\xc3")
        self.code.label(empty)
        self.code.bytes(b"\x41\xc6\x02\x00")            # mov byte [r10], 0
        self.code.mov_reg(0, 10)
        self.code.bytes(b"\xc3")

    def _emit_contains_helper(self) -> None:
        """rcx = text, rdx = needle: rax = 1 when the needle occurs, else 0."""
        self.code.label("function:anvil_str_contains")
        self.code.mov_reg(10, 1)                          # r10 = text
        self.code.mov_reg(11, 2)                          # r11 = needle
        self.code.bytes(b"\x41\x80\x3b\x00")            # cmp byte [r11], 0
        yes = self.label("contains_yes")
        no = self.label("contains_no")
        outer = self.label("contains_outer")
        inner = self.label("contains_inner")
        next_pos = self.label("contains_next")
        self.code.conditional_jump(0x84, yes)              # je: empty needle
        self.code.bytes(b"\x45\x31\xc0")                 # r8d = position
        self.code.label(outer)
        self.code.bytes(b"\x43\x0f\xb6\x04\x02")       # movzx eax, [r10+r8]
        self.code.bytes(b"\x85\xc0")                     # test eax, eax
        self.code.conditional_jump(0x84, no)               # je: text exhausted
        self.code.bytes(b"\x4b\x8d\x0c\x02")            # lea rcx, [r10+r8]
        self.code.bytes(b"\x45\x31\xc9")                 # r9d = 0
        self.code.label(inner)
        self.code.bytes(b"\x43\x0f\xb6\x14\x0b")       # movzx edx, [r11+r9]
        self.code.bytes(b"\x85\xd2")                     # test edx, edx
        self.code.conditional_jump(0x84, yes)              # je: the needle matched
        self.code.bytes(b"\x42\x0f\xb6\x04\x09")       # movzx eax, [rcx+r9]
        self.code.bytes(b"\x38\xd0")                     # cmp al, dl
        self.code.conditional_jump(0x85, next_pos)         # jne: mismatch
        self.code.bytes(b"\x41\xff\xc1")                 # ++r9d
        self.code.jump(inner)
        self.code.label(next_pos)
        self.code.bytes(b"\x41\xff\xc0")                 # ++r8d
        self.code.jump(outer)
        self.code.label(yes)
        self.code.mov_imm(0, 1)
        self.code.bytes(b"\xc3")
        self.code.label(no)
        self.code.bytes(b"\x31\xc0")
        self.code.bytes(b"\xc3")

    def _emit_char_at_helper(self) -> None:
        """rcx = destination, rdx = source, xmm0 = index: one-character text."""
        self.code.label("function:anvil_text_char")
        self.code.mov_reg(10, 1)                          # r10 = destination
        self.code.mov_reg(11, 2)                          # r11 = source
        self.code.bytes(b"\xf2\x48\x0f\x2c\xc0")      # rax = (the index)
        empty = self.label("char_empty")
        self.code.bytes(b"\x48\x85\xc0")                 # test rax, rax
        self.code.conditional_jump(0x8c, empty)           # jl: negative index
        self.code.bytes(b"\x45\x31\xc0")                 # r8d = 0 (length scan)
        len_loop = self.label("char_len_loop")
        have_len = self.label("char_have_len")
        copy = self.label("char_copy")
        self.code.label(len_loop)
        self.code.bytes(b"\x43\x0f\xb6\x0c\x03")       # movzx ecx, [r11+r8]
        self.code.bytes(b"\x85\xc9")                     # test ecx, ecx
        self.code.conditional_jump(0x84, have_len)         # je: got the length
        self.code.bytes(b"\x41\xff\xc0")                 # ++r8d
        self.code.jump(len_loop)
        self.code.label(have_len)
        self.code.bytes(b"\x4c\x39\xc0")                 # cmp rax, r8
        self.code.conditional_jump(0x83, empty)            # jae: past the end
        self.code.label(copy)
        self.code.bytes(b"\x41\x0f\xb6\x0c\x03")       # movzx ecx, [r11+rax]
        self.code.bytes(b"\x41\x88\x0a")                 # mov [r10], cl
        self.code.bytes(b"\x41\xc6\x42\x01\x00")       # mov byte [r10+1], 0
        self.code.mov_reg(0, 10)                          # rax = destination
        self.code.bytes(b"\xc3")
        self.code.label(empty)
        self.code.bytes(b"\x41\xc6\x02\x00")            # mov byte [r10], 0
        self.code.mov_reg(0, 10)
        self.code.bytes(b"\xc3")

    def _emit_edge_helpers(self) -> None:
        """starts: rcx = text, rdx = prefix. ends: rcx = text, rdx = suffix."""
        self.code.label("function:anvil_str_starts")
        self.code.mov_reg(10, 1)                          # r10 = text
        self.code.mov_reg(11, 2)                          # r11 = prefix
        self.code.bytes(b"\x31\xc0")                     # index = 0
        loop = self.label("starts_loop")
        yes = self.label("starts_yes")
        no = self.label("starts_no")
        self.code.label(loop)
        self.code.bytes(b"\x45\x0f\xb6\x04\x02")       # movzx r8d, [r10+rax]
        self.code.bytes(b"\x45\x0f\xb6\x0c\x03")       # movzx r9d, [r11+rax]
        self.code.bytes(b"\x45\x84\xc9")                 # test r9b, r9b
        self.code.conditional_jump(0x84, yes)              # je: the prefix ended
        self.code.bytes(b"\x45\x38\xc8")                 # cmp r8b, r9b
        self.code.conditional_jump(0x85, no)               # jne: mismatch
        self.code.bytes(b"\x48\xff\xc0")                 # ++rax
        self.code.jump(loop)
        self.code.label(yes)
        self.code.mov_imm(0, 1)
        self.code.bytes(b"\xc3")
        self.code.label(no)
        self.code.bytes(b"\x31\xc0")
        self.code.bytes(b"\xc3")

        self.code.label("function:anvil_str_ends")
        # The body is the machine code clang generated for the same algorithm
        # (verified against the C reference); the internal jumps are relative,
        # so the blob is position-independent.
        self.code.bytes(bytes.fromhex(
            "4989ca4989d34531c0430fb60c0285c9740541ffc0ebf2"
            "4531c9430fb60c0b85c9740541ffc1ebf24539c8722a"
            "4c89c04c89c94885c97419410fb65402ff450fb6440b"
            "ff4438c2750e48ffc848ffc9ebe2b801000000c331c0c3"
        ))

    def _emit_compare_helper(self) -> None:
        self.code.label("function:anvil_str_compare")
        self.code.mov_reg(10, 1)                          # r10 = a
        self.code.mov_reg(11, 2)                          # r11 = b
        self.code.bytes(b"\x31\xc0")                     # index = 0
        loop = self.label("cmp_loop")
        differ = self.label("cmp_differ")
        less = self.label("cmp_less")
        equal = self.label("cmp_equal")
        self.code.label(loop)
        self.code.bytes(b"\x45\x0f\xb6\x04\x02")       # movzx r8d, [r10+rax]
        self.code.bytes(b"\x45\x0f\xb6\x0c\x03")       # movzx r9d, [r11+rax]
        self.code.bytes(b"\x45\x38\xc8")                 # cmp r8b, r9b
        self.code.conditional_jump(0x85, differ)           # jne: the bytes differ
        self.code.bytes(b"\x45\x84\xc0")                 # test r8b, r8b
        self.code.conditional_jump(0x84, equal)            # je: both ended
        self.code.bytes(b"\x48\xff\xc0")                 # ++rax
        self.code.jump(loop)
        self.code.label(differ)
        self.code.conditional_jump(0x82, less)             # jb: a < b
        self.code.mov_imm(0, 1)                            # a > b -> +1
        self.code.bytes(b"\xc3")
        self.code.label(less)
        self.code.mov_imm(0, -1)                           # a < b -> -1
        self.code.bytes(b"\xc3")
        self.code.label(equal)
        self.code.bytes(b"\x31\xc0")                     # 0
        self.code.bytes(b"\xc3")

    def _emit_trim_helper(self) -> None:
        """rcx = destination, rdx = source: copy without edge spaces/tabs."""
        self.code.label("function:anvil_text_trim")
        self.code.mov_reg(10, 1)                          # r10 = destination
        self.code.mov_reg(11, 2)                          # r11 = source
        self.code.bytes(b"\x31\xc0")                     # index = 0
        len_loop = self.label("trim_len_loop")
        got_len = self.label("trim_got_len")
        back_step = self.label("trim_back_step")
        back_check = self.label("trim_back_check")
        have_end = self.label("trim_have_end")
        start_loop = self.label("trim_start_loop")
        start_step = self.label("trim_start_step")
        copy = self.label("trim_copy")
        copy_loop = self.label("trim_copy_loop")
        copy_done = self.label("trim_copy_done")
        empty = self.label("trim_empty")
        self.code.label(len_loop)
        self.code.bytes(b"\x41\x0f\xb6\x0c\x03")       # movzx ecx, [r11+rax]
        self.code.bytes(b"\x85\xc9")                     # test ecx, ecx
        self.code.conditional_jump(0x84, got_len)          # je: got the length
        self.code.bytes(b"\x48\xff\xc0")                 # ++rax
        self.code.jump(len_loop)
        self.code.label(got_len)
        self.code.label(back_check)
        self.code.bytes(b"\x48\x85\xc0")                 # test rax, rax
        self.code.conditional_jump(0x84, empty)            # je: empty / all whitespace
        self.code.bytes(b"\x41\x0f\xb6\x4c\x03\xff")  # movzx ecx, [r11+rax-1]
        self.code.bytes(b"\x80\xf9\x20")                 # cmp cl, ' '
        self.code.conditional_jump(0x84, back_step)        # je: trailing space
        self.code.bytes(b"\x80\xf9\x09")                 # cmp cl, '\t'
        self.code.conditional_jump(0x84, back_step)        # je: trailing tab
        self.code.jump(have_end)
        self.code.label(back_step)
        self.code.bytes(b"\x48\xff\xc8")                 # --rax
        self.code.jump(back_check)
        self.code.label(have_end)
        self.code.bytes(b"\x45\x31\xc9")                 # r9d = 0 (start)
        self.code.label(start_loop)
        self.code.bytes(b"\x41\x39\xc1")                 # cmp r9d, eax
        self.code.conditional_jump(0x83, copy)             # jae: empty slice
        self.code.bytes(b"\x43\x0f\xb6\x0c\x0b")       # movzx ecx, [r11+r9]
        self.code.bytes(b"\x80\xf9\x20")                 # cmp cl, ' '
        self.code.conditional_jump(0x84, start_step)       # je: leading space
        self.code.bytes(b"\x80\xf9\x09")                 # cmp cl, '\t'
        self.code.conditional_jump(0x84, start_step)       # je: leading tab
        self.code.jump(copy)
        self.code.label(start_step)
        self.code.bytes(b"\x41\xff\xc1")                 # ++r9d
        self.code.jump(start_loop)
        self.code.label(copy)
        self.code.mov_reg(1, 10)                          # rcx = destination
        self.code.bytes(b"\x31\xd2")                     # rdx = copy count
        self.code.label(copy_loop)
        self.code.bytes(b"\x41\x39\xc1")                 # cmp r9d, eax
        self.code.conditional_jump(0x83, copy_done)        # jae: copied the slice
        self.code.bytes(b"\x47\x0f\xb6\x04\x0b")       # movzx r8d, [r11+r9]
        self.code.bytes(b"\x44\x88\x04\x11")            # mov [rcx+rdx], r8b
        self.code.bytes(b"\x41\xff\xc1")                 # ++r9d
        self.code.bytes(b"\x48\xff\xc2")                 # ++rdx
        self.code.jump(copy_loop)
        self.code.label(copy_done)
        self.code.bytes(b"\x42\xc6\x04\x12\x00")       # mov byte [r10+rdx], 0
        self.code.mov_reg(0, 10)                          # rax = destination
        self.code.bytes(b"\xc3")
        self.code.label(empty)
        self.code.bytes(b"\x41\xc6\x02\x00")            # mov byte [r10], 0
        self.code.mov_reg(0, 10)
        self.code.bytes(b"\xc3")

    def _emit_chr_error(self) -> None:
        """Shared out-of-range exit for chr(): report on stderr and stop."""
        self.code.label("chr_range_error")
        message = b"Anvil chr out of range\n"
        if message not in self._error_messages:
            self._error_messages[message] = self.reserve_data(message)
        self.code.mov_imm(1, -12)  # STD_ERROR_HANDLE
        self.code.rip_call_import("GetStdHandle")
        self.code.mov_reg(1, 0)
        self.code.rip_lea_data(2, self._error_messages[message])
        self.code.mov_imm(8, len(message))
        self.code.stack_int(9, 0x28, address=True)
        self.code.mov_imm(0, 0)
        self.code.stack_int(0, 0x20, store=True)
        self.code.rip_call_import("WriteFile")
        self.code.mov_imm(1, 1)  # exit code 1
        self.code.rip_call_import("ExitProcess")
        self.code.bytes(b"\xcc")

    def _emit_case_helper(self) -> None:
        """rcx = destination, rdx = source, r8d = mode (0 upper, 1 lower)."""
        self.code.label("function:anvil_text_case")
        self.code.mov_reg(10, 1)                          # r10 = destination
        self.code.mov_reg(11, 2)                          # r11 = source
        self.code.bytes(b"\x31\xc0")                     # index = 0
        loop = self.label("case_loop")
        lower_path = self.label("case_lower")
        store = self.label("case_store")
        done = self.label("case_done")
        self.code.label(loop)
        self.code.bytes(b"\x41\x0f\xb6\x0c\x03")       # movzx ecx, [r11+rax]
        self.code.bytes(b"\x85\xc9")                     # test ecx, ecx
        self.code.conditional_jump(0x84, done)            # je: end of text
        self.code.bytes(b"\x41\x83\xf8\x00")            # cmp r8d, 0
        self.code.conditional_jump(0x85, lower_path)      # jne: lower mode
        self.code.bytes(b"\x83\xf9\x61")                 # cmp ecx, 'a'
        self.code.conditional_jump(0x82, store)           # jb: keep
        self.code.bytes(b"\x83\xf9\x7a")                 # cmp ecx, 'z'
        self.code.conditional_jump(0x87, store)           # ja: keep
        self.code.bytes(b"\x83\xe9\x20")                 # sub ecx, 32
        self.code.jump(store)
        self.code.label(lower_path)
        self.code.bytes(b"\x83\xf9\x41")                 # cmp ecx, 'A'
        self.code.conditional_jump(0x82, store)           # jb: keep
        self.code.bytes(b"\x83\xf9\x5a")                 # cmp ecx, 'Z'
        self.code.conditional_jump(0x87, store)           # ja: keep
        self.code.bytes(b"\x83\xc1\x20")                 # add ecx, 32
        self.code.label(store)
        self.code.bytes(b"\x41\x88\x0c\x02")            # mov [r10+rax], cl
        self.code.bytes(b"\x48\xff\xc0")                 # ++rax
        self.code.bytes(b"\x48\x3d\xff\x00\x00\x00")   # cmp rax, 255
        self.code.conditional_jump(0x82, loop)            # jb: continue
        self.code.label(done)
        self.code.bytes(b"\x41\xc6\x04\x02\x00")       # [r10+rax] = 0
        self.code.mov_reg(0, 10)                          # rax = destination
        self.code.bytes(b"\xc3")

    def _emit_string_helpers(self) -> None:
        """strlen / copy / append over 256-byte text buffers in .data."""
        self.code.label("function:anvil_str_len")
        self.code.bytes(b"\x31\xc0")                    # xor eax, eax
        scan = self.label("str_len_scan")
        reached = self.label("str_len_done")
        self.code.label(scan)
        self.code.bytes(b"\x80\x39\x00")               # cmp byte [rcx], 0
        self.code.conditional_jump(0x84, reached)
        self.code.bytes(b"\x48\xff\xc0\x48\xff\xc1")  # inc rax; inc rcx
        self.code.jump(scan)
        self.code.label(reached)
        self.code.bytes(b"\xc3")

        self.code.label("function:anvil_str_copy")
        self.code.mov_reg(10, 1)                         # r10 = dst
        self.code.mov_reg(11, 2)                         # r11 = src
        self.code.mov_reg(1, 11)                         # rcx = src
        self.code.call("function:anvil_str_len")         # rax = length
        overflow_copy = self.label("str_copy_overflow")
        done_copy = self.label("str_copy_done")
        loop_copy = self.label("str_copy_loop")
        self.code.bytes(b"\x48\x3d\xff\x00\x00\x00")  # cmp rax, 255
        self.code.conditional_jump(0x87, overflow_copy)  # ja: too long
        self.code.mov_reg(9, 0)                          # r9 = length
        self.code.mov_reg(8, 9)                          # r8 = original length
        self.code.label(loop_copy)
        self.code.bytes(b"\x4d\x85\xc9")               # test r9, r9
        self.code.conditional_jump(0x84, done_copy)
        self.code.bytes(b"\x41\x0f\xb6\x03")          # movzx eax, byte [r11]
        self.code.bytes(b"\x41\x88\x02")               # mov byte [r10], al
        self.code.bytes(b"\x49\xff\xc2\x49\xff\xc3\x49\xff\xc9")
        self.code.jump(loop_copy)
        self.code.label(done_copy)
        self.code.bytes(b"\x41\xc6\x02\x00")          # store terminator
        self.code.bytes(b"\x4c\x89\xd0")               # rax = r10 (end)
        self.code.bytes(b"\x4c\x29\xc0")               # rax -= r8: original dst
        self.code.bytes(b"\xc3")
        self.code.label(overflow_copy)
        self.emit_runtime_error("Anvil text is limited to 255 characters\n")

        self.code.label("function:anvil_str_append")
        self.code.bytes(b"\x48\x83\xec\x28")           # locals
        self.code.mov_reg(10, 2)                         # r10 = src
        self.code.mov_reg(9, 1)                          # r9 = dst
        self.code.call("function:anvil_str_len")         # rax = len(dst)
        self.code.bytes(b"\x4b\x8d\x0c\x01")           # lea rcx, [r9+rax] = dst+len
        self.code.mov_reg(2, 10)                         # rdx = src
        self.code.call("function:anvil_str_copy")        # copy src at dst+len
        self.code.mov_reg(0, 9)                          # rax = dst
        self.code.bytes(b"\x48\x83\xc4\x28\xc3")      # add rsp,0x28; ret

    def _emit_text_helper(self) -> None:
        """Write RDX bytes starting at RCX to stdout (no newline)."""
        self.code.label("function:anvil_print_text")
        self.code.bytes(b"\x48\x83\xec\x58")            # shadow space, aligned
        self.code.bytes(b"\x48\x89\x4c\x24\x30")        # save buffer pointer
        self.code.bytes(b"\x48\x89\x54\x24\x38")        # save length
        self.code.mov_imm(1, -11)                          # STD_OUTPUT_HANDLE
        self.code.rip_call_import("GetStdHandle")
        self.code.bytes(b"\x48\x89\xc1")                  # rcx = handle
        self.code.bytes(b"\x48\x8b\x54\x24\x30")        # rdx = buffer
        self.code.bytes(b"\x44\x8b\x44\x24\x38")        # r8d = length
        self.code.bytes(b"\x4c\x8d\x4c\x24\x28")        # r9 = &written
        self.code.bytes(b"\x48\xc7\x44\x24\x20\x00\x00\x00\x00")  # overlapped = NULL
        self.code.rip_call_import("WriteFile")
        self.code.bytes(b"\x48\x83\xc4\x58\xc3")        # add rsp,0x58; ret

    def generate(self) -> bytes:
        if any(node.kind == "scene" for node in self.top):
            return self._generate_window()
        calls = [node for node in self.top if node.kind == "call"]
        if any(node.kind not in ("call", "seed", "set") for node in self.top):
            unsupported = next(node for node in self.top if node.kind not in ("call", "seed", "set"))
            raise CompileError(
                f"{unsupported.source or self.path}:{unsupported.line}: top-level configuration is not implemented by the native x64 backend yet"
            )
        from compiler.modules import reachable_functions
        for name, fn in reachable_functions(self.functions, self.top, graphical=False):
            self._emit_function(name, fn)
        # Top-level `set` statements seed globals before main runs, in source order.
        setup = [node for node in self.top if node.kind in ("seed", "set")]
        if setup:
            self._emit_function("native:console_setup", Node("function", 1, body=setup))
        if calls:
            # Any number of top-level calls, in source order. A call to main has
            # its return printed (unless main only talks); other calls discard it,
            # exactly like the C backend's entry.
            main_body = self.functions["main"].body if "main" in self.functions else []
            main_kinds = set(_walk_native_kinds(main_body)) if main_body else set()
            quiet_main = (
                "say" in main_kinds or "write" in main_kinds or "ask" in main_kinds
            ) and "output" not in main_kinds
            body = []
            for call in calls:
                target = self.functions.get(call.name)
                if target is None:
                    raise CompileError(
                        f"{call.source or self.path}:{call.line}: unknown function {call.name!r}"
                    )
                arguments = (", " + call.value) if call.value.strip() else ""
                if call.name == "main" and not quiet_main:
                    body.append(Node("say", call.line, value=f"call fn(main{arguments})", source=call.source))
                else:
                    body.append(Node("call", call.line, name=call.name, value=call.value, source=call.source))
            self._emit_function("native:entry_main", Node(
                "function", calls[0].line, name="native:entry_main", source=calls[0].source,
                body=body,
            ))
        self._math.emit_pending()
        self._emit_print_helper()
        if self._needs_text_helper:
            self._emit_text_helper()
        if self._needs_input_helper:
            self._emit_input_helper()
        if self._needs_string_helpers:
            self._emit_string_helpers()
        if self._needs_case_helper:
            self._emit_case_helper()
        if self._needs_trim_helper:
            self._emit_trim_helper()
        if self._needs_char_at_helper:
            self._emit_char_at_helper()
        if self._needs_mid_helper:
            self._emit_mid_helper()
        if self._needs_contains_helper:
            self._emit_contains_helper()
        if self._needs_edge_helpers:
            self._emit_edge_helpers()
        if self._needs_compare_helper:
            self._emit_compare_helper()
        if self._needs_chr_error:
            self._emit_chr_error()
        if self._needs_parse_number:
            self._emit_parse_number_helper()
        if self._needs_equal_helper:
            self._emit_equal_helper()
        if self._needs_read_line:
            self._emit_read_line_helper()
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
        # The implicit-main path prints main's numeric return; a say-only main
        # must not trail a stray "0". Explicit top-level calls print inside
        # native:entry_main instead, so they skip this trailing print.
        main_kinds = (
            set(_walk_native_kinds(self.functions["main"].body))
            if "main" in self.functions
            else set()
        )
        text_only = (
            "say" in main_kinds or "write" in main_kinds or "ask" in main_kinds
        ) and "output" not in main_kinds
        if not calls and main_kinds and not text_only:
            self.code.mov_imm(1, 1)  # append the newline like output always did
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
