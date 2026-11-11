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
MAX_STRINGS_PER_EXPRESSION = 200

# Join sites need distinct scratch buffers across the WHOLE program: a function
# that returns `a & b` and its caller's `"[" & call fn(..) & "]"` used to share
# anvil_str_scratch[0] and clobbered each other. Number slots live in the upper
# half (128..255) so they never collide with a cat slot (0..127).
_CAT_SLOT_COUNTER = 0


def _next_join_slots() -> tuple[int, int, int]:
    global _CAT_SLOT_COUNTER
    slot = _CAT_SLOT_COUNTER
    _CAT_SLOT_COUNTER += 1
    return slot % 128, 128 + (slot * 2) % 126, 128 + (slot * 2 + 1) % 126
_PARSE_DEPTH = ContextVar("anvil_expression_parse_depth", default=0)
# Which variables hold text. Set by the code generators before lowering; the
# compiler is single-threaded, so a module-level registry is safe.
STRING_VARIABLES: set[str] = set()
# List names declared with `list <name>`; `count(name)` reads their counter.
LISTS: set[str] = set()


def set_string_variables(names) -> None:
    STRING_VARIABLES.clear()
    STRING_VARIABLES.update(names)


def split_amp(text: str) -> list[str]:
    """Split on top-level ampersands, respecting quotes and parentheses."""
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
        elif not quoted and depth == 0 and ch == "&":
            result.append(text[start:i].strip())
            start = i + 1
    tail = text[start:].strip()
    if tail or result:
        result.append(tail)
    return result


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
    r"""(<=|>=|!=|==|[(),+\-*/%&=<>])|([A-Za-z_][\w-]*))"""
)

BUILTINS = {
    "time": (0, 0),
    "delta": (0, 0),
    "rnd": (2, 2),
    "noise": (3, 3),
    "fbm": (6, 6),
    "floor": (1, 1),
    "round": (1, 1),
    "ceil": (1, 1),
    "sqrt": (1, 1),
    "sin": (1, 1),
    "cos": (1, 1),
    "abs": (1, 1),
    "len": (1, 1),
    "upper": (1, 1),
    "lower": (1, 1),
    "ord": (1, 1),
    "chr": (1, 1),
    "trim": (1, 1),
    "number": (1, 1),
    "char": (2, 2),
    "contains": (2, 2),
    "mid": (3, 3),
    "left": (2, 2),
    "right": (2, 2),
    "starts_with": (2, 2),
    "ends_with": (2, 2),
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
    "round": "round",
    "len": "(double)strlen",
    "upper": "anvil_text_upper",
    "lower": "anvil_text_lower",
    "chr": "anvil_text_chr",
    "ord": "anvil_text_ord",
    "trim": "anvil_text_trim",
    "number": "anvil_text_to_number",
    "char": "anvil_text_char",
    "contains": "anvil_str_contains",
    "mid": "anvil_text_mid",
    "left": "anvil_text_left",
    "right": "anvil_text_right",
    "starts_with": "anvil_str_starts",
    "ends_with": "anvil_str_ends",
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

BUILTIN_TEXT_RETURNING = {"upper", "lower", "chr", "trim", "char", "mid", "left", "right"}

# Common names from other languages, mapped to the Anvil spelling. A beginner
# who types `random(1, 10)` gets a "did you mean rnd" instead of a variable hint.
NAME_SUGGESTIONS = {
    "random": "rnd(low, high)",
    "rand": "rnd(low, high)",
    "print": "say",
    "println": "say",
    "puts": "say",
    "length": "len(text)",
    "str": "text(value) or use & to join",
    "int": "round(value) or floor(value)",
    "float": "a plain number, e.g. 1.5",
    "string": "text, written with double quotes",
    "input": "ask var(x)",
    "readline": "ask var(x)",
    "toupper": "upper(text)",
    "tolower": "lower(text)",
}

BUILTIN_ARG_KINDS = {
    "char": ("string", "number"),
    "mid": ("string", "number", "number"),
    "left": ("string", "number"),
    "right": ("string", "number"),
}

BUILTIN_STRING_ARGUMENTS = {
    "contains",
    "starts_with",
    "ends_with",
    "number",
    "trim",
    "ord",
    "upper",
    "lower",
    "len",
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
        "&": 5,
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
        self._cat_index = 0
        validate_expression_depth(source, path, line)
        self.tokens: list[tuple[str, str]] = []
        pos = 0
        while pos < len(source):
            call_prefix = re.match(r"\s*call\s+fn\(|\s*array\(|\s*count\(", source[pos:])
            if call_prefix:
                is_call = "call" in call_prefix.group(0)
                is_count = "count(" in call_prefix.group(0)
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
                    token_name = (
                        "function call"
                        if is_call
                        else ("count()" if is_count else "array access")
                    )
                    raise CompileError(f"{path}:{line}: unclosed {token_name}")
                token_kind = "call" if is_call else ("count" if is_count else "array")
                self.tokens.append((token_kind, source[call_start:scan]))
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
            if name in STRING_VARIABLES:
                # A text parameter holds its pointer directly; a text global
                # lives in the generated anvil_str_<name> buffer.
                is_param = self.scope is not None and name in self.scope.params
                symbol = (
                    c_name(self.scope.name + "__" + name)
                    if is_param
                    else f"anvil_str_{c_name(name)}"
                )
                left = (symbol, "string")
            else:
                left = (variable_code(name, self.scope), "number")
        elif kind == "local":
            name = value[6:-1]
            if not self.scope or name not in self.scope.locals:
                raise CompileError(
                    f"{self.path}:{self.line}: unknown local variable {name!r}"
                )
            left = (c_name(self.scope.name + "__" + name), "number")
        elif kind == "count":
            contents = value[value.index("count(") + 6 : -1].strip()
            if not re.fullmatch(r"[A-Za-z_][\w-]*", contents):
                raise CompileError(
                    f"{self.path}:{self.line}: count() expects a list name"
                )
            if contents not in LISTS:
                raise CompileError(
                    f"{self.path}:{self.line}: unknown list {contents!r}; "
                    f"declare it with list {contents}"
                )
            left = (variable_code(f"{contents}__count", self.scope), "number")
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
            target = self.functions[name] if self.functions is not None else None
            text_params = getattr(target, "text_params", set()) if target else set()
            args = []
            for index, arg in enumerate(raw_args):
                param = (
                    target.params[index]
                    if target is not None and index < len(target.params)
                    else None
                )
                expected = "string" if param in text_params else "number"
                args.append(
                    ExpressionParser(
                        self.path, self.line, arg, self.functions, self.scope, self.arrays
                    ).compile(expected)
                )
            result_kind = (
                "string"
                if getattr(self.functions[name], "returns_text", False)
                else "number"
            )
            left = (c_name(name) + "(" + ", ".join(args) + ")", result_kind)
        elif kind == "op" and value in ("+", "-"):
            left = (f"({value}{self.require_number(self.parse(7))})", "number")
        elif kind == "op" and value == "(":
            left = self.parse()
            self.expect(")")
        elif kind == "word" and value == "not":
            # Prefix `not` binds looser than comparisons so `not a = b` reads as
            # "a is not equal to b", but tighter than and/or.
            operand = self.require_number(self.parse(3))
            left = (f"((double)(!({self.checked_number(operand)})))", "number")
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
            arg_kinds = BUILTIN_ARG_KINDS.get(value)
            if not self.peek(")"):
                while True:
                    argument = self.parse()
                    if arg_kinds is not None:
                        kind = arg_kinds[min(len(args), len(arg_kinds) - 1)]
                        if kind == "string":
                            args.append(self.require_string(argument))
                        else:
                            args.append(self.require_number(argument))
                    elif value in BUILTIN_STRING_ARGUMENTS:
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
            if value in BUILTIN_TEXT_RETURNING:
                left = (call, "string")
            else:
                call = self.checked_number(call)
                left = (call, "number")
        elif kind == "word":
            hint = NAME_SUGGESTIONS.get(value.lower())
            if hint is not None:
                raise CompileError(
                    f"{self.path}:{self.line}: unknown name {value!r}; "
                    f"did you mean {hint}?"
                )
            raise CompileError(
                f"{self.path}:{self.line}: unknown name {value!r} "
                f"(variables are written var({value}))"
            )
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
            if operator == "&":
                # Text joining: either side may be a string or a number; the
                # buffer index keeps every intermediate value in its own slot.
                def as_text(operand, slot):
                    code, kind = operand
                    if kind == "string":
                        return code
                    return f"anvil_str_from_number({slot}, {self.checked_number(code)})"

                if self._cat_index + 2 > MAX_STRINGS_PER_EXPRESSION:
                    raise CompileError(
                        f"{self.path}:{self.line}: an expression may join at most "
                        f"{MAX_STRINGS_PER_EXPRESSION} values with &"
                    )
                cat_slot, left_slot, right_slot = _next_join_slots()
                left_text = as_text(left, left_slot)
                right_text = as_text(self.parse(precedence + 1), right_slot)
                left = (
                    f"anvil_str_cat(anvil_str_scratch[{cat_slot}], "
                    f"{left_text}, {right_text}, "
                    f"{json.dumps(str(self.path))}, {self.line})",
                    "string",
                )
                self._cat_index += 1
                continue
            if operator in ("=", "==", "!=", "<", "<=", ">", ">=") and left[1] == "string":
                right = self.parse(precedence + 1)
                right_code, right_kind = right
                if right_kind != "string":
                    raise CompileError(
                        f"{self.path}:{self.line}: cannot compare text with a number"
                    )
                c_operator = {
                    "=": "==", "==": "==", "!=": "!=",
                    "<": "<", "<=": "<=", ">": ">", ">=": ">=",
                }[operator]
                left = (
                    f"((strcmp({left[0]}, {right_code}) {c_operator} 0) "
                    f"? 1.0 : 0.0)",
                    "number",
                )
                continue
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
                # C's &&/|| yield int; the double cast keeps printed and stored
                # values numeric instead of an int reinterpreted as a double.
                left = (
                    f"(((double)(({left_code}) {c_operator} "
                    f"({self.checked_number(right)})) == 1.0) ? 1.0 : 0.0)",
                    "number",
                )
            elif operator in ("=", "==", "!=", "<", "<=", ">", ">="):
                c_operator = "==" if operator == "=" else operator
                # Comparisons are int in C; force the documented 1.0/0.0 doubles.
                left = (
                    f"(((double)(({left_code}) {c_operator} "
                    f"({self.checked_number(right)})) == 1.0) ? 1.0 : 0.0)",
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
