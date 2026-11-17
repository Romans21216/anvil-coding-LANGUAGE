"""Compile-time glTF import.

`model_draw("file.gltf", x, y, z, scale, rx, ry, rz)` is lowered by the C
backend into a static triangle array plus `anvil_mesh_draw`, so the runtime
never parses JSON and the model ships inside the executable. This module reads
the file during compilation and returns flat triangles.

Supported: .gltf (JSON) with a .bin file or base64 data URI buffers, node
hierarchies with matrix or TRS transforms, triangle/triangle-strip/triangle-fan
primitives, POSITION and optional COLOR_0 attributes, per-material
baseColorFactor, and node TRS animation clips (translation/rotation/scale,
LINEAR and STEP keys). A model with an animation clip bakes its triangles in
node-local space plus the node hierarchy and keyframes, and the runtime
evaluates the pose; a static model keeps the cheaper world-space bake.
A model with one skin bakes mesh-space vertices with four joint indices and
weights each, plus the skin's inverse bind matrices, so the runtime can blend
the joints. Not supported yet: morph targets, multiple skins, CUBICSPLINE keys,
textures and sparse accessors.
"""

from __future__ import annotations

import base64
import json
import pathlib
import re
import struct

MAX_TRIANGLES = 200_000
# The C runtime keeps one clip clock per model in ANVIL_MODEL_STATES slots; a
# posed model (animated or skinned) past this index would silently read 0 and
# never move, so the importer refuses it at the model_draw line instead.
MODEL_STATES = 32

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
    morph_out: list[float] | None = None,
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

    targets = primitive.get("targets", [])
    deltas: list[list[tuple[float, float, float]]] = []
    for target in targets:
        if "POSITION" not in target:
            raise ModelError("a morph target needs a POSITION delta")
        raw = _accessor(document, target["POSITION"], base_dir, binary)
        # Only the linear part of the world matrix applies to a delta; the
        # translation would move a delta that is a displacement, not a point.
        deltas.append(
            [
                (
                    matrix[0] * row[0] + matrix[4] * row[1] + matrix[8] * row[2],
                    matrix[1] * row[0] + matrix[5] * row[1] + matrix[9] * row[2],
                    matrix[2] * row[0] + matrix[6] * row[1] + matrix[10] * row[2],
                )
                for row in raw
            ]
        )

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
        if morph_out is not None:
            for corner in corners:
                for target in deltas:
                    morph_out.extend(target[corner])
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


MAX_MORPH_TARGETS = 8


def _static_walk(
    document: dict,
    binary: bytes | None,
    base_dir: pathlib.Path,
    morph_out: list[float] | None = None,
) -> tuple[list[float], list[int]]:
    """Bake every mesh in world space; optionally collect morph deltas."""
    nodes = document.get("nodes", [])
    scenes = document.get("scenes")
    if scenes:
        roots = scenes[document.get("scene", 0)].get("nodes", [])
    else:
        roots = list(range(len(nodes)))
    triangles: list[float] = []
    target_counts: list[int] = []

    def visit(index: int, parent: list[float], depth: int) -> None:
        if depth > 64:
            raise ModelError("the node hierarchy is deeper than 64 levels")
        if index < 0 or index >= len(nodes):
            raise ModelError("a node index is out of range")
        node = nodes[index]
        world = _multiply(parent, _node_matrix(node))
        if "mesh" in node:
            mesh = _mesh_for_node(document, node)
            for primitive in mesh.get("primitives", []):
                triangles.extend(
                    _primitive(document, primitive, world, base_dir, binary, morph_out)
                )
                target_counts.append(len(primitive.get("targets", [])))
                if len(triangles) // 12 > MAX_TRIANGLES:
                    raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
        for child in node.get("children", []):
            visit(child, world, depth + 1)

    for root in roots:
        visit(root, _identity(), 0)
    return triangles, target_counts


def _mesh_for_node(document: dict, node: dict) -> dict:
    """Resolve the mesh a node references.

    A negative index is not a Python from-end index here: glTF indices are
    unsigned, so `-1` used to select the last mesh and silently bake the wrong
    geometry. Every loader goes through this check.
    """
    index = node["mesh"]
    meshes = document.get("meshes") or []
    if (
        not isinstance(index, int)
        or isinstance(index, bool)
        or index < 0
        or index >= len(meshes)
    ):
        raise ModelError("a mesh index is out of range")
    return meshes[index]


def _static_document(path: pathlib.Path) -> tuple[dict, bytes | None]:
    document, binary = _container(path)
    if not isinstance(document, dict) or "asset" not in document:
        raise ModelError(f"{path.name} has no glTF 'asset' block")
    return document, binary


def load_triangles(path: pathlib.Path) -> list[float]:
    document, binary = _static_document(path)
    triangles, _ = _static_walk(document, binary, path.parent)
    if not triangles:
        raise ModelError("the model has no triangle geometry")
    return triangles


def load_morphed(path: pathlib.Path) -> dict:
    """Bake a static model with morph target deltas.

    Every primitive must declare the same positive number of targets, so the
    per-vertex delta stride is uniform; the deltas are stored per vertex, per
    target.
    """
    document, binary = _static_document(path)
    morph: list[float] = []
    triangles, counts = _static_walk(document, binary, path.parent, morph)
    if not triangles:
        raise ModelError("the model has no triangle geometry")
    if not counts or max(counts) == 0:
        raise ModelError("the model has no morph targets")
    targets = counts[0]
    if any(count != targets for count in counts):
        raise ModelError("every primitive must use the same morph target count")
    if targets > MAX_MORPH_TARGETS:
        raise ModelError(f"a model may use at most {MAX_MORPH_TARGETS} morph targets")
    defaults = [0.0] * targets
    for mesh in document.get("meshes", []):
        weights = mesh.get("weights")
        if weights:
            if len(weights) != targets:
                raise ModelError("a mesh's default morph weights do not match its targets")
            defaults = [float(value) for value in weights]
            break
    return {
        "vertices": triangles,
        "morph": morph,
        "morph_count": targets,
        "morph_defaults": defaults,
    }


# ---- Animation -------------------------------------------------------------

# glTF animation channel paths, in the order the runtime switches on them.
PATHS = {"translation": 0, "rotation": 1, "scale": 2}
INTERPOLATIONS = {"LINEAR": 0, "STEP": 1}


def _node_trs(node: dict) -> tuple[list[float], list[float], list[float]]:
    """Base translation/rotation/scale for a node, decomposing a matrix if one
    is present (an animated node must use TRS in glTF, but its parents may use
    a matrix)."""
    if "matrix" not in node:
        translation = [float(v) for v in node.get("translation", (0.0, 0.0, 0.0))]
        rotation = [float(v) for v in node.get("rotation", (0.0, 0.0, 0.0, 1.0))]
        scale = [float(v) for v in node.get("scale", (1.0, 1.0, 1.0))]
        if len(translation) != 3 or len(rotation) != 4 or len(scale) != 3:
            raise ModelError("a node transform has the wrong number of components")
        x, y, z, w = rotation
        norm = (x * x + y * y + z * z + w * w) ** 0.5
        if norm > 0.0:
            rotation = [x / norm, y / norm, z / norm, w / norm]
        return translation, rotation, scale
    matrix = [float(value) for value in node["matrix"]]
    if len(matrix) != 16:
        raise ModelError("a node matrix must have 16 entries")
    translation = [matrix[12], matrix[13], matrix[14]]
    columns = [
        [matrix[0], matrix[1], matrix[2]],
        [matrix[4], matrix[5], matrix[6]],
        [matrix[8], matrix[9], matrix[10]],
    ]
    scale = [
        (column[0] ** 2 + column[1] ** 2 + column[2] ** 2) ** 0.5
        for column in columns
    ]
    if min(scale) <= 1.0e-12:
        raise ModelError("a node matrix collapses an axis and cannot be used with animation")
    determinant = (
        columns[0][0] * (columns[1][1] * columns[2][2] - columns[1][2] * columns[2][1])
        - columns[1][0] * (columns[0][1] * columns[2][2] - columns[0][2] * columns[2][1])
        + columns[2][0] * (columns[0][1] * columns[1][2] - columns[0][2] * columns[1][1])
    )
    if determinant < 0.0:
        # The decomposition below takes a positive scale per column, so a
        # mirrored matrix would silently lose its reflection and pose a
        # different shape. Refuse it instead of pretending to decompose it.
        raise ModelError(
            "a node matrix mirrors an axis (negative determinant) and cannot be "
            "decomposed for animation"
        )
    r = [[columns[column][row] / scale[column] for column in range(3)] for row in range(3)]
    trace = r[0][0] + r[1][1] + r[2][2]
    if trace > 0.0:
        s = (trace + 1.0) ** 0.5 * 2.0
        w = 0.25 * s
        x = (r[2][1] - r[1][2]) / s
        y = (r[0][2] - r[2][0]) / s
        z = (r[1][0] - r[0][1]) / s
    elif r[0][0] > r[1][1] and r[0][0] > r[2][2]:
        s = (1.0 + r[0][0] - r[1][1] - r[2][2]) ** 0.5 * 2.0
        w = (r[2][1] - r[1][2]) / s
        x = 0.25 * s
        y = (r[0][1] + r[1][0]) / s
        z = (r[0][2] + r[2][0]) / s
    elif r[1][1] > r[2][2]:
        s = (1.0 + r[1][1] - r[0][0] - r[2][2]) ** 0.5 * 2.0
        w = (r[0][2] - r[2][0]) / s
        x = (r[0][1] + r[1][0]) / s
        y = 0.25 * s
        z = (r[1][2] + r[2][1]) / s
    else:
        s = (1.0 + r[2][2] - r[0][0] - r[1][1]) ** 0.5 * 2.0
        w = (r[1][0] - r[0][1]) / s
        x = (r[0][2] + r[2][0]) / s
        y = (r[1][2] + r[2][1]) / s
        z = 0.25 * s
    norm = (x * x + y * y + z * z + w * w) ** 0.5
    if norm > 0.0:
        x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return translation, [x, y, z, w], scale


def _clip(
    document: dict, nodes_doc: list, base_dir: pathlib.Path, binary: bytes | None
) -> tuple[list[int], list[float], list[float], float]:
    """Flatten the first animation clip into track metadata plus key arrays.

    A track is six ints: node index, path (0 translation, 1 rotation, 2 scale),
    interpolation (0 LINEAR, 1 STEP), first time index, first value index and
    key count.
    """
    animations = document.get("animations") or []
    if not animations:
        return [], [], [], 0.0
    if len(animations) > 1:
        raise ModelError("only the first animation clip is supported")
    clip = animations[0]
    samplers = clip.get("samplers", [])
    tracks: list[int] = []
    times: list[float] = []
    values: list[float] = []
    length = 0.0
    for channel in clip.get("channels", []):
        target = channel.get("target", {})
        path_name = target.get("path")
        if path_name not in PATHS:
            continue
        node_index = target.get("node")
        if not isinstance(node_index, int) or not 0 <= node_index < len(nodes_doc):
            raise ModelError("an animation targets a node that does not exist")
        sampler_index = channel.get("sampler")
        if not isinstance(sampler_index, int) or not 0 <= sampler_index < len(samplers):
            raise ModelError("an animation refers to a missing sampler")
        sampler = samplers[sampler_index]
        interpolation = sampler.get("interpolation", "LINEAR")
        if interpolation not in INTERPOLATIONS:
            raise ModelError(f"animation interpolation {interpolation!r} is not supported")
        key_times = [float(row[0]) for row in _accessor(document, sampler["input"], base_dir, binary)]
        key_values = _accessor(document, sampler["output"], base_dir, binary)
        if not key_times or not key_values:
            raise ModelError("an animation sampler is empty")
        width = 4 if path_name == "rotation" else 3
        if len(key_values[0]) != width:
            raise ModelError("an animation sampler has the wrong component count")
        if len(key_times) != len(key_values):
            raise ModelError("an animation sampler's keys and values differ in length")
        tracks.extend(
            (node_index, PATHS[path_name], INTERPOLATIONS[interpolation],
             len(times), len(values), len(key_times))
        )
        times.extend(key_times)
        for row in key_values:
            values.extend(float(v) for v in row)
        length = max(length, key_times[-1])
    if not tracks:
        raise ModelError("the animation clip has no translation, rotation or scale channels")
    return tracks, times, values, length


def load_skinned(path: pathlib.Path) -> dict:
    """Bake a skinned model: skin joints, inverse bind matrices and weights.

    Vertices are stored in mesh space with four joint indices and four weights
    each; the runtime fuses them with the posed joint matrices. One skin and
    one mesh hierarchy are supported.
    """
    document, binary = _container(path)
    if not isinstance(document, dict) or "asset" not in document:
        raise ModelError(f"{path.name} has no glTF 'asset' block")
    nodes_doc = document.get("nodes", [])
    if len(nodes_doc) > 128:
        raise ModelError("the model has more than 128 nodes")
    skins = document.get("skins") or []
    if len(skins) != 1:
        raise ModelError("only a model with exactly one skin is supported")
    skin = skins[0]
    joint_nodes = [int(node) for node in skin.get("joints", [])]
    if not joint_nodes or len(joint_nodes) > 64:
        raise ModelError("a skin must have 1 to 64 joints")
    for node in joint_nodes:
        if not 0 <= node < len(nodes_doc):
            raise ModelError("a skin joint is not a node")
    bind_accessor = skin.get("inverseBindMatrices")
    if bind_accessor is None:
        # Khronos marks inverseBindMatrices optional: without it every joint
        # binds in mesh space, which is an identity matrix per joint.
        bind_rows = [
            [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
            for _ in joint_nodes
        ]
    else:
        bind_rows = _accessor(document, bind_accessor, path.parent, binary)
    if len(bind_rows) != len(joint_nodes):
        raise ModelError("the inverse bind matrices do not match the joint count")
    bind: list[float] = []
    for row in bind_rows:
        if len(row) != 16:
            raise ModelError("an inverse bind matrix must have 16 entries")
        bind.extend(float(value) for value in row)

    parents = [-1] * len(nodes_doc)
    for index, node in enumerate(nodes_doc):
        for child in node.get("children", []):
            if not isinstance(child, int) or child < 0 or child >= len(nodes_doc):
                raise ModelError("a node index is out of range")
            parents[child] = index

    nodes: list[float] = []
    for node in nodes_doc:
        translation, rotation, scale = _node_trs(node)
        nodes.extend(translation)
        nodes.extend(rotation)
        nodes.extend(scale)

    skin_nodes = [index for index, node in enumerate(nodes_doc) if "skin" in node]
    if not skin_nodes:
        raise ModelError("no node uses the skin")
    vertices: list[float] = []
    for node_index in skin_nodes:
        node = nodes_doc[node_index]
        if "mesh" not in node:
            continue
        for primitive in _mesh_for_node(document, node).get("primitives", []):
            vertices.extend(_skinned_primitive(document, primitive, path.parent, binary))
        if len(vertices) // 14 > MAX_TRIANGLES * 3:
            raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
    if not vertices:
        raise ModelError("the skinned model has no triangle geometry")

    tracks, times, values, length = _clip(document, nodes_doc, path.parent, binary)
    return {
        "vertices": vertices,
        "nodes": nodes,
        "parents": parents,
        "joint_nodes": joint_nodes,
        "bind": bind,
        "tracks": tracks,
        "times": times,
        "values": values,
        "length": length,
    }


def _skinned_primitive(
    document: dict, primitive: dict, base_dir: pathlib.Path, binary: bytes | None
) -> list[float]:
    if primitive.get("targets"):
        # The skinned draw path has no morph input, so a combined mesh would
        # silently render its base shape. Refuse it rather than mislead.
        raise ModelError(
            "a skinned mesh with morph targets is not supported; split the mesh"
        )
    attributes = primitive.get("attributes", {})
    for required in ("POSITION", "JOINTS_0", "WEIGHTS_0"):
        if required not in attributes:
            raise ModelError(f"a skinned primitive needs {required}")
    positions = _accessor(document, attributes["POSITION"], base_dir, binary)
    joints = _accessor(document, attributes["JOINTS_0"], base_dir, binary)
    weights = _accessor(document, attributes["WEIGHTS_0"], base_dir, binary)
    if primitive.get("indices") is not None:
        indices = [int(row[0]) for row in _accessor(document, primitive["indices"], base_dir, binary)]
    else:
        indices = list(range(len(positions)))
    colours = None
    if "COLOR_0" in attributes:
        raw = _accessor(document, attributes["COLOR_0"], base_dir, binary)
        colours = [tuple(max(0, min(255, int(round(v * 255.0)))) for v in row[:3]) for row in raw]
    fallback = _material_colour(document, primitive)
    out: list[float] = []
    for a, b, c in _triangle_indices(primitive.get("mode", 4), len(indices)):
        corners = (indices[a], indices[b], indices[c])
        if max(corners) >= len(positions) or min(corners) < 0:
            raise ModelError("an index points past the POSITION accessor")
        if max(corners) >= len(joints) or max(corners) >= len(weights):
            raise ModelError("an index points past the skin attributes")
        channels = [colours[i] for i in corners] if colours is not None else None
        colour = (
            tuple(int(round(sum(channel[k] for channel in channels) / 3.0)) for k in range(3))
            if channels is not None
            else fallback
        )
        for i in corners:
            out.extend(float(v) for v in positions[i][:3])
            out.extend((float(colour[0]), float(colour[1]), float(colour[2])))
            joint_row = list(joints[i])[:4]
            weight_row = [float(value) for value in list(weights[i])[:4]]
            while len(joint_row) < 4:
                joint_row.append(0)
            while len(weight_row) < 4:
                weight_row.append(0.0)
            total = sum(weight_row)
            if total > 0.0:
                weight_row = [value / total for value in weight_row]
            out.extend(float(value) for value in joint_row)
            out.extend(weight_row)
    return out


def load_animated(path: pathlib.Path) -> dict:
    """Bake a model with its node hierarchy and one animation clip.

    Triangles stay in node-local space so the runtime can pose the hierarchy
    each frame; a static model is still baked in world space, which is cheaper.
    """
    document, binary = _container(path)
    if not isinstance(document, dict) or "asset" not in document:
        raise ModelError(f"{path.name} has no glTF 'asset' block")
    animations = document.get("animations") or []
    if not animations:
        raise ModelError("the model has no animation clips")
    if len(animations) > 1:
        raise ModelError("only the first animation clip is supported")
    nodes_doc = document.get("nodes", [])
    if len(nodes_doc) > 128:
        raise ModelError("the model has more than 128 nodes")
    base_dir = path.parent

    parents = [-1] * len(nodes_doc)
    for index, node in enumerate(nodes_doc):
        for child in node.get("children", []):
            if not isinstance(child, int) or child < 0 or child >= len(nodes_doc):
                raise ModelError("a node index is out of range")
            parents[child] = index

    nodes: list[float] = []
    for node in nodes_doc:
        translation, rotation, scale = _node_trs(node)
        nodes.extend(translation)
        nodes.extend(rotation)
        nodes.extend(scale)

    scenes = document.get("scenes")
    if scenes:
        roots = scenes[document.get("scene", 0)].get("nodes", [])
    else:
        roots = list(range(len(nodes_doc)))

    vertices: list[float] = []
    groups: list[int] = []

    def visit(index: int, depth: int) -> None:
        if depth > 64:
            raise ModelError("the node hierarchy is deeper than 64 levels")
        if index < 0 or index >= len(nodes_doc):
            raise ModelError("a node index is out of range")
        node = nodes_doc[index]
        if "mesh" in node:
            first = len(vertices) // 12
            for primitive in _mesh_for_node(document, node).get("primitives", []):
                vertices.extend(_primitive(document, primitive, _identity(), base_dir, binary))
            count = len(vertices) // 12 - first
            if count:
                groups.extend((index, first, count))
            if len(vertices) // 12 > MAX_TRIANGLES:
                raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
        for child in node.get("children", []):
            visit(child, depth + 1)

    for root in roots:
        visit(root, 0)
    if not vertices:
        raise ModelError("the model has no triangle geometry")

    tracks, times, values, length = _clip(document, nodes_doc, base_dir, binary)

    return {
        "vertices": vertices,
        "nodes": nodes,
        "parents": parents,
        "groups": groups,
        "tracks": tracks,
        "times": times,
        "values": values,
        "length": length,
    }


# ---- Compiler integration -------------------------------------------------

_registry: dict[str, tuple[str, int, list[float], tuple[float, float, float, float]]] = {}
_prescan: set[str] = set()
PATTERN = re.compile(
    r'\b(?:model_draw|ray_mesh|model_animate|model_animation_length|model_morph)\s*\(\s*"((?:[^"\\]|\\.)*)"'
)


def reset() -> None:
    _registry.clear()
    _prescan.clear()


def prescan(source_text: str, source_path: pathlib.Path) -> None:
    """Register every literal model path before C emission starts."""
    for match in PATTERN.finditer(source_text):
        try:
            asset = json.loads('"' + match.group(1) + '"')
        except ValueError:
            continue
        try:
            ensure_model(asset, source_path)
        except ModelError:
            # The lowering reports the model error at its source line; a
            # prescan has no line to name.
            continue
        _prescan.add(str(_resolve(asset, source_path)))


def _resolve(asset: str, source_path: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(asset)
    if not path.is_absolute():
        path = pathlib.Path(source_path).parent / path
    return path.resolve()


def bounds_of(data: list[float]) -> tuple[float, float, float, float]:
    """Centre and radius of a sphere around the baked triangles."""
    if not data:
        return (0.0, 0.0, 0.0, 0.0)
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for start in range(0, len(data), 12):
        for vertex in range(3):
            xs.append(data[start + vertex * 3])
            ys.append(data[start + vertex * 3 + 1])
            zs.append(data[start + vertex * 3 + 2])
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    cz = (min(zs) + max(zs)) / 2.0
    radius = 0.0
    for x, y, z in zip(xs, ys, zs):
        distance = ((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) ** 0.5
        radius = max(radius, distance)
    return (cx, cy, cz, radius)


def _kind(path: pathlib.Path) -> str:
    """Classify the model from one read: skinned, animated or static."""
    try:
        document, _ = _container(path)
    except ModelError:
        return "static"
    if not isinstance(document, dict):
        return "static"
    nodes = document.get("nodes", [])
    if document.get("skins") and any("skin" in node for node in nodes):
        return "skinned"
    if document.get("animations"):
        return "animated"
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if primitive.get("targets"):
                return "morphed"
    return "static"


def _skinned_bounds(vertices: list[float]) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for start in range(0, len(vertices), 14):
        xs.append(vertices[start])
        ys.append(vertices[start + 1])
        zs.append(vertices[start + 2])
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    cz = (min(zs) + max(zs)) / 2.0
    radius = 0.0
    for x, y, z in zip(xs, ys, zs):
        radius = max(radius, ((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2) ** 0.5)
    return (cx, cy, cz, radius)


def ensure_model(asset: str, source_path: pathlib.Path) -> dict:
    """Register a model and return everything code generation needs.

    The returned dict always has symbol/count/bounds/id; an animated model also
    has the clip arrays and its length.
    """
    path = _resolve(asset, source_path)
    key = str(path)
    if key in _registry:
        return _registry[key]
    if not path.is_file():
        raise ModelError(f"cannot find model {asset!r} (resolved to {path})")
    if not key.endswith((".gltf", ".glb")):
        raise ModelError("only .gltf and .glb models are supported")
    entry: dict = {"id": len(_registry), "symbol": f"anvil_model_{len(_registry)}"}
    kind = _kind(path)
    if kind == "skinned":
        clip = load_skinned(path)
        entry.update(clip)
        entry["skinned"] = True
        entry["animated"] = False
        entry["count"] = len(clip["vertices"]) // 14 // 3
        entry["data"] = clip["vertices"]
        entry["bounds"] = _skinned_bounds(clip["vertices"])
    elif kind == "morphed":
        morph = load_morphed(path)
        entry.update(morph)
        entry["animated"] = False
        entry["count"] = len(morph["vertices"]) // 12
        entry["data"] = morph["vertices"]
        entry["bounds"] = bounds_of(morph["vertices"])
    elif kind == "animated":
        clip = load_animated(path)
        entry.update(clip)
        entry["animated"] = True
        entry["count"] = len(clip["vertices"]) // 12
        entry["data"] = clip["vertices"]
        entry["bounds"] = bounds_of(clip["vertices"])
    else:
        data = load_triangles(path)
        entry.update({"animated": False, "count": len(data) // 12, "data": data})
        entry["bounds"] = bounds_of(data)
    if (entry.get("animated") or entry.get("skinned")) and entry["id"] >= MODEL_STATES:
        # The runtime's clock table has MODEL_STATES slots; a posed model past
        # it would read clock 0 forever and never move. Fail at the source line.
        raise ModelError(
            f"the model needs clock slot {entry['id']} but only {MODEL_STATES} "
            "models can be registered; reduce the number of models before it"
        )
    _registry[key] = entry
    return entry


def ensure_emitted(
    asset: str, source_path: pathlib.Path
) -> tuple[str, int, tuple[float, float, float, float]]:
    entry = ensure_model(asset, source_path)
    return entry["symbol"], entry["count"], entry["bounds"]


def _double_array(lines: list[str], symbol: str, values: list[float], per_line: int) -> None:
    if not values:
        # A model with no clip still has to reference the time/value arrays; a
        # one-element placeholder keeps C happy and nothing reads it.
        values = [0.0]
    lines.append(f"static const double {symbol}[{len(values)}] = {{")
    for start in range(0, len(values), per_line):
        chunk = values[start : start + per_line]
        lines.append("    " + ", ".join(f"{value:.6g}" for value in chunk) + ",")
    lines.append("};")


def _int_array(lines: list[str], symbol: str, values: list[int], per_line: int) -> None:
    if not values:
        values = [0]
    lines.append(f"static const int {symbol}[{len(values)}] = {{")
    for start in range(0, len(values), per_line):
        chunk = values[start : start + per_line]
        lines.append("    " + ", ".join(str(value) for value in chunk) + ",")
    lines.append("};")


def definitions() -> list[str]:
    lines: list[str] = []
    for key, entry in _registry.items():
        symbol = entry["symbol"]
        count = entry["count"]
        if entry.get("skinned"):
            lines.append(
                f"/* model: {pathlib.Path(key).name}, {count} skinned triangles, "
                f"{len(entry['joint_nodes'])} joints */"
            )
            _double_array(lines, symbol, entry["data"], 14)
            _double_array(lines, symbol + "_nodes", entry["nodes"], 10)
            _int_array(lines, symbol + "_parents", entry["parents"], 16)
            _int_array(lines, symbol + "_joints", entry["joint_nodes"], 16)
            _double_array(lines, symbol + "_bind", entry["bind"], 16)
            _double_array(lines, symbol + "_times", entry["times"], 8)
            _double_array(lines, symbol + "_values", entry["values"], 8)
            _int_array(lines, symbol + "_tracks", entry["tracks"], 6)
        elif entry.get("morph_count"):
            lines.append(
                f"/* model: {pathlib.Path(key).name}, {count} morphing triangles, "
                f"{entry['morph_count']} targets */"
            )
            _double_array(lines, symbol, entry["data"], 12)
            _double_array(lines, symbol + "_morph", entry["morph"], 12)
            _double_array(lines, symbol + "_morph_default", entry["morph_defaults"], 8)
        elif entry.get("animated"):
            lines.append(
                f"/* model: {pathlib.Path(key).name}, {count} animated triangles, "
                f"{entry['length']:.6g} s clip */"
            )
            _double_array(lines, symbol, entry["data"], 12)
            _double_array(lines, symbol + "_nodes", entry["nodes"], 10)
            _int_array(lines, symbol + "_parents", entry["parents"], 16)
            _int_array(lines, symbol + "_groups", entry["groups"], 12)
            _double_array(lines, symbol + "_times", entry["times"], 8)
            _double_array(lines, symbol + "_values", entry["values"], 8)
            _int_array(lines, symbol + "_tracks", entry["tracks"], 6)
        else:
            lines.append(f"/* model: {pathlib.Path(key).name}, {count} triangles */")
            _double_array(lines, symbol, entry["data"], 12)
        lines.append("")
    return lines


def late_models() -> list[str]:
    """Models discovered during emission but not pre-scanned (unsupported)."""
    return [key for key in _registry if key not in _prescan]
