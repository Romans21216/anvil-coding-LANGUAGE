"""No-link project and reachable asset preflight."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import tomllib

from compiler.common import CompileError
from compiler.parser import parse

MODEL_CALLS = {
    "model_draw",
    "model_draw_instance",
    "model_animate",
    "model_animation_length",
    "model_instance",
    "model_instance_destroy",
    "model_morph",
    "model_instance_morph",
    "ray_mesh",
}
ASSET_CALLS = {"image_load", "sound_load", "music_load"} | MODEL_CALLS


def _asset_calls(text: str):
    """Yield (name, literal path) calls, ignoring identifiers inside strings."""
    i = 0
    while i < len(text):
        if text[i] == '"':
            i += 1
            escaped = False
            while i < len(text):
                char = text[i]
                i += 1
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    break
            continue
        match = re.match(r"[A-Za-z_][A-Za-z_0-9]*", text[i:])
        if not match:
            i += 1
            continue
        name = match.group(0)
        end_name = i + len(name)
        if name not in ASSET_CALLS:
            i = end_name
            continue
        opening = end_name
        while opening < len(text) and text[opening].isspace():
            opening += 1
        if opening >= len(text) or text[opening] != "(":
            i = end_name
            continue
        arg_start = opening + 1
        cursor = arg_start
        depth = 1
        quoted = False
        escaped = False
        while cursor < len(text) and depth:
            char = text[cursor]
            if escaped:
                escaped = False
            elif char == "\\" and quoted:
                escaped = True
            elif char == '"':
                quoted = not quoted
            elif not quoted and char == "(":
                depth += 1
            elif not quoted and char == ")":
                depth -= 1
                if depth == 0:
                    break
            elif not quoted and char == "," and depth == 1:
                break
            cursor += 1
        argument = text[arg_start:cursor].strip()
        try:
            path = json.loads(argument)
        except (ValueError, TypeError):
            path = None
        if isinstance(path, str):
            yield name, path
        else:
            yield name, None
        i = max(cursor + 1, opening + 1)


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.body)
        yield from _walk(node.otherwise)


def _read_project(path: pathlib.Path):
    root = path.resolve().parent
    manifest = tomllib.loads(path.read_text(encoding="utf-8"))
    allowed = {"name", "entry", "engine", "assets"}
    unknown = set(manifest) - allowed
    if unknown:
        raise CompileError(
            f"{path}: unsupported project setting(s): {', '.join(sorted(unknown))}"
        )
    name = manifest.get("name", "Anvil Game")
    if (
        not isinstance(name, str)
        or not name.strip()
        or "\0" in name
        or any(ord(char) < 32 for char in name)
    ):
        raise CompileError(
            f"{path}: project name must be a non-empty string without control characters"
        )
    entry = manifest.get("entry")
    if not isinstance(entry, str) or not entry:
        raise CompileError(f"{path}: manifest needs a non-empty string 'entry'")
    entry_path = (root / entry).resolve()
    try:
        entry_path.relative_to(root)
    except ValueError as error:
        raise CompileError(f"{path}: entry must resolve inside the project folder") from error
    engine = manifest.get("engine", {})
    if not isinstance(engine, dict):
        raise CompileError(f"{path}: 'engine' must be a TOML table")
    unknown_engine = set(engine) - {"fixed_hz"}
    if unknown_engine:
        raise CompileError(
            f"{path}: unsupported engine setting(s): {', '.join(sorted(unknown_engine))}"
        )
    rate = engine.get("fixed_hz", 60)
    if isinstance(rate, bool) or not isinstance(rate, int) or not 1 <= rate <= 240:
        raise CompileError(f"{path}: engine.fixed_hz must be an integer from 1 to 240")
    assets = manifest.get("assets", {})
    if not isinstance(assets, dict):
        raise CompileError(f"{path}: 'assets' must be a TOML table")
    unknown_assets = set(assets) - {"files"}
    if unknown_assets:
        raise CompileError(
            f"{path}: unsupported asset setting(s): {', '.join(sorted(unknown_assets))}"
        )
    declared = assets.get("files", [])
    if not isinstance(declared, list) or any(
        not isinstance(item, str) or not item for item in declared
    ):
        raise CompileError(f"{path}: assets.files must be a list of non-empty strings")
    return root, entry_path, declared


def verify(source_arg: pathlib.Path) -> tuple[list[dict], pathlib.Path | None]:
    diagnostics: list[dict] = []
    manifest_path = None
    declared: list[str] = []
    source_path = source_arg.resolve()
    include_root = None
    try:
        if source_arg.suffix.lower() == ".anvlproj":
            manifest_path = source_arg.resolve()
            include_root, source_path, declared = _read_project(manifest_path)
        source = source_path.read_text(encoding="utf-8")
        functions, top, variables, arrays = parse(
            source_path, source, include_root=include_root
        )
    except (OSError, UnicodeError, CompileError, tomllib.TOMLDecodeError) as error:
        message = (
            f"cannot read {source_path}: {error}"
            if isinstance(error, OSError)
            else str(error)
        )
        return [
            {"path": str(source_arg), "line": None, "asset": None, "message": message}
        ], None

    from compiler.modules import reachable_functions

    graphical = (
        "draw" in functions
        or "update" in functions
        or any(node.kind == "scene" for node in top)
    )
    reachable = reachable_functions(functions, top, graphical=graphical)
    sites: dict[tuple[str, str | None, pathlib.Path, int], tuple[int, str]] = {}
    for node in _walk(top + [fn for _name, fn in reachable]):
        origin = node.source or source_path
        for text in [node.value, *node.params]:
            for call, literal in _asset_calls(text or ""):
                sites.setdefault(
                    (call, literal, pathlib.Path(origin), node.line),
                    (node.line, call),
                )
    for asset in declared:
        sites.setdefault(("declared", asset, manifest_path or source_path, 1), (1, "declared"))

    from compiler import gltf, wasm

    gltf.reset()
    checked: set[tuple[str, pathlib.Path]] = set()
    for (call, literal, origin, _site_line), (line, _call) in sites.items():
        if literal is None:
            diagnostics.append(
                {
                    "path": str(origin),
                    "line": line,
                    "asset": None,
                    "message": f"{call} requires a string literal path for asset preflight",
                }
            )
            continue
        kind = "model" if call in MODEL_CALLS else call
        target = pathlib.Path(literal)
        if not target.is_absolute():
            target = origin.parent / target
        target = target.resolve()
        if call == "declared" and manifest_path is not None:
            try:
                target.relative_to(manifest_path.parent)
            except ValueError:
                diagnostics.append(
                    {
                        "path": str(manifest_path),
                        "line": line,
                        "asset": literal,
                        "message": "declared project assets must resolve inside the project folder",
                    }
                )
                continue
        key = (kind, target)
        if key in checked:
            continue
        checked.add(key)
        message = None
        try:
            if kind == "model":
                gltf.ensure_model(literal, origin)
            elif kind == "image_load":
                wasm._bmp_pixels(target)
            elif kind in {"sound_load", "music_load"}:
                wasm._wav_pcm(target)
            elif kind == "declared":
                suffix = target.suffix.lower()
                if suffix in {".gltf", ".glb"}:
                    gltf.ensure_model(literal, origin)
                elif suffix == ".bmp":
                    wasm._bmp_pixels(target)
                elif suffix == ".wav":
                    wasm._wav_pcm(target)
                else:
                    raise ValueError("unsupported asset type; expected BMP, WAV, glTF or GLB")
        except (OSError, ValueError, gltf.ModelError) as error:
            message = str(error)
        if message:
            diagnostics.append(
                {
                    "path": str(origin),
                    "line": line,
                    "asset": literal,
                    "message": message,
                }
            )
    if not diagnostics:
        try:
            from compiler.codegen import emit_c

            emit_c(source_path, functions, top, variables, arrays)
        except CompileError as error:
            rendered = str(error)
            match = re.match(r"(.*?):(\d+):\s*(.*)", rendered)
            if match:
                diagnostics.append(
                    {
                        "path": match.group(1),
                        "line": int(match.group(2)),
                        "asset": None,
                        "message": match.group(3),
                    }
                )
            else:
                diagnostics.append({"path": str(source_path), "line": None, "asset": None, "message": rendered})
    return diagnostics, source_path


def main(source: pathlib.Path, output_format: str = "text") -> int:
    diagnostics, _source_path = verify(source)
    if output_format == "json":
        print(
            json.dumps(
                {"version": 1, "ok": not diagnostics, "diagnostics": diagnostics},
                sort_keys=True,
            )
        )
    elif diagnostics:
        for item in diagnostics:
            location = item["path"] + (
                f":{item['line']}" if item["line"] is not None else ""
            )
            asset = f" [{item['asset']}]" if item["asset"] else ""
            print(f"{location}: error:{asset} {item['message']}", file=sys.stderr)
    else:
        print(f"{source}: ok")
    return 1 if diagnostics else 0
