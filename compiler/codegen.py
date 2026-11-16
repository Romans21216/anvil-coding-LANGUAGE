"""C backend: lower validated Anvil nodes into runtime calls and C source."""

from __future__ import annotations

import pathlib
import re

from compiler.suggestions import suggestion_suffix
from compiler.common import (
    MAX_ACTIVE_LOCAL_ARRAY_BYTES,
    MAX_ACTIVE_LOCAL_ARRAY_MIB,
    CompileError,
    Node,
    array_code,
    array_size,
    c_name,
    c_string_literal,
    c_bytes_literal,
    variable_code,
    decode_string,
)
from compiler.common import constant_truth
from compiler.expressions import (
    LISTS,
    BOOL_VARIABLES,
    STRING_VARIABLES,
    TEXT_LISTS,
    TEXT_LIST_CAP,
    expr,
    set_string_variables,
    split_args,
    split_amp,
)


def _walk_statement_nodes(nodes):
    for node in nodes:
        yield node
        yield from _walk_statement_nodes(node.body)
        yield from _walk_statement_nodes(node.otherwise)


def _walk_nodes(top, functions):
    yield from _walk_statement_nodes(top)
    for function in functions.values():
        yield from _walk_statement_nodes(function.body)


_VAR_PATTERN = __import__("re").compile(r"var\(([A-Za-z_][\w-]*)\)")


def _is_bool_variable(part: str) -> bool:
    match = _VAR_PATTERN.fullmatch(part.strip())
    return match is not None and match.group(1) in BOOL_VARIABLES


def _is_string_variable(part: str) -> bool:
    match = _VAR_PATTERN.fullmatch(part.strip())
    return match is not None and match.group(1) in STRING_VARIABLES


_TEXT_LIST_READ = __import__("re").compile(r"array\(\s*([A-Za-z_][\w-]*)\s*,")


def _is_text_list_read(part: str) -> bool:
    match = _TEXT_LIST_READ.match(part.strip())
    return match is not None and match.group(1) in TEXT_LISTS


def rgb_style(
    raw: str,
    path: pathlib.Path,
    line: int,
    functions: dict[str, Node],
    scope: Node | None = None,
    arrays: dict[str, int] | None = None,
    temporary_owner: Node | None = None,
    temporary_counter: list[int] | None = None,
) -> tuple[list[str], str]:
    color = ["255", "255", "255", "255"]
    modifiers, raw = _take_display_modifiers(raw, {"rgb", "rgba"}, path, line)
    if modifiers:
        vals = split_args(modifiers[0][1])
        if len(vals) not in (3, 4):
            raise CompileError(f"{path}:{line}: -rgb/-rgba expects 3 or 4 values")
        color = [
            expr(path, line, value, functions, scope=scope, arrays=arrays,
                 temporary_owner=temporary_owner, temporary_counter=temporary_counter)
            for value in vals
        ]
        if len(color) == 3:
            color.append("255")
    return color, raw


def say_string(raw: str) -> str:
    """Convert an Anvil string literal token into a C string literal body.

    Anvil escapes (\\n, \\t, \\\\, \\") are decoded first, then the result is
    re-escaped for C so printf receives exactly the characters the author wrote.
    """
    text = decode_string(raw)
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )


def emit_display(
    path: pathlib.Path,
    node: Node,
    ind: str,
    functions: dict[str, Node],
    scope: Node | None = None,
    arrays: dict[str, int] | None = None,
    temporary_owner: Node | None = None,
    temporary_counter: list[int] | None = None,
) -> tuple[str, str]:
    raw = node.value.strip()
    color, raw = rgb_style(raw, path, node.line, functions, scope, arrays,
                           temporary_owner, temporary_counter)
    rot = ["0", "0", "0"]
    loc = None
    modifiers, raw = _take_display_modifiers(raw, {"rotate", "l"}, path, node.line)
    seen = set()
    for name, arguments in modifiers:
        if name in seen:
            raise CompileError(f"{path}:{node.line}: malformed display command: repeated -{name} modifier")
        seen.add(name)
        values = [
            expr(path, node.line, value, functions, scope=scope, arrays=arrays,
                 temporary_owner=temporary_owner, temporary_counter=temporary_counter)
            for value in split_args(arguments)
        ]
        if name == "rotate":
            if len(values) != 3:
                raise CompileError(f"{path}:{node.line}: -rotate expects x,y,z")
            rot = values
        else:
            if len(values) != 2:
                raise CompileError(f"{path}:{node.line}: -l expects x,y")
            loc = values
    call = re.fullmatch(
        r"(cube|sphere|ray_sphere|plane|rect|circle|line|text)\((.*)\)(?:\s+[0-9]+)?",
        raw.strip(),
    )
    if not call:
        raise CompileError(f"{path}:{node.line}: malformed display command")
    shape, arg_text = call.groups()
    args = split_args(arg_text)
    if shape == "text" and loc:
        dynamic = re.fullmatch(
            r'\s*("(?:\\.|[^"\\])*")\s*\+\s*(var\([A-Za-z_][\w-]*\))\s*', arg_text
        )
        if dynamic:
            prefix = dynamic.group(1)[:-1].replace("%", "%%")
            value = expr(
                path, node.line, dynamic.group(2), functions, scope=scope, arrays=arrays,
                temporary_owner=temporary_owner, temporary_counter=temporary_counter,
            )
            separator = "" if prefix.endswith((" ", "\t")) else " "
            fmt = prefix + separator + '%.0f"'
            return shape, (
                f"{ind}anvil_text_number({', '.join(loc)}, {fmt}, {value}, "
                f"{', '.join(color)});"
            )
    expected = "string" if shape == "text" else "number"
    values = [
        expr(path, node.line, item, functions, expected, scope=scope, arrays=arrays,
             temporary_owner=temporary_owner, temporary_counter=temporary_counter)
        for item in args
    ]
    tail = ", ".join(color)
    if shape == "cube" and len(values) == 4:
        return shape, f"{ind}anvil_cube({', '.join(values)}, {', '.join(rot)}, {tail});"
    if shape == "sphere" and len(values) == 4:
        return shape, f"{ind}anvil_sphere({', '.join(values)}, {tail});"
    if shape == "ray_sphere" and len(values) == 4:
        return shape, f"{ind}anvil_trace_sphere({', '.join(values)}, {tail});"
    if shape == "plane" and len(values) == 5:
        return shape, f"{ind}anvil_plane({', '.join(values)}, {tail});"
    if shape == "rect" and len(values) == 4:
        return shape, f"{ind}anvil_rect({', '.join(values)}, {tail});"
    if shape == "circle" and len(values) == 3:
        return shape, f"{ind}anvil_circle({', '.join(values)}, {tail});"
    if shape == "line" and len(values) in (4, 5):
        thick = values[4] if len(values) == 5 else "1.0"
        return shape, f"{ind}anvil_line({', '.join(values[:4])}, {tail}, {thick});"
    if shape == "text" and loc and len(values) == 1:
        return shape, f"{ind}anvil_text({', '.join(loc)}, {values[0]}, {tail});"
    raise CompileError(f"{path}:{node.line}: invalid arguments for display {shape}")

def emit_display(path, node, ind, functions, scope=None, arrays=None) -> str:
    """Compatibility API: return the generated statement only."""
    return _lower_display(path, node, ind, functions, scope, arrays)[1]



_TEXT_CALL = re.compile(r"call\s+fn\(([^,)]*)")


def _is_text_function_call(part: str, functions: dict[str, "Node"] | None) -> bool:
    """True when `part` is a call to a function whose output is text."""
    match = _TEXT_CALL.match(part.strip())
    if match is None or not functions:
        return False
    target = functions.get(match.group(1).strip())
    return bool(target is not None and getattr(target, "returns_text", False))


_COMPARISON = re.compile(r"<=|>=|!=|==|[<>=]")


def _has_comparison(part: str) -> bool:
    """True when the part compares values, which yields a number, not text."""
    stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', part)
    return _COMPARISON.search(stripped) is not None


def emit_nodes(
    path: pathlib.Path,
    nodes: list[Node],
    functions: dict[str, Node],
    indent: str,
    scope: Node | None = None,
    arrays: dict[str, int] | None = None,
    loops: list[dict] | None = None,
) -> list[str]:
    arrays = arrays or {}
    loops = loops if loops is not None else []
    out = []

    def lower(node: Node, value: str | None = None, expected: str = "number") -> str:
        return expr(
            path,
            node.line,
            node.value if value is None else value,
            functions,
            expected,
            scope,
            arrays,
            scope or n,
            temporary_counter,
        )

    original_path = path
    for n in nodes:
        temporary_counter = [0]
        path = n.source or original_path
        source_path = json.dumps(str(path))
        if n.kind == "set":
            if n.string:
                buffer = f"anvil_str_{c_name(n.name)}"
                out.append(
                    f"{indent}anvil_str_set({buffer}, "
                    f"{expr(path, n.line, n.value, functions, 'string', scope, arrays)}, "
                    f"{source_path}, {n.line});"
                )
            else:
                out.append(f"{indent}{variable_code(n.name, scope)} = {lower(n)};")
        elif n.kind == "local_set":
            out.append(f"{indent}{c_name(scope.name + '__' + n.name)} = {lower(n)};")
        elif n.kind == "text_list_remove":
            out.append(
                f"{indent}anvil_text_list_remove({c_name(n.name)}__text, "
                f"(int)({lower(n)}), "
                f"{variable_code(n.name + '__count', scope)});"
            )
        elif n.kind == "text_list_add":
            out.append(
                f"{indent}anvil_text_list_set({c_name(n.name)}__text, "
                f"(int){variable_code(n.name + '__count', scope)}, "
                f"{variable_code(n.name + '__count', scope)}, "
                f"{expr(path, n.line, n.value, functions, 'string', scope, arrays)}, "
                f"{source_path}, {n.line});"
            )
        elif n.kind == "array_set" and n.name in TEXT_LISTS:
            out.append(
                f"{indent}anvil_text_list_set({c_name(n.name)}__text, "
                f"(int)({lower(n, n.params[0])}), 0.0, "
                f"{expr(path, n.line, n.value, functions, 'string', scope, arrays)}, "
                f"{source_path}, {n.line});"
            )
        elif n.kind == "array_set":
            size = array_size(n.name, scope, arrays)
            if size is None:
                raise CompileError(f"{path}:{n.line}: unknown array {n.name!r}")
            suffix = f"{c_name(scope.name if scope else 'top')}_{n.line}"
            index_var, value_var = (
                f"_anvil_array_index_{suffix}",
                f"_anvil_array_value_{suffix}",
            )
            out.extend(
                [
                    f"{indent}{{",
                    f"{indent}    const double {index_var} = {lower(n, n.params[0])};",
                    f"{indent}    const double {value_var} = {lower(n)};",
                    f"{indent}    anvil_array_set({array_code(n.name, scope)}, "
                    f"{size}, {index_var}, {value_var}, {source_path}, {n.line});",
                    f"{indent}}}",
                ]
            )
        elif n.kind in ("add", "sub",'global_add','global_sub'):
            op = "+" if n.kind in ("add",'global_add') else "-"
            target = variable_code(n.name, None if n.kind.startswith('global_') else scope)
            value = lower(n)
            out.append(
                f"{indent}{target} = anvil_check_number(({target} {op} {value}), "
                f"{source_path}, {n.line});"
            )
        elif n.kind in ("local_add", "local_sub"):
            op = "+" if n.kind == "local_add" else "-"
            target = c_name(scope.name + "__" + n.name)
            value = lower(n)
            out.append(
                f"{indent}{target} = anvil_check_number(({target} {op} {value}), "
                f"{source_path}, {n.line});"
            )
        elif n.kind == "output":
            if scope is not None and getattr(scope, "returns_text", False):
                value = lower(n, expected="string")
                if scope.local_arrays:
                    out.append(f"{indent}{{")
                    out.append(f"{indent}    const char *_anvil_return_text = {value};")
                    out.extend(local_array_cleanup(scope, indent + "    "))
                    out.append(f"{indent}    return _anvil_return_text;")
                    out.append(f"{indent}}}")
                else:
                    out.append(f"{indent}return {value};")
                continue
            value = lower(n)
            if scope is not None and scope.local_arrays:
                out.append(f"{indent}{{")
                out.append(f"{indent}    const double _anvil_return_value = {value};")
                out.extend(local_array_cleanup(scope, indent + "    "))
                out.append(f"{indent}    return _anvil_return_value;")
                out.append(f"{indent}}}")
            else:
                out.append(f"{indent}return {value};")
        elif n.kind == "wait":
            out.append(f"{indent}anvil_wait({lower(n)});")
        elif n.kind == "press_enter":
            out.append(f"{indent}anvil_press_enter();")
        elif n.kind == "ask":
            prompt = n.value.strip()
            if n.string:
                buffer = f"anvil_str_{c_name(n.params[0])}"
                if prompt:
                    rendered = expr(path, n.line, prompt, functions, "string", scope, arrays)
                    out.append(
                        f"{indent}anvil_ask({rendered}, {buffer});"
                    )
                else:
                    out.append(f"{indent}anvil_ask(0, {buffer});")
            else:
                target = variable_code(n.params[0], scope)
                if prompt:
                    rendered = expr(path, n.line, prompt, functions, "string", scope, arrays)
                    out.append(
                        f"{indent}{target} = anvil_check_number("
                        f"anvil_ask_number({rendered}), {source_path}, {n.line});"
                    )
                else:
                    out.append(
                        f"{indent}{target} = anvil_check_number("
                        f"anvil_ask_number(0), {source_path}, {n.line});"
                    )
        elif n.kind == "write":
            parts = split_args(n.value)
            if not parts:
                raise CompileError(f"{path}:{n.line}: write expects text or a value")
            for part in parts:
                part = part.strip()
                if not part:
                    raise CompileError(f"{path}:{n.line}: write has an empty part")
                if _has_comparison(part):
                    out.append(f'{indent}printf("%s", anvil_format_number({lower(n, part)}));')
                elif (
                    len(split_amp(part)) > 1
                    or _is_text_list_read(part)
                    or _is_text_function_call(part, functions)
                    or re.fullmatch(
                        r"(upper|lower|chr|trim|char|mid|left|right|image_error|sound_error|music_error|load_text|save_error)\s*\(.*\)", part, re.DOTALL
                    )
                ):
                    rendered = expr(path, n.line, part, functions, "string", scope, arrays)
                    out.append(f'{indent}printf("%s", {rendered});')
                elif part.startswith('"'):
                    rendered = expr(path, n.line, part, functions, "string", scope, arrays)
                    out.append(f'{indent}printf("%s", "{say_string(rendered)}");')
                elif _is_bool_variable(part):
                    out.append(f"{indent}anvil_print_bool({lower(n, part)});")
                elif _is_string_variable(part):
                    rendered = expr(path, n.line, part, functions, "string", scope, arrays)
                    out.append(f'{indent}printf("%s", {rendered});')
                else:
                    out.append(f'{indent}printf("%s", anvil_format_number({lower(n, part)}));')
        elif n.kind == "say":
            parts = split_args(n.value)
            if not parts:
                raise CompileError(f"{path}:{n.line}: say expects text or a value")
            for part in parts:
                part = part.strip()
                if not part:
                    raise CompileError(f"{path}:{n.line}: say has an empty part")
                if _has_comparison(part):
                    out.append(f'{indent}printf("%s", anvil_format_number({lower(n, part)}));')
                elif (
                    len(split_amp(part)) > 1
                    or _is_text_list_read(part)
                    or _is_text_function_call(part, functions)
                    or re.fullmatch(
                        r"(upper|lower|chr|trim|char|mid|left|right|image_error|sound_error|music_error|load_text|save_error)\s*\(.*\)", part, re.DOTALL
                    )
                ):
                    rendered = expr(path, n.line, part, functions, "string", scope, arrays)
                    out.append(f'{indent}printf("%s", {rendered});')
                elif part.startswith('"'):
                    rendered = expr(path, n.line, part, functions, "string", scope, arrays)
                    out.append(f'{indent}printf("%s", "{say_string(rendered)}");')
                elif _is_bool_variable(part):
                    out.append(f"{indent}anvil_print_bool({lower(n, part)});")
                elif _is_string_variable(part):
                    rendered = expr(path, n.line, part, functions, "string", scope, arrays)
                    out.append(f'{indent}printf("%s", {rendered});')
                else:
                    out.append(f'{indent}printf("%s", anvil_format_number({lower(n, part)}));')
            out.append(f'{indent}printf("\\n");')
            # Flush each line so a piped reader (test harness, log collector)
            # sees output while the program is still running.
            out.append(f"{indent}fflush(stdout);")
        elif n.kind == "stop":
            out.append(f"{indent}exit(0);")
        elif n.kind == "call":
            if n.name not in functions:
                raise CompileError(
                    f"{n.source or path}:{n.line}: unknown function {n.name!r}"
                    f"{suggestion_suffix(n.name, functions)}"
                )
            args = split_args(n.value)
            if len(args) != len(functions[n.name].params):
                raise CompileError(
                    f"{n.source or path}:{n.line}: function {n.name!r} expects "
                    f"{len(functions[n.name].params)} argument(s), got {len(args)}"
                )
            call_expression = "call fn(" + n.name + (", " + n.value if n.value else "") + ")"
            if scope is None and n.name == "main":
                out.append(
                    f'{indent}printf("%.15g\\n", {lower(n, call_expression)});'
                )
            else:
                out.append(f"{indent}(void){lower(n, call_expression)};")
        elif n.kind=='callable_error':
            message=c_string_literal(f'{path}:{n.line}: function reference is unset or invalid\n')
            out.append(f'{indent}fputs({message},stderr); exit(2);')
        elif n.kind == "if":
            truth = constant_truth(n.value)
            if truth is not None:
                out.extend(
                    emit_nodes(
                        path,
                        n.body if truth else n.otherwise,
                        functions,
                        indent,
                        scope,
                        arrays,
                        loops,
                    )
                )
                continue
            out.append(f"{indent}if ({lower(n)} != 0.0) {{")
            out.extend(
                emit_nodes(path, n.body, functions, indent + "    ", scope, arrays, loops)
            )
            if n.otherwise:
                out.append(f"{indent}}} else {{")
                out.extend(
                    emit_nodes(
                        path, n.otherwise, functions, indent + "    ", scope, arrays
                    )
                )
            out.append(f"{indent}}}")
        elif n.kind == "while":
            truth = constant_truth(n.value)
            if truth is False:
                continue
            out.append(f"{indent}while ({lower(n)} != 0.0) {{")
            loops.append({})
            try:
                out.extend(
                    emit_nodes(path, n.body, functions, indent + "    ", scope, arrays, loops)
                )
            finally:
                loops.pop()
            out.append(f"{indent}}}")
        elif n.kind == "for":
            if scope is None:
                raise CompileError(
                    f"{path}:{n.line}: for loops must be inside a function"
                )
            loop_var = c_name(scope.name + "__" + n.name)
            suffix = f"{c_name(scope.name)}_{n.line}"
            start_var = f"_anvil_for_start_{suffix}"
            end_var = f"_anvil_for_end_{suffix}"
            step_var = f"_anvil_for_step_{suffix}"
            start_expr, end_expr, step_expr = n.params
            inner = indent + "    "
            out.append(f"{indent}{{")
            out.append(f"{inner}const double {start_var} = {lower(n, start_expr)};")
            out.append(f"{inner}const double {end_var} = {lower(n, end_expr)};")
            out.append(f"{inner}const double {step_var} = {lower(n, step_expr)};")
            out.append(f"{inner}{loop_var} = {start_var};")
            out.append(f"{inner}if ({step_var} != 0.0) {{")
            condition = (
                f"(({step_var} > 0.0 && {loop_var} <= {end_var}) "
                f"|| ({step_var} < 0.0 && {loop_var} >= {end_var}))"
            )
            out.append(f"{inner}    while ({condition}) {{")
            loops.append({
                "for_increment": (
                    f"{loop_var} = anvil_check_number("
                    f"({loop_var} + {step_var}), {source_path}, {n.line});"
                )
            })
            try:
                out.extend(
                    emit_nodes(
                        path, n.body, functions, inner + "        ", scope, arrays, loops
                    )
                )
            finally:
                loops.pop()
            out.append(
                f"{inner}        {loop_var} = anvil_check_number("
                f"({loop_var} + {step_var}), {source_path}, {n.line});"
            )
            out.append(f"{inner}    }}")
            out.append(f"{inner}}}")
            out.append(f"{indent}}}")
        elif n.kind in ("break", "continue"):
            if not loops:
                raise CompileError(
                    f"{path}:{n.line}: {n.kind} must be inside a loop"
                )
            if n.kind == "continue":
                increment = loops[-1].get("for_increment")
                if increment:
                    # A C `continue` would skip the for-loop increment entirely,
                    # so apply it first and then continue.
                    out.append(f"{indent}{increment}")
            out.append(f"{indent}{n.kind};")
        elif n.kind == "scene":
            out.append(f"{indent}anvil_set_scene3d({1 if n.value == '3d' else 0});")
        elif n.kind == "camera":
            vals = n.value.split()
            if len(vals) != 3:
                raise CompileError(f"{path}:{n.line}: camera perspective expects x y z")
            out.append(
                f"{indent}anvil_camera_perspective("
                f"{', '.join(lower(n, x) for x in vals)});"
            )
        elif n.kind == "camera_fov":
            vals = split_args(n.value)
            if len(vals) != 1:
                raise CompileError(f"{path}:{n.line}: camera fov expects one value")
            out.append(f"{indent}anvil_camera_fov({lower(n, vals[0])});")
        elif n.kind == "camera_control":
            vals = split_args(n.value)
            if len(vals) != 2:
                raise CompileError(
                    f"{path}:{n.line}: camera control expects speed and turn rate"
                )
            out.append(
                f"{indent}anvil_camera_control({lower(n, vals[0])}, "
                f"{lower(n, vals[1])});"
            )
        elif n.kind == "clear":
            args = split_args(n.value[1:-1])
            if len(args) != 4:
                raise CompileError(f"{path}:{n.line}: clear rgba expects 4 values")
            out.append(f"{indent}anvil_clear({', '.join(lower(n, x) for x in args)});")
        elif n.kind == "display":
            shape, statement = _lower_display(
                path, n, indent, functions, scope, arrays, scope or n, temporary_counter
            )
            if shape != "ray_sphere":
                out.append(f"{indent}anvil_trace_finish();")
            out.append(statement)
        elif n.kind == "seed":
            out.append(f"{indent}anvil_seed((unsigned long long)({lower(n)}));")
        elif n.kind == "window_set":
            function = (
                "anvil_window_fullscreen" if n.name == "fullscreen"
                else "anvil_window_on_top"
            )
            out.append(f"{indent}{function}({lower(n)});")
        elif n.kind == "net_send":
            out.append(
                f"{indent}anvil_net_ok = (double)anvil_net_send({lower(n)});"
            )
        elif n.kind == "net_host":
            out.append(
                f"{indent}anvil_net_ok = (double)anvil_net_host({n.value});"
            )
        elif n.kind == "net_join":
            address, port = n.value.rsplit(",", 1)
            out.append(
                f"{indent}anvil_net_ok = "
                f"(double)anvil_net_join({address}, {port});"
            )
    return out


def local_array_cleanup(scope: Node, indent: str) -> list[str]:
    return [
        f"{indent}anvil_local_array_free({c_name(scope.name + '__' + name)}, {size});"
        for name, size in sorted(scope.local_arrays.items())
    ]


def _walk_nodes(nodes):
    for node in nodes:
        yield node
        for branch in (node.body, node.otherwise):
            if branch:
                yield from _walk_nodes(branch)


def _walk_kinds(nodes):
    for node in nodes:
        yield node.kind
        for branch in (node.body, node.otherwise):
            if branch:
                yield from _walk_kinds(branch)


def emit_c(
    path: pathlib.Path,
    functions: dict[str, Node],
    top: list[Node],
    variables: set[str],
    arrays: dict[str, int] | None = None,
    fixed_hz: int = 60,
    project_name: str = "Anvil Game",
    runtime_header: str = "anvil_runtime.h",
    minimal_includes: bool = False,
) -> str:
    if (
        isinstance(active_local_array_bytes, bool)
        or not isinstance(active_local_array_bytes, int)
        or not 1024 * 1024 <= active_local_array_bytes
        <= MAX_ACTIVE_LOCAL_ARRAY_MIB * 1024 * 1024
        or active_local_array_bytes % (1024 * 1024)
    ):
        raise CompileError(
            f"{path}: active local array budget must be an integer number of MiB "
            f"from 1 to {MAX_ACTIVE_LOCAL_ARRAY_MIB} MiB"
        )
    arrays = arrays or {}
    from compiler import gltf as _gltf

    _gltf.reset()
    try:
        _gltf.prescan(pathlib.Path(path).read_text(encoding="utf-8"), pathlib.Path(path))
    except OSError:
        pass
    # Emit only functions reachable from the real entry points (top-level calls,
    # main, and active engine callbacks), exactly like the native backend. A
    # helper that is never called should not reach the generated C at all.
    from compiler.modules import reachable_functions

    graphical = (
        "draw" in functions
        or "update" in functions
        or any(node.kind == "scene" for node in top)
    )
    reachable = dict(reachable_functions(
        functions, top, graphical=graphical, extra=("random-pipeline",)
    ))
    # Check call targets against every declared function before pruning, so a
    # typo can suggest an existing function even when that function is dead.
    for node in _walk_nodes(list(reachable.values()) + list(top)):
        if node.kind == "call" and node.name not in functions:
            raise CompileError(
                f"{node.source or path}:{node.line}: unknown function {node.name!r}"
                f"{suggestion_suffix(node.name, functions)}"
            )
    functions = reachable
    string_variables = set(STRING_VARIABLES)
    from compiler.builtin_usage import used_builtins

    resolved = used_builtins(functions, top)
    if minimal_includes:
        lines = [
            "/* Generated from Anvil source. The .ANVL source remains the program. */",
            "/* builtins used: " + (", ".join(resolved) or "none") + " */",
            f'#include "{runtime_header}"',
            "",
        ]
    else:
        lines = [
            "/* Generated from Anvil source. The .ANVL source remains the program. */",
            "/* builtins used: " + (", ".join(resolved) or "none") + " */",
            f'#include "{runtime_header}"',
            "#include <math.h>",
            "#include <stdio.h>",
            "#include <string.h>",
            "#include <stdlib.h>",
            "#include <io.h>",
            "#include <fcntl.h>",
            "",
        ]
    from compiler import extensions as _extensions

    lines += _extensions.c_declarations()
    lines += [
        f"static double {c_name(name)};"
        for name in sorted(variables - string_variables)
    ]

    lines += [
        f"static char anvil_str_{c_name(name)}[256];"
        for name in sorted(string_variables)
    ]
    lines += [
        f"static char {c_name(name)}__text[{TEXT_LIST_CAP}][256];"
        for name in sorted(TEXT_LISTS)
    ]
    lines += [
        f"static double {c_name(name)}[{size}];"
        for name, size in sorted(arrays.items())
    ]
    model_lines = _gltf.definitions()
    if model_lines:
        lines.extend(model_lines)
    if any(fn.local_arrays for fn in functions.values()):
        lines.extend(
            [
                f"#define ANVIL_LOCAL_ARRAY_BUDGET_BYTES "
                f"{MAX_ACTIVE_LOCAL_ARRAY_BYTES}u",
                "static size_t anvil_active_local_array_bytes;",
                "static double *anvil_local_array_alloc(size_t count, "
                "const char *path, int line) {",
                "    const size_t bytes = count * sizeof(double);",
                "    if (bytes > ANVIL_LOCAL_ARRAY_BUDGET_BYTES - "
                "anvil_active_local_array_bytes) {",
                '        fprintf(stderr, "%s:%d: active local arrays exceed the '
                '%u MiB Anvil memory limit\\n", path, line, '
                "ANVIL_LOCAL_ARRAY_BUDGET_BYTES / (1024u * 1024u));",
                "        exit(2);",
                "    }",
                "    double *values = (double *)calloc(count, sizeof(double));",
                "    if (!values) {",
                '        fprintf(stderr, "%s:%d: unable to allocate local array '
                '(%zu bytes)\\n", path, line, bytes);',
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
            ]
        )
    for name, fn in functions.items():
        if name in ("draw", "update") and fn.params:
            raise CompileError(
                f"{fn.source or path}:{fn.line}: engine callback '{name}' cannot have parameters"
            )
        text_params = getattr(fn, "text_params", set())
        params = (
            ", ".join(
                f"{'const char *' if param in text_params else 'double'} "
                f"{c_name(name + '__' + param)}"
                for param in fn.params
            )
            or "void"
        )
        result_type = (
            "const char *" if getattr(fn, "returns_text", False) else "double"
        )
        lines.append(f"static {result_type} {c_name(name)}({params});")
    lines.append("")
    for name, fn in functions.items():
        text_params = getattr(fn, "text_params", set())
        params = (
            ", ".join(
                f"{'const char *' if param in text_params else 'double'} "
                f"{c_name(name + '__' + param)}"
                for param in fn.params
            )
            or "void"
        )
        result_type = (
            "const char *" if getattr(fn, "returns_text", False) else "double"
        )
        lines.append(f"static {result_type} {c_name(name)}_body({params}) {{")
        lines.extend(
            f"    double {c_name(name + '__' + local)} = 0.0;"
            for local in sorted(fn.locals)
        )
        lines.extend(
            f"    double *{c_name(name + '__' + local)} = "
            f"anvil_local_array_alloc({size}, {json.dumps(str(fn.source or path))}, "
            f"{fn.local_array_lines[local]});"
            for local, size in sorted(fn.local_arrays.items())
        )
        previous_strings = set(STRING_VARIABLES)
        set_string_variables(previous_strings | text_params)
        try:
            body = emit_nodes(path, fn.body, functions, "    ", fn, arrays)
        finally:
            set_string_variables(previous_strings)
        lines.extend(body)
        if not any(n.kind == "output" for n in fn.body):
            lines.extend(local_array_cleanup(fn, "    "))
            lines.append(
                '    return "";' if getattr(fn, "returns_text", False) else "    return 0.0;"
            )
        lines.append("}")
        arguments = ", ".join(c_name(name + "__" + param) for param in fn.params)
        lines.append(f"static {result_type} {c_name(name)}({params}) {{")
        lines.append("    anvil_frame_enter();")
        lines.append(f"    {result_type} result = {c_name(name)}_body({arguments});")
        lines.append("    anvil_frame_leave();")
        lines.append("    return result;")
        lines.extend(["}", ""])
    # Setup commands and initial values run before callbacks.
    setup = [
        n
        for n in top
        if n.kind
        in (
            "set",
            "say",
            "write",
            "wait",
            "press_enter",
            "ask",
            "scene",
            "camera",
            "camera_fov",
            "camera_control",
            "clear",
            "seed",
            "net_host",
            "net_ip",
            "net_leave",
            "net_join",
        )
    ]
    calls = [n for n in top if n.kind == "call"]
    invalid = [
        n
        for n in top
        if n.kind
        not in (
            "set",
            "say",
            "write",
            "wait",
            "press_enter",
            "ask",
            "scene",
            "camera",
            "camera_fov",
            "camera_control",
            "clear",
            "seed",
            "net_host",
            "net_ip",
            "net_leave",
            "net_join",
            "call",
            "import",
            "library_import",
        )
    ]
    if invalid:
        raise CompileError(
            f"{invalid[0].source or path}:{invalid[0].line}: only configuration, initial values, "
            "and calls are allowed at top level"
        )
    for n in calls:
        if n.name not in functions:
            raise CompileError(
                f"{n.source or path}:{n.line}: unknown function {n.name!r}"
                f"{suggestion_suffix(n.name, functions)}"
            )
        if len(split_args(n.value)) != len(functions[n.name].params):
            raise CompileError(
                f"{n.source or path}:{n.line}: function {n.name!r} expects "
                f"{len(functions[n.name].params)} argument(s), "
                f"got {len(split_args(n.value))}"
            )
    has_engine = (
        any(
            n.kind in ("scene", "camera", "camera_fov", "camera_control", "clear")
            for n in setup
        )
        or "draw" in functions
        or "update" in functions
    )
    if has_engine and "main" in functions and functions["main"].params:
        raise CompileError(
            f"{functions['main'].source or path}:{functions['main'].line}: main cannot have parameters "
            "when used as an engine callback program"
        )
    if not has_engine and not calls and "main" in functions and functions["main"].params:
        raise CompileError(
            f"{functions['main'].source or path}:{functions['main'].line}: main function parameters "
            "require an explicit call with arguments"
        )
    from compiler.modules import reachable_functions, reachable_storage

    emitted_functions = reachable_functions(functions, top, graphical=has_engine)
    emitted_variables, emitted_arrays = reachable_storage(
        top, emitted_functions, variables, arrays
    )
    function_bodies = {
        name: emit_nodes(path, fn.body, functions, "    ", fn, arrays)
        for name, fn in functions.items()
    }
    setup_body = emit_nodes(path, setup, functions, "    ", arrays=arrays)
    calls_body = emit_nodes(path, calls, functions, "    ", arrays=arrays)
    reachable_c_body = [setup_body, calls_body] + [
        function_bodies[name] for name, _fn in emitted_functions
    ]
    reachable_statements = [
        mask_strings(statement)
        for body in reachable_c_body
        for statement in body
    ]
    selected_runtime_modules = {
        name
        for name, module in RUNTIME_MODULES.items()
        if any(
            re.search(pattern, statement)
            for pattern in module.trigger_patterns
            for statement in reachable_statements
        )
    }
    lines = [
        "/* Generated from Anvil source. The .ANVL source remains the program. */",
        '#include "anvil_runtime.h"',
        "#include <math.h>",
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "",
    ]
    runtime_markers = [
        f"/* ANVIL_RUNTIME_MODULE: {name} */"
        for name in sorted(selected_runtime_modules)
    ]
    lines[1:1] = runtime_markers
    metadata_payload=pack(metadata)
    if metadata_payload:
        lines.append('static const char _anvil_metadata_blob[] = '+c_bytes_literal(metadata_payload)+';')
    lines += [f"static double {c_name(name)};" for name in sorted(emitted_variables)]
    lines += [f'static double {c_name(name)};' for node in top for name in sorted(node.c_temporaries)]
    lines += [
        f"static double {c_name(name)}[{size}];"
        for name, size in sorted(arrays.items())
        if name in emitted_arrays
    ]
    if any(fn.local_arrays for _name, fn in emitted_functions):
        lines.extend(
            [
                f"#define ANVIL_LOCAL_ARRAY_BUDGET_BYTES "
                f"{active_local_array_bytes}u",
                "static size_t anvil_active_local_array_bytes;",
                "static double *anvil_local_array_alloc(size_t count, "
                "const char *path, int line) {",
                "    const size_t bytes = count * sizeof(double);",
                "    if (bytes > ANVIL_LOCAL_ARRAY_BUDGET_BYTES - "
                "anvil_active_local_array_bytes) {",
                '        fprintf(stderr, "%s:%d: active local arrays exceed the '
                '%u MiB Anvil memory limit\\n", path, line, '
                "ANVIL_LOCAL_ARRAY_BUDGET_BYTES / (1024u * 1024u));",
                "        exit(2);",
                "    }",
                "    double *values = (double *)calloc(count, sizeof(double));",
                "    if (!values) {",
                '        fprintf(stderr, "%s:%d: unable to allocate local array '
                '(%zu bytes)\\n", path, line, bytes);',
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
            ]
        )
    for name, fn in emitted_functions:
        if name in ("draw", "update") and fn.params:
            raise CompileError(
                f"{fn.source or path}:{fn.line}: engine callback '{name}' cannot have parameters"
            )
        params = (
            ", ".join(f"double {c_name(name + '__' + param)}" for param in fn.params)
            or "void"
        )
        lines.append(f"static double {c_name(name)}({params});")
    lines.append("")
    for name, fn in emitted_functions:
        params = (
            ", ".join(f"double {c_name(name + '__' + param)}" for param in fn.params)
            or "void"
        )
        lines.append(f"static double {c_name(name)}({params}) {{")
        lines.extend(
            f"    double {c_name(name + '__' + local)} = 0.0;"
            for local in sorted(fn.locals | fn.c_temporaries)
        )
        lines.extend(
            f"    double *{c_name(name + '__' + local)} = "
            f"anvil_local_array_alloc({size}, {c_string_literal(str(fn.source or path))}, "
            f"{fn.local_array_lines[local]});"
            for local, size in sorted(fn.local_arrays.items())
        )
        body = function_bodies[name]
        lines.extend(body)
        if not any(n.kind == "output" for n in fn.body):
            lines.extend(local_array_cleanup(fn, "    "))
            lines.append("    return 0.0;")
        lines.extend(["}", ""])
    lines.append("int main(void) {")
    # Binary stdout keeps the bytes identical to the native backend (which writes
    # through WriteFile and never translates newlines) and to a redirected file.
    lines.append("#ifdef _WIN32")
    lines.append("    _setmode(_fileno(stdout), _O_BINARY);")
    lines.append("#endif")
    lines.append(f"    anvil_set_fixed_hz({fixed_hz});")
    lines.append(
        f"    anvil_set_project({json.dumps(project_name, ensure_ascii=True)});"
    )
    lines.extend(emit_nodes(path, setup, functions, "    ", arrays=arrays))
    if has_engine:
        lines.append(f"    anvil_set_fixed_hz({fixed_hz});")
    lines.extend(setup_body)
    if has_engine:
        lines.extend(calls_body)
        lines.append(
            f"    anvil_run({c_name('update') if 'update' in functions else 'NULL'}, "
            f"{c_name('draw') if 'draw' in functions else 'NULL'}, "
            f"{c_string_literal(project_name)});"
        )
    elif calls:
        for n in calls:
            values = [expr(n.source or path, n.line, arg, functions) for arg in split_args(n.value)]
            call = f"{c_name(n.name)}({', '.join(values)})"
            kinds = set(_walk_kinds(functions["main"].body)) if n.name == "main" else set()
            if n.name == "main" and ("say" in kinds or "write" in kinds or "ask" in kinds) and "output" not in kinds:
                # A main that only talks must not trail a stray "0" return value.
                lines.append(f"    (void){call};")
            elif n.name == "main":
                lines.append(f'    printf("%s\\n", anvil_format_number({call}));')
            else:
                lines.append(f"    (void){call};")
    elif "main" in functions:
        if functions["main"].params:
            raise CompileError(
                f"{functions['main'].source or path}:{functions['main'].line}: main function parameters "
                "require an explicit call with arguments"
            )
        kinds = set(_walk_kinds(functions["main"].body))
        if ("say" in kinds or "write" in kinds or "ask" in kinds) and "output" not in kinds:
            # Implicit entry follows the same rule as `call fn(main)`.
            lines.append(f"    (void){c_name('main')}();")
        else:
            lines.append(f'    printf("%s\\n", anvil_format_number({c_name("main")}()));')
    lines.append("    anvil_net_close();")
    lines.extend(["    return 0;", "}", ""])
    from compiler.semantics import validate_program
    from compiler.common import ParsedProgram
    validate_program(ParsedProgram(path, functions, top, variables, arrays, [], []))
    return "\n".join(lines)
