"""Libraries on disk: one function per file, one folder per library.

`library import essentials` looks for `libraries-essentials/` (or
`libraries/essentials/`) beside the file that wrote the line, then in its parent
folders, then beside the compiler itself, and loads every `<name>.ANVL` in that
folder into the program. Each file must define the function named after it.

Only the functions a program calls reach the output: reachability already prunes
everything else, so importing a library costs nothing for the functions you do
not use.
"""

from __future__ import annotations

from pathlib import Path

from compiler.common import CompileError

# How far up from the importing file to look for a library folder.
PARENT_SEARCH_DEPTH = 8


def folder_for(entry: Path, name: str) -> Path | None:
    """Where the library named `name` lives, if it exists."""
    start = entry.resolve().parent
    for base in [start, *start.parents[:PARENT_SEARCH_DEPTH]]:
        for candidate in (base / f"libraries-{name}", base / "libraries" / name):
            if candidate.is_dir():
                return candidate
    # Libraries shipped with the compiler itself.
    package = Path(__file__).resolve().parents[1]
    for candidate in (package / f"libraries-{name}", package / "libraries" / name):
        if candidate.is_dir():
            return candidate
    return None


def files_in(folder: Path) -> list[Path]:
    """The library's function files, in a stable order."""
    return sorted(folder.glob("*.ANVL"))


def missing_message(entry: Path, name: str) -> str:
    return (
        f"library {name!r} not found; expected a folder named libraries-{name} "
        f"or libraries/{name} beside {entry.name} or in a parent folder"
    )


def empty_message(folder: Path, name: str) -> str:
    return f"library {name!r} has no .ANVL files in {folder}"


def name_mismatch_message(path: Path) -> str:
    return (
        f"{path}: a library file must define the function {path.stem!r} "
        "(one function per file)"
    )


def check_file(path: Path, functions: dict) -> None:
    """The file must define exactly the function named after it."""
    resolved = path.resolve()
    owned = sorted(
        name
        for name, node in functions.items()
        if getattr(node, "source", None) is not None
        and Path(node.source).resolve() == resolved
    )
    if path.stem not in owned:
        raise CompileError(name_mismatch_message(path))
    if len(owned) > 1:
        extra = ", ".join(name for name in owned if name != path.stem)
        raise CompileError(
            f"{path}: a library file holds one function, but this one also defines {extra}"
        )
