"""Libraries on disk: one function per file, one folder per library.

A program says ``library import math``; the compiler looks for a folder named
``libraries-math`` (or ``libraries/math``) beside the entry file, and treats each
``<name>.ANVL`` inside it as the function ``<name>``. Only the functions the
program actually calls reach the output, because reachability already prunes
everything else.
"""

from __future__ import annotations

import pathlib

from compiler.common import CompileError


def folder_for(entry: pathlib.Path, name: str) -> pathlib.Path | None:
    """Where a library named ``name`` lives, if it exists."""
    base = entry.resolve().parent
    for candidate in (base / f"libraries-{name}", base / "libraries" / name):
        if candidate.is_dir():
            return candidate
    return None


def load(entry: pathlib.Path, name: str, where: str, line: int):
    """Parse every file in the library, returning (function name, node) pairs."""
    from compiler.parser import parse

    folder = folder_for(entry, name)
    if folder is None:
        raise CompileError(
            f"{where}:{line}: library {name!r} not found; expected a folder named "
            f"libraries-{name} or libraries/{name} beside {entry.name}"
        )
    files = sorted(folder.glob("*.ANVL"))
    if not files:
        raise CompileError(
            f"{where}:{line}: library {name!r} has no .ANVL files in {folder}"
        )
    found = []
    for file in files:
        source = file.read_text(encoding="utf-8", errors="replace")
        functions, _, _, _ = parse(file, source)
        stem = file.stem
        if stem not in functions:
            raise CompileError(
                f"{file}: a library file must define the function {stem!r} "
                f"(one function per file)"
            )
        if len(functions) > 1:
            extra = ", ".join(sorted(set(functions) - {stem}))
            raise CompileError(
                f"{file}: a library file holds one function, but this one also "
                f"defines {extra}"
            )
        found.append((stem, functions[stem]))
    return found
