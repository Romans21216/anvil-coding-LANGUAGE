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
    """Statements that can never run because the block already returned."""
    found = []
    for function in functions.values():
        found.extend(_unreachable_in(function.body))
    return found


def _unreachable_in(nodes) -> list:
    dead = []
    for index, node in enumerate(nodes):
        if node.kind == "output" and index + 1 < len(nodes):
            dead.append(nodes[index + 1])
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


def report(functions) -> list[tuple[str, object]]:
    """Warnings as (message, node) pairs, ready for the CLI to render."""
    warnings = []
    for node in unreachable(functions):
        warnings.append((f"unreachable statement after output", node))
    for node, name in unused_locals(functions):
        warnings.append((f"unused local '{name}'", node))
    return warnings
