"""Source statement parsing and semantic validation."""

from __future__ import annotations

import pathlib
import re

from compiler.common import (
    LANGUAGE_VERSION,
    ArrayDeclarations,
    MAX_ARRAY_SIZE,
    MAX_LOCAL_ARRAY_ELEMENTS,
    CompileError,
    Node,
    ParsedProgram,
)
from compiler.expressions import split_args
from compiler.lexer import split_keyword, strip_comment, validate_port
from compiler.semantics import validate_program

# `list <name>` reserves this many slots; `add` appends until it is full.
LIST_CAPACITY = 256


def parse_syntax(path: pathlib.Path, source: str) -> ParsedProgram:
    functions: dict[str, Node] = {}
    top: list[Node] = []
    variables: set[str] = set()
    arrays = ArrayDeclarations()
    lists: set[str] = set()
    variable_references: list[tuple[str, int, str | None, pathlib.Path]] = []
    local_references: list[tuple[str, int, str | None, pathlib.Path]] = []
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
        if re.match(r"include\b", line):
            if len(stack) != 1:
                raise CompileError(f"{path}:{line_no}: include must be at top level")
            from compiler.modules import include_name
            raw_name = line[len("include"):].strip()
            include_name(raw_name, path, line_no)
            top.append(Node("include", line_no, value=raw_name, source=path))
            continue
        for reference in re.finditer(r"var\(([A-Za-z_][\w-]*)\)", line):
            variable_references.append(
                (
                    reference.group(1),
                    line_no,
                    current_function.name if current_function else None,
                    path,
                )
            )
        for reference in re.finditer(r"local\(([A-Za-z_][\w-]*)\)", line):
            local_references.append(
                (
                    reference.group(1),
                    line_no,
                    current_function.name if current_function else None,
                    path,
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
                arrays.locations[name] = (path, line_no)
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
        list_decl = re.fullmatch(r"list\s+([A-Za-z_][\w-]*)", line)
        if list_decl:
            name = list_decl.group(1)
            if current_function is not None or len(stack) != 1:
                raise CompileError(
                    f"{path}:{line_no}: lists must be declared at top level"
                )
            if name in arrays:
                raise CompileError(
                    f"{path}:{line_no}: duplicate array or list '{name}'"
                )
            arrays[name] = LIST_CAPACITY
            arrays.locations[name] = (path, line_no)
            lists.add(name)
            # The counter is a normal global; both backends zero-initialise
            # globals, so no top-level `set` node is needed (native rejects
            # top-level statements in console programs).
            variables.add(f"{name}__count")
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
        elif_match = re.fullmatch(r"elif\s+(.+)", line)
        if elif_match:
            # `elif` chains read as one decision; compile as a nested if in the
            # previous if's else branch, so both backends need no new node kind.
            if stack[-1][1] != "if":
                raise CompileError(
                    f"{path}:{line_no}: 'elif' must directly follow an 'if' body"
                )
            chain = stack[-1][2]
            assert chain is not None
            condition = elif_match.group(1).strip()
            if not condition:
                raise CompileError(f"{path}:{line_no}: elif needs a condition")
            node = Node("if", line_no, value=condition)
            chain.otherwise.append(node)
            stack[-1] = (node.body, "if", node)
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
        if line == "stop":
            node = Node("stop", line_no)
            stack[-1][0].append(node)
            continue
        if line in ("break", "continue"):
            if not any(entry[1] in ("while", "for", "repeat") for entry in stack):
                raise CompileError(
                    f"{path}:{line_no}: {line} must be inside a loop"
                )
            stack[-1][0].append(Node(line, line_no))
            continue
        if line == "repeat" or line.startswith("repeat "):
            count = line[len("repeat "):].strip() if line != "repeat" else ""
            if not count:
                raise CompileError(f"{path}:{line_no}: repeat needs a count")
            if current_function is None:
                raise CompileError(
                    f"{path}:{line_no}: repeat loops must be inside a function"
                )
            loop_name = f"repeat{line_no}"
            current_function.locals.add(loop_name)
            node = Node("for", line_no, name=loop_name, params=["1", count, "1"])
            stack[-1][0].append(node)
            stack.append((node.body, "for", node))
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
            # `null` used to be a silent no-op, which left the variable undefined
            # and produced a confusing error later. Say what is wrong instead.
            raise CompileError(
                f"{path}:{line_no}: null is not a value in Anvil; assign a "
                "number or text"
            )
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
        match = re.fullmatch(
            r"set\s+var\(([A-Za-z_][\w-]*)\)(?:\s*:\s*([A-Za-z]+))?\s*=\s*(.+)",
            line,
        )
        if node is None and match:
            declared = match.group(2)
            if declared is not None:
                if declared not in ("number", "text", "bool"):
                    raise CompileError(
                        f"{path}:{line_no}: unknown type {declared!r}; write "
                        "number, text or bool"
                    )
            node = Node("set", line_no, match.group(3), match.group(1))
            node.declared_type = declared
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
            match = re.fullmatch(r"add\s+([A-Za-z_][\w-]*)\s+(.+)", line)
            if match and match.group(1) in lists:
                if current_function is None:
                    raise CompileError(
                        f"{path}:{line_no}: list writes must be inside a function"
                    )
                list_name, value_expr = match.group(1), match.group(2)
                counter = f"{list_name}__count"
                stack[-1][0].append(
                    Node(
                        "array_set",
                        line_no,
                        value_expr,
                        list_name,
                        params=[f"var({counter})"],
                    )
                )
                stack[-1][0].append(Node("add", line_no, "1", counter))
                continue
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
            if line == "write" or line.startswith("write "):
                parts = line[len("write "):].strip() if line != "write" else ""
                if not parts:
                    raise CompileError(f"{path}:{line_no}: write expects text or a value")
                node = Node("write", line_no, parts)
                stack[-1][0].append(node)
                continue
            match = re.fullmatch(r"say\s+(.+)", line)
            if match:
                node = Node("say", line_no, match.group(1))
        if node is None:
            match = re.fullmatch(r"wait\s+(.+)", line)
            if match:
                node = Node("wait", line_no, match.group(1))
        if node is None and line == "press enter":
            node = Node("press_enter", line_no)
        if node is None:
            match = re.fullmatch(r"ask\s+(.+)", line)
            if match:
                parts = split_args(match.group(1))
                target = None
                if parts and re.fullmatch(r"var\([A-Za-z_][\w-]*\)", parts[-1].strip()):
                    target = parts[-1].strip()[4:-1]
                    parts = parts[:-1]
                if target is None:
                    raise CompileError(
                        f"{path}:{line_no}: ask needs a variable to store the answer, "
                        "like ask \"Name? \", var(name)"
                    )
                if target not in variables:
                    variables.add(target)
                node = Node("ask", line_no, ", ".join(parts), target, params=[target])
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
    def mark_source(nodes):
        pending = list(nodes)
        while pending:
            node = pending.pop()
            node.source = path
            pending.extend(node.body)
            pending.extend(node.otherwise)

    from compiler.expressions import LISTS

    # Accumulate: a program may include several files, each declaring lists.
    # load_program clears the registry once per program.
    LISTS.update(lists)
    mark_source(top)
    for function in functions.values():
        function.source = path
        mark_source(function.body)
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
    path: pathlib.Path, source: str, *, include_root: pathlib.Path | None = None
) -> tuple[dict[str, Node], list[Node], set[str], dict[str, int]]:
    """Parse Anvil syntax, run semantic checks, and preserve the legacy tuple API."""
    from compiler.modules import load_program
    program = load_program(path, source, include_root=include_root)
    validate_program(program)
    return program.functions, program.top, program.variables, program.arrays
