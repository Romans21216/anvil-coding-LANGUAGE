"""Rust-style lints: dead code and locals nobody reads.

Both are warnings rather than errors — the program still builds — and both are
fatal under ``--deny-warnings``, so a project can insist on a clean report.
"""

from __future__ import annotations

import re

_LOCAL_READ = re.compile(r"local\(([A-Za-z_][\w-]*)\)")


def _children(node):
    body = getattr(node, "body", None)
    return body if isinstance(body, list) else []


def _walk(nodes):
    for node in nodes:
        yield node
        for child in _children(node):
            yield from _walk([child])


def _text_of(node) -> str:
    parts = []
    for attribute in ("value", "name", "items", "args", "params"):
        raw = getattr(node, attribute, None)
        if isinstance(raw, str):
            parts.append(raw)
        elif isinstance(raw, (list, tuple)):
            parts.extend(str(item) for item in raw)
    return "\n".join(parts)


def unreachable(functions):
    """(dead statement, terminator kind) for code that can never run."""
    found = []
    for function in functions.values():
        found.extend(_unreachable_in(function.body))
    return found


def _unreachable_in(nodes) -> list:
    dead = []
    for index, node in enumerate(nodes):
        if node.kind in ("output", "stop") and index + 1 < len(nodes):
            dead.append((nodes[index + 1], node.kind))
            break
    for node in nodes:
        dead.extend(_unreachable_in(_children(node)))
    return dead


def unused_locals(functions):
    """(node, name) for every ``set local`` that nothing ever reads."""
    found = []
    for function in functions.values():
        defined = {}
        mentioned = set()
        for node in _walk(function.body):
            if node.kind == "local_set" and getattr(node, "name", ""):
                defined.setdefault(node.name, node)
            for match in _LOCAL_READ.finditer(_text_of(node)):
                mentioned.add(match.group(1))
        for name, node in defined.items():
            if name not in mentioned:
                found.append((node, name))
    return found


_DIVIDE_BY_ZERO = re.compile(r"[%/]\s*0+(?:\.0*)?\s*(?=[),;]|$)")


def divides_by_zero(functions, top):
    """(node, operator) where a divisor is the literal constant zero."""
    found = []
    nodes = list(top)
    for function in functions.values():
        nodes.extend(_walk(function.body))
    for node in nodes:
        text = _text_of(node)
        match = _DIVIDE_BY_ZERO.search(text)
        if match:
            found.append((node, match.group(0)[0]))
    return found


def _has_output(body) -> bool:
    return any(node.kind == "output" for node in _walk(body))


def silent_zero_calls(functions, top):
    """Calls that use a function with no output as if it returned a value.

    A function without ``output`` still runs, and its value is 0. Using that as
    a number is almost always a missing ``output`` rather than a zero.
    """
    warnings = []
    silent = {
        name for name, function in functions.items() if not _has_output(function.body)
    }
    if not silent:
        return warnings
    nodes = list(top)
    for function in functions.values():
        nodes.extend(_walk(function.body))
    for node in nodes:
        if getattr(node, "kind", "") == "call":
            continue   # a bare call statement discards the value on purpose
        text = _text_of(node)
        for name in sorted(silent):
            if re.search(r"call\s+fn\(\s*" + re.escape(name) + r"\b", text):
                warnings.append(
                    (
                        f"function '{name}' has no output, so this call yields 0",
                        node,
                    )
                )
    return warnings


def _body_text(body) -> str:
    return "\n".join(_text_of(node) for node in _walk(body))


ENTRY_POINTS = ("main", "draw", "update")


def unused_functions(functions, top, entry=None):
    """Functions nothing calls (the engine callbacks and main excepted).

    Only the entry file is checked: an include or the stdlib is shared code, and
    a function there may be meant for a caller that lives elsewhere.
    """
    from compiler.modules import called_functions

    called = set(called_functions(top))
    for function in functions.values():
        called |= called_functions(function.body)
    return [
        function
        for name, function in functions.items()
        if name not in called
        and name not in ENTRY_POINTS
        and (entry is None or getattr(function, "source", None) == entry)
    ]


def unused_parameters(functions, entry=None):
    """(function, parameter) pairs the body never reads."""
    found = []
    for name, function in functions.items():
        if name in ENTRY_POINTS:
            continue   # callbacks keep their signature by contract
        if entry is not None and getattr(function, "source", None) != entry:
            continue
        text = _body_text(function.body)
        for index, parameter in enumerate(function.params):
            if index == 0 and parameter == "main":
                continue
            if not re.search(r"var\(\s*" + re.escape(parameter) + r"\s*\)", text):
                found.append((function, parameter))
    return found


def _literal_number(text: str):
    value = text.strip()
    try:
        return float(value)
    except ValueError:
        return None


def empty_for_loops(functions, top):
    """``for`` loops whose literal range can never run."""
    warnings = []
    nodes = list(top)
    for function in functions.values():
        nodes.extend(_walk(function.body))
    for node in nodes:
        if node.kind != "for" or len(node.params) < 2:
            continue
        start = _literal_number(node.params[0])
        end = _literal_number(node.params[1])
        step = _literal_number(node.params[2]) if len(node.params) > 2 else 1.0
        if start is None or end is None or step is None:
            continue
        if step == 0:
            warnings.append(("for loop never runs: step is 0", node))
        elif (step > 0 and start > end) or (step < 0 and start < end):
            warnings.append(
                (f"for loop never runs: {start:g} to {end:g} step {step:g}", node)
            )
    return warnings


_NUMBER_LITERAL = __import__("re").compile(r'number\(\s*"([^"]*)"\s*\)')


def bad_number_literals(functions, top):
    """``number("...")`` calls whose literal argument is not a number."""
    warnings = []
    nodes = list(top)
    for function in functions.values():
        nodes.extend(_walk(function.body))
    for node in nodes:
        for match in _NUMBER_LITERAL.finditer(_text_of(node)):
            text = match.group(1)
            try:
                float(text.strip())
            except ValueError:
                warnings.append(
                    (f'number("{text}") is not a number, so it evaluates to 0', node)
                )
    return warnings


_VAR_READ = __import__("re").compile(r"var\(\s*([A-Za-z_][\w-]*)\s*\)")


def unused_globals(functions, top):
    """Globals that are assigned but never read anywhere in the program."""
    nodes = list(top)
    for function in functions.values():
        nodes.extend(_walk(function.body))
    writes = {}
    reads = set()
    for node in nodes:
        if node.kind == "set" and getattr(node, "name", ""):
            writes.setdefault(node.name, node)
        for match in _VAR_READ.finditer(_text_of(node)):
            reads.add(match.group(1))
    return [
        (node, name)
        for name, node in writes.items()
        if name not in reads
        # Anvil has no expression statements, so `set var(x) = some_call()` is the
        # only way to call for effect; a discarded result there is intentional.
        and "(" not in str(getattr(node, "value", ""))
    ]


_SCENE_STATEMENTS = {"display", "clear", "camera", "camera_fov", "camera_control"}


def scene_statements_without_scene(functions, top):
    """Drawing or camera statements in a program that never declares a scene."""
    if any(getattr(node, "kind", "") == "scene" for node in top):
        return []
    nodes = list(top)
    for function in functions.values():
        nodes.extend(_walk(function.body))
    return [
        (f"{node.kind} has no effect without a scene 2d program", node)
        for node in nodes
        if getattr(node, "kind", "") in _SCENE_STATEMENTS
    ]


def report(functions, top=(), entry=None) -> list[tuple[str, object]]:
    """Warnings as (message, node) pairs, ready for the CLI to render."""
    warnings = []
    for node, terminator in unreachable(functions):
        warnings.append((f"unreachable statement after {terminator}", node))
    for node, name in unused_locals(functions):
        warnings.append((f"unused local '{name}'", node))
    for node, operator in divides_by_zero(functions, top):
        what = "division by zero" if operator == "/" else "remainder by zero"
        warnings.append((what, node))
    warnings.extend(silent_zero_calls(functions, top))
    warnings.extend(empty_for_loops(functions, top))
    warnings.extend(bad_number_literals(functions, top))
    warnings.extend(scene_statements_without_scene(functions, top))
    for node, name in unused_globals(functions, top):
        warnings.append((f"global '{name}' is never read", node))
    for function in unused_functions(functions, top, entry):
        warnings.append((f"function '{function.name}' is never called", function))
    for function, parameter in unused_parameters(functions, entry):
        warnings.append(
            (f"parameter '{parameter}' of '{function.name}' is never used", function)
        )
    return warnings
