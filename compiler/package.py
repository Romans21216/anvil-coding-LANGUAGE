"""Package a built program: assets, hashes and a machine-readable manifest.

Part 8 section 8.14 asks for stable packaging with a dry run, missing-asset
validation, and a manifest that records the compiler, target, features, asset
hashes and checksums.  The output is deterministic: no timestamps are written,
so rebuilding the same inputs produces the same manifest bytes.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil

from compiler.common import CompileError

PACKAGE_FORMAT = 1
MANIFEST_NAME = "anvil-package.json"
# Asset paths are the literal arguments of the file-loading builtins.
ASSET_PATTERN = re.compile(r'\b(?:image_load|sound_load)\s*\(\s*"([^"]+)"')


def _sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


sha256_file = _sha256


def _inside(root: pathlib.Path, candidate: pathlib.Path, label: str) -> pathlib.Path:
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CompileError(f"{label} resolves outside the project folder") from exc
    return resolved


def collect_assets(
    root: pathlib.Path, sources: list[pathlib.Path], declared: list[str]
) -> list[pathlib.Path]:
    """Declared assets plus literal image_load/sound_load paths, deduplicated."""
    assets: list[pathlib.Path] = []
    for name in declared:
        candidate = _inside(root, root / name, f"asset {name!r}")
        if candidate not in assets:
            assets.append(candidate)
    for source in sources:
        try:
            text = source.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in ASSET_PATTERN.finditer(text):
            candidate = _inside(root, root / match.group(1), f"asset {match.group(1)!r}")
            if candidate not in assets:
                assets.append(candidate)
    return assets


def package(
    *,
    project_root: pathlib.Path,
    name: str,
    backend: str,
    entry: pathlib.Path,
    program: pathlib.Path,
    declared_assets: list[str],
    sources: list[pathlib.Path],
    features: list[str],
    compiler: str,
    target_dir: pathlib.Path,
    dry_run: bool,
) -> int:
    root = project_root.resolve()
    assets = collect_assets(root, sources, declared_assets)
    missing = [asset for asset in assets if not asset.is_file()]
    if missing:
        listing = "\n".join(f"  {path}" for path in missing)
        raise CompileError(
            f"{len(missing)} asset(s) are missing and would not ship:\n{listing}"
        )
    rows = []
    checksums = {}
    for asset in assets:
        relative = asset.relative_to(root).as_posix()
        digest = _sha256(asset)
        rows.append({"path": relative, "size": asset.stat().st_size, "sha256": digest})
        checksums[relative] = digest
    program_digest = _sha256(program)
    checksums[program.name] = program_digest
    manifest = {
        "format": PACKAGE_FORMAT,
        "name": name,
        "target": f"windows-x64-{backend}",
        "backend": backend,
        "compiler": compiler,
        "entry": entry.resolve().relative_to(root).as_posix(),
        "features": features,
        "program": {
            "path": program.name,
            "size": program.stat().st_size,
            "sha256": program_digest,
        },
        "assets": rows,
        "checksums": dict(sorted(checksums.items())),
    }
    text = json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    if dry_run:
        print(text, end="")
        return 0
    target = target_dir.resolve()
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(program, target / program.name)
    for asset in assets:
        relative = asset.relative_to(root)
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, destination)
    (target / MANIFEST_NAME).write_text(text, encoding="utf-8", newline="\n")
    print(f"Packaged {len(assets) + 1} file(s) into {target_dir}")
    return 0
