"""Project lifecycle commands required by Part 8 section 8.14.

`new`, `clean` and `doctor` are deliberately small: they only touch files the
toolchain itself creates, and they report what they would do before doing it.
"""

from __future__ import annotations

import pathlib
import platform
import shutil
import sys

STARTER_PROGRAM = """fn(main)
  say "Hello from Anvil"
end
call fn(main)
"""

STARTER_MANIFEST = """name = "My Anvil Game"
entry = "main.ANVL"

[engine]
fixed_hz = 60
"""

STARTER_README = """# My Anvil Game

Build and run:

    python <path to anvil>/compiler/anvil.py game.ANVLproj --run

Package for sharing:

    python <path to anvil>/compiler/anvil.py game.ANVLproj --package dist
"""


def doctor(toolchain_root: pathlib.Path) -> int:
    """Print the toolchain inputs a first-time user needs to see."""
    from compiler.build import find_compiler

    runtime = toolchain_root / "runtime"
    print("Anvil doctor")
    print(f"  python:   {platform.python_version()} ({sys.executable})")
    print(f"  platform: {platform.platform()}")
    compiler = find_compiler(None)
    if compiler:
        print(f"  C backend: {compiler[0]} at {compiler[1]}")
    else:
        print(
            "  C backend: no C compiler found (install Visual Studio 2022 Build "
            "Tools with the C++ workload)"
        )
    print("  native backend: ready (writes an AMD64 PE without a C compiler)")
    for name in ("anvil_runtime.c", "anvil_runtime.h", "anvil_projection.h"):
        path = runtime / name
        state = "ok" if path.is_file() else "MISSING"
        print(f"  runtime/{name}: {state}")
    return 0


def clean(root: pathlib.Path) -> int:
    """Remove generated artifacts the toolchain wrote beside a project."""
    root = root.resolve()
    removed: list[pathlib.Path] = []
    for pattern in ("*.generated.c", "*.partial.exe", "*.build.cmd"):
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                path.unlink()
                removed.append(path)
    for path in sorted(root.glob("*_obj")):
        if path.is_dir():
            shutil.rmtree(path)
            removed.append(path)
    cache = root / ".anvil-cache"
    if cache.is_dir():
        shutil.rmtree(cache)
        removed.append(cache)
    for path in removed:
        print(f"removed {path}")
    print(f"cleaned {len(removed)} item(s) in {root}")
    return 0


def format_file(path: pathlib.Path, check: bool) -> int:
    """Normalise whitespace and indentation; --format-check only reports."""
    from compiler.formatting import format_source

    path = path.resolve()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        print(f"cannot read {path}: {error.strerror or error}", file=sys.stderr)
        return 1
    formatted = format_source(text)
    if formatted == text:
        print(f"{path}: already formatted")
        return 0
    if check:
        print(f"{path}: would be reformatted", file=sys.stderr)
        return 1
    path.write_text(formatted, encoding="utf-8", newline="\n")
    print(f"{path}: formatted")
    return 0


def new_project(destination: pathlib.Path) -> int:
    """Scaffold a runnable project in an empty directory."""
    destination = destination.resolve()
    if destination.exists() and any(destination.iterdir()):
        print(
            f"{destination} already exists and is not empty; choose a new folder",
            file=sys.stderr,
        )
        return 1
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "main.ANVL").write_text(STARTER_PROGRAM, encoding="utf-8", newline="\n")
    (destination / "game.ANVLproj").write_text(
        STARTER_MANIFEST, encoding="utf-8", newline="\n"
    )
    (destination / "README.md").write_text(STARTER_README, encoding="utf-8", newline="\n")
    print(f"Created {destination}")
    print("Next: python compiler/anvil.py game.ANVLproj --run")
    return 0
