"""Source statement parsing and semantic validation."""

from __future__ import annotations

import pathlib
import re

from compiler.common import (
    LANGUAGE_VERSION,
    MAX_ARRAY_SIZE,
    MAX_LOCAL_ARRAY_ELEMENTS,
    CompileError,
    Node,
    ParsedProgram,
)
from compiler.expressions import split_args
from compiler.lexer import split_keyword, strip_comment, validate_port
from compiler.semantics import validate_program


def parse_syntax(path: pathlib.Path, source: str) -> ParsedProgram:
    functions: dict[str, Node] = {}
    top: list[Node] = []
    variables: set[str] = set()
    arrays: dict[str, int] = {}
    variable_references: list[tuple[str, int, str | None]] = []
    local_references: list[tuple[str, int, str | None]] = []
    stack: list[tuple[list[Node], str, Node | None]] = [(top, "top", None)]
    version_declared = False
    source_code_seen = False
    for line_no, raw in enumerate(source.splitlines(), 1):
        line = strip_comment(raw).strip()
        if not line:
            continue
        if line == "language" or line.startswith("language "):
            if source_code_seen:
                raise CompileError(
                    f"{path}:{line_no}: language version declaration must "
                    "appear before all other source code"
                )
            if version_declared:
                raise CompileError(
                    f"{path}:{line_no}: language version may only be declared once"
                )
            declaration = re.fullmatch(r"language\s+version\s+([0-9]+)", line)
            if not declaration:
                raise CompileError(
                    f"{path}:{line_no}: language version declaration must "
                    "use 'language version N'"
                )
            version_declared = True
            version_text = declaration.group(1)
            # Compare decimal text without constructing an unbounded Python int.
            # Python limits extremely long int conversions and would leak ValueError.
            version = version_text.lstrip("0") or "0"
            if version != str(LANGUAGE_VERSION):
                shown_version = version if len(version) <= 32 else "value too large"
                raise CompileError(
                    f"{path}:{line_no}: unsupported Anvil language version "
                    f"{shown_version}; compiler supports version {LANGUAGE_VERSION}"
                )
            continue
        source_code_seen = True
        current_function = next(
            (frame[2] for frame in reversed(stack) if frame[1] == "function"), None
        )
        for reference in re.finditer(r"var\(([A-Za-z_][\w-]*)\)", line):
            variable_references.append(
                (
                    reference.group(1),
                    line_no,
                    current_function.name if current_function else None,
                )
            )
        for reference in re.finditer(r"local\(([A-Za-z_][\w-]*)\)", line):
            local_references.append(
                (
                    reference.group(1),
                    line_no,
                    current_function.name if current_function else None,
                )
            )
        array_decl = re.fullmatch(
            r"array\s+([A-Za-z_][\w-]*)\s*\(\s*([0-9]+)\s*\)", line
        )
        if array_decl:
            name, raw_size = array_decl.groups()
            normalized_size = raw_size.lstrip("0") or "0"
            max_array_text = str(MAX_ARRAY_SIZE)
            if len(normalized_size) > len(max_array_text) or (
                len(normalized_size) == len(max_array_text)
                and normalized_size > max_array_text
            ):
                raise CompileError(
                    f"{path}:{line_no}: array size must be between "
                    f"1 and {MAX_ARRAY_SIZE}"
                )
            size = int(normalized_size)
            if size < 1:
                raise CompileError(
                    f"{path}:{line_no}: array size must be between "
                    f"1 and {MAX_ARRAY_SIZE}"
                )
            if current_function is None:
                if len(stack) != 1:
                    raise CompileError(
                        f"{path}:{line_no}: global arrays must be declared at top level"
                    )
                if name in arrays:
                    raise CompileError(f"{path}:{line_no}: duplicate array '{name}'")
                arrays[name] = size
            else:
                if name in current_function.local_arrays:
                    raise CompileError(
                        f"{path}:{line_no}: duplicate local array '{name}' "
                        f"in function '{current_function.name}'"
                    )
                if (
                    sum(current_function.local_arrays.values()) + size
                    > MAX_LOCAL_ARRAY_ELEMENTS
                ):
                    raise CompileError(
                        f"{path}:{line_no}: local arrays in a function may "
                        f"contain at most {MAX_LOCAL_ARRAY_ELEMENTS} elements total"
                    )
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
                raise CompileError(
                    f"{path}:{line_no}: function parameters must be identifiers"
                )
            if len(params) != len(set(params)):
                raise CompileError(
                    f"{path}:{line_no}: duplicate parameter in function '{name}'"
                )
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
            condition = line[len("while ") :].strip()
            if not condition:
                raise CompileError(f"{path}:{line_no}: while needs a condition")
            node = Node("while", line_no, value=condition)
            stack[-1][0].append(node)
            stack.append((node.body, "while", node))
            continue
        for_loop = re.fullmatch(r"for\s+local\(([A-Za-z_][\w-]*)\)\s*=\s*(.+)", line)
        if for_loop:
            if current_function is None:
                raise CompileError(
                    f"{path}:{line_no}: for loops must be inside a function"
                )
            loop_name, range_text = for_loop.groups()
            if loop_name in current_function.params:
                raise CompileError(
                    f"{path}:{line_no}: for-loop variable cannot be a "
                    "function parameter"
                )
            if any(
                kind == "for" and block is not None and block.name == loop_name
                for _, kind, block in stack
            ):
                raise CompileError(
                    f"{path}:{line_no}: nested for loops must use "
                    "different local variables"
                )
            range_parts = split_keyword(range_text, "to")
            if not range_parts:
                raise CompileError(
                    f"{path}:{line_no}: for loop expects 'to' between its bounds"
                )
            start_expr, end_and_step = range_parts
            step_parts = split_keyword(end_and_step, "step")
            if step_parts:
                end_expr, step_expr = step_parts
            else:
                end_expr, step_expr = end_and_step, "1"
            if not start_expr or not end_expr or not step_expr:
                raise CompileError(
                    f"{path}:{line_no}: for loop needs start, end, and step expressions"
                )
            current_function.locals.add(loop_name)
            node = Node(
                "for", line_no, name=loop_name, params=[start_expr, end_expr, step_expr]
            )
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
                raise CompileError(
                    f"{path}:{line_no}: local variables must be "
                    "declared inside a function"
                )
            if match.group(1) in current_function.params:
                raise CompileError(
                    f"{path}:{line_no}: local variable {match.group(1)!r} "
                    "conflicts with a function parameter"
                )
            current_function.locals.add(match.group(1))
            node = Node("local_set", line_no, match.group(2), match.group(1))
        if node is None:
            match = re.fullmatch(
                r"set\s+array\(([A-Za-z_][\w-]*)\s*,\s*(.*)\)\s*=\s*(.+)", line
            )
            if match:
                if current_function is None:
                    raise CompileError(
                        f"{path}:{line_no}: array writes must be inside a function"
                    )
                array_name, index_expr, value_expr = match.groups()
                node = Node(
                    "array_set", line_no, value_expr, array_name, params=[index_expr]
                )
        match = re.fullmatch(r"set\s+var\(([A-Za-z_][\w-]*)\)\s*=\s*(.+)", line)
        if node is None and match:
            node = Node("set", line_no, match.group(2), match.group(1))
            if (
                current_function is None
                or match.group(1) not in current_function.params
            ):
                variables.add(match.group(1))
        if node is None:
            match = re.fullmatch(r"(add|sub)\s+local\(([A-Za-z_][\w-]*)\)\s+(.+)", line)
            if match:
                if current_function is None:
                    raise CompileError(
                        f"{path}:{line_no}: local variables can only be "
                        "changed inside a function"
                    )
                if match.group(2) in current_function.params:
                    raise CompileError(
                        f"{path}:{line_no}: local variable {match.group(2)!r} "
                        "conflicts with a function parameter"
                    )
                current_function.locals.add(match.group(2))
                node = Node(
                    "local_" + match.group(1), line_no, match.group(3), match.group(2)
                )
        if node is None:
            match = re.fullmatch(r"(add|sub)\s+var\(([A-Za-z_][\w-]*)\)\s+(.+)", line)
            if match:
                node = Node(match.group(1), line_no, match.group(3), match.group(2))
                if (
                    current_function is None
                    or match.group(2) not in current_function.params
                ):
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
                    raise CompileError(
                        f"{path}:{line_no}: expected a function name in call"
                    )
                node = Node(
                    "call", line_no, value=", ".join(call_args[1:]), name=call_args[0]
                )
        if node is None:
            if re.fullmatch(r"scene\s+(?:2d|3d)", line):
                node = Node("scene", line_no, value=line.split()[1])
            elif line.startswith("camera perspective "):
                node = Node("camera", line_no, value=line[len("camera perspective ") :])
            elif re.fullmatch(r"camera fov\(.*\)", line):
                node = Node("camera_fov", line_no, value=line[len("camera fov(") : -1])
            elif re.fullmatch(r"camera control\(.*\)", line):
                node = Node(
                    "camera_control", line_no, value=line[len("camera control(") : -1]
                )
            elif line.startswith("clear rgba("):
                node = Node("clear", line_no, value=line[len("clear rgba") :])
            elif line.startswith("display "):
                node = Node("display", line_no, value=line[len("display ") :])
            elif m := re.fullmatch(r"net\s+host\(([0-9]+)\)", line):
                validate_port(path, line_no, m.group(1))
                node = Node("net_host", line_no, value=m.group(1))
            elif m := re.fullmatch(
                r'net\s+join\(("(?:\\.|[^"\\])*")\s*,\s*([0-9]+)\)', line
            ):
                validate_port(path, line_no, m.group(2))
                node = Node("net_join", line_no, value=m.group(1) + "," + m.group(2))
            elif line.startswith("net send(") and line.endswith(")"):
                node = Node("net_send", line_no, value=line[len("net send(") : -1])
            elif line.startswith("seed(") and line.endswith(")"):
                node = Node("seed", line_no, value=line[5:-1])
        if node is None:
            raise CompileError(f"{path}:{line_no}: unsupported statement: {line}")
        stack[-1][0].append(node)
    if len(stack) != 1:
        _, kind, node = stack[-1]
        raise CompileError(
            f"{path}:{node.line if node else 1}: unclosed {kind}; expected 'end'"
        )
    return ParsedProgram(
        path,
        functions,
        top,
        variables,
        arrays,
        variable_references,
        local_references,
    )


def parse(
    path: pathlib.Path, source: str
) -> tuple[dict[str, Node], list[Node], set[str], dict[str, int]]:
    """Parse Anvil syntax, run semantic checks, and preserve the legacy tuple API."""
    program = parse_syntax(path, source)
    validate_program(program)
    return program.functions, program.top, program.variables, program.arrays
