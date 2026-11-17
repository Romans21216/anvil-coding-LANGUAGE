"""Compile-time warnings: code that builds but cannot do what it says.

Each warning carries the same `path:line: message` shape as a CompileError and
is rendered by compiler.diagnostics, so warnings and errors look alike and a
build still succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Warning:
    message: str
    hint: str | None = None
    needle: str | None = None


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.body)
        yield from _walk(node.otherwise)


def _draw_statements(functions, top):
    nodes = list(_walk(top))
    for function in functions.values():
        nodes.extend(_walk(function.body))
    return [n for n in nodes if n.kind in ("display", "clear", "camera", "camera_fov")]


def _output_warnings(nodes, inside_loop, out):
    for position, node in enumerate(nodes):
        if node.kind == "output":
            if inside_loop:
                out.append(
                    Warning(
                        f"{node.source}:{node.line}: `output` returns from the function, "
                        "so this loop runs at most once",
                        hint="keep a result variable and `output` after the loop; "
                             "Anvil has no `break`",
                        needle="output",
                    )
                )
            if position + 1 < len(nodes):
                following = nodes[position + 1]
                out.append(
                    Warning(
                        f"{following.source}:{following.line}: unreachable statement "
                        "after `output`",
                        hint="`output` returns immediately; delete this line or move it "
                             "above the `output`",
                        needle=following.value or following.name or None,
                    )
                )
                break
        _output_warnings(node.body, inside_loop or node.kind in ("while", "for"), out)
        _output_warnings(node.otherwise, inside_loop, out)


def lint(functions, top) -> list[Warning]:
    """Return every warning worth showing for this program."""
    warnings: list[Warning] = []

    has_engine = (
        any(n.kind in ("scene", "camera", "camera_fov", "camera_control", "clear") for n in top)
        or "draw" in functions
        or "update" in functions
    )
    if not has_engine:
        draws = _draw_statements(functions, top)
        if draws:
            first = draws[0]
            what = "display" if first.kind == "display" else first.kind
            warnings.append(
                Warning(
                    f"{first.source}:{first.line}: `{what}` has no effect without a scene "
                    "or a draw callback",
                    hint="add `scene 2d` and a `fn(draw)` callback, or remove the draw call",
                    needle=first.value.strip() if first.value else None,
                )
            )

    for function in functions.values():
        _output_warnings(function.body, False, warnings)
    _output_warnings(top, False, warnings)
    return warnings
