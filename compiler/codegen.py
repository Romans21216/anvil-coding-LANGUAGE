"""C backend: lower validated Anvil nodes into runtime calls and C source."""

from __future__ import annotations

import json
import pathlib
import re

from compiler.common import (
    MAX_ACTIVE_LOCAL_ARRAY_BYTES,
    CompileError,
    Node,
    array_code,
    array_size,
    c_name,
    variable_code,
)
from compiler.expressions import expr, split_args


def rgb_style(
    raw: str,
    path: pathlib.Path,
    line: int,
    functions: dict[str, Node],
    scope: Node | None = None,
    arrays: dict[str, int] | None = None,
) -> tuple[list[str], str]:
    color = ["255", "255", "255", "255"]
    m = re.search(r"-rgba?\(([^)]*)\)", raw)
    if m:
        vals = split_args(m.group(1))
        if len(vals) not in (3, 4):
            raise CompileError(f"{path}:{line}: -rgb/-rgba expects 3 or 4 values")
        color = [
            expr(path, line, v, functions, scope=scope, arrays=arrays) for v in vals
        ]
        if len(color) == 3:
            color.append("255")
    raw = re.sub(r"\s+-rgba?\([^)]*\)", "", raw)
    return color, raw


def emit_display(
    path: pathlib.Path,
    node: Node,
    ind: str,
    functions: dict[str, Node],
    scope: Node | None = None,
    arrays: dict[str, int] | None = None,
) -> str:
    raw = node.value.strip()
    color, raw = rgb_style(raw, path, node.line, functions, scope, arrays)
    rot = ["0", "0", "0"]
    rm = re.search(r"-rotate\(((?:[^()]|\([^()]*\))*)\)", raw)
    if rm:
        rot = [
            expr(path, node.line, v, functions, scope=scope, arrays=arrays)
            for v in split_args(rm.group(1))
        ]
        if len(rot) != 3:
            raise CompileError(f"{path}:{node.line}: -rotate expects x,y,z")
        raw = raw.replace(rm.group(0), "")
    loc = None
    lm = re.search(r"-l\(((?:[^()]|\([^()]*\))*)\)", raw)
    if lm:
        loc = [
            expr(path, node.line, v, functions, scope=scope, arrays=arrays)
            for v in split_args(lm.group(1))
        ]
        if len(loc) != 2:
            raise CompileError(f"{path}:{node.line}: -l expects x,y")
        raw = raw.replace(lm.group(0), "")
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
                path, node.line, dynamic.group(2), functions, scope=scope, arrays=arrays
            )
            separator = "" if prefix.endswith((" ", "\t")) else " "
            fmt = prefix + separator + '%.0f"'
            return (
                f"{ind}anvil_text_number({', '.join(loc)}, {fmt}, {value}, "
                f"{', '.join(color)});"
            )
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


def emit_nodes(
    path: pathlib.Path,
    nodes: list[Node],
    functions: dict[str, Node],
    indent: str,
    scope: Node | None = None,
    arrays: dict[str, int] | None = None,
) -> list[str]:
    arrays = arrays or {}
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
        )

    source_path = json.dumps(str(path))
    for n in nodes:
        if n.kind == "set":
            out.append(f"{indent}{variable_code(n.name, scope)} = {lower(n)};")
        elif n.kind == "local_set":
            out.append(f"{indent}{c_name(scope.name + '__' + n.name)} = {lower(n)};")
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
        elif n.kind in ("add", "sub"):
            op = "+" if n.kind == "add" else "-"
            target = variable_code(n.name, scope)
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
            value = lower(n)
            if scope is not None and scope.local_arrays:
                out.append(f"{indent}{{")
                out.append(f"{indent}    const double _anvil_return_value = {value};")
                out.extend(local_array_cleanup(scope, indent + "    "))
                out.append(f"{indent}    return _anvil_return_value;")
                out.append(f"{indent}}}")
            else:
                out.append(f"{indent}return {value};")
        elif n.kind == "call":
            if n.name not in functions:
                raise CompileError(f"{path}:{n.line}: unknown function {n.name!r}")
            args = split_args(n.value)
            if len(args) != len(functions[n.name].params):
                raise CompileError(
                    f"{path}:{n.line}: function {n.name!r} expects "
                    f"{len(functions[n.name].params)} argument(s), got {len(args)}"
                )
            values = [lower(n, arg) for arg in args]
            out.append(f"{indent}(void){c_name(n.name)}({', '.join(values)});")
        elif n.kind == "if":
            out.append(f"{indent}if ({lower(n)} != 0.0) {{")
            out.extend(
                emit_nodes(path, n.body, functions, indent + "    ", scope, arrays)
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
            out.append(f"{indent}while ({lower(n)} != 0.0) {{")
            out.extend(
                emit_nodes(path, n.body, functions, indent + "    ", scope, arrays)
            )
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
            out.extend(
                emit_nodes(path, n.body, functions, inner + "        ", scope, arrays)
            )
            out.append(
                f"{inner}        {loop_var} = anvil_check_number("
                f"({loop_var} + {step_var}), {source_path}, {n.line});"
            )
            out.append(f"{inner}    }}")
            out.append(f"{inner}}}")
            out.append(f"{indent}}}")
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
            statement = emit_display(path, n, indent, functions, scope, arrays)
            if "anvil_trace_sphere(" not in statement:
                out.append(f"{indent}anvil_trace_finish();")
            out.append(statement)
        elif n.kind == "seed":
            out.append(f"{indent}anvil_seed((unsigned long long)({lower(n)}));")
        elif n.kind == "net_send":
            out.append(f"{indent}anvil_net_send({lower(n)});")
        elif n.kind == "net_host":
            out.append(f"{indent}(void)anvil_net_host({n.value});")
        elif n.kind == "net_join":
            address, port = n.value.rsplit(",", 1)
            out.append(f"{indent}(void)anvil_net_join({address}, {port});")
    return out


def local_array_cleanup(scope: Node, indent: str) -> list[str]:
    return [
        f"{indent}anvil_local_array_free({c_name(scope.name + '__' + name)}, {size});"
        for name, size in sorted(scope.local_arrays.items())
    ]


def emit_c(
    path: pathlib.Path,
    functions: dict[str, Node],
    top: list[Node],
    variables: set[str],
    arrays: dict[str, int] | None = None,
    fixed_hz: int = 60,
    project_name: str = "Anvil Game",
) -> str:
    arrays = arrays or {}
    lines = [
        "/* Generated from Anvil source. The .ANVL source remains the program. */",
        '#include "anvil_runtime.h"',
        "#include <math.h>",
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "",
    ]
    lines += [f"static double {c_name(name)};" for name in sorted(variables)]
    lines += [
        f"static double {c_name(name)}[{size}];"
        for name, size in sorted(arrays.items())
    ]
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
                f"{path}:{fn.line}: engine callback '{name}' cannot have parameters"
            )
        params = (
            ", ".join(f"double {c_name(name + '__' + param)}" for param in fn.params)
            or "void"
        )
        lines.append(f"static double {c_name(name)}({params});")
    lines.append("")
    for name, fn in functions.items():
        params = (
            ", ".join(f"double {c_name(name + '__' + param)}" for param in fn.params)
            or "void"
        )
        lines.append(f"static double {c_name(name)}({params}) {{")
        lines.extend(
            f"    double {c_name(name + '__' + local)} = 0.0;"
            for local in sorted(fn.locals)
        )
        lines.extend(
            f"    double *{c_name(name + '__' + local)} = "
            f"anvil_local_array_alloc({size}, {json.dumps(str(path))}, "
            f"{fn.local_array_lines[local]});"
            for local, size in sorted(fn.local_arrays.items())
        )
        body = emit_nodes(path, fn.body, functions, "    ", fn, arrays)
        lines.extend(body)
        if not any(n.kind == "output" for n in fn.body):
            lines.extend(local_array_cleanup(fn, "    "))
            lines.append("    return 0.0;")
        lines.extend(["}", ""])
    # Setup commands and initial values run before callbacks.
    setup = [
        n
        for n in top
        if n.kind
        in (
            "set",
            "scene",
            "camera",
            "camera_fov",
            "camera_control",
            "clear",
            "seed",
            "net_host",
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
            "scene",
            "camera",
            "camera_fov",
            "camera_control",
            "clear",
            "seed",
            "net_host",
            "net_join",
            "call",
        )
    ]
    if invalid:
        raise CompileError(
            f"{path}:{invalid[0].line}: only configuration, initial values, "
            "and calls are allowed at top level"
        )
    for n in calls:
        if n.name not in functions:
            raise CompileError(f"{path}:{n.line}: unknown function {n.name!r}")
        if len(split_args(n.value)) != len(functions[n.name].params):
            raise CompileError(
                f"{path}:{n.line}: function {n.name!r} expects "
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
            f"{path}:{functions['main'].line}: main cannot have parameters "
            "when used as an engine callback program"
        )
    lines.append("int main(void) {")
    lines.append(f"    anvil_set_fixed_hz({fixed_hz});")
    lines.extend(emit_nodes(path, setup, functions, "    ", arrays=arrays))
    if has_engine:
        lines.append(
            f"    anvil_run({c_name('update') if 'update' in functions else 'NULL'}, "
            f"{c_name('draw') if 'draw' in functions else 'NULL'}, "
            f"{json.dumps(project_name, ensure_ascii=True)});"
        )
    elif calls:
        for n in calls:
            values = [expr(path, n.line, arg, functions) for arg in split_args(n.value)]
            call = f"{c_name(n.name)}({', '.join(values)})"
            if n.name == "main":
                lines.append(f'    printf("%.15g\\n", {call});')
            else:
                lines.append(f"    (void){call};")
    elif "main" in functions:
        if functions["main"].params:
            raise CompileError(
                f"{path}:{functions['main'].line}: main function parameters "
                "require an explicit call with arguments"
            )
        lines.append(f'    printf("%.15g\\n", {c_name("main")}());')
    lines.append("    anvil_net_close();")
    lines.extend(["    return 0;", "}", ""])
    return "\n".join(lines)
