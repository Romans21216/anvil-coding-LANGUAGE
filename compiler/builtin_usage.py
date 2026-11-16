"""Which builtins a program actually uses, resolved automatically.

``import builtins`` states the intent; this module is what makes the compiler
work out the real answer. It walks the reachable program, finds every call to a
builtin name, and returns the sorted set. Both backends already emit runtime
helpers on demand, so the answer is what they must provide — and ``--print-imports``
prints it so a build can be audited.
"""

from __future__ import annotations

import re

_TEXT_BUILTINS = {
    "len", "upper", "lower", "ord", "chr", "trim", "number", "char",
    "contains", "mid", "left", "right", "starts_with", "ends_with",
}
_MATH_BUILTINS = {
    "abs", "sqrt", "floor", "ceil", "min", "max", "round", "sin", "cos",
    "memory_images", "memory_audio", "memory_video", "memory_total",
    "noise", "fbm",
}
_RANDOM_BUILTINS = {"rnd", "random"}

MODULE_MEMBERS = {
    "math": _MATH_BUILTINS,
    "text": _TEXT_BUILTINS,
    "random": _RANDOM_BUILTINS,
}

BUILTIN_MODULES = {
    "builtins": "every builtin in the language",
    "math": "numeric builtins (abs, floor, ceil, sqrt, sin, cos, min, max, ...)",
    "text": "text builtins (len, upper, lower, trim, mid, char, contains, ...)",
    "random": "rnd, random, seed",
}

_CALL = re.compile(r"\b([A-Za-z_][\w]*)\s*\(")


def _body_text(body) -> str:
    """Flatten a function body into source text for a name scan."""
    parts = []
    for node in body:
        for attribute in ("value", "name"):
            raw = getattr(node, attribute, None)
            if isinstance(raw, str):
                parts.append(raw)
        for attribute in ("params", "args", "items"):
            raw = getattr(node, attribute, None)
            if isinstance(raw, (list, tuple)):
                parts.extend(str(item) for item in raw)
        nested = getattr(node, "body", None)
        if isinstance(nested, list):
            parts.append(_body_text(nested))
    return "\n".join(parts)


def used_builtins(functions, top) -> list[str]:
    """Every builtin the program calls, sorted, from reachable code only."""
    from compiler.expressions import BUILTINS
    from compiler.modules import reachable_functions

    graphical = (
        "draw" in functions
        or "update" in functions
        or any(getattr(node, "kind", "") == "scene" for node in top)
    )
    reachable = reachable_functions(
        functions, top, graphical=graphical, extra=("random-pipeline",)
    )
    text = [_body_text(top)]
    text.extend(_body_text(function.body) for _, function in reachable)
    found = set()
    for chunk in text:
        for match in _CALL.finditer(chunk):
            name = match.group(1)
            if name in BUILTINS:
                found.add(name)
    return sorted(found)


def describe(module: str) -> str:
    return BUILTIN_MODULES.get(module, "")


def module_is_used(module: str, used) -> bool:
    """True when the import earns its place in the program."""
    used = set(used)
    if module == "builtins":
        return bool(used)
    return bool(used & MODULE_MEMBERS.get(module, set()))


def unused_imports(functions, top):
    """The ``import`` nodes whose module contributes nothing to the build."""
    used = used_builtins(functions, top)
    return [
        node
        for node in top
        if getattr(node, "kind", "") == "import"
        and not module_is_used(getattr(node, "value", ""), used)
    ]
