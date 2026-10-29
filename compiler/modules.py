"""Bounded local include resolution and native function dependency discovery."""

from __future__ import annotations

import json
from pathlib import Path
import re

from compiler.common import CompileError, IDENTIFIER, FUNCTION_REFERENCE
from compiler.lexer import mask_strings

MAX_INCLUDE_FILES = 256
MAX_INCLUDE_DEPTH = 64
MAX_SOURCE_BYTES = 4 * 1024 * 1024


def include_name(raw, path, line):
    try:
        name = json.loads(raw)
    except (ValueError, TypeError) as error:
        raise CompileError(f'{path}:{line}: include expects a quoted relative .ANVL path') from error
    if not isinstance(name, str) or not name or any(ord(char) < 32 for char in name):
        raise CompileError(f'{path}:{line}: include expects a quoted relative .ANVL path')
    relative = Path(name)
    if relative.is_absolute() or relative.drive or relative.root or relative.suffix.lower() != ".anvl":
        raise CompileError(f'{path}:{line}: include requires a relative .ANVL file')
    return relative


def include_spec(raw, path, line):
    """Return selected function, public alias and the original quoted path."""
    if not raw.startswith("fn("):
        include_name(raw, path, line)
        return "", "", raw
    match = re.fullmatch(rf'fn\(\s*({IDENTIFIER})\s*\)\s+-\s+("(?:\\.|[^"\\])*")(?:\s+as\s+({IDENTIFIER}))?', raw)
    if not match:
        raise CompileError(f'{path}:{line}: expected include fn(name) - "file.ANVL" [as alias]')
    relative = include_name(match[2], path, line)
    alias = match[3] or relative.stem
    if not re.fullmatch(IDENTIFIER, alias):
        raise CompileError(f"{path}:{line}: filename needs an explicit 'as alias' identifier")
    return match[1], alias, match[2]


def load_program(path, source, *, include_root=None):
    from compiler.module_loader import ProgramLoader
    return ProgramLoader(path, include_root).load(source)


def called_functions(nodes):
    """Collect explicit calls, excluding call-like text inside string literals."""
    result = set()
    pending = list(nodes)
    while pending:
        node = pending.pop()
        if node.kind == "call":
            result.add(node.name)
        for text in [node.value] + node.params:
            unquoted = mask_strings(text)
            for match in re.finditer(rf'\bcall\s+fn\(\s*({FUNCTION_REFERENCE})(?=\s*[,\)])', unquoted):
                result.add(match[2] + (" - " + match[3] if match[3] else ""))
        pending.extend(node.body)
        pending.extend(node.otherwise)
    return result


def reachable_functions(functions, top, *, graphical):
    needed = called_functions(top)
    needed.update(name for name in (("draw", "update") if graphical else ("main",)) if name in functions)
    pending = list(needed)
    while pending:
        name = pending.pop()
        if name not in functions:
            continue  # normal code generation reports the original call location
        for dependency in called_functions(functions[name].body) - needed:
            needed.add(dependency)
            pending.append(dependency)
    return [(name, fn) for name, fn in functions.items() if name in needed]
