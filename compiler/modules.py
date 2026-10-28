"""Bounded local include resolution and native function dependency discovery."""

from __future__ import annotations

import json
from pathlib import Path
import re

from compiler.common import ArrayDeclarations, CompileError, ParsedProgram
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
    if relative.is_absolute() or relative.drive or relative.suffix.lower() != ".anvl":
        raise CompileError(f'{path}:{line}: include requires a relative .ANVL file')
    return relative


def load_program(path, source, *, include_root=None):
    from compiler.parser import parse_syntax

    path = Path(path)
    root = Path(include_root).resolve() if include_root is not None else path.resolve().parent
    result = ParsedProgram(path, {}, [], set(), ArrayDeclarations(), [], [])
    seen = set()
    active = []
    total_bytes = 0

    def visit(unit_path, text, origin=None):
        nonlocal total_bytes
        canonical = unit_path.resolve()
        where = f"{origin.source}:{origin.line}" if origin is not None else str(unit_path)
        if canonical in active:
            chain = " -> ".join(str(item) for item in active + [canonical])
            raise CompileError(f"{where}: include cycle: {chain}")
        if canonical in seen:
            return
        if len(active) >= MAX_INCLUDE_DEPTH:
            raise CompileError(f"{where}: include nesting exceeds {MAX_INCLUDE_DEPTH} files")
        if len(seen) >= MAX_INCLUDE_FILES:
            raise CompileError(f"{where}: include graph exceeds {MAX_INCLUDE_FILES} files")
        if text is None:
            try:
                with canonical.open("rb") as stream:
                    payload = stream.read(MAX_SOURCE_BYTES - total_bytes + 1)
                if len(payload) + total_bytes > MAX_SOURCE_BYTES:
                    raise CompileError(f"{where}: include source exceeds the 4 MiB budget")
                text = payload.decode("utf-8-sig")
            except (OSError, UnicodeError) as error:
                raise CompileError(f"{where}: cannot read include {canonical}: {error}") from error
            source_bytes = len(payload)
        else:
            source_bytes = len(text.encode("utf-8"))
        total_bytes += source_bytes
        if total_bytes > MAX_SOURCE_BYTES:
            raise CompileError(f"{where}: include source exceeds the 4 MiB budget")
        unit = parse_syntax(unit_path, text)
        seen.add(canonical)
        active.append(canonical)
        for name, function in unit.functions.items():
            if name in result.functions:
                previous = result.functions[name]
                raise CompileError(f"{unit_path}:{function.line}: duplicate function {name!r}; already declared at {previous.source}:{previous.line}")
            result.functions[name] = function
        for name, size in unit.arrays.items():
            if name in result.arrays:
                previous_path, previous_line = result.arrays.locations[name]
                raise CompileError(f"{unit_path}:{unit.arrays.locations[name][1]}: duplicate array {name!r}; already declared at {previous_path}:{previous_line}")
            result.arrays[name] = size
            result.arrays.locations[name] = unit.arrays.locations[name]
        result.variables.update(unit.variables)
        result.variable_references.extend(unit.variable_references)
        result.local_references.extend(unit.local_references)
        for node in unit.top:
            if node.kind == "include":
                relative = include_name(node.value, unit_path, node.line)
                target = (canonical.parent / relative).resolve()
                try:
                    target.relative_to(root)
                except ValueError as error:
                    raise CompileError(f"{unit_path}:{node.line}: include must resolve inside {root}") from error
                visit(target, None, node)
            else:
                result.top.append(node)
        active.pop()

    visit(path, source)
    return result


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
            result.update(re.findall(r'\bcall\s+fn\(\s*([A-Za-z_][\w-]*)', unquoted))
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
