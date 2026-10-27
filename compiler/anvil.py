#!/usr/bin/env python3
"""Small ahead-of-time Anvil-to-C compiler. C is emitted as ordinary source."""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "anvil_runtime.c"
INCLUDE = ROOT / "runtime"


@dataclass
class Node:
    kind: str
    line: int
    value: str = ""
    name: str = ""
    body: list["Node"] = field(default_factory=list)
    otherwise: list["Node"] = field(default_factory=list)
    params: list[str] = field(default_factory=list)
    locals: set[str] = field(default_factory=set)
    local_arrays: dict[str, int] = field(default_factory=dict)
    local_array_lines: dict[str, int] = field(default_factory=dict)


class CompileError(Exception):
    pass


def c_name(name: str) -> str:
    return "anvil_" + re.sub(r"[^A-Za-z0-9_]", "_", name)


def variable_code(name: str, scope: Node | None = None) -> str:
    if scope and name in scope.params:
        return c_name(scope.name + "__" + name)
    return c_name(name)


def array_size(name: str, scope: Node | None, arrays: dict[str, int]) -> int | None:
    if scope is not None and name in scope.local_arrays:
        return scope.local_arrays[name]
    return arrays.get(name)


def array_code(name: str, scope: Node | None) -> str:
    if scope is not None and name in scope.local_arrays:
        return c_name(scope.name + "__" + name)
    return c_name(name)


RUNTIME_C_NAMES = {
    "anvil_run", "anvil_divide", "anvil_check_number", "anvil_set_scene3d", "anvil_camera_perspective", "anvil_clear",
    "anvil_rect", "anvil_circle", "anvil_line", "anvil_cube", "anvil_sphere",
    "anvil_plane", "anvil_text", "anvil_text_number", "anvil_time", "anvil_delta",
    "anvil_pressed", "anvil_held", "anvil_rnd", "anvil_seed", "anvil_noise",
    "anvil_fbm", "anvil_net_host", "anvil_net_join", "anvil_net_send",
    "anvil_net_receive", "anvil_net_close", "anvil_array_get", "anvil_array_set",
    "anvil_local_array_alloc", "anvil_local_array_free",
    "anvil_ray_backend", "anvil_ray_backend_available",
    "anvil_body_create", "anvil_body_create_box", "anvil_body_destroy", "anvil_body_active",
    "anvil_body_x", "anvil_body_y", "anvil_body_vx", "anvil_body_vy",
    "anvil_body_set_velocity", "anvil_body_force", "anvil_body_restitution",
    "anvil_body_friction",
    "anvil_body_collision", "anvil_physics_capacity", "anvil_physics_gravity",
    "anvil_physics_step",
}


def strip_comment(line: str) -> str:
    quoted = False
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
        elif ch == "\\" and quoted:
            escaped = True
        elif ch == '"':
            quoted = not quoted
        elif ch == "#" and not quoted:
            return line[:i]
    return line


def validate_port(path: pathlib.Path, line: int, text: str) -> None:
    try:
        port = int(text)
    except ValueError as exc:
        raise CompileError(f"{path}:{line}: invalid UDP port") from exc
    if not 1 <= port <= 65535:
        raise CompileError(f"{path}:{line}: UDP port must be between 1 and 65535")


def split_keyword(text: str, keyword: str) -> tuple[str, str] | None:
    """Split at a standalone keyword outside strings and parentheses."""
    depth, quoted, escaped = 0, False, False
    index = 0
    while index < len(text):
        ch = text[index]
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
        elif not quoted and depth == 0 and text.startswith(keyword, index):
            before_ok = index > 0 and text[index - 1].isspace()
            after = index + len(keyword)
            after_ok = after < len(text) and text[after].isspace()
            if before_ok and after_ok:
                return text[:index].strip(), text[after:].strip()
        index += 1
    return None


MAX_ARRAY_SIZE = 1_048_576
MAX_LOCAL_ARRAY_ELEMENTS = 8_192
MAX_ACTIVE_LOCAL_ARRAY_BYTES = 16 * 1024 * 1024


def parse(path: pathlib.Path, source: str) -> tuple[dict[str, Node], list[Node], set[str], dict[str, int]]:
    functions: dict[str, Node] = {}
    top: list[Node] = []
    variables: set[str] = set()
    arrays: dict[str, int] = {}
    variable_references: list[tuple[str, int, str | None]] = []
    local_references: list[tuple[str, int, str | None]] = []
    stack: list[tuple[list[Node], str, Node | None]] = [(top, "top", None)]
    for line_no, raw in enumerate(source.splitlines(), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        current_function = next((frame[2] for frame in reversed(stack)
                                 if frame[1] == "function"), None)
        for reference in re.finditer(r"var\(([A-Za-z_][\w-]*)\)", line):
            variable_references.append((reference.group(1), line_no,
                                        current_function.name if current_function else None))
        for reference in re.finditer(r"local\(([A-Za-z_][\w-]*)\)", line):
            local_references.append((reference.group(1), line_no,
                                     current_function.name if current_function else None))
        array_decl = re.fullmatch(r"array\s+([A-Za-z_][\w-]*)\s*\(\s*(\d+)\s*\)", line)
        if array_decl:
            name, raw_size = array_decl.groups()
            size = int(raw_size)
            if not 1 <= size <= MAX_ARRAY_SIZE:
                raise CompileError(f"{path}:{line_no}: array size must be between 1 and {MAX_ARRAY_SIZE}")
            if current_function is None:
                if len(stack) != 1:
                    raise CompileError(f"{path}:{line_no}: global arrays must be declared at top level")
                if name in arrays:
                    raise CompileError(f"{path}:{line_no}: duplicate array '{name}'")
                arrays[name] = size
            else:
                if name in current_function.local_arrays:
                    raise CompileError(f"{path}:{line_no}: duplicate local array '{name}' in function '{current_function.name}'")
                if sum(current_function.local_arrays.values()) + size > MAX_LOCAL_ARRAY_ELEMENTS:
                    raise CompileError(f"{path}:{line_no}: local arrays in a function may contain at most {MAX_LOCAL_ARRAY_ELEMENTS} elements total")
                current_function.local_arrays[name] = size
                current_function.local_array_lines[name] = line_no
            continue
        fn = re.fullmatch(r"fn\(([A-Za-z_][\w-]*)(?:\s*,\s*(.*))?\)", line)
        if fn:
            name = fn.group(1)
            if len(stack) != 1:
                raise CompileError(f"{path}:{line_no}: functions must be top-level")
            if name in functions:
                raise CompileError(f"{path}:{line_no}: duplicate function '{name}'")
            params = split_args(fn.group(2) or "")
            if any(not re.fullmatch(r"[A-Za-z_][\w-]*", param) for param in params):
                raise CompileError(f"{path}:{line_no}: function parameters must be identifiers")
            if len(params) != len(set(params)):
                raise CompileError(f"{path}:{line_no}: duplicate parameter in function '{name}'")
            node = Node("function", line_no, name=name, params=params)
            functions[name] = node
            stack.append((node.body, "function", node))
            continue
        if line == "else":
            if stack[-1][1] != "if":
                raise CompileError(f"{path}:{line_no}: 'else' must match an if")
            block = stack[-1][2]
            assert block is not None
            stack[-1] = (block.otherwise, "else", block)
            continue
        if line == "end":
            if len(stack) == 1:
                raise CompileError(f"{path}:{line_no}: unexpected 'end'")
            _, kind, _ = stack.pop()
            if kind not in ("function", "if", "else", "while", "for"):
                raise CompileError(f"{path}:{line_no}: mismatched block end")
            continue
        if line.startswith("if "):
            node = Node("if", line_no, value=line[3:].strip())
            stack[-1][0].append(node)
            stack.append((node.body, "if", node))
            continue
        if line == "while" or line.startswith("while "):
            condition = line[len("while "):].strip()
            if not condition:
                raise CompileError(f"{path}:{line_no}: while needs a condition")
            node = Node("while", line_no, value=condition)
            stack[-1][0].append(node)
            stack.append((node.body, "while", node))
            continue
        for_loop = re.fullmatch(
            r"for\s+local\(([A-Za-z_][\w-]*)\)\s*=\s*(.+)", line
        )
        if for_loop:
            if current_function is None:
                raise CompileError(f"{path}:{line_no}: for loops must be inside a function")
            loop_name, range_text = for_loop.groups()
            if loop_name in current_function.params:
                raise CompileError(f"{path}:{line_no}: for-loop variable cannot be a function parameter")
            if any(kind == "for" and block is not None and block.name == loop_name
                   for _, kind, block in stack):
                raise CompileError(f"{path}:{line_no}: nested for loops must use different local variables")
            range_parts = split_keyword(range_text, "to")
            if not range_parts:
                raise CompileError(f"{path}:{line_no}: for loop expects 'to' between its bounds")
            start_expr, end_and_step = range_parts
            step_parts = split_keyword(end_and_step, "step")
            if step_parts:
                end_expr, step_expr = step_parts
            else:
                end_expr, step_expr = end_and_step, "1"
            if not start_expr or not end_expr or not step_expr:
                raise CompileError(f"{path}:{line_no}: for loop needs start, end, and step expressions")
            current_function.locals.add(loop_name)
            node = Node("for", line_no, name=loop_name,
                        params=[start_expr, end_expr, step_expr])
            stack[-1][0].append(node)
            stack.append((node.body, "for", node))
            continue
        node = None
        if re.fullmatch(r"set\s+var\([A-Za-z_][\w-]*\)\s*=\s*null", line):
            # Cleanup after output is syntactic sugar; scalar values live in globals.
            continue
        match = re.fullmatch(r"set\s+local\(([A-Za-z_][\w-]*)\)\s*=\s*(.+)", line)
        if match:
            if current_function is None:
                raise CompileError(f"{path}:{line_no}: local variables must be declared inside a function")
            if match.group(1) in current_function.params:
                raise CompileError(f"{path}:{line_no}: local variable {match.group(1)!r} conflicts with a function parameter")
            current_function.locals.add(match.group(1))
            node = Node("local_set", line_no, match.group(2), match.group(1))
        if node is None:
            match = re.fullmatch(r"set\s+array\(([A-Za-z_][\w-]*)\s*,\s*(.*)\)\s*=\s*(.+)", line)
            if match:
                if current_function is None:
                    raise CompileError(f"{path}:{line_no}: array writes must be inside a function")
                array_name, index_expr, value_expr = match.groups()
                node = Node("array_set", line_no, value_expr, array_name, params=[index_expr])
        match = re.fullmatch(r"set\s+var\(([A-Za-z_][\w-]*)\)\s*=\s*(.+)", line)
        if node is None and match:
            node = Node("set", line_no, match.group(2), match.group(1))
            if current_function is None or match.group(1) not in current_function.params:
                variables.add(match.group(1))
        if node is None:
            match = re.fullmatch(r"(add|sub)\s+local\(([A-Za-z_][\w-]*)\)\s+(.+)", line)
            if match:
                if current_function is None:
                    raise CompileError(f"{path}:{line_no}: local variables can only be changed inside a function")
                if match.group(2) in current_function.params:
                    raise CompileError(f"{path}:{line_no}: local variable {match.group(2)!r} conflicts with a function parameter")
                current_function.locals.add(match.group(2))
                node = Node("local_" + match.group(1), line_no, match.group(3), match.group(2))
        if node is None:
            match = re.fullmatch(r"(add|sub)\s+var\(([A-Za-z_][\w-]*)\)\s+(.+)", line)
            if match:
                node = Node(match.group(1), line_no, match.group(3), match.group(2))
                if current_function is None or match.group(2) not in current_function.params:
                    variables.add(match.group(2))
        if node is None:
            match = re.fullmatch(r"output\s+(.+)", line)
            if match:
                node = Node("output", line_no, match.group(1))
        if node is None:
            match = re.fullmatch(r"call\s+fn\((.*)\)", line)
            if match:
                call_args = split_args(match.group(1))
                if not call_args or not re.fullmatch(r"[A-Za-z_][\w-]*", call_args[0]):
                    raise CompileError(f"{path}:{line_no}: expected a function name in call")
                node = Node("call", line_no, value=", ".join(call_args[1:]),
                            name=call_args[0])
        if node is None:
            if re.fullmatch(r"scene\s+(?:2d|3d)", line):
                node = Node("scene", line_no, value=line.split()[1])
            elif line.startswith("camera perspective "):
                node = Node("camera", line_no, value=line[len("camera perspective "):])
            elif re.fullmatch(r"camera fov\(.*\)", line):
                node = Node("camera_fov", line_no, value=line[len("camera fov("):-1])
            elif re.fullmatch(r"camera control\(.*\)", line):
                node = Node("camera_control", line_no, value=line[len("camera control("):-1])
            elif line.startswith("clear rgba("):
                node = Node("clear", line_no, value=line[len("clear rgba"):])
            elif line.startswith("display "):
                node = Node("display", line_no, value=line[len("display "):])
            elif (m := re.fullmatch(r"net\s+host\((\d+)\)", line)):
                validate_port(path, line_no, m.group(1))
                node = Node("net_host", line_no, value=m.group(1))
            elif (m := re.fullmatch(r'net\s+join\(("(?:\\.|[^"\\])*")\s*,\s*(\d+)\)', line)):
                validate_port(path, line_no, m.group(2))
                node = Node("net_join", line_no, value=m.group(1) + "," + m.group(2))
            elif line.startswith("net send(") and line.endswith(")"):
                node = Node("net_send", line_no, value=line[len("net send("):-1])
            elif line.startswith("seed(") and line.endswith(")"):
                node = Node("seed", line_no, value=line[5:-1])
        if node is None:
            raise CompileError(f"{path}:{line_no}: unsupported statement: {line}")
        stack[-1][0].append(node)
    if len(stack) != 1:
        _, kind, node = stack[-1]
        raise CompileError(f"{path}:{node.line if node else 1}: unclosed {kind}; expected 'end'")
    if not functions:
        raise CompileError(f"{path}: define at least one fn(name) function")
    for name, line_no, function_name in variable_references:
        fn = functions.get(function_name) if function_name else None
        if name not in variables and (fn is None or name not in fn.params):
            raise CompileError(f"{path}:{line_no}: unknown variable {name!r}; assign it with set var({name}) first")
    for name, line_no, function_name in local_references:
        fn = functions.get(function_name) if function_name else None
        if fn is None or name not in fn.locals:
            raise CompileError(f"{path}:{line_no}: unknown local variable {name!r}; declare it with set local({name}) first")
    for fn in functions.values():
        for name in fn.local_arrays:
            if name in fn.params or name in fn.locals:
                raise CompileError(f"{path}:{fn.line}: local array {name!r} conflicts with a local variable or parameter in function '{fn.name}'")
    c_symbols: dict[str, tuple[str, str]] = {}
    symbols = ([(name, "variable") for name in variables]
               + [(name, "function") for name in functions]
               + [(name, "array") for name in arrays])
    for fn in functions.values():
        symbols.extend((fn.name + "__" + name, "function-local")
                       for name in fn.params + sorted(fn.locals) + sorted(fn.local_arrays))
    for name, kind in sorted(symbols):
        generated = c_name(name)
        if generated in RUNTIME_C_NAMES:
            raise CompileError(f"{path}: identifier {name!r} conflicts with a reserved runtime name")
        previous = c_symbols.get(generated)
        if previous is not None:
            previous_name, previous_kind = previous
            if previous_name != name:
                raise CompileError(f"{path}: identifiers {previous_name!r} and {name!r} both map to C name {generated!r}")
            if previous_kind != kind:
                raise CompileError(f"{path}: {kind} {name!r} conflicts with another declaration of the same name")
        c_symbols[generated] = (name, kind)
    return functions, top, variables, arrays


TOKEN = re.compile(r'''\s*(?:(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)|("(?:\\.|[^"\\])*")|(var\([A-Za-z_][\w-]*\))|(local\([A-Za-z_][\w-]*\))|(<=|>=|!=|==|[(),+\-*/%=<>])|([A-Za-z_][\w-]*))''')


BUILTINS = {
    "time": (0, 0), "delta": (0, 0), "rnd": (2, 2),
    "noise": (3, 3), "fbm": (6, 6), "floor": (1, 1), "ceil": (1, 1),
    "sqrt": (1, 1), "sin": (1, 1), "cos": (1, 1), "abs": (1, 1),
    "min": (2, 2), "max": (2, 2), "pressed": (1, 1), "held": (1, 1),
    "receive": (0, 0),
    "body_create": (4, 4), "body_create_box": (5, 5),
    "body_destroy": (1, 1), "body_active": (1, 1),
    "body_x": (1, 1), "body_y": (1, 1), "body_vx": (1, 1), "body_vy": (1, 1),
    "body_set_velocity": (3, 3), "body_force": (3, 3),
    "body_restitution": (2, 2), "body_friction": (2, 2),
    "body_collision": (2, 2),
    "physics_capacity": (1, 1), "physics_gravity": (2, 2),
    "physics_step": (0, 0),
    "ray_backend": (1, 1), "ray_backend_available": (1, 1),
}
BUILTIN_C_NAMES = {
    "time": "anvil_time", "delta": "anvil_delta", "rnd": "anvil_rnd",
    "noise": "anvil_noise", "fbm": "anvil_fbm",
    "pressed": "anvil_pressed", "held": "anvil_held",
    "receive": "anvil_net_receive", "abs": "fabs", "min": "fmin", "max": "fmax",
    "body_create": "anvil_body_create", "body_create_box": "anvil_body_create_box",
    "body_destroy": "anvil_body_destroy",
    "body_active": "anvil_body_active", "body_x": "anvil_body_x",
    "body_y": "anvil_body_y", "body_vx": "anvil_body_vx",
    "body_vy": "anvil_body_vy", "body_set_velocity": "anvil_body_set_velocity",
    "body_force": "anvil_body_force", "body_restitution": "anvil_body_restitution",
    "body_friction": "anvil_body_friction",
    "body_collision": "anvil_body_collision", "physics_gravity": "anvil_physics_gravity",
    "physics_capacity": "anvil_physics_capacity",
    "physics_step": "anvil_physics_step",
    "ray_backend": "anvil_ray_backend",
    "ray_backend_available": "anvil_ray_backend_available",
}
BUILTIN_STRING_ARGUMENTS = {"ray_backend", "ray_backend_available"}


class ExpressionParser:
    """Parse the supported expression grammar and emit safe C expressions."""

    PRECEDENCE = {"or": 1, "and": 2, "=": 3, "==": 3, "!=": 3,
                  "<": 4, "<=": 4, ">": 4, ">=": 4,
                  "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}

    def __init__(self, path: pathlib.Path, line: int, source: str,
                 functions: dict[str, Node] | None, scope: Node | None = None,
                 arrays: dict[str, int] | None = None):
        self.path, self.line, self.source, self.functions = path, line, source, functions
        self.scope = scope
        self.arrays = arrays or {}
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
                self.tokens.append(("call" if is_call else "array", source[call_start:scan]))
                pos = scan
                continue
            match = TOKEN.match(source, pos)
            if not match:
                raise CompileError(f"{path}:{line}: invalid expression near {source[pos:pos+20]!r}")
            number, string, variable, local, op, word = match.groups()
            kind, value = ("number", number) if number else ("string", string) if string else ("variable", variable) if variable else ("local", local) if local else ("op", op) if op else ("word", word)
            self.tokens.append((kind, value))
            pos = match.end()
        self.index = 0

    def peek(self, value: str | None = None) -> bool:
        return self.index < len(self.tokens) and (value is None or self.tokens[self.index][1] == value)

    def take(self) -> tuple[str, str]:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def expect(self, value: str) -> None:
        if not self.peek(value):
            raise CompileError(f"{self.path}:{self.line}: expected {value!r} in expression")
        self.index += 1

    def require_number(self, value: tuple[str, str]) -> str:
        code, kind = value
        if kind != "number":
            raise CompileError(f"{self.path}:{self.line}: expected a number, got a string")
        return code

    def checked_number(self, code: str) -> str:
        return (f"anvil_check_number(({code}), {json.dumps(str(self.path))}, "
                f"{self.line})")

    def require_string(self, value: tuple[str, str]) -> str:
        code, kind = value
        if kind != "string":
            raise CompileError(f"{self.path}:{self.line}: expected a string, got a number")
        return code

    def parse(self, minimum: int = 0) -> tuple[str, str]:
        if not self.peek():
            raise CompileError(f"{self.path}:{self.line}: expected an expression")
        kind, value = self.take()
        if kind == "number":
            if not math.isfinite(float(value)):
                raise CompileError(f"{self.path}:{self.line}: numeric literal must be finite")
            left = (value if any(char in value for char in ".eE") else value + ".0", "number")
        elif kind == "string":
            left = (value, "string")
        elif kind == "variable":
            name = value[4:-1]
            left = (variable_code(name, self.scope), "number")
        elif kind == "local":
            name = value[6:-1]
            if not self.scope or name not in self.scope.locals:
                raise CompileError(f"{self.path}:{self.line}: unknown local variable {name!r}")
            left = (c_name(self.scope.name + "__" + name), "number")
        elif kind == "array":
            contents = value[value.index("array(") + 6:-1]
            parts = split_args(contents)
            if len(parts) != 2 or not re.fullmatch(r"[A-Za-z_][\w-]*", parts[0]):
                raise CompileError(f"{self.path}:{self.line}: array access expects array(name, index)")
            name = parts[0]
            size = array_size(name, self.scope, self.arrays)
            if size is None:
                raise CompileError(f"{self.path}:{self.line}: unknown array {name!r}")
            index_expr = ExpressionParser(self.path, self.line, parts[1], self.functions,
                                          self.scope, self.arrays).compile()
            left = (f"anvil_array_get({array_code(name, self.scope)}, {size}, {index_expr}, "
                    f"{json.dumps(str(self.path))}, {self.line})", "number")
        elif kind == "call":
            contents = value[value.index("fn(") + 3:-1]
            parts = split_args(contents)
            name, raw_args = parts[0], parts[1:]
            if self.functions is not None and name not in self.functions:
                raise CompileError(f"{self.path}:{self.line}: unknown function {name!r}")
            if self.functions is not None and len(raw_args) != len(self.functions[name].params):
                expected = len(self.functions[name].params)
                raise CompileError(f"{self.path}:{self.line}: function {name!r} expects {expected} argument(s), got {len(raw_args)}")
            args = [ExpressionParser(self.path, self.line, arg, self.functions,
                                     self.scope, self.arrays).compile() for arg in raw_args]
            left = (c_name(name) + "(" + ", ".join(args) + ")", "number")
        elif kind == "op" and value in ("+", "-"):
            left = (f"({value}{self.require_number(self.parse(7))})", "number")
        elif kind == "op" and value == "(":
            left = self.parse()
            self.expect(")")
        elif kind == "word" and value in ("true", "false"):
            left = ("1.0" if value == "true" else "0.0", "number")
        elif kind == "word" and value in ("and", "or"):
            raise CompileError(f"{self.path}:{self.line}: operator {value!r} needs a left operand")
        elif kind == "word" and value in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" and len(value) == 1:
            left = ("ANVIL_KEY_" + value, "number")
        elif kind == "word" and value in ("SPACE", "UP", "DOWN", "LEFT", "RIGHT", "ENTER", "ESCAPE"):
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
                raise CompileError(f"{self.path}:{self.line}: {value}() expects {expected} argument(s), got {len(args)}")
            name = BUILTIN_C_NAMES.get(value, value)
            call = f"{name} ( {', '.join(args)} )" if args else f"{name} ( )"
            if value in {"time", "delta", "rnd", "noise", "fbm", "floor", "ceil",
                         "sqrt", "sin", "cos", "abs", "min", "max"}:
                call = self.checked_number(call)
            left = (call, "number")
        elif kind == "word":
            raise CompileError(f"{self.path}:{self.line}: unknown name {value!r}")
        else:
            raise CompileError(f"{self.path}:{self.line}: unexpected token {value!r} in expression")

        while self.peek():
            operator = self.tokens[self.index][1]
            precedence = self.PRECEDENCE.get(operator, -1)
            if precedence < minimum:
                break
            self.take()
            if not self.peek() or self.peek(")") or self.peek(","):
                raise CompileError(f"{self.path}:{self.line}: operator {operator!r} needs a right operand")
            left_code = self.checked_number(self.require_number(left))
            right = self.require_number(self.parse(precedence + 1))
            if operator == "/":
                left = (f"anvil_divide({left_code}, {right}, {json.dumps(str(self.path))}, {self.line})", "number")
            elif operator == "%":
                left = (self.checked_number(f"fmod({left_code}, {self.checked_number(right)})"), "number")
            elif operator in ("and", "or"):
                c_operator = "&&" if operator == "and" else "||"
                left = (f"({left_code} {c_operator} {self.checked_number(right)})", "number")
            elif operator in ("=", "==", "!=", "<", "<=", ">", ">="):
                c_operator = "==" if operator == "=" else operator
                left = (f"({left_code} {c_operator} {self.checked_number(right)})", "number")
            else:
                left = (self.checked_number(f"({left_code} {operator} {self.checked_number(right)})"), "number")
        return left

    def compile(self, expected: str = "number") -> str:
        result = self.parse()
        if self.peek():
            raise CompileError(f"{self.path}:{self.line}: unexpected token {self.tokens[self.index][1]!r} in expression")
        code, actual = result
        if actual != expected:
            raise CompileError(f"{self.path}:{self.line}: expected {expected}, got {actual}")
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
            result.append(text[start:i].strip()); start = i + 1
    tail = text[start:].strip()
    if tail or result:
        result.append(tail)
    return result


def expr(path: pathlib.Path, line: int, source: str, functions: dict[str, Node] | None = None,
         expected: str = "number", scope: Node | None = None,
         arrays: dict[str, int] | None = None) -> str:
    source = source.strip()
    if source.startswith("compute(") and source.endswith(")"):
        source = source[8:-1]
    return ExpressionParser(path, line, source, functions, scope, arrays).compile(expected)


def rgb_style(raw: str, path: pathlib.Path, line: int, functions: dict[str, Node],
              scope: Node | None = None, arrays: dict[str, int] | None = None) -> tuple[list[str], str]:
    color = ["255", "255", "255", "255"]
    m = re.search(r"-rgba?\(([^)]*)\)", raw)
    if m:
        vals = split_args(m.group(1))
        if len(vals) not in (3, 4):
            raise CompileError(f"{path}:{line}: -rgb/-rgba expects 3 or 4 values")
        color = [expr(path, line, v, functions, scope=scope, arrays=arrays) for v in vals]
        if len(color) == 3: color.append("255")
    raw = re.sub(r"\s+-rgba?\([^)]*\)", "", raw)
    return color, raw


def emit_display(path: pathlib.Path, node: Node, ind: str,
                 functions: dict[str, Node], scope: Node | None = None,
                 arrays: dict[str, int] | None = None) -> str:
    raw = node.value.strip()
    color, raw = rgb_style(raw, path, node.line, functions, scope, arrays)
    rot = ["0", "0", "0"]
    rm = re.search(r"-rotate\(((?:[^()]|\([^()]*\))*)\)", raw)
    if rm:
        rot = [expr(path, node.line, v, functions, scope=scope, arrays=arrays) for v in split_args(rm.group(1))]
        if len(rot) != 3: raise CompileError(f"{path}:{node.line}: -rotate expects x,y,z")
        raw = raw.replace(rm.group(0), "")
    loc = None
    lm = re.search(r"-l\(((?:[^()]|\([^()]*\))*)\)", raw)
    if lm:
        loc = [expr(path, node.line, v, functions, scope=scope, arrays=arrays) for v in split_args(lm.group(1))]
        if len(loc) != 2: raise CompileError(f"{path}:{node.line}: -l expects x,y")
        raw = raw.replace(lm.group(0), "")
    call = re.fullmatch(r"(cube|sphere|ray_sphere|plane|rect|circle|line|text)\((.*)\)(?:\s+\d+)?", raw.strip())
    if not call:
        raise CompileError(f"{path}:{node.line}: malformed display command")
    shape, arg_text = call.groups()
    args = split_args(arg_text)
    if shape == "text" and loc:
        dynamic = re.fullmatch(r'\s*("(?:\\.|[^"\\])*")\s*\+\s*(var\([A-Za-z_][\w-]*\))\s*', arg_text)
        if dynamic:
            prefix = dynamic.group(1)[:-1].replace("%", "%%")
            value = expr(path, node.line, dynamic.group(2), functions, scope=scope, arrays=arrays)
            separator = "" if prefix.endswith((" ", "\t")) else " "
            fmt = prefix + separator + "%.0f\""
            return f"{ind}anvil_text_number({', '.join(loc)}, {fmt}, {value}, {', '.join(color)});"
    expected = "string" if shape == "text" else "number"
    values = [expr(path, node.line, item, functions, expected, scope) for item in args]
    tail = ", ".join(color)
    if shape == "cube" and len(values) == 4:
        return f"{ind}anvil_cube({', '.join(values)}, {', '.join(rot)}, {tail});"
    if shape == "sphere" and len(values) == 4:
        return f"{ind}anvil_sphere({', '.join(values)}, {tail});"
    if shape == "ray_sphere" and len(values) == 4:
        return f"{ind}anvil_trace_sphere({', '.join(values)}, {tail});"
    if shape == "plane" and len(values) == 5:
        return f"{ind}anvil_plane({', '.join(values)}, {tail});"
    if shape == "rect" and len(values) == 4:
        return f"{ind}anvil_rect({', '.join(values)}, {tail});"
    if shape == "circle" and len(values) == 3:
        return f"{ind}anvil_circle({', '.join(values)}, {tail});"
    if shape == "line" and len(values) in (4, 5):
        thick = values[4] if len(values) == 5 else "1.0"
        return f"{ind}anvil_line({', '.join(values[:4])}, {tail}, {thick});"
    if shape == "text" and loc and len(values) == 1:
        return f"{ind}anvil_text({', '.join(loc)}, {values[0]}, {tail});"
    raise CompileError(f"{path}:{node.line}: invalid arguments for display {shape}")


def emit_nodes(path: pathlib.Path, nodes: list[Node], functions: dict[str, Node],
               indent: str, scope: Node | None = None,
               arrays: dict[str, int] | None = None) -> list[str]:
    arrays = arrays or {}
    out = []
    for n in nodes:
        if n.kind == "set": out.append(f"{indent}{variable_code(n.name, scope)} = {expr(path, n.line, n.value, functions, scope=scope, arrays=arrays)};")
        elif n.kind == "local_set": out.append(f"{indent}{c_name(scope.name + '__' + n.name)} = {expr(path, n.line, n.value, functions, scope=scope, arrays=arrays)};")
        elif n.kind == "array_set":
            size = array_size(n.name, scope, arrays)
            if size is None:
                raise CompileError(f"{path}:{n.line}: unknown array {n.name!r}")
            suffix = f"{c_name(scope.name if scope else 'top')}_{n.line}"
            index_var, value_var = f"_anvil_array_index_{suffix}", f"_anvil_array_value_{suffix}"
            out.extend([f"{indent}{{",
                        f"{indent}    const double {index_var} = {expr(path, n.line, n.params[0], functions, scope=scope, arrays=arrays)};",
                        f"{indent}    const double {value_var} = {expr(path, n.line, n.value, functions, scope=scope, arrays=arrays)};",
                        f"{indent}    anvil_array_set({array_code(n.name, scope)}, {size}, {index_var}, {value_var}, {json.dumps(str(path))}, {n.line});",
                        f"{indent}}}"])
        elif n.kind in ("add", "sub"):
            op = "+" if n.kind == "add" else "-"
            target = variable_code(n.name, scope)
            value = expr(path, n.line, n.value, functions, scope=scope, arrays=arrays)
            out.append(f"{indent}{target} = anvil_check_number(({target} {op} {value}), {json.dumps(str(path))}, {n.line});")
        elif n.kind in ("local_add", "local_sub"):
            op = "+" if n.kind == "local_add" else "-"
            target = c_name(scope.name + '__' + n.name)
            value = expr(path, n.line, n.value, functions, scope=scope, arrays=arrays)
            out.append(f"{indent}{target} = anvil_check_number(({target} {op} {value}), {json.dumps(str(path))}, {n.line});")
        elif n.kind == "output":
            value = expr(path, n.line, n.value, functions, scope=scope, arrays=arrays)
            if scope is not None and scope.local_arrays:
                out.append(f"{indent}{{")
                out.append(f"{indent}    const double _anvil_return_value = {value};")
                out.extend(local_array_cleanup(scope, indent + "    "))
                out.append(f"{indent}    return _anvil_return_value;")
                out.append(f"{indent}}}")
            else:
                out.append(f"{indent}return {value};")
        elif n.kind == "call":
            if n.name not in functions: raise CompileError(f"{path}:{n.line}: unknown function {n.name!r}")
            args = split_args(n.value)
            if len(args) != len(functions[n.name].params):
                raise CompileError(f"{path}:{n.line}: function {n.name!r} expects {len(functions[n.name].params)} argument(s), got {len(args)}")
            values = [expr(path, n.line, arg, functions, scope=scope, arrays=arrays) for arg in args]
            out.append(f"{indent}(void){c_name(n.name)}({', '.join(values)});")
        elif n.kind == "if":
            out.append(f"{indent}if ({expr(path, n.line, n.value, functions, scope=scope, arrays=arrays)} != 0.0) {{")
            out.extend(emit_nodes(path, n.body, functions, indent + "    ", scope, arrays))
            if n.otherwise:
                out.append(f"{indent}}} else {{")
                out.extend(emit_nodes(path, n.otherwise, functions, indent + "    ", scope, arrays))
            out.append(f"{indent}}}")
        elif n.kind == "while":
            out.append(f"{indent}while ({expr(path, n.line, n.value, functions, scope=scope, arrays=arrays)} != 0.0) {{")
            out.extend(emit_nodes(path, n.body, functions, indent + "    ", scope, arrays))
            out.append(f"{indent}}}")
        elif n.kind == "for":
            if scope is None:
                raise CompileError(f"{path}:{n.line}: for loops must be inside a function")
            loop_var = c_name(scope.name + "__" + n.name)
            suffix = f"{c_name(scope.name)}_{n.line}"
            start_var = f"_anvil_for_start_{suffix}"
            end_var = f"_anvil_for_end_{suffix}"
            step_var = f"_anvil_for_step_{suffix}"
            start_expr, end_expr, step_expr = n.params
            inner = indent + "    "
            out.append(f"{indent}{{")
            out.append(f"{inner}const double {start_var} = {expr(path, n.line, start_expr, functions, scope=scope, arrays=arrays)};")
            out.append(f"{inner}const double {end_var} = {expr(path, n.line, end_expr, functions, scope=scope, arrays=arrays)};")
            out.append(f"{inner}const double {step_var} = {expr(path, n.line, step_expr, functions, scope=scope, arrays=arrays)};")
            out.append(f"{inner}{loop_var} = {start_var};")
            out.append(f"{inner}if ({step_var} != 0.0) {{")
            condition = f"(({step_var} > 0.0 && {loop_var} <= {end_var}) || ({step_var} < 0.0 && {loop_var} >= {end_var}))"
            out.append(f"{inner}    while ({condition}) {{")
            out.extend(emit_nodes(path, n.body, functions, inner + "        ", scope, arrays))
            out.append(f"{inner}        {loop_var} = anvil_check_number(({loop_var} + {step_var}), {json.dumps(str(path))}, {n.line});")
            out.append(f"{inner}    }}")
            out.append(f"{inner}}}")
            out.append(f"{indent}}}")
        elif n.kind == "scene": out.append(f"{indent}anvil_set_scene3d({1 if n.value == '3d' else 0});")
        elif n.kind == "camera":
            vals = n.value.split()
            if len(vals) != 3: raise CompileError(f"{path}:{n.line}: camera perspective expects x y z")
            out.append(f"{indent}anvil_camera_perspective({', '.join(expr(path,n.line,x,functions,scope=scope,arrays=arrays) for x in vals)});")
        elif n.kind == "camera_fov":
            vals = split_args(n.value)
            if len(vals) != 1: raise CompileError(f"{path}:{n.line}: camera fov expects one value")
            out.append(f"{indent}anvil_camera_fov({expr(path,n.line,vals[0],functions,scope=scope,arrays=arrays)});")
        elif n.kind == "camera_control":
            vals = split_args(n.value)
            if len(vals) != 2: raise CompileError(f"{path}:{n.line}: camera control expects speed and turn rate")
            out.append(f"{indent}anvil_camera_control({expr(path,n.line,vals[0],functions,scope=scope,arrays=arrays)}, {expr(path,n.line,vals[1],functions,scope=scope,arrays=arrays)});")
        elif n.kind == "clear":
            args = split_args(n.value[1:-1])
            if len(args) != 4: raise CompileError(f"{path}:{n.line}: clear rgba expects 4 values")
            out.append(f"{indent}anvil_clear({', '.join(expr(path,n.line,x,functions,scope=scope,arrays=arrays) for x in args)});")
        elif n.kind == "display":
            statement = emit_display(path, n, indent, functions, scope, arrays)
            if "anvil_trace_sphere(" not in statement:
                out.append(f"{indent}anvil_trace_finish();")
            out.append(statement)
        elif n.kind == "seed": out.append(f"{indent}anvil_seed((unsigned long long)({expr(path,n.line,n.value,functions,scope=scope,arrays=arrays)}));")
        elif n.kind == "net_send": out.append(f"{indent}anvil_net_send({expr(path,n.line,n.value,functions,scope=scope,arrays=arrays)});")
        elif n.kind == "net_host": out.append(f"{indent}(void)anvil_net_host({n.value});")
        elif n.kind == "net_join":
            address, port = n.value.rsplit(",", 1)
            out.append(f"{indent}(void)anvil_net_join({address}, {port});")
    return out


def local_array_cleanup(scope: Node, indent: str) -> list[str]:
    return [f"{indent}anvil_local_array_free({c_name(scope.name + '__' + name)}, {size});"
            for name, size in sorted(scope.local_arrays.items())]


def emit_c(path: pathlib.Path, functions: dict[str, Node], top: list[Node], variables: set[str],
           arrays: dict[str, int] | None = None, fixed_hz: int = 60,
           project_name: str = "Anvil Game") -> str:
    arrays = arrays or {}
    lines = ["/* Generated from Anvil source. The .ANVL source remains the program. */", '#include "anvil_runtime.h"', "#include <math.h>", "#include <stdio.h>", "#include <stdlib.h>", ""]
    lines += [f"static double {c_name(name)};" for name in sorted(variables)]
    lines += [f"static double {c_name(name)}[{size}];" for name, size in sorted(arrays.items())]
    if any(fn.local_arrays for fn in functions.values()):
        lines.extend([
            f"#define ANVIL_LOCAL_ARRAY_BUDGET_BYTES {MAX_ACTIVE_LOCAL_ARRAY_BYTES}u",
            "static size_t anvil_active_local_array_bytes;",
            "static double *anvil_local_array_alloc(size_t count, const char *path, int line) {",
            "    const size_t bytes = count * sizeof(double);",
            "    if (bytes > ANVIL_LOCAL_ARRAY_BUDGET_BYTES - anvil_active_local_array_bytes) {",
            "        fprintf(stderr, \"%s:%d: active local arrays exceed the %u MiB Anvil memory limit\\n\", path, line, ANVIL_LOCAL_ARRAY_BUDGET_BYTES / (1024u * 1024u));",
            "        exit(2);",
            "    }",
            "    double *values = (double *)calloc(count, sizeof(double));",
            "    if (!values) {",
            "        fprintf(stderr, \"%s:%d: unable to allocate local array (%zu bytes)\\n\", path, line, bytes);",
            "        exit(2);",
            "    }",
            "    anvil_active_local_array_bytes += bytes;",
            "    return values;",
            "}",
            "static void anvil_local_array_free(double *values, size_t count) {",
            "    if (values) {",
            "        free(values);",
            "        anvil_active_local_array_bytes -= count * sizeof(double);",
            "    }",
            "}",
            "",
        ])
    for name, fn in functions.items():
        if name in ("draw", "update") and fn.params:
            raise CompileError(f"{path}:{fn.line}: engine callback '{name}' cannot have parameters")
        params = ", ".join(f"double {c_name(name + '__' + param)}" for param in fn.params) or "void"
        lines.append(f"static double {c_name(name)}({params});")
    lines.append("")
    for name, fn in functions.items():
        params = ", ".join(f"double {c_name(name + '__' + param)}" for param in fn.params) or "void"
        lines.append(f"static double {c_name(name)}({params}) {{")
        lines.extend(f"    double {c_name(name + '__' + local)} = 0.0;" for local in sorted(fn.locals))
        lines.extend(f"    double *{c_name(name + '__' + local)} = anvil_local_array_alloc({size}, {json.dumps(str(path))}, {fn.local_array_lines[local]});"
                     for local, size in sorted(fn.local_arrays.items()))
        body = emit_nodes(path, fn.body, functions, "    ", fn, arrays)
        lines.extend(body)
        if not any(n.kind == "output" for n in fn.body):
            lines.extend(local_array_cleanup(fn, "    "))
            lines.append("    return 0.0;")
        lines.extend(["}", ""])
    # Setup commands and initial values run before callbacks.
    setup = [n for n in top if n.kind in ("set", "scene", "camera", "camera_fov", "camera_control", "clear", "seed", "net_host", "net_join")]
    calls = [n for n in top if n.kind == "call"]
    invalid = [n for n in top if n.kind not in ("set", "scene", "camera", "camera_fov", "camera_control", "clear", "seed", "net_host", "net_join", "call")]
    if invalid: raise CompileError(f"{path}:{invalid[0].line}: only configuration, initial values, and calls are allowed at top level")
    for n in calls:
        if n.name not in functions: raise CompileError(f"{path}:{n.line}: unknown function {n.name!r}")
        if len(split_args(n.value)) != len(functions[n.name].params):
            raise CompileError(f"{path}:{n.line}: function {n.name!r} expects {len(functions[n.name].params)} argument(s), got {len(split_args(n.value))}")
    has_engine = any(n.kind in ("scene", "camera", "camera_fov", "camera_control", "clear") for n in setup) or "draw" in functions or "update" in functions
    if has_engine and "main" in functions and functions["main"].params:
        raise CompileError(f"{path}:{functions['main'].line}: main cannot have parameters when used as an engine callback program")
    lines.append("int main(void) {")
    lines.append(f"    anvil_set_fixed_hz({fixed_hz});")
    lines.extend(emit_nodes(path, setup, functions, "    ", arrays=arrays))
    if has_engine:
        lines.append(f"    anvil_run({c_name('update') if 'update' in functions else 'NULL'}, {c_name('draw') if 'draw' in functions else 'NULL'}, {json.dumps(project_name, ensure_ascii=True)});")
    elif calls:
        for n in calls:
            values = [expr(path, n.line, arg, functions) for arg in split_args(n.value)]
            call = f"{c_name(n.name)}({', '.join(values)})"
            if n.name == "main": lines.append(f'    printf("%.15g\\n", {call});')
            else: lines.append(f"    (void){call};")
    elif "main" in functions:
        if functions["main"].params:
            raise CompileError(f"{path}:{functions['main'].line}: main function parameters require an explicit call with arguments")
        lines.append(f'    printf("%.15g\\n", {c_name("main")}());')
    lines.append("    anvil_net_close();")
    lines.extend(["    return 0;", "}", ""])
    return "\n".join(lines)


def find_compiler(requested: str | None):
    # MSVC is the supported default for the Windows-only native runtime.
    for name in ([requested] if requested else ["cl"]):
        if name and shutil.which(name): return name, shutil.which(name)
    if requested in (None, "cl", "cl.exe"):
        for root in (pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files")), pathlib.Path(r"C:\Program Files (x86)")):
            for p in root.glob("Microsoft Visual Studio/*/*/VC/Tools/MSVC/*/bin/Hostx64/x64/cl.exe"):
                return "cl.exe", str(p)
    return None


def build_c(compiler: str, generated: pathlib.Path, output: pathlib.Path, release: bool):
    output.parent.mkdir(parents=True, exist_ok=True)
    if pathlib.Path(compiler).name.lower() == "cl.exe":
        obj_dir = output.parent / (output.stem + "_obj")
        obj_dir.mkdir(exist_ok=True)
        args = [compiler, "/nologo", "/TC", "/I" + str(INCLUDE), str(generated), str(RUNTIME), "/Fe:" + str(output), "/Fo:" + str(obj_dir) + "\\", "/O2" if release else "/Od"]
        install_root = pathlib.Path(compiler).parents[7]
        devcmd = install_root / "Common7" / "Tools" / "VsDevCmd.bat"
        if os.name == "nt" and devcmd.exists():
            helper = output.parent / (output.stem + ".build.cmd")
            helper.write_text('@echo off\ncall "' + str(devcmd) + '" -arch=x64 >nul\nif errorlevel 1 exit /b %errorlevel%\n' + subprocess.list2cmdline(args) + '\nexit /b %errorlevel%\n', encoding="utf-8")
            try: subprocess.run(["cmd.exe", "/d", "/c", str(helper)], check=True)
            finally: helper.unlink(missing_ok=True)
        else: subprocess.run(args, check=True)
    else:
        args = [compiler, str(generated), str(RUNTIME), "-I", str(INCLUDE), "-o", str(output), "-lm", "-lgdi32", "-luser32", "-lws2_32"]
        args += ["-O3", "-DNDEBUG"] if release else ["-O0", "-g"]
        subprocess.run(args, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Compile Anvil source or project to C, then link a native executable.")
    ap.add_argument("source", type=pathlib.Path, help="input .ANVL source or .ANVLproj project manifest")
    ap.add_argument("--emit-c", type=pathlib.Path, help="emit C source only and stop")
    ap.add_argument("--generated-c", type=pathlib.Path, help="choose generated C path")
    ap.add_argument("--output", "-o", type=pathlib.Path, help="output executable")
    ap.add_argument("--cc", help="explicit C compiler compatible with the Windows runtime (MSVC is verified)")
    ap.add_argument("--release", action="store_true", help="enable native optimization")
    args = ap.parse_args()
    try:
        source_path = args.source
        fixed_hz = 60
        project_name = "Anvil Game"
        if args.source.suffix.lower() == ".anvlproj":
            manifest_text = args.source.read_text(encoding="utf-8")
            manifest = tomllib.loads(manifest_text)
            unknown_keys = set(manifest) - {"name", "entry", "engine"}
            if unknown_keys:
                raise CompileError(f"{args.source}: unsupported project setting(s): {', '.join(sorted(unknown_keys))}")
            name = manifest.get("name", project_name)
            if not isinstance(name, str) or not name.strip() or "\0" in name or any(ord(ch) < 32 for ch in name):
                raise CompileError(f"{args.source}: project name must be a non-empty string without control characters")
            project_name = name.strip()
            engine = manifest.get("engine", {})
            if not isinstance(engine, dict):
                raise CompileError(f"{args.source}: 'engine' must be a TOML table")
            unknown_engine_keys = set(engine) - {"fixed_hz"}
            if unknown_engine_keys:
                raise CompileError(f"{args.source}: unsupported engine setting(s): {', '.join(sorted(unknown_engine_keys))}")
            fixed_hz = engine.get("fixed_hz", 60)
            if isinstance(fixed_hz, bool) or not isinstance(fixed_hz, int) or not 1 <= fixed_hz <= 240:
                raise CompileError(f"{args.source}: engine.fixed_hz must be an integer from 1 to 240")
            entry = manifest.get("entry")
            if not isinstance(entry, str) or not entry:
                raise CompileError(f"{args.source}: manifest needs a non-empty string 'entry'")
            project_root = args.source.resolve().parent
            source_path = (project_root / entry).resolve()
            try:
                source_path.relative_to(project_root)
            except ValueError as exc:
                raise CompileError(f"{args.source}: entry must resolve inside the project folder") from exc
        source = source_path.read_text(encoding="utf-8")
        funcs, top, variables, arrays = parse(source_path, source)
        generated = emit_c(source_path, funcs, top, variables, arrays, fixed_hz, project_name)
        c_path = args.emit_c or args.generated_c or source_path.with_suffix(".generated.c")
        c_path.parent.mkdir(parents=True, exist_ok=True)
        c_path.write_text(generated, encoding="utf-8", newline="\n")
        if args.emit_c:
            print(f"Wrote {c_path}"); return 0
        compiler = find_compiler(args.cc)
        if not compiler:
            print(f"No C compiler found. Install Visual Studio 2022 Build Tools with the C++ workload. Generated source: {c_path}", file=sys.stderr); return 2
        out = args.output or source_path.with_suffix(".exe")
        build_c(compiler[1], c_path, out, args.release)
        print(f"Built {out} using {compiler[0]}"); return 0
    except tomllib.TOMLDecodeError as e:
        print(f"{args.source}: {e}", file=sys.stderr)
        return 1
    except (CompileError, OSError, UnicodeError, subprocess.CalledProcessError) as e:
        print(str(e), file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())

