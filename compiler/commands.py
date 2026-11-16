"""Project and toolchain commands: ``doctor``, ``new`` and ``clean``.

Part 8 asks for "stable new/run/build/test/format/clean/doctor/package
commands".  ``run``, ``build`` and ``format`` already exist as flags on the
compiler entry point; the three commands that need project- or
toolchain-level knowledge live here so the flag surface stays small.
"""

from __future__ import annotations

import pathlib
import shutil
import sys

from compiler.build import find_compiler

# The starter program is deliberately literal-only: it compiles on the C
# backend and on the experimental native backend, so a new project builds
# with whichever backend the author selects.
STARTER_SOURCE = """\
# {name} - an Anvil starter project.
# Run it:      python compiler/anvil.py {manifest} --run
# Check it:    python compiler/anvil.py {manifest} --check
# Format it:   python compiler/anvil.py main.ANVL --format

scene 2d
clear rgba(11, 16, 27, 255)

set var(spin) = 0.0

fn(update)
  set var(spin) = compute(var(spin) + delta() * 90)
end

fn(draw)
  display circle(320, 240, 96) -rgb(88, 164, 255)
  display rect(20, 20, 180, 4) -rgb(93, 223, 199)
  display text("Hello from Anvil") -l(20, 40) -rgb(237, 243, 255)
end
"""

MANIFEST_TEMPLATE = """\
name = "{name}"
entry = "main.ANVL"

[engine]
fixed_hz = 60
"""

_READY = "ok"
_NOTE = "warn"
_FAIL = "fail"


def _report(label: str, status: str, detail: str, stream) -> None:
    print(f"  [{status:>4}] {label:<22} {detail}", file=stream)


def _python_check() -> tuple[str, str, str]:
    major, minor = sys.version_info[:2]
    version = f"{major}.{minor}.{sys.version_info[2]}"
    if (major, minor) >= (3, 11):
        # tomllib is the only 3.11+ requirement in the compiler.
        return _READY, "Python", f"{version} (tomllib available)"
    return _FAIL, "Python", f"{version} needs 3.11 or newer for TOML manifests"


def _compiler_check() -> tuple[str, str, str]:
    found = find_compiler(None)
    if found:
        return _READY, "C backend", f"{found[0]} at {found[1]}"
    return _NOTE, "C backend", "no C compiler found; install Visual Studio 2022 Build Tools"


def _runtime_check(root: pathlib.Path) -> tuple[str, str, str]:
    header = root / "runtime" / "anvil_runtime.h"
    source = root / "runtime" / "anvil_runtime.c"
    missing = [p.name for p in (header, source) if not p.is_file()]
    if missing:
        return _FAIL, "C runtime", "missing " + ", ".join(missing)
    return _READY, "C runtime", "runtime/anvil_runtime.c present"


def _icon_check(root: pathlib.Path) -> tuple[str, str, str]:
    icon = root / "assets" / "icons" / "anvil-executable.ico"
    if icon.is_file():
        return _READY, "Executable icon", "assets/icons/anvil-executable.ico present"
    return _NOTE, "Executable icon", "missing; C builds will stop until it is restored"


def _extension_check(root: pathlib.Path) -> tuple[str, str, str]:
    grammar = root / "vscode-extension" / "syntaxes" / "anvil.tmLanguage.json"
    if grammar.is_file():
        return _READY, "Editor grammar", "vscode-extension/syntaxes/anvil.tmLanguage.json"
    return _NOTE, "Editor grammar", "not installed; syntax highlighting unavailable"


def doctor(stream=None) -> int:
    """Report which backends and assets this checkout can actually use."""
    out = stream or sys.stdout
    root = pathlib.Path(__file__).resolve().parent.parent
    checks = [
        _python_check(),
        _compiler_check(),
        _runtime_check(root),
        _icon_check(root),
        _extension_check(root),
    ]
    print("Anvil toolchain", file=out)
    for status, label, detail in checks:
        _report(label, status, detail, out)
    _report("Native backend", _READY, "built in; needs no C compiler", out)
    failures = [label for status, label, _ in checks if status == _FAIL]
    if failures:
        print(
            f"\n{len(failures)} blocking problem(s): {', '.join(failures)}",
            file=out,
        )
        return 1
    print("\nNo blocking problems. Run a program with --run.", file=out)
    return 0


def new_project(target: pathlib.Path, name: str | None = None, stream=None) -> int:
    """Create a runnable project folder. Refuses to touch an existing folder."""
    out = stream or sys.stdout
    target = target.resolve()
    if target.exists():
        if not target.is_dir():
            print(f"{target}: already exists and is not a folder", file=sys.stderr)
            return 1
        if any(target.iterdir()):
            print(f"{target}: folder is not empty; refusing to overwrite", file=sys.stderr)
            return 1
    project_name = (name or target.name or "Anvil Game").strip()
    if not project_name:
        print(f"{target}: project name must not be empty", file=sys.stderr)
        return 1
    manifest_name = f"{project_name.replace(' ', '_')}.ANVLproj"
    target.mkdir(parents=True, exist_ok=True)
    (target / "assets").mkdir(exist_ok=True)
    manifest = target / manifest_name
    manifest.write_text(
        MANIFEST_TEMPLATE.format(name=project_name), encoding="utf-8", newline="\n"
    )
    source = target / "main.ANVL"
    source.write_text(
        STARTER_SOURCE.format(name=project_name, manifest=manifest_name),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Created {project_name} in {target}", file=out)
    print(f"  {manifest_name}", file=out)
    print("  main.ANVL", file=out)
    print("  assets/", file=out)
    print(f"\nBuild and run:  python compiler/anvil.py {manifest} --run", file=out)
    return 0


def _artifact_paths(source: pathlib.Path) -> list[pathlib.Path]:
    """Paths a build of ``source`` may leave behind next to the source."""
    stem = source.with_suffix("")
    candidates = [
        source.with_suffix(".exe"),
        stem.with_suffix(".c"),
        pathlib.Path(f"{stem}.generated.c"),
    ]
    return candidates


def clean(source: pathlib.Path, stream=None) -> int:
    """Remove build artifacts for one source file or project manifest."""
    out = stream or sys.stdout
    source = source.resolve()
    if not source.exists():
        print(f"{source}: no such file", file=sys.stderr)
        return 1
    roots: list[pathlib.Path] = []
    if source.suffix.lower() == ".anvlproj":
        import tomllib

        manifest = tomllib.loads(source.read_text(encoding="utf-8"))
        entry = manifest.get("entry")
        if isinstance(entry, str) and entry:
            roots.append((source.parent / entry).resolve())
        roots.append(source.parent / "build")
    else:
        roots.append(source)
    removed: list[pathlib.Path] = []
    for root in roots:
        if root.is_dir():
            shutil.rmtree(root, ignore_errors=True)
            removed.append(root)
            continue
        for artifact in _artifact_paths(root):
            if artifact.is_file():
                artifact.unlink()
                removed.append(artifact)
    if not removed:
        print(f"{source}: nothing to clean", file=out)
        return 0
    for path in removed:
        print(f"Removed {path}", file=out)
    return 0
