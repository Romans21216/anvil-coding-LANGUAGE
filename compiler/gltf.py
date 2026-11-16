"""Compile-time glTF import.

`model_draw("file.gltf", x, y, z, scale, rx, ry, rz)` is lowered by the C
backend into a static triangle array plus `anvil_mesh_draw`, so the runtime
never parses JSON and the model ships inside the executable. This module reads
the file during compilation and returns flat triangles.

Supported: .gltf (JSON) with a .bin file or base64 data URI buffers, node
hierarchies with matrix or TRS transforms, triangle/triangle-strip/triangle-fan
primitives, POSITION and optional COLOR_0 attributes, and per-material
baseColorFactor. Not supported yet: .glb containers, skins, morph targets,
animations, textures and sparse accessors.
"""

from __future__ import annotations

import base64
import json
import pathlib
import re
import struct

MAX_TRIANGLES = 200_000

COMPONENTS = {
    5120: ("b", 1, 127.0),
    5121: ("B", 1, 255.0),
    5122: ("h", 2, 32767.0),
    5123: ("H", 2, 65535.0),
    5125: ("I", 4, 1.0),
    5126: ("f", 4, 1.0),
}
TYPE_SIZE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
DEFAULT_COLOR = (204, 204, 217)


class ModelError(Exception):
    pass


def _buffer_bytes(
    document: dict, index: int, base_dir: pathlib.Path, binary: bytes | None = None
) -> bytes:
    buffer = document["buffers"][index]
    uri = buffer.get("uri")
    if not uri:
        if index == 0 and binary is not None:
            return binary
        raise ModelError("a buffer has no uri and the file has no GLB binary chunk")
    if uri.startswith("data:"):
        header, _, payload = uri.partition(",")
        if ";base64" not in header:
            raise ModelError("only base64 data URIs are supported")
        try:
            return base64.b64decode(payload)
        except ValueError as error:
            raise ModelError(f"invalid base64 buffer: {error}") from error
    path = (base_dir / uri).resolve()
    try:
        return path.read_bytes()
    except OSError as error:
        raise ModelError(f"cannot read buffer {uri!r}: {error}") from error


def _accessor(
    document: dict, index: int, base_dir: pathlib.Path, binary: bytes | None = None
) -> list[tuple]:
    accessor = document["accessors"][index]
    if accessor.get("sparse"):
        raise ModelError("sparse accessors are not supported")
    view = document["bufferViews"][accessor["bufferView"]]
    buffer = _buffer_bytes(document, view["buffer"], base_dir, binary)
    component = accessor["componentType"]
    if component not in COMPONENTS:
        raise ModelError(f"unsupported accessor component type {component}")
    fmt, size, scale = COMPONENTS[component]
    width = TYPE_SIZE[accessor["type"]]
    stride = view.get("byteStride", size * width)
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    count = accessor["count"]
    values = []
    for i in range(count):
        base = offset + i * stride
        if base + size * width > len(buffer):
            raise ModelError("an accessor reads past the end of its buffer")
        row = struct.unpack_from("<" + fmt * width, buffer, base)
        if accessor.get("normalized") and scale != 1.0:
            row = tuple(value / scale for value in row)
        values.append(row)
    return values


def _identity() -> list[float]:
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _multiply(a: list[float], b: list[float]) -> list[float]:
    out = [0.0] * 16
    for column in range(4):
        for row in range(4):
            out[column * 4 + row] = sum(a[k * 4 + row] * b[column * 4 + k] for k in range(4))
    return out


def _apply(matrix: list[float], point: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    return (
        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
    )


def _node_matrix(node: dict) -> list[float]:
    if "matrix" in node:
        values = [float(value) for value in node["matrix"]]
        if len(values) != 16:
            raise ModelError("a node matrix must have 16 entries")
        return values
    translation = [float(v) for v in node.get("translation", (0.0, 0.0, 0.0))]
    rotation = [float(v) for v in node.get("rotation", (0.0, 0.0, 0.0, 1.0))]
    scale = [float(v) for v in node.get("scale", (1.0, 1.0, 1.0))]
    if len(translation) != 3 or len(rotation) != 4 or len(scale) != 3:
        raise ModelError("a node transform has the wrong number of components")
    x, y, z, w = rotation
    norm = (x * x + y * y + z * z + w * w) ** 0.5
    if norm > 0.0:
        x, y, z, w = x / norm, y / norm, z / norm, w / norm
    # Column-major: rotation * scale, then translation.
    r = [
        1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w), 0.0,
        2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w), 0.0,
        2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y), 0.0,
        0.0, 0.0, 0.0, 1.0,
    ]
    for column in range(3):
        r[column * 4 + 0] *= scale[0]
        r[column * 4 + 1] *= scale[1]
        r[column * 4 + 2] *= scale[2]
    r[12], r[13], r[14] = translation
    return r


def _triangle_indices(mode: int, count: int) -> list[tuple[int, int, int]]:
    if mode == 4:  # TRIANGLES
        return [(i, i + 1, i + 2) for i in range(0, count - 2, 3)]
    if mode == 5:  # TRIANGLE_STRIP
        triangles = []
        for i in range(count - 2):
            if i % 2 == 0:
                triangles.append((i, i + 1, i + 2))
            else:
                triangles.append((i + 1, i, i + 2))
        return triangles
    if mode == 6:  # TRIANGLE_FAN
        return [(0, i, i + 1) for i in range(1, count - 1)]
    raise ModelError(f"unsupported primitive mode {mode}; only triangles, strips and fans are supported")


def _material_colour(document: dict, primitive: dict) -> tuple[int, int, int]:
    index = primitive.get("material")
    if index is None:
        return DEFAULT_COLOR
    try:
        factor = document["materials"][index]["pbrMetallicRoughness"]["baseColorFactor"]
    except (KeyError, IndexError, TypeError):
        return DEFAULT_COLOR
    if len(factor) < 3:
        return DEFAULT_COLOR
    return tuple(max(0, min(255, int(round(float(channel) * 255.0)))) for channel in factor[:3])


def _primitive(
    document: dict,
    primitive: dict,
    matrix: list[float],
    base_dir: pathlib.Path,
    binary: bytes | None = None,
) -> list[float]:
    attributes = primitive.get("attributes", {})
    if "POSITION" not in attributes:
        raise ModelError("a primitive has no POSITION attribute")
    positions = _accessor(document, attributes["POSITION"], base_dir, binary)
    if attributes.get("POSITION") is not None and len(positions) and len(positions[0]) != 3:
        raise ModelError("POSITION must be a VEC3 accessor")
    if primitive.get("indices") is not None:
        indices = [
            int(row[0])
            for row in _accessor(document, primitive["indices"], base_dir, binary)
        ]
    else:
        indices = list(range(len(positions)))

    colours = None
    if "COLOR_0" in attributes:
        raw = _accessor(document, attributes["COLOR_0"], base_dir, binary)
        colours = [tuple(max(0, min(255, int(round(v * 255.0)))) for v in row[:3]) for row in raw]
    fallback = _material_colour(document, primitive)

    triangles = _triangle_indices(primitive.get("mode", 4), len(indices))
    out: list[float] = []
    for a, b, c in triangles:
        corners = (indices[a], indices[b], indices[c])
        if max(corners) >= len(positions) or min(corners) < 0:
            raise ModelError("an index points past the POSITION accessor")
        points = [_apply(matrix, positions[i]) for i in corners]
        if colours is not None:
            channels = [colours[i] for i in corners]
            colour = tuple(int(round(sum(channel[k] for channel in channels) / 3.0)) for k in range(3))
        else:
            colour = fallback
        for point in points:
            out.extend(point)
        out.extend((float(colour[0]), float(colour[1]), float(colour[2])))
    return out


def _container(path: pathlib.Path) -> tuple[dict, bytes | None]:
    """Return (document, GLB binary chunk) for a .gltf or .glb file."""
    suffix = path.suffix.lower()
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise ModelError(f"cannot read {path.name}: {error}") from error
    if suffix == ".gltf":
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ModelError(f"{path.name} is not valid glTF JSON: {error}") from error
        return document, None
    if suffix != ".glb":
        raise ModelError("only .gltf and .glb models are supported")
    if len(raw) < 12 or raw[:4] != b"glTF":
        raise ModelError(f"{path.name} is not a GLB file")
    version, length = struct.unpack_from("<II", raw, 4)
    if version != 2:
        raise ModelError(f"unsupported GLB version {version}; only version 2 is supported")
    if length > len(raw):
        raise ModelError("the GLB header length runs past the end of the file")
    offset = 12
    document = None
    binary = None
    while offset + 8 <= length:
        chunk_length, chunk_type = struct.unpack_from("<II", raw, offset)
        offset += 8
        if offset + chunk_length > len(raw):
            raise ModelError("a GLB chunk is truncated")
        payload = raw[offset : offset + chunk_length]
        offset += chunk_length
        if chunk_type == 0x4E4F534A:  # 'JSON'
            try:
                document = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as error:
                raise ModelError(f"the GLB JSON chunk is invalid: {error}") from error
        elif chunk_type == 0x004E4942:  # 'BIN\0'
            binary = payload
    if document is None:
        raise ModelError("the GLB file has no JSON chunk")
    return document, binary


def load_triangles(path: pathlib.Path) -> list[float]:
    document, binary = _container(path)
    if not isinstance(document, dict) or "asset" not in document:
        raise ModelError(f"{path.name} has no glTF 'asset' block")
    base_dir = path.parent
    nodes = document.get("nodes", [])
    scenes = document.get("scenes")
    if scenes:
        roots = scenes[document.get("scene", 0)].get("nodes", [])
    else:
        roots = list(range(len(nodes)))
    triangles: list[float] = []

    def visit(index: int, parent: list[float], depth: int) -> None:
        if depth > 64:
            raise ModelError("the node hierarchy is deeper than 64 levels")
        if index < 0 or index >= len(nodes):
            raise ModelError("a node index is out of range")
        node = nodes[index]
        world = _multiply(parent, _node_matrix(node))
        if "mesh" in node:
            mesh = document["meshes"][node["mesh"]]
            for primitive in mesh.get("primitives", []):
                triangles.extend(
                    _primitive(document, primitive, world, base_dir, binary)
                )
                if len(triangles) // 12 > MAX_TRIANGLES:
                    raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
        for child in node.get("children", []):
            visit(child, world, depth + 1)

    for root in roots:
        visit(root, _identity(), 0)
    if not triangles:
        raise ModelError("the model has no triangle geometry")
    return triangles


# ---- Compiler integration -------------------------------------------------

_registry: dict[str, tuple[str, int, list[float]]] = {}
_prescan: set[str] = set()
PATTERN = re.compile(r'\bmodel_draw\s*\(\s*"((?:[^"\\]|\\.)*)"')


def reset() -> None:
    _registry.clear()
    _prescan.clear()


def prescan(source_text: str, source_path: pathlib.Path) -> None:
    """Register every literal model_draw path before C emission starts."""
    for match in PATTERN.finditer(source_text):
        try:
            asset = json.loads('"' + match.group(1) + '"')
        except ValueError:
            continue
        ensure_emitted(asset, source_path)
        _prescan.add(str(_resolve(asset, source_path)))


def _resolve(asset: str, source_path: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(asset)
    if not path.is_absolute():
        path = pathlib.Path(source_path).parent / path
    return path.resolve()


def ensure_emitted(asset: str, source_path: pathlib.Path) -> tuple[str, int]:
    path = _resolve(asset, source_path)
    key = str(path)
    if key in _registry:
        symbol, count, _ = _registry[key]
        return symbol, count
    if not path.is_file():
        raise ModelError(f"cannot find model {asset!r} (resolved to {path})")
    if not key.endswith((".gltf", ".glb")):
        raise ModelError("only .gltf and .glb models are supported")
    data = load_triangles(path)
    symbol = f"anvil_model_{len(_registry)}"
    count = len(data) // 12
    _registry[key] = (symbol, count, data)
    return symbol, count


def definitions() -> list[str]:
    lines: list[str] = []
    for key, (symbol, count, data) in _registry.items():
        lines.append(f"/* model: {pathlib.Path(key).name}, {count} triangles */")
        rows = []
        for start in range(0, len(data), 12):
            chunk = data[start : start + 12]
            rows.append("    " + ", ".join(f"{value:.6g}" for value in chunk) + ",")
        lines.append(f"static const double {symbol}[{len(data)}] = {{")
        lines.extend(rows)
        lines.append("};")
        lines.append("")
    return lines


def late_models() -> list[str]:
    """Models discovered during emission but not pre-scanned (unsupported)."""
    return [key for key in _registry if key not in _prescan]
