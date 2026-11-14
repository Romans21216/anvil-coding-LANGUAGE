"""Libraries on disk: one function per file, one folder per library.

A program says ``library import math``; the compiler looks for a folder named
``libraries-math`` (or ``libraries/math``), starting beside the file that wrote
the line and then walking up its parents, and treats each ``<name>.ANVL`` inside
it as the function ``<name>``. A library file may import another library the same
way. Only the functions the program calls reach the output, because reachability
already prunes everything else.
"""

from __future__ import annotations

import pathlib

from compiler.common import CompileError

# Folders currently being loaded, so a cycle (a imports b, b imports a) is a
# diagnostic instead of an infinite recursion.
_LOADING: list[pathlib.Path] = []


def folder_for(entry: pathlib.Path, name: str) -> pathlib.Path | None:
    """Where a library named ``name`` lives, if it exists.

    The file's own folder wins, then each parent up to a few levels: a library
    file inside ``libraries-a`` should still find ``libraries-b`` at the project
    root, which is where people put them.
    """
    start = entry.resolve().parent
    for base in [start, *start.parents[:8]]:
        for candidate in (base / f"libraries-{name}", base / "libraries" / name):
            if candidate.is_dir():
                return candidate
    return None


def load(entry: pathlib.Path, name: str, where: str, line: int):
    """Parse every file in the library, returning (function name, node) pairs."""
    from compiler.modules import load_program

    folder = folder_for(entry, name)
    if folder is None:
        raise CompileError(
            f"{where}:{line}: library {name!r} not found; expected a folder named "
            f"libraries-{name} or libraries/{name} beside {entry.name} or in a "
            "parent folder"
        )
    if folder in _LOADING:
        chain = " -> ".join(path.name for path in [*_LOADING[_LOADING.index(folder):], folder])
        raise CompileError(f"{where}:{line}: circular library import: {chain}")
    files = sorted(folder.glob("*.ANVL"))
    if not files:
        raise CompileError(
            f"{where}:{line}: library {name!r} has no .ANVL files in {folder}"
        )
    _LOADING.append(folder)
    try:
        return _load_files(files, load_program)
    finally:
        _LOADING.pop()


def _load_files(files, load_program):
    found = []
    seen: set[str] = set()
    for file in files:
        source = file.read_text(encoding="utf-8", errors="replace")
        program = load_program(file, source)
        stem = file.stem
        # An include inside a library file registers its target under an aliased
        # name (helper--helper), and a library import adds functions from another
        # folder; neither belongs to this file.
        own = {
            function_name: node
            for function_name, node in program.functions.items()
            if "--" not in function_name
            and function_name not in program.library_functions
        }
        if stem not in own:
            raise CompileError(
                f"{file}: a library file must define the function {stem!r} "
                f"(one function per file)"
            )
        if len(own) > 1:
            extra = ", ".join(sorted(set(own) - {stem}))
            raise CompileError(
                f"{file}: a library file holds one function, but this one also "
                f"defines {extra}"
            )
        if stem not in seen:
            seen.add(stem)
            found.append((stem, own[stem]))
        # A file may import another library; those functions have to travel with
        # it or the outer program cannot resolve the call inside this file.
        for extra_name, extra_node in sorted(program.functions.items()):
            if extra_name == stem or "--" in extra_name or extra_name in seen:
                continue
            seen.add(extra_name)
            found.append((extra_name, extra_node))
    return found
