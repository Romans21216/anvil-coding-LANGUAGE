"""Expression parsing and Anvil-to-C expression lowering."""

from __future__ import annotations

import json
from contextvars import ContextVar
import math
import pathlib
import re

from compiler.common import (
    CompileError,
    KEY_CODES,
    Node,
    array_code,
    array_size,
    c_name,
    variable_code,
)

MAX_EXPRESSION_DEPTH = 64
_PARSE_DEPTH = ContextVar("anvil_expression_parse_depth", default=0)


def validate_expression_depth(source, path, line):
    depth, quoted, escaped = 0, False, False
    for char in source:
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted:
            if char == "(":
                depth += 1
                if depth > MAX_EXPRESSION_DEPTH:
                    raise CompileError(f"{path}:{line}: expression nesting exceeds {MAX_EXPRESSION_DEPTH} levels")
            elif char == ")":
                depth -= 1


TOKEN = re.compile(
    r"""\s*(?:([0-9]+(?:\.[0-9]*)?(?:[eE][+-]?[0-9]+)?)|("(?:\\.|[^"\\])*")|"""
    r"""(var\([A-Za-z_][\w-]*\))|(local\([A-Za-z_][\w-]*\))|"""
    r"""(<=|>=|!=|==|[(),+\-*/%=<>])|([A-Za-z_][\w-]*))"""
)

BUILTINS = {
    "time": (0, 0),
    "delta": (0, 0),
    "rnd": (2, 2),
    "noise": (3, 3),
    "fbm": (6, 6),
    "floor": (1, 1),
    "ceil": (1, 1),
    "sqrt": (1, 1),
    "sin": (1, 1),
    "cos": (1, 1),
    "abs": (1, 1),
    "min": (2, 2),
    "max": (2, 2),
    "pressed": (1, 1),
    "held": (1, 1),
    "mouse_x": (0, 0),
    "mouse_y": (0, 0),
    "mouse_pressed": (1, 1),
    "mouse_held": (1, 1),
    "mouse_wheel": (0, 0),
    "image_load": (1, 1),
    "image_width": (1, 1),
    "image_height": (1, 1),
    "image_destroy": (1, 1),
    "image_draw": (3, 3),
    "image_draw_scaled": (5, 5),
    "receive": (0, 0),
    "body_create": (4, 4),
    "body_create_box": (5, 5),
    "body_destroy": (1, 1),
    "body_active": (1, 1),
    "body_x": (1, 1),
    "body_y": (1, 1),
    "body_vx": (1, 1),
    "body_vy": (1, 1),
    "body_set_velocity": (3, 3),
    "body_force": (3, 3),
    "body_restitution": (2, 2),
    "body_friction": (2, 2),
    "body_collision": (2, 2),
    "physics_capacity": (1, 1),
    "physics_gravity": (2, 2),
    "physics_step": (0, 0),
    "ray_backend": (1, 1),
    "ray_backend_available": (1, 1),
}

BUILTIN_C_NAMES = {
    "time": "anvil_time",
    "delta": "anvil_delta",
    "rnd": "anvil_rnd",
    "noise": "anvil_noise",
    "fbm": "anvil_fbm",
    "pressed": "anvil_pressed",
    "held": "anvil_held",
    "mouse_x": "anvil_mouse_x",
    "mouse_y": "anvil_mouse_y",
    "mouse_pressed": "anvil_mouse_pressed",
    "mouse_held": "anvil_mouse_held",
    "mouse_wheel": "anvil_mouse_wheel",
    "image_load": "anvil_image_load",
    "image_width": "anvil_image_width",
    "image_height": "anvil_image_height",
    "image_destroy": "anvil_image_destroy",
    "image_draw": "anvil_image_draw",
    "image_draw_scaled": "anvil_image_draw_scaled",
    "receive": "anvil_net_receive",
    "abs": "fabs",
    "min": "fmin",
    "max": "fmax",
    "body_create": "anvil_body_create",
    "body_create_box": "anvil_body_create_box",
    "body_destroy": "anvil_body_destroy",
    "body_active": "anvil_body_active",
    "body_x": "anvil_body_x",
    "body_y": "anvil_body_y",
    "body_vx": "anvil_body_vx",
    "body_vy": "anvil_body_vy",
    "body_set_velocity": "anvil_body_set_velocity",
    "body_force": "anvil_body_force",
    "body_restitution": "anvil_body_restitution",
    "body_friction": "anvil_body_friction",
    "body_collision": "anvil_body_collision",
    "physics_gravity": "anvil_physics_gravity",
    "physics_capacity": "anvil_physics_capacity",
    "physics_step": "anvil_physics_step",
    "ray_backend": "anvil_ray_backend",
    "ray_backend_available": "anvil_ray_backend_available",
}

BUILTIN_STRING_ARGUMENTS = {
    "ray_backend",
    "ray_backend_available",
    "mouse_pressed",
    "mouse_held",
    "image_load",
}


class ExpressionParser:
    """Parse the supported expression grammar and emit safe C expressions."""

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

    def __init__(
        self,
        path: pathlib.Path,
        line: int,
        source: str,
        functions: dict[str, Node] | None,
        scope: Node | None = None,
        arrays: dict[str, int] | None = None,
    ):
        self.path, self.line, self.source, self.functions = (
            path,
            line,
            source,
            functions,
        )
        self.scope = scope
        self.arrays = arrays or {}
        validate_expression_depth(source, path, line)
        self.tokens: list[tuple[str, str]] = []
        pos = 0
        while pos < len(source):
            call_prefix = re.match(r"\s*call\s+fn\(|\s*array\(", source[pos:])
            if call_prefix:
                is_call = "call" in call_prefix.group(0)
                call_start = pos + call_prefix.start()
                scan = pos + call_prefix.end()
                depth, quoted, escaped = 1, False, False
                while scan < len(source) and depth:
                    ch = source[scan]
                    if escaped:
                        escaped = False
                    elif ch == "\\" and quoted:
                        escaped = True
                    elif ch == '"':
                        quoted = not quoted
                    elif not quoted and ch == "(":
                        depth += 1
                    elif not quoted and ch == ")":
                        depth -= 1
                    scan += 1
                if depth:
                    token_name = "function call" if is_call else "array access"
                    raise CompileError(f"{path}:{line}: unclosed {token_name}")
                self.tokens.append(
                    ("call" if is_call else "array", source[call_start:scan])
                )
                pos = scan
                continue
            match = TOKEN.match(source, pos)
            if not match:
                raise CompileError(
                    f"{path}:{line}: invalid expression near {source[pos:pos+20]!r}"
                )
            number, string, variable, local, op, word = match.groups()
            kind, value = (
                ("number", number)
                if number
                else (
                    ("string", string)
                    if string
                    else (
                        ("variable", variable)
                        if variable
                        else (
                            ("local", local)
                            if local
                            else ("op", op) if op else ("word", word)
                        )
                    )
                )
            )
            self.tokens.append((kind, value))
            pos = match.end()
        self.index = 0

    def peek(self, value: str | None = None) -> bool:
        return self.index < len(self.tokens) and (
            value is None or self.tokens[self.index][1] == value
        )

    def take(self) -> tuple[str, str]:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def expect(self, value: str) -> None:
        if not self.peek(value):
            raise CompileError(
                f"{self.path}:{self.line}: expected {value!r} in expression"
            )
        self.index += 1

    def require_number(self, value: tuple[str, str]) -> str:
        code, kind = value
        if kind != "number":
            raise CompileError(
                f"{self.path}:{self.line}: expected a number, got a string"
            )
        return code

    def checked_number(self, code: str) -> str:
        return (
            f"anvil_check_number(({code}), {json.dumps(str(self.path))}, "
            f"{self.line})"
        )

    def require_string(self, value: tuple[str, str]) -> str:
        code, kind = value
        if kind != "string":
            raise CompileError(
                f"{self.path}:{self.line}: expected a string, got a number"
            )
        return code

    def parse(self, minimum: int = 0) -> tuple[str, str]:
        depth = _PARSE_DEPTH.get() + 1
        if depth > MAX_EXPRESSION_DEPTH:
            raise CompileError(f"{self.path}:{self.line}: expression nesting exceeds {MAX_EXPRESSION_DEPTH} parser levels")
        token = _PARSE_DEPTH.set(depth)
        try:
            return self._parse_impl(minimum)
        finally:
            _PARSE_DEPTH.reset(token)

    def _parse_impl(self, minimum: int = 0) -> tuple[str, str]:
        if not self.peek():
            raise CompileError(f"{self.path}:{self.line}: expected an expression")
        kind, value = self.take()
        if kind == "number":
            if not math.isfinite(float(value)):
                raise CompileError(
                    f"{self.path}:{self.line}: numeric literal must be finite"
                )
            left = (
                value if any(char in value for char in ".eE") else value + ".0",
                "number",
            )
        elif kind == "string":
            left = (value, "string")
        elif kind == "variable":
            name = value[4:-1]
            left = (variable_code(name, self.scope), "number")
        elif kind == "local":
            name = value[6:-1]
            if not self.scope or name not in self.scope.locals:
                raise CompileError(
                    f"{self.path}:{self.line}: unknown local variable {name!r}"
                )
            left = (c_name(self.scope.name + "__" + name), "number")
        elif kind == "array":
            contents = value[value.index("array(") + 6 : -1]
            parts = split_args(contents)
            if len(parts) != 2 or not re.fullmatch(r"[A-Za-z_][\w-]*", parts[0]):
                raise CompileError(
                    f"{self.path}:{self.line}: array access expects array(name, index)"
                )
            name = parts[0]
            size = array_size(name, self.scope, self.arrays)
            if size is None:
                raise CompileError(f"{self.path}:{self.line}: unknown array {name!r}")
            index_expr = ExpressionParser(
                self.path, self.line, parts[1], self.functions, self.scope, self.arrays
            ).compile()
            left = (
                f"anvil_array_get({array_code(name, self.scope)}, {size}, "
                f"{index_expr}, "
                f"{json.dumps(str(self.path))}, {self.line})",
                "number",
            )
        elif kind == "call":
            contents = value[value.index("fn(") + 3 : -1]
            parts = split_args(contents)
            name, raw_args = parts[0], parts[1:]
            if self.functions is not None and name not in self.functions:
                raise CompileError(
                    f"{self.path}:{self.line}: unknown function {name!r}"
                )
            if self.functions is not None and len(raw_args) != len(
                self.functions[name].params
            ):
                expected = len(self.functions[name].params)
                raise CompileError(
                    f"{self.path}:{self.line}: function {name!r} expects "
                    f"{expected} argument(s), got {len(raw_args)}"
                )
            args = [
                ExpressionParser(
                    self.path, self.line, arg, self.functions, self.scope, self.arrays
                ).compile()
                for arg in raw_args
            ]
            left = (c_name(name) + "(" + ", ".join(args) + ")", "number")
        elif kind == "op" and value in ("+", "-"):
            left = (f"({value}{self.require_number(self.parse(7))})", "number")
        elif kind == "op" and value == "(":
            left = self.parse()
            self.expect(")")
        elif kind == "word" and value in ("true", "false"):
            left = ("1.0" if value == "true" else "0.0", "number")
        elif kind == "word" and value in ("and", "or"):
            raise CompileError(
                f"{self.path}:{self.line}: operator {value!r} needs a left operand"
            )
        elif kind == "word" and value in KEY_CODES:
            left = ("ANVIL_KEY_" + value, "number")
        elif kind == "word" and value in BUILTINS:
            self.expect("(")
            args = []
            if not self.peek(")"):
                while True:
                    argument = self.parse()
                    if value in BUILTIN_STRING_ARGUMENTS:
                        args.append(self.require_string(argument))
                    else:
                        args.append(self.require_number(argument))
                    if not self.peek(","):
                        break
                    self.take()
            self.expect(")")
            low, high = BUILTINS[value]
            if not low <= len(args) <= high:
                expected = str(low) if low == high else f"{low}..{high}"
                raise CompileError(
                    f"{self.path}:{self.line}: {value}() expects {expected} "
                    f"argument(s), got {len(args)}"
                )
            name = BUILTIN_C_NAMES.get(value, value)
            call = f"{name} ( {', '.join(args)} )" if args else f"{name} ( )"
            if value in BUILTINS:
                call = self.checked_number(call)
            left = (call, "number")
        elif kind == "word":
            raise CompileError(f"{self.path}:{self.line}: unknown name {value!r}")
        else:
            raise CompileError(
                f"{self.path}:{self.line}: unexpected token {value!r} in expression"
            )

        while self.peek():
            operator = self.tokens[self.index][1]
            precedence = self.PRECEDENCE.get(operator, -1)
            if precedence < minimum:
                break
            self.take()
            if not self.peek() or self.peek(")") or self.peek(","):
                raise CompileError(
                    f"{self.path}:{self.line}: operator {operator!r} needs "
                    "a right operand"
                )
            left_code = self.checked_number(self.require_number(left))
            right = self.require_number(self.parse(precedence + 1))
            if operator == "/":
                left = (
                    f"anvil_divide({left_code}, {right}, "
                    f"{json.dumps(str(self.path))}, {self.line})",
                    "number",
                )
            elif operator == "%":
                left = (
                    self.checked_number(
                        f"fmod({left_code}, {self.checked_number(right)})"
                    ),
                    "number",
                )
            elif operator in ("and", "or"):
                c_operator = "&&" if operator == "and" else "||"
                left = (
                    f"({left_code} {c_operator} {self.checked_number(right)})",
                    "number",
                )
            elif operator in ("=", "==", "!=", "<", "<=", ">", ">="):
                c_operator = "==" if operator == "=" else operator
                left = (
                    f"({left_code} {c_operator} {self.checked_number(right)})",
                    "number",
                )
            else:
                left = (
                    self.checked_number(
                        f"({left_code} {operator} {self.checked_number(right)})"
                    ),
                    "number",
                )
        return left

    def compile(self, expected: str = "number") -> str:
        result = self.parse()
        if self.peek():
            raise CompileError(
                f"{self.path}:{self.line}: unexpected token "
                f"{self.tokens[self.index][1]!r} in expression"
            )
        code, actual = result
        if actual != expected:
            raise CompileError(
                f"{self.path}:{self.line}: expected {expected}, got {actual}"
            )
        return code


def split_args(text: str) -> list[str]:
    result, start, depth, quoted, escaped = [], 0, 0, False, False
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
        elif ch == "\\" and quoted:
            escaped = True
        elif ch == '"':
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
        elif not quoted and depth == 0 and ch == ",":
            result.append(text[start:i].strip())
            start = i + 1
    tail = text[start:].strip()
    if tail or result:
        result.append(tail)
    return result


def expr(
    path: pathlib.Path,
    line: int,
    source: str,
    functions: dict[str, Node] | None = None,
    expected: str = "number",
    scope: Node | None = None,
    arrays: dict[str, int] | None = None,
) -> str:
    source = source.strip()
    if source.startswith("compute(") and source.endswith(")"):
        source = source[8:-1]
    return ExpressionParser(path, line, source, functions, scope, arrays).compile(
        expected
    )
