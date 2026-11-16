"""Project and toolchain commands: ``doctor``, ``new`` and ``clean``.

Part 8 asks for "stable new/run/build/test/format/clean/doctor/package
commands".  ``run``, ``build`` and ``format`` already exist as flags on the
compiler entry point; the three commands that need project- or
toolchain-level knowledge live here so the flag surface stays small.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

from compiler.build import find_compiler
from compiler.common import CompileError

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPILER = ROOT / "compiler" / "anvil.py"

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

SMOKE_TEST = """\
# {name}: headless checks.  Run them with:
#   python compiler/anvil.py {manifest} --test
fn(main)
  expect(2 + 2, 4)
  expect(round(2.5), 3)
  expect_text(upper("ok"), "OK")
  print "smoke test passed"
end
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
    tests = target / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "smoke_test.ANVL").write_text(
        SMOKE_TEST.format(name=project_name, manifest=manifest_name),
        encoding="utf-8",
        newline="\n",
    )
    print(f"Created {project_name} in {target}", file=out)
    print(f"  {manifest_name}", file=out)
    print("  main.ANVL", file=out)
    print("  assets/", file=out)
    print("  tests/smoke_test.ANVL", file=out)
    print(f"\nBuild and run:  python compiler/anvil.py {manifest} --run", file=out)
    print(f"Run the tests:  python compiler/anvil.py {manifest} --test", file=out)
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


_ASSET_CALL = re.compile(r'image_load\s*\(\s*"([^"]*)"')


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return cleaned or "anvil-game"


def _sources_for(source: pathlib.Path) -> list[pathlib.Path]:
    """Sources a package of ``source`` is built from.

    A manifest owns every .ANVL file under its folder; a plain source owns only
    itself, so an unrelated broken file elsewhere in the folder cannot veto it.
    """
    if source.suffix.lower() != ".anvlproj":
        return [source]
    root = source.parent
    return sorted(
        path for path in root.rglob("*.ANVL") if "dist" not in path.parts
    )


def _asset_references(sources: list[pathlib.Path]) -> dict[str, list[pathlib.Path]]:
    """Map each ``image_load`` path in the project to the files that ask for it."""
    references: dict[str, list[pathlib.Path]] = {}
    for path in sources:
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _ASSET_CALL.finditer(text):
            references.setdefault(match.group(1), []).append(path)
    return references


def _features(sources: list[pathlib.Path]) -> list[str]:
    """Name the runtime feature groups the project's sources reach for."""
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in sources
    )
    features = ["console", "window", "2d-render"]
    if "image_load" in text:
        features.append("image")
    if "body_" in text or "physics_" in text:
        features.append("physics-2d")
    if "net_" in text:
        features.append("network")
    return features


def _package_plan(
    source: pathlib.Path, sources: list[pathlib.Path]
) -> tuple[str, pathlib.Path, pathlib.Path, list[pathlib.Path]]:
    """Return ``(project name, entry, dist folder, assets)`` for ``source``."""
    root = source.parent
    project_name = source.stem
    entry = source
    if source.suffix.lower() == ".anvlproj":
        manifest = tomllib.loads(source.read_text(encoding="utf-8"))
        entry_name = manifest.get("entry")
        if not isinstance(entry_name, str) or not entry_name:
            raise CompileError(f"{source}: manifest needs a non-empty string 'entry'")
        entry = (root / entry_name).resolve()
        try:
            entry.relative_to(root)
        except ValueError as error:
            raise CompileError(f"{source}: entry must resolve inside the project folder") from error
        name = manifest.get("name")
        if isinstance(name, str) and name.strip():
            project_name = name.strip()
    if not entry.is_file():
        raise CompileError(f"{entry}: entry source is missing")

    assets: list[pathlib.Path] = []
    if source.suffix.lower() == ".anvlproj":
        # A project ships its whole assets folder: content may be chosen at run
        # time from data the compiler cannot see.
        assets_root = root / "assets"
        if assets_root.is_dir():
            assets = sorted(p for p in assets_root.rglob("*") if p.is_file())
    for reference in _asset_references(sources):
        candidate = (root / reference).resolve()
        if candidate.is_file() and candidate not in assets:
            assets.append(candidate)
    return project_name, entry, root / "dist" / _slug(project_name), assets


def package(
    source: pathlib.Path,
    *,
    dry_run: bool = False,
    backend: str = "c",
    stream=None,
) -> int:
    """Build a project and emit a distributable folder with a hashed manifest."""
    out = stream or sys.stdout
    source = pathlib.Path(source).resolve()
    if not source.is_file():
        print(f"{source}: no such file", file=sys.stderr)
        return 1

    sources = _sources_for(source)
    try:
        project_name, entry, dist, assets = _package_plan(source, sources)
    except CompileError as error:
        print(f"error: {error.message}", file=sys.stderr)
        return 1

    root = source.parent
    references = _asset_references(sources)
    missing = sorted(ref for ref in references if not (root / ref).is_file())
    if missing:
        for reference in missing:
            print(
                f"error: {reference}: referenced by image_load but not found",
                file=sys.stderr,
            )
        print(
            f"error: {len(missing)} missing asset(s); package aborted before building",
            file=sys.stderr,
        )
        return 1

    executable = dist / f"{entry.stem}.exe"
    manifest_copy = dist / source.name if source.suffix.lower() == ".anvlproj" else None

    print(f"Package {project_name}", file=out)
    print(f"  target    windows-x64 ({backend} backend)", file=out)
    print(f"  entry     {entry.relative_to(root)}", file=out)
    print(f"  output    {dist}", file=out)
    print(f"  features  {', '.join(_features(sources))}", file=out)
    for asset in assets:
        print(f"  asset     {asset.relative_to(root)}", file=out)
    if dry_run:
        print("\nDry run: nothing written.", file=out)
        return 0

    dist.mkdir(parents=True, exist_ok=True)
    built = subprocess.run(
        [
            sys.executable,
            str(COMPILER),
            str(source),
            "--release",
            "--backend",
            backend,
            "--output",
            str(executable),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(root),
    )
    if built.returncode != 0:
        print(built.stdout, end="", file=out)
        print(built.stderr, end="", file=sys.stderr)
        print(f"error: build failed; {dist} was not packaged", file=sys.stderr)
        return 1

    copied: list[tuple[pathlib.Path, str]] = [(executable, "executable")]
    if manifest_copy is not None:
        shutil.copy2(source, manifest_copy)
        copied.append((manifest_copy, "project-manifest"))
    for asset in assets:
        destination = dist / asset.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, destination)
        copied.append((destination, "asset"))

    files = []
    checksums = {}
    for path, role in copied:
        digest = _sha256(path)
        relative = path.relative_to(dist).as_posix()
        files.append(
            {
                "path": relative,
                "role": role,
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
        checksums[relative] = f"sha256:{digest}"

    manifest = {
        "name": project_name,
        "language_version": 1,
        "compiler": {"name": "anvil", "backend": backend},
        "target": "windows-x64",
        "features": _features(sources),
        "entry": entry.relative_to(root).as_posix(),
        "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": files,
        "checksums": checksums,
        "dependencies": [],
        "licenses": ["Anvil compiler and runtime: see LICENSE"],
    }
    (dist / "package.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    print(f"\nWrote {dist / 'package.json'} and {len(files)} file(s).", file=out)
    print(f"Run it with:  {executable}", file=out)
    return 0


def _test_files(source: pathlib.Path) -> list[pathlib.Path]:
    """Test files for ``source``: itself for a .ANVL, discovered for a project."""
    if source.suffix.lower() != ".anvlproj":
        return [source]
    root = source.parent
    found = list(sorted(root.glob("*_test.ANVL")))
    tests_dir = root / "tests"
    if tests_dir.is_dir():
        found.extend(sorted(tests_dir.rglob("*.ANVL")))
    unique: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for path in found:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def test_project(source: pathlib.Path, *, backend: str = "c", stream=None) -> int:
    """Build and run each test file; a failing run fails the command."""
    out = stream or sys.stdout
    source = pathlib.Path(source).resolve()
    if not source.is_file():
        print(f"{source}: no such file", file=sys.stderr)
        return 1

    root = source.parent
    files = _test_files(source)
    if not files:
        print(
            f"{source}: no tests found; add tests/*.ANVL or a *_test.ANVL file",
            file=sys.stderr,
        )
        return 1

    print(f"Running {len(files)} test file(s) with the {backend} backend", file=out)
    failures: list[tuple[pathlib.Path, subprocess.CompletedProcess]] = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
        build_dir = pathlib.Path(temporary)
        for path in files:
            label = path.relative_to(root) if path.is_relative_to(root) else path
            executable = build_dir / f"{path.stem}.exe"
            built = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(path),
                    "--backend",
                    backend,
                    "--output",
                    str(executable),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(root),
            )
            if built.returncode != 0:
                print(f"  fail  {label} (build)", file=out)
                failures.append((path, built))
                continue
            try:
                ran = subprocess.run(
                    [str(executable)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=str(root),
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                print(f"  fail  {label} (timed out after 120s)", file=out)
                failures.append(
                    (path, subprocess.CompletedProcess([], 1, "", "timed out after 120s"))
                )
                continue
            if ran.returncode == 0:
                print(f"  pass  {label}", file=out)
            else:
                print(f"  fail  {label}", file=out)
                failures.append((path, ran))

    if failures:
        for path, result in failures:
            print(f"\n--- {path} ---", file=out)
            if result.stdout:
                print(result.stdout, end="", file=out)
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
        print(
            f"\n{len(files) - len(failures)} passed, {len(failures)} failed",
            file=out,
        )
        return 1

    print(f"\n{len(files)} passed", file=out)
    return 0
