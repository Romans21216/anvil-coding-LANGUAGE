"""Compile-time glTF import.

`model_draw("file.gltf" or "file.glb", x, y, z, scale, rx, ry, rz)` is lowered
by the C and WebAssembly backends into baked triangle data, so the runtime never
parses model JSON and the model ships inside the executable. This module reads
the source during compilation and returns flat triangles plus any supported
animation, skin or morph data.

Supported containers are glTF JSON and binary GLB 2. Buffers can come from
external files, base64 data URIs or the GLB BIN chunk. The importer handles node
hierarchies with matrix or TRS transforms, triangle/triangle-strip/triangle-fan
primitives, POSITION and optional COLOR_0 attributes, per-material
baseColorFactor, and node TRS animation clips (translation/rotation/scale,
LINEAR and STEP keys). Animated models bake node-local triangles and hierarchy
data for runtime posing; static models use a cheaper world-space bake. One skin
can bake mesh-space vertices with four joint indices and weights per vertex,
plus inverse bind matrices. Morph targets are supported for unskinned static
and animated models. Base-color PNG textures with `TEXCOORD_0` are supported
for static, animated and skinned `model_draw` calls in both backends. Sparse
accessors are not
supported yet.
"""

from __future__ import annotations

import base64
import array
import functools
import json
import math
import pathlib
import struct
import time
from urllib.parse import unquote
import zlib

MAX_TRIANGLES = 200_000
MAX_CONTAINER_BYTES = 64 * 1024 * 1024
MAX_BUFFER_BYTES = 256 * 1024 * 1024
MAX_ACCESSOR_DECODED_BYTES = 64 * 1024 * 1024
MAX_GEOMETRY_BYTES = 512 * 1024 * 1024
MAX_TEXTURE_BYTES = 64 * 1024 * 1024
MAX_TEXTURE_PIXELS = 16 * 1024 * 1024
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


def _safe_resolve(path: pathlib.Path, label: str) -> pathlib.Path:
    try:
        return path.resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise ModelError(f"cannot resolve {label}: {error}") from None


def _translate_malformed_structure(loader):
    """Keep malformed JSON failures inside the importer's diagnostic contract."""
    @functools.wraps(loader)
    def wrapped(*args, **kwargs):
        owns_cache_scope = not _cache_import_reads
        if owns_cache_scope:
            _begin_import_cache()
        try:
            return loader(*args, **kwargs)
        except ModelError:
            raise
        except (KeyError, IndexError, TypeError, ValueError, OverflowError, AttributeError) as error:
            raise ModelError(f"malformed glTF structure: {error}") from None
        finally:
            if owns_cache_scope:
                _end_import_cache()

    return wrapped


def _buffer_bytes(
    document: dict, index: int, base_dir: pathlib.Path, binary: bytes | None = None
) -> bytes:
    cache_key = (id(document), index)
    cached = _buffer_cache.get(cache_key) if _cache_import_reads else None
    if cached is not None:
        return cached
    buffer = document["buffers"][index]
    uri = buffer.get("uri")
    if uri is None:
        if index == 0 and binary is not None:
            return binary
        raise ModelError("a buffer has no uri and the file has no GLB binary chunk")
    if not isinstance(uri, str):
        raise ModelError("a buffer uri must be a string")
    if uri[:5].lower() == "data:":
        header, _, payload = uri.partition(",")
        if not payload or ";base64" not in header.lower():
            raise ModelError("only base64 data URIs are supported")
        try:
            declared = buffer.get("byteLength")
            if isinstance(declared, int) and declared > MAX_BUFFER_BYTES:
                raise ModelError(f"a buffer exceeds the {MAX_BUFFER_BYTES} byte import limit")
            if len(payload) > ((MAX_BUFFER_BYTES + 2) // 3) * 4 + 8:
                raise ModelError(f"a buffer exceeds the {MAX_BUFFER_BYTES} byte import limit")
            decoded = base64.b64decode(payload, validate=True)
            if len(decoded) > MAX_BUFFER_BYTES:
                raise ModelError(f"a buffer exceeds the {MAX_BUFFER_BYTES} byte import limit")
            if _cache_import_reads:
                _buffer_cache[cache_key] = decoded
            return decoded
        except ValueError as error:
            raise ModelError(f"invalid base64 buffer: {error}") from error
    root = _asset_root or _safe_resolve(base_dir, "project folder")
    path = pathlib.Path(unquote(uri))
    if not path.is_absolute():
        path = base_dir / path
    path = _safe_resolve(path, f"buffer uri {uri!r}")
    try:
        path.relative_to(_safe_resolve(root, "project folder"))
    except ValueError:
        raise ModelError("a buffer uri must resolve inside the project folder") from None
    try:
        if path.stat().st_size > MAX_BUFFER_BYTES:
            raise ModelError(f"a buffer exceeds the {MAX_BUFFER_BYTES} byte import limit")
        data = path.read_bytes()
        if _cache_import_reads:
            _buffer_cache[cache_key] = data
        return data
    except OSError as error:
        raise ModelError(f"cannot read buffer {uri!r}: {error}") from error


def _decode_png_rgba(raw: bytes) -> tuple[int, int, array.array]:
    """Decode a bounded, non-interlaced 8-bit RGB/RGBA PNG to 0xAARRGGBB."""
    if len(raw) > MAX_TEXTURE_BYTES:
        raise ModelError(f"a texture exceeds the {MAX_TEXTURE_BYTES} byte import limit")
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ModelError("only PNG base-color textures are supported")
    offset = 8
    width = height = bit_depth = color_type = None
    compressed = bytearray()
    saw_header = saw_end = False
    while offset + 12 <= len(raw):
        chunk_length = struct.unpack_from(">I", raw, offset)[0]
        chunk_type = raw[offset + 4 : offset + 8]
        end = offset + 12 + chunk_length
        if end > len(raw):
            raise ModelError("a PNG texture chunk is truncated")
        payload = raw[offset + 8 : offset + 8 + chunk_length]
        expected_crc = struct.unpack_from(">I", raw, offset + 8 + chunk_length)[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            raise ModelError("a PNG texture chunk has an invalid checksum")
        if chunk_type == b"IHDR":
            if saw_header or chunk_length != 13:
                raise ModelError("a PNG texture has an invalid header")
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            if compression != 0 or filtering != 0 or interlace != 0:
                raise ModelError("interlaced or non-standard PNG textures are not supported")
            if bit_depth != 8 or color_type not in (2, 6):
                raise ModelError("PNG textures must use 8-bit RGB or RGBA pixels")
            if width == 0 or height == 0 or width * height > MAX_TEXTURE_PIXELS:
                raise ModelError(f"a texture exceeds the {MAX_TEXTURE_PIXELS} pixel import limit")
            saw_header = True
        elif chunk_type == b"IDAT":
            if not saw_header or saw_end:
                raise ModelError("a PNG texture has misplaced image data")
            if len(compressed) + chunk_length > MAX_TEXTURE_BYTES:
                raise ModelError(f"a texture exceeds the {MAX_TEXTURE_BYTES} byte import limit")
            compressed.extend(payload)
        elif chunk_type == b"IEND":
            if chunk_length != 0:
                raise ModelError("a PNG texture has an invalid end chunk")
            saw_end = True
            offset = end
            break
        elif chunk_type[0] & 0x20 == 0 and chunk_type not in (b"IHDR", b"PLTE"):
            raise ModelError("a PNG texture uses an unsupported critical chunk")
        offset = end
    if not saw_header or not saw_end or offset != len(raw) or not compressed:
        raise ModelError("a PNG texture is incomplete")
    channels = 3 if color_type == 2 else 4
    stride = width * channels
    expected_size = height * (stride + 1)
    try:
        inflater = zlib.decompressobj()
        decoded = inflater.decompress(bytes(compressed), expected_size + 1)
    except zlib.error as error:
        raise ModelError(f"a PNG texture has invalid compressed data: {error}") from None
    if (
        len(decoded) != expected_size
        or not inflater.eof
        or inflater.unused_data
        or inflater.unconsumed_tail
    ):
        raise ModelError("a PNG texture has an invalid decompressed size")
    pixels = bytearray(height * stride)
    source_offset = 0
    for y in range(height):
        filter_type = decoded[source_offset]
        source_offset += 1
        row = decoded[source_offset : source_offset + stride]
        source_offset += stride
        destination = y * stride
        previous = pixels[destination - stride : destination] if y else None
        for x in range(stride):
            left = pixels[destination + x - channels] if x >= channels else 0
            above = previous[x] if previous is not None else 0
            upper_left = previous[x - channels] if previous is not None and x >= channels else 0
            if filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                p = left + above - upper_left
                pa, pb, pc = abs(p - left), abs(p - above), abs(p - upper_left)
                predictor = left if pa <= pb and pa <= pc else above if pb <= pc else upper_left
            elif filter_type == 0:
                predictor = 0
            else:
                raise ModelError("a PNG texture uses an unsupported row filter")
            pixels[destination + x] = (row[x] + predictor) & 0xFF
    packed = array.array("I")
    for index in range(0, len(pixels), channels):
        red, green, blue = pixels[index : index + 3]
        alpha = pixels[index + 3] if channels == 4 else 255
        packed.append((alpha << 24) | (red << 16) | (green << 8) | blue)
    return width, height, packed


def _image_bytes(
    document: dict, image: dict, base_dir: pathlib.Path, binary: bytes | None
) -> bytes:
    """Read a glTF image from a project-contained URI or a bufferView."""
    uri = image.get("uri")
    if uri is not None:
        if not isinstance(uri, str):
            raise ModelError("an image uri must be a string")
        if uri[:5].lower() == "data:":
            header, separator, payload = uri.partition(",")
            if not separator or ";base64" not in header.lower():
                raise ModelError("only base64 data URIs are supported for images")
            if len(payload) > ((MAX_TEXTURE_BYTES + 2) // 3) * 4 + 8:
                raise ModelError(f"a texture exceeds the {MAX_TEXTURE_BYTES} byte import limit")
            try:
                raw = base64.b64decode(payload, validate=True)
            except ValueError as error:
                raise ModelError(f"an image has invalid base64 data: {error}") from None
            if len(raw) > MAX_TEXTURE_BYTES:
                raise ModelError(f"a texture exceeds the {MAX_TEXTURE_BYTES} byte import limit")
            return raw
        root = _asset_root or _safe_resolve(base_dir, "project folder")
        path = pathlib.Path(unquote(uri))
        if not path.is_absolute():
            path = base_dir / path
        path = _safe_resolve(path, f"image uri {uri!r}")
        try:
            path.relative_to(_safe_resolve(root, "project folder"))
        except ValueError:
            raise ModelError("an image uri must resolve inside the project folder") from None
        try:
            if path.stat().st_size > MAX_TEXTURE_BYTES:
                raise ModelError(f"a texture exceeds the {MAX_TEXTURE_BYTES} byte import limit")
            return path.read_bytes()
        except OSError as error:
            raise ModelError(f"cannot read image {uri!r}: {error}") from None

    view_index = image.get("bufferView")
    views = document.get("bufferViews")
    if (
        not isinstance(view_index, int)
        or isinstance(view_index, bool)
        or not isinstance(views, list)
        or not 0 <= view_index < len(views)
        or not isinstance(views[view_index], dict)
    ):
        raise ModelError("an image needs a valid uri or bufferView")
    view = views[view_index]
    buffer_index = view.get("buffer")
    buffers = document.get("buffers")
    if (
        not isinstance(buffer_index, int)
        or isinstance(buffer_index, bool)
        or not isinstance(buffers, list)
        or not 0 <= buffer_index < len(buffers)
        or not isinstance(buffers[buffer_index], dict)
    ):
        raise ModelError("an image bufferView refers to an invalid buffer")
    offset = view.get("byteOffset", 0)
    length = view.get("byteLength")
    declared = buffers[buffer_index].get("byteLength")
    if (
        not isinstance(offset, int)
        or isinstance(offset, bool)
        or not isinstance(length, int)
        or isinstance(length, bool)
        or not isinstance(declared, int)
        or isinstance(declared, bool)
        or offset < 0
        or length <= 0
        or length > MAX_TEXTURE_BYTES
        or offset + length > declared
    ):
        raise ModelError("an image bufferView has an invalid byte range")
    data = _buffer_bytes(document, buffer_index, base_dir, binary)
    if len(data) < declared or offset + length > len(data):
        raise ModelError("an image bufferView reads past its buffer")
    return data[offset : offset + length]


def _accessor(
    document: dict, index: int, base_dir: pathlib.Path, binary: bytes | None = None,
    *, vertex_attribute: bool = False, semantic: str | None = None,
) -> list[tuple]:
    accessors = document.get("accessors")
    if (
        not isinstance(accessors, list)
        or not isinstance(index, int)
        or isinstance(index, bool)
        or index < 0
        or index >= len(accessors)
        or not isinstance(accessors[index], dict)
    ):
        raise ModelError("an accessor index is out of range")
    accessor = accessors[index]
    if accessor.get("sparse"):
        raise ModelError("sparse accessors are not supported")
    views = document.get("bufferViews")
    view_index = accessor.get("bufferView")
    if (
        not isinstance(views, list)
        or not isinstance(view_index, int)
        or isinstance(view_index, bool)
        or view_index < 0
        or view_index >= len(views)
        or not isinstance(views[view_index], dict)
    ):
        raise ModelError("an accessor bufferView index is out of range")
    view = views[view_index]
    buffers = document.get("buffers")
    buffer_index = view.get("buffer")
    if (
        not isinstance(buffers, list)
        or not isinstance(buffer_index, int)
        or isinstance(buffer_index, bool)
        or buffer_index < 0
        or buffer_index >= len(buffers)
        or not isinstance(buffers[buffer_index], dict)
    ):
        raise ModelError("a bufferView buffer index is out of range")

    def nonnegative_integer(value, label: str, *, positive: bool = False) -> int:
        minimum = 1 if positive else 0
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            qualifier = "positive " if positive else "non-negative "
            raise ModelError(f"{label} must be a {qualifier}integer")
        return value

    buffer_spec = buffers[buffer_index]
    declared_buffer_length = nonnegative_integer(
        buffer_spec.get("byteLength"), "a buffer byteLength", positive=True
    )
    view_offset = nonnegative_integer(view.get("byteOffset", 0), "a bufferView byteOffset")
    view_length = nonnegative_integer(view.get("byteLength"), "a bufferView byteLength", positive=True)
    if view_offset + view_length > declared_buffer_length:
        raise ModelError("a bufferView reads past its declared buffer")

    component = accessor.get("componentType")
    if component not in COMPONENTS:
        raise ModelError(f"unsupported accessor component type {component}")
    fmt, size, scale = COMPONENTS[component]
    accessor_type = accessor.get("type")
    if accessor_type not in TYPE_SIZE:
        raise ModelError(f"unsupported accessor type {accessor_type}")
    width = TYPE_SIZE[accessor_type]
    element_size = size * width
    accessor_offset = nonnegative_integer(
        accessor.get("byteOffset", 0), "an accessor byteOffset"
    )
    count = nonnegative_integer(accessor.get("count"), "an accessor count", positive=True)
    if count > MAX_TRIANGLES * 3 + 2:
        raise ModelError(f"an accessor exceeds the {MAX_TRIANGLES * 3 + 2} element import limit")
    # Account for the unpacked Python number and tuple/list references, not
    # only the tightly packed bytes in the source buffer.
    if count * width * 16 > MAX_ACCESSOR_DECODED_BYTES:
        raise ModelError(
            f"an accessor exceeds the {MAX_ACCESSOR_DECODED_BYTES} byte decoded import limit"
        )
    if "byteStride" in view:
        if not vertex_attribute:
            raise ModelError("byteStride is only valid for vertex attribute accessors")
        stride = nonnegative_integer(view["byteStride"], "a bufferView byteStride", positive=True)
        if stride < 4 or stride > 252 or stride % 4 or stride % size or stride > view_length:
            raise ModelError("a bufferView byteStride must be 4-252 bytes, component-aligned, and no larger than its bufferView")
    else:
        stride = element_size
    if stride < element_size or stride % size:
        raise ModelError("a bufferView byteStride is smaller than or misaligned for its accessor")
    if view_offset % size or accessor_offset % size:
        raise ModelError("an accessor is not aligned to its component size")
    if accessor_offset + (count - 1) * stride + element_size > view_length:
        raise ModelError("an accessor reads past its declared bufferView")
    offset = view_offset + accessor_offset
    normalized = accessor.get("normalized", False)
    if not isinstance(normalized, bool):
        raise ModelError("an accessor normalized value must be a boolean")
    if normalized and component not in (5120, 5121, 5122, 5123):
        raise ModelError("normalized is only valid for BYTE, UNSIGNED_BYTE, SHORT, or UNSIGNED_SHORT accessors")
    if normalized and semantic == "JOINTS_0":
        raise ModelError("JOINTS_0 accessors cannot be normalized")
    # Validate metadata and decode/allocation bounds before opening the buffer.
    buffer = _buffer_bytes(document, buffer_index, base_dir, binary)
    if len(buffer) < declared_buffer_length:
        raise ModelError("a buffer is shorter than its declared byteLength")
    values = []
    for i in range(count):
        base = offset + i * stride
        row = struct.unpack_from("<" + fmt * width, buffer, base)
        if normalized and scale != 1.0:
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


def _triangle_count(mode: int, count: int) -> int:
    if mode == 4:
        return count // 3
    if mode in (5, 6):
        return max(0, count - 2)
    raise ModelError(f"unsupported primitive mode {mode}; only triangles, strips and fans are supported")


def _validate_index_accessor(document: dict, index: int) -> int:
    accessors = document.get("accessors", [])
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(accessors):
        raise ModelError("an accessor index is out of range")
    accessor = accessors[index]
    if accessor.get("type") != "SCALAR":
        raise ModelError("an index accessor must have SCALAR type")
    if accessor.get("componentType") not in (5121, 5123, 5125):
        raise ModelError("an index accessor must use an unsigned byte, short or int component type")
    normalized = accessor.get("normalized", False)
    if not isinstance(normalized, bool):
        raise ModelError("an accessor normalized value must be a boolean")
    if normalized and accessor.get("componentType") not in (5120, 5121, 5122, 5123):
        raise ModelError("normalized is only valid for BYTE, UNSIGNED_BYTE, SHORT, or UNSIGNED_SHORT accessors")
    if normalized:
        raise ModelError("an index accessor cannot be normalized")
    return accessor.get("count", 0)


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


def _material_alpha(document: dict, primitive: dict) -> int:
    index = primitive.get("material")
    if index is None:
        return 255
    try:
        factor = document["materials"][index]["pbrMetallicRoughness"]["baseColorFactor"]
        alpha = float(factor[3])
    except (KeyError, IndexError, TypeError, ValueError, OverflowError):
        return 255
    if not math.isfinite(alpha):
        raise ModelError("baseColorFactor alpha must be finite")
    return max(0, min(255, int(round(alpha * 255.0))))


def _has_base_color_texture(document: dict) -> bool:
    materials = document.get("materials", [])
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            material_index = primitive.get("material")
            if (
                isinstance(material_index, int)
                and not isinstance(material_index, bool)
                and 0 <= material_index < len(materials)
                and isinstance(materials[material_index], dict)
            ):
                pbr = materials[material_index].get("pbrMetallicRoughness", {})
                if isinstance(pbr, dict) and pbr.get("baseColorTexture") is not None:
                    return True
    return False


def _collect_base_color_textures(
    document: dict, base_dir: pathlib.Path, binary: bytes | None
) -> tuple[dict[int, int], list[tuple[int, int, array.array]]]:
    """Load the PNGs referenced by baseColorTexture, in compact table order."""
    textures = document.get("textures", [])
    images = document.get("images", [])
    materials = document.get("materials", [])
    if not isinstance(textures, list) or not isinstance(images, list) or not isinstance(materials, list):
        raise ModelError("glTF texture, image and material tables must be arrays")
    texture_to_image: dict[int, int] = {}
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            material_index = primitive.get("material")
            if material_index is None:
                continue
            if not isinstance(material_index, int) or isinstance(material_index, bool) or not 0 <= material_index < len(materials):
                raise ModelError("a primitive material index is out of range")
            material = materials[material_index]
            pbr = material.get("pbrMetallicRoughness", {})
            info = pbr.get("baseColorTexture")
            if info is None:
                continue
            if not isinstance(info, dict):
                raise ModelError("a baseColorTexture entry must be an object")
            tex_coord = info.get("texCoord", 0)
            if not isinstance(tex_coord, int) or isinstance(tex_coord, bool) or tex_coord != 0:
                raise ModelError("base-color textures currently require TEXCOORD_0")
            extensions = info.get("extensions", {})
            if not isinstance(extensions, dict):
                raise ModelError("baseColorTexture extensions must be an object")
            if "KHR_texture_transform" in extensions:
                raise ModelError("KHR_texture_transform is not supported for base-color textures")
            texture_index = info.get("index")
            if not isinstance(texture_index, int) or isinstance(texture_index, bool) or not 0 <= texture_index < len(textures):
                raise ModelError("a baseColorTexture index is out of range")
            texture = textures[texture_index]
            if not isinstance(texture, dict):
                raise ModelError("a glTF texture entry must be an object")
            sampler_index = texture.get("sampler")
            if sampler_index is not None:
                samplers = document.get("samplers", [])
                if not isinstance(sampler_index, int) or isinstance(sampler_index, bool) or not isinstance(samplers, list) or not 0 <= sampler_index < len(samplers):
                    raise ModelError("a glTF texture sampler index is out of range")
                sampler = samplers[sampler_index]
                if sampler.get("wrapS", 10497) != 10497 or sampler.get("wrapT", 10497) != 10497:
                    raise ModelError("base-color texture samplers must use REPEAT wrapping")
            image_index = texture.get("source")
            if not isinstance(image_index, int) or isinstance(image_index, bool) or not 0 <= image_index < len(images):
                raise ModelError("a glTF texture source image index is out of range")
            texture_to_image[texture_index] = image_index
    image_slots: dict[int, int] = {}
    decoded: list[tuple[int, int, array.array]] = []
    texture_slots: dict[int, int] = {}
    total_bytes = 0
    for texture_index, image_index in texture_to_image.items():
        slot = image_slots.get(image_index)
        if slot is None:
            image = images[image_index]
            if not isinstance(image, dict):
                raise ModelError("a glTF image entry must be an object")
            width, height, pixels = _decode_png_rgba(
                _image_bytes(document, image, base_dir, binary)
            )
            total_bytes += len(pixels) * 4
            if total_bytes > MAX_TEXTURE_BYTES:
                raise ModelError(f"model textures exceed the {MAX_TEXTURE_BYTES} byte import limit")
            slot = len(decoded)
            image_slots[image_index] = slot
            decoded.append((width, height, pixels))
        texture_slots[texture_index] = slot
    return texture_slots, decoded


def _primitive(
    document: dict,
    primitive: dict,
    matrix: list[float],
    base_dir: pathlib.Path,
    binary: bytes | None = None,
    morph_out: list[float] | None = None,
    max_triangles: int = MAX_TRIANGLES,
    texture_out: list[float] | None = None,
    texture_slots: dict[int, int] | None = None,
) -> list[float]:
    attributes = primitive.get("attributes", {})
    if "POSITION" not in attributes:
        raise ModelError("a primitive has no POSITION attribute")
    if primitive.get("indices") is not None:
        index_count = _validate_index_accessor(document, primitive["indices"])
    else:
        position_index = attributes["POSITION"]
        accessors = document.get("accessors", [])
        if not isinstance(position_index, int) or isinstance(position_index, bool) or not 0 <= position_index < len(accessors):
            raise ModelError("an accessor index is out of range")
        index_count = accessors[position_index].get("count", 0)
    if _triangle_count(primitive.get("mode", 4), index_count) > max_triangles:
        raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
    positions = _accessor(document, attributes["POSITION"], base_dir, binary, vertex_attribute=True, semantic="POSITION")
    if attributes.get("POSITION") is not None and len(positions) and len(positions[0]) != 3:
        raise ModelError("POSITION must be a VEC3 accessor")
    if any(not math.isfinite(float(value)) for row in positions for value in row):
        raise ModelError("POSITION contains a non-finite value")
    if primitive.get("indices") is not None:
        indices = [row[0] for row in _accessor(document, primitive["indices"], base_dir, binary)]
    else:
        indices = list(range(len(positions)))

    colours = None
    if "COLOR_0" in attributes:
        raw = _accessor(document, attributes["COLOR_0"], base_dir, binary, vertex_attribute=True, semantic="COLOR_0")
        colours = [tuple(max(0, min(255, int(round(v * 255.0)))) for v in row[:3]) for row in raw]
    fallback = _material_colour(document, primitive)
    texture_index = -1
    if texture_slots is not None:
        material_index = primitive.get("material")
        if material_index is not None:
            info = document["materials"][material_index].get("pbrMetallicRoughness", {}).get("baseColorTexture")
            if info is not None:
                texture_index = texture_slots[info["index"]]
    texcoords = None
    if texture_index >= 0:
        if "TEXCOORD_0" not in attributes:
            raise ModelError("a textured primitive has no TEXCOORD_0 attribute")
        texcoords = _accessor(
            document, attributes["TEXCOORD_0"], base_dir, binary,
            vertex_attribute=True, semantic="TEXCOORD_0",
        )
        if len(texcoords) != len(positions) or any(len(row) != 2 for row in texcoords):
            raise ModelError("TEXCOORD_0 must be a VEC2 accessor matching POSITION")
        if any(not math.isfinite(float(value)) for row in texcoords for value in row):
            raise ModelError("TEXCOORD_0 contains a non-finite value")

    targets = primitive.get("targets", [])
    deltas: list[list[tuple[float, float, float]]] = []
    if morph_out is not None and len(targets) > MAX_MORPH_TARGETS:
        raise ModelError(f"a model may use at most {MAX_MORPH_TARGETS} morph targets")
    for target in (targets if morph_out is not None else ()):
        if "POSITION" not in target:
            raise ModelError("a morph target needs a POSITION delta")
        raw = _accessor(document, target["POSITION"], base_dir, binary, vertex_attribute=True, semantic="POSITION")
        if any(not math.isfinite(float(value)) for row in raw for value in row):
            raise ModelError("a morph target contains a non-finite value")
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
    if any(
        not math.isfinite(component)
        for target in deltas
        for vertex in target
        for component in vertex
    ):
        raise ModelError("a transformed morph target contains a non-finite value")

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
        if texture_out is not None:
            for corner, point in zip(corners, points):
                texture_out.extend(point)
                texture_out.extend(texcoords[corner] if texcoords is not None else (0.0, 0.0))
            texture_colour = colour
            if texture_index >= 0:
                vertex_colour = (
                    tuple(
                        sum(colours[i][channel] for i in corners) / 3.0
                        for channel in range(3)
                    )
                    if colours is not None
                    else (255.0, 255.0, 255.0)
                )
                texture_colour = tuple(
                    int(round(fallback[channel] * vertex_colour[channel] / 255.0))
                    for channel in range(3)
                )
            texture_out.extend(float(channel) for channel in texture_colour)
            texture_out.append(float(_material_alpha(document, primitive)))
            texture_out.append(float(texture_index))
        if morph_out is not None:
            for corner in corners:
                for target in deltas:
                    morph_out.extend(target[corner])
    if any(not math.isfinite(value) for value in out):
        raise ModelError("the transformed geometry contains a non-finite value")
    return out


def _container(path: pathlib.Path) -> tuple[dict, bytes | None]:
    """Return (document, GLB binary chunk) for a .gltf or .glb file."""
    path = _safe_resolve(path, f"model {path}")
    cached = _container_cache.get(path) if _cache_import_reads else None
    if cached is not None:
        return cached
    suffix = path.suffix.lower()
    try:
        if path.stat().st_size > MAX_CONTAINER_BYTES:
            raise ModelError(f"{path.name} exceeds the {MAX_CONTAINER_BYTES} byte model import limit")
        raw = path.read_bytes()
    except OSError as error:
        raise ModelError(f"cannot read {path.name}: {error}") from error
    if suffix == ".gltf":
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ModelError(f"{path.name} is not valid glTF JSON: {error}") from error
        _validate_document(document, path.name)
        result = (document, None)
        if _cache_import_reads:
            _container_cache[path] = result
        return result
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
    _validate_document(document, path.name)
    result = (document, binary)
    if _cache_import_reads:
        _container_cache[path] = result
    return result


def _validate_document(document: object, name: str) -> None:
    """Reject malformed structural JSON before loaders traverse its graph."""
    if not isinstance(document, dict):
        raise ModelError(f"{name} root must be a JSON object")
    asset = document.get("asset")
    if not isinstance(asset, dict) or not isinstance(asset.get("version"), str):
        raise ModelError(f"{name} has no valid glTF 'asset' block")

    def array(key: str, required: bool = False) -> list:
        value = document.get(key, [] if not required else None)
        if not isinstance(value, list):
            raise ModelError(f"glTF {key} must be an array")
        return value

    buffers = array("buffers")
    views = array("bufferViews")
    accessors = array("accessors")
    meshes = array("meshes")
    nodes = array("nodes")
    scenes = array("scenes")
    skins = array("skins")
    animations = array("animations")
    for index, value in enumerate(buffers):
        if not isinstance(value, dict):
            raise ModelError(f"glTF buffer {index} must be an object")
        if "uri" in value and not isinstance(value["uri"], str):
            raise ModelError(f"glTF buffer {index} uri must be a string")
        byte_length = value.get("byteLength")
        if not isinstance(byte_length, int) or isinstance(byte_length, bool) or byte_length < 0:
            raise ModelError(f"glTF buffer {index} byteLength must be a non-negative integer")
        if byte_length > MAX_BUFFER_BYTES:
            raise ModelError(f"a buffer exceeds the {MAX_BUFFER_BYTES} byte import limit")
    for index, view in enumerate(views):
        if not isinstance(view, dict):
            raise ModelError(f"glTF bufferView {index} must be an object")
        buffer_index = view.get("buffer")
        if not isinstance(buffer_index, int) or isinstance(buffer_index, bool) or not 0 <= buffer_index < len(buffers):
            raise ModelError(f"glTF bufferView {index} references an invalid buffer")
    for index, accessor in enumerate(accessors):
        if not isinstance(accessor, dict):
            raise ModelError(f"glTF accessor {index} must be an object")
        view_index = accessor.get("bufferView")
        if view_index is not None and (
            not isinstance(view_index, int) or isinstance(view_index, bool)
            or not 0 <= view_index < len(views)
        ):
            raise ModelError(f"glTF accessor {index} references an invalid bufferView")
    for index, mesh in enumerate(meshes):
        if not isinstance(mesh, dict):
            raise ModelError(f"glTF mesh {index} must be an object")
        primitives = mesh.get("primitives", [])
        if not isinstance(primitives, list):
            raise ModelError(f"glTF mesh {index} primitives must be an array")
        for primitive in primitives:
            if not isinstance(primitive, dict):
                raise ModelError(f"glTF mesh {index} primitive must be an object")
            attributes = primitive.get("attributes", {})
            targets = primitive.get("targets", [])
            if not isinstance(attributes, dict) or not isinstance(targets, list):
                raise ModelError("glTF primitive attributes and targets must be objects/arrays")
            for accessor_index in list(attributes.values()) + ([primitive["indices"]] if "indices" in primitive else []):
                if not isinstance(accessor_index, int) or isinstance(accessor_index, bool) or not 0 <= accessor_index < len(accessors):
                    raise ModelError("glTF primitive references an invalid accessor")
            material_index = primitive.get("material")
            if material_index is not None:
                materials = array("materials")
                if not isinstance(material_index, int) or isinstance(material_index, bool) or not 0 <= material_index < len(materials):
                    raise ModelError("glTF primitive references an invalid material")
            if any(not isinstance(target, dict) for target in targets):
                raise ModelError("glTF morph targets must be objects")
            for target in targets:
                for accessor_index in target.values():
                    if not isinstance(accessor_index, int) or isinstance(accessor_index, bool) or not 0 <= accessor_index < len(accessors):
                        raise ModelError("glTF morph target references an invalid accessor")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ModelError(f"glTF node {index} must be an object")
        for key in ("children",):
            if key in node and not isinstance(node[key], list):
                raise ModelError(f"glTF node {index} {key} must be an array")
        children = node.get("children", [])
        if any(not isinstance(child, int) or isinstance(child, bool) or not 0 <= child < len(nodes) for child in children):
            raise ModelError("a node index is out of range")
        if "mesh" in node and (
            not isinstance(node["mesh"], int) or isinstance(node["mesh"], bool)
            or not 0 <= node["mesh"] < len(meshes)
        ):
            raise ModelError("a mesh index is out of range")
        if "skin" in node and (
            not isinstance(node["skin"], int) or isinstance(node["skin"], bool)
            or not 0 <= node["skin"] < len(skins)
        ):
            raise ModelError("a node references an invalid skin")
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict) or not isinstance(scene.get("nodes", []), list):
            raise ModelError(f"glTF scene {index} must be an object with a node array")
        if any(
            not isinstance(node, int) or isinstance(node, bool) or not 0 <= node < len(nodes)
            for node in scene.get("nodes", [])
        ):
            raise ModelError("a scene node index is out of range")
    if scenes:
        scene_index = document.get("scene", 0)
        if not isinstance(scene_index, int) or isinstance(scene_index, bool) or not 0 <= scene_index < len(scenes):
            raise ModelError("the scene index is out of range")
    for index, skin in enumerate(skins):
        if not isinstance(skin, dict) or not isinstance(skin.get("joints", []), list):
            raise ModelError(f"glTF skin {index} must be an object with a joint array")
        if any(not isinstance(node, int) or isinstance(node, bool) or not 0 <= node < len(nodes) for node in skin.get("joints", [])):
            raise ModelError("a skin joint is not a node")
        if "inverseBindMatrices" in skin:
            accessor_index = skin["inverseBindMatrices"]
            if not isinstance(accessor_index, int) or isinstance(accessor_index, bool) or not 0 <= accessor_index < len(accessors):
                raise ModelError("a skin references an invalid inverse bind accessor")
    for index, animation in enumerate(animations):
        if not isinstance(animation, dict):
            raise ModelError(f"glTF animation {index} must be an object")
        for key in ("samplers", "channels"):
            if key in animation and not isinstance(animation[key], list):
                raise ModelError(f"glTF animation {index} {key} must be an array")
        samplers = animation.get("samplers", [])
        channels = animation.get("channels", [])
        for sampler in samplers:
            if not isinstance(sampler, dict):
                raise ModelError("glTF animation sampler must be an object")
            for key in ("input", "output"):
                accessor_index = sampler.get(key)
                if not isinstance(accessor_index, int) or isinstance(accessor_index, bool) or not 0 <= accessor_index < len(accessors):
                    raise ModelError("glTF animation sampler references an invalid accessor")
        for channel in channels:
            if not isinstance(channel, dict) or not isinstance(channel.get("target", {}), dict):
                raise ModelError("glTF animation channel target must be an object")
            sampler_index = channel.get("sampler")
            if not isinstance(sampler_index, int) or isinstance(sampler_index, bool) or not 0 <= sampler_index < len(samplers):
                raise ModelError("glTF animation channel references an invalid sampler")
            target = channel.get("target", {})
            if "node" in target and (
                not isinstance(target["node"], int) or isinstance(target["node"], bool)
                or not 0 <= target["node"] < len(nodes)
            ):
                raise ModelError("an animation targets a node that does not exist")


MAX_MORPH_TARGETS = 8


def _static_walk(
    document: dict,
    binary: bytes | None,
    base_dir: pathlib.Path,
    morph_out: list[float] | None = None,
    morph_defaults_out: list[list[float]] | None = None,
    morph_groups_out: list[int] | None = None,
    texture_out: list[float] | None = None,
    texture_slots: dict[int, int] | None = None,
) -> tuple[list[float], list[int]]:
    """Bake every mesh in world space; optionally collect morph deltas."""
    nodes = document.get("nodes", [])
    scenes = document.get("scenes")
    if scenes:
        roots = scenes[document.get("scene", 0)].get("nodes", [])
    else:
        child_nodes = {
            child
            for node in nodes
            for child in node.get("children", [])
        }
        roots = [index for index in range(len(nodes)) if index not in child_nodes]
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
                attributes = primitive.get("attributes", {})
                index = primitive.get("indices")
                if index is not None:
                    item_count = _validate_index_accessor(document, index)
                else:
                    item_count = document["accessors"][attributes["POSITION"]]["count"]
                primitive_triangles = _triangle_count(
                    primitive.get("mode", 4), item_count
                )
                if len(triangles) // 12 + primitive_triangles > MAX_TRIANGLES:
                    raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
                morph_targets = len(primitive.get("targets", []))
                if morph_out is not None and morph_targets > MAX_MORPH_TARGETS:
                    raise ModelError(f"a model may use at most {MAX_MORPH_TARGETS} morph targets")
                generated_components = (
                    len(triangles) + primitive_triangles * 12
                    + (primitive_triangles * 20 if texture_out is not None else 0)
                    + (len(morph_out) if morph_out is not None else 0)
                    + primitive_triangles * 9 * morph_targets
                )
                if generated_components * 32 > MAX_GEOMETRY_BYTES:
                    raise ModelError(
                        f"generated model geometry exceeds the {MAX_GEOMETRY_BYTES} byte import limit"
                    )
                first = len(triangles) // 12
                triangles.extend(
                    _primitive(
                        document, primitive, world, base_dir, binary, morph_out,
                        MAX_TRIANGLES - len(triangles) // 12,
                        texture_out, texture_slots,
                    )
                )
                target_counts.append(len(primitive.get("targets", [])))
                if morph_defaults_out is not None and primitive.get("targets"):
                    morph_defaults_out.append(
                        _morph_defaults(document, node, len(primitive["targets"]))
                    )
                    if morph_groups_out is not None:
                        morph_groups_out.extend((first, len(triangles) // 12 - first))
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


def _morph_defaults(document: dict, node: dict, target_count: int) -> list[float]:
    """Resolve the glTF node-over-mesh default precedence for one group."""
    mesh = _mesh_for_node(document, node)
    raw = node.get("weights", mesh.get("weights", [0.0] * target_count))
    if not isinstance(raw, list) or len(raw) != target_count:
        raise ModelError("a node's default morph weights do not match its targets")
    try:
        values = [float(value) for value in raw]
    except (TypeError, ValueError, OverflowError) as error:
        raise ModelError("a node's default morph weights are not numeric") from error
    if any(not math.isfinite(value) for value in values):
        raise ModelError("a node's default morph weights must be finite")
    return values


def _static_document(path: pathlib.Path) -> tuple[dict, bytes | None]:
    document, binary = _container(path)
    if not isinstance(document, dict) or "asset" not in document:
        raise ModelError(f"{path.name} has no glTF 'asset' block")
    return document, binary


@_translate_malformed_structure
def load_triangles(path: pathlib.Path) -> list[float]:
    document, binary = _static_document(path)
    triangles, _ = _static_walk(document, binary, path.parent)
    if not triangles:
        raise ModelError("the model has no triangle geometry")
    return triangles


@_translate_malformed_structure
def load_textured(path: pathlib.Path) -> dict:
    """Bake static geometry plus UVs and decoded base-color PNG images."""
    document, binary = _static_document(path)
    texture_slots, textures = _collect_base_color_textures(
        document, path.parent, binary
    )
    if not textures:
        raise ModelError("the model has no base-color textures")
    textured: list[float] = []
    triangles, _ = _static_walk(
        document, binary, path.parent, texture_out=textured,
        texture_slots=texture_slots,
    )
    if not triangles:
        raise ModelError("the model has no triangle geometry")
    return {"vertices": triangles, "textured": textured, "textures": textures}


@_translate_malformed_structure
def load_morphed(path: pathlib.Path) -> dict:
    """Bake a static model with morph target deltas.

    Every primitive must declare the same positive number of targets, so the
    per-vertex delta stride is uniform; the deltas are stored per vertex, per
    target.
    """
    document, binary = _static_document(path)
    morph: list[float] = []
    group_defaults: list[list[float]] = []
    morph_groups: list[int] = []
    triangles, counts = _static_walk(
        document, binary, path.parent, morph, group_defaults, morph_groups
    )
    if not triangles:
        raise ModelError("the model has no triangle geometry")
    if not counts or max(counts) == 0:
        raise ModelError("the model has no morph targets")
    targets = counts[0]
    if any(count != targets for count in counts):
        raise ModelError("every primitive must use the same morph target count")
    if targets > MAX_MORPH_TARGETS:
        raise ModelError(f"a model may use at most {MAX_MORPH_TARGETS} morph targets")
    group_bounds: list[float] = []
    for group, (first, count) in enumerate(
        zip(morph_groups[::2], morph_groups[1::2])
    ):
        if count <= 0:
            group_bounds.extend((0.0, 0.0, 0.0, 0.0))
            continue
        defaults = group_defaults[group]
        lower = [math.inf, math.inf, math.inf]
        upper = [-math.inf, -math.inf, -math.inf]
        for triangle in range(first, first + count):
            for corner in range(3):
                vertex = triangle * 3 + corner
                base = triangles[triangle * 12 + corner * 3 : triangle * 12 + corner * 3 + 3]
                delta_start = vertex * targets * 3
                for axis in range(3):
                    low = high = base[axis]
                    for target in range(targets):
                        delta = morph[delta_start + target * 3 + axis]
                        weight_low = min(0.0, 1.0, defaults[target])
                        weight_high = max(0.0, 1.0, defaults[target])
                        low += min(delta * weight_low, delta * weight_high)
                        high += max(delta * weight_low, delta * weight_high)
                    lower[axis] = min(lower[axis], low)
                    upper[axis] = max(upper[axis], high)
        centre = [(lower[axis] + upper[axis]) / 2.0 for axis in range(3)]
        radius = math.sqrt(
            sum(((upper[axis] - lower[axis]) / 2.0) ** 2 for axis in range(3))
        )
        radius += max(1.0, *(abs(value) for value in (*lower, *upper))) * 1e-9
        group_bounds.extend((*centre, radius))
    return {
        "vertices": triangles,
        "morph": morph,
        "morph_count": targets,
        "morph_defaults": [weight for group in group_defaults for weight in group],
        "morph_groups": morph_groups,
        "morph_group_bounds": group_bounds,
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


@_translate_malformed_structure
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
    textured_vertices: list[float] = []
    texture_slots, textures = _collect_base_color_textures(
        document, path.parent, binary
    )
    for node_index in skin_nodes:
        node = nodes_doc[node_index]
        if "mesh" not in node:
            continue
        for primitive in _mesh_for_node(document, node).get("primitives", []):
            index = primitive.get("indices")
            if index is not None:
                item_count = _validate_index_accessor(document, index)
            else:
                item_count = document["accessors"][primitive["attributes"]["POSITION"]]["count"]
            primitive_triangles = _triangle_count(primitive.get("mode", 4), item_count)
            if len(vertices) // 42 + primitive_triangles > MAX_TRIANGLES:
                raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
            if (len(vertices) + primitive_triangles * 42) * 32 > MAX_GEOMETRY_BYTES:
                raise ModelError(
                    f"generated model geometry exceeds the {MAX_GEOMETRY_BYTES} byte import limit"
                )
            if textures:
                first_textured = len(textured_vertices) // 20
                _primitive(
                    document, primitive, _identity(), path.parent, binary,
                    texture_out=textured_vertices, texture_slots=texture_slots,
                    max_triangles=MAX_TRIANGLES - len(textured_vertices) // 20,
                )
                expected = _triangle_count(primitive.get("mode", 4), item_count)
                if len(textured_vertices) // 20 - first_textured != expected:
                    raise ModelError("textured and skinned triangle data became misaligned")
            vertices.extend(_skinned_primitive(
                document, primitive, path.parent, binary,
                MAX_TRIANGLES - len(vertices) // 42,
            ))
    if not vertices:
        raise ModelError("the skinned model has no triangle geometry")

    tracks, times, values, length = _clip(document, nodes_doc, path.parent, binary)
    entry = {
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
    if textures:
        entry.update({"textured_data": textured_vertices, "textures": textures,
                      "textured": True})
    return entry


def _skinned_primitive(
    document: dict, primitive: dict, base_dir: pathlib.Path, binary: bytes | None,
    max_triangles: int = MAX_TRIANGLES,
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
    if primitive.get("indices") is not None:
        index_count = _validate_index_accessor(document, primitive["indices"])
    else:
        accessor_index = attributes["POSITION"]
        accessors = document.get("accessors", [])
        if not isinstance(accessor_index, int) or isinstance(accessor_index, bool) or not 0 <= accessor_index < len(accessors):
            raise ModelError("an accessor index is out of range")
        index_count = accessors[accessor_index].get("count", 0)
    if _triangle_count(primitive.get("mode", 4), index_count) > max_triangles:
        raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
    positions = _accessor(document, attributes["POSITION"], base_dir, binary, vertex_attribute=True, semantic="POSITION")
    joints = _accessor(document, attributes["JOINTS_0"], base_dir, binary, vertex_attribute=True, semantic="JOINTS_0")
    weights = _accessor(document, attributes["WEIGHTS_0"], base_dir, binary, vertex_attribute=True, semantic="WEIGHTS_0")
    if primitive.get("indices") is not None:
        indices = [row[0] for row in _accessor(document, primitive["indices"], base_dir, binary)]
    else:
        indices = list(range(len(positions)))
    colours = None
    if "COLOR_0" in attributes:
        raw = _accessor(document, attributes["COLOR_0"], base_dir, binary, vertex_attribute=True, semantic="COLOR_0")
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


@_translate_malformed_structure
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
    textured_vertices: list[float] = []
    texture_slots, textures = _collect_base_color_textures(
        document, base_dir, binary
    )
    groups: list[int] = []
    morph: list[float] = []
    morph_counts: list[int] = []
    group_defaults: list[list[float]] = []

    def visit(index: int, depth: int) -> None:
        if depth > 64:
            raise ModelError("the node hierarchy is deeper than 64 levels")
        if index < 0 or index >= len(nodes_doc):
            raise ModelError("a node index is out of range")
        node = nodes_doc[index]
        if "mesh" in node:
            first = len(vertices) // 12
            textured_first = len(textured_vertices) // 20
            mesh = _mesh_for_node(document, node)
            primitives = mesh.get("primitives", [])
            node_target_count = max(
                (len(primitive.get("targets", [])) for primitive in primitives),
                default=0,
            )
            node_defaults = (
                _morph_defaults(document, node, node_target_count)
                if node_target_count
                else None
            )
            for primitive in primitives:
                vertices.extend(
                    _primitive(
                        document, primitive, _identity(), base_dir, binary,
                        morph if primitive.get("targets") else None,
                        texture_out=textured_vertices if textures else None,
                        texture_slots=texture_slots if textures else None,
                    )
                )
                morph_counts.append(len(primitive.get("targets", [])))
            count = len(vertices) // 12 - first
            if textures and len(textured_vertices) // 20 - textured_first != count:
                raise ModelError("textured and animated triangle data became misaligned")
            if count:
                groups.extend((index, first, count))
                if node_defaults is not None:
                    group_defaults.append(node_defaults)
            if len(vertices) // 12 > MAX_TRIANGLES:
                raise ModelError(f"the model exceeds the {MAX_TRIANGLES} triangle budget")
        for child in node.get("children", []):
            visit(child, depth + 1)

    for root in roots:
        visit(root, 0)
    if not vertices:
        raise ModelError("the model has no triangle geometry")

    tracks, times, values, length = _clip(document, nodes_doc, base_dir, binary)
    entry = {
        "vertices": vertices,
        "nodes": nodes,
        "parents": parents,
        "groups": groups,
        "tracks": tracks,
        "times": times,
        "values": values,
        "length": length,
    }
    if textures:
        entry.update({"textured_data": textured_vertices, "textures": textures,
                      "textured": True})
    if morph_counts and max(morph_counts) > 0:
        target_count = morph_counts[0]
        if target_count > MAX_MORPH_TARGETS:
            raise ModelError(f"a model may use at most {MAX_MORPH_TARGETS} morph targets")
        if any(count != target_count for count in morph_counts):
            raise ModelError("every animated primitive must use the same morph target count")
        entry.update({"morph": morph, "morph_count": target_count,
                      "morph_defaults": [weight for group in group_defaults
                                          for weight in group]})
    elif any(morph_counts):
        raise ModelError("every animated primitive must use the same morph target count")
    return entry


# ---- Compiler integration -------------------------------------------------

_registry: dict[str, tuple[str, int, list[float], tuple[float, float, float, float]]] = {}
_container_cache: dict[pathlib.Path, tuple[dict, bytes | None]] = {}
_buffer_cache: dict[tuple[int, int], bytes] = {}
_asset_root: pathlib.Path | None = None
_cache_import_reads = False
_import_seconds = 0.0
_measure_import_time = False


def reset(*, clear_asset_root: bool = True) -> None:
    global _asset_root, _cache_import_reads
    _registry.clear()
    _container_cache.clear()
    _buffer_cache.clear()
    if clear_asset_root:
        _asset_root = None
    _cache_import_reads = False


def _begin_import_cache() -> None:
    global _cache_import_reads
    _container_cache.clear()
    _buffer_cache.clear()
    _cache_import_reads = True


def _end_import_cache() -> None:
    global _cache_import_reads
    _container_cache.clear()
    _buffer_cache.clear()
    _cache_import_reads = False


def set_asset_root(root: pathlib.Path) -> None:
    """Set the project boundary used for model and external buffer paths."""
    global _asset_root
    _asset_root = _safe_resolve(pathlib.Path(root), "project folder")


def reset_import_time() -> None:
    global _import_seconds
    _import_seconds = 0.0


def measure_import_time(enabled: bool) -> None:
    global _measure_import_time
    _measure_import_time = enabled


def import_time_seconds() -> float:
    """Return cumulative time spent resolving and decoding model assets."""
    return _import_seconds


def _resolve(asset: str, source_path: pathlib.Path) -> pathlib.Path:
    path = pathlib.Path(asset)
    source = _safe_resolve(pathlib.Path(source_path), "source file")
    root = _asset_root or source.parent
    if not path.is_absolute():
        path = root / path
    path = _safe_resolve(path, f"model path {asset!r}")
    try:
        path.relative_to(_safe_resolve(root, "project folder"))
    except ValueError:
        raise ModelError("a model path must resolve inside the project folder") from None
    return path


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


def _kind(path: pathlib.Path, *, include_textures: bool = True) -> str:
    """Classify the model from one read: skinned, animated or static."""
    document, _ = _container(path)
    if not isinstance(document, dict):
        return "static"
    nodes = document.get("nodes", [])
    has_texture = include_textures and _has_base_color_texture(document)
    if document.get("skins") and any("skin" in node for node in nodes):
        return "textured_skinned" if has_texture else "skinned"
    if document.get("animations"):
        return "textured_animated" if has_texture else "animated"
    for mesh in document.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if primitive.get("targets"):
                return "textured_morphed" if has_texture else "morphed"
    if has_texture:
        return "textured"
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


def ensure_model(
    asset: str, source_path: pathlib.Path, *, include_textures: bool = True
) -> dict:
    global _import_seconds
    owns_cache_scope = not _cache_import_reads
    if owns_cache_scope:
        _begin_import_cache()
    started = time.perf_counter() if _measure_import_time else None
    try:
        return _ensure_model(asset, source_path, include_textures=include_textures)
    finally:
        if started is not None:
            _import_seconds += time.perf_counter() - started
        if owns_cache_scope:
            _end_import_cache()


def _ensure_model(
    asset: str, source_path: pathlib.Path, *, include_textures: bool = True
) -> dict:
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
    kind = _kind(path, include_textures=include_textures)
    if kind in ("skinned", "textured_skinned"):
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
    elif kind in ("animated", "textured_animated"):
        clip = load_animated(path)
        entry.update(clip)
        entry["animated"] = True
        entry["count"] = len(clip["vertices"]) // 12
        entry["data"] = clip["vertices"]
        entry["bounds"] = bounds_of(clip["vertices"])
    elif kind == "textured":
        model = load_textured(path)
        entry["animated"] = False
        entry["count"] = len(model["vertices"]) // 12
        entry["data"] = model["vertices"]
        entry["textured_data"] = model["textured"]
        entry["textures"] = model["textures"]
        entry["textured"] = True
        entry["bounds"] = bounds_of(model["vertices"])
    else:
        data = load_triangles(path)
        entry.update({"animated": False, "count": len(data) // 12, "data": data})
        entry["bounds"] = bounds_of(data)
    if (
        (entry.get("animated") or entry.get("skinned") or entry.get("morph_count"))
        and entry["id"] >= MODEL_STATES
    ):
        # The runtime state table also stores morph overrides. A morphing model
        # past it would silently ignore model_morph() writes. Fail at source.
        raise ModelError(
            f"the model needs runtime state slot {entry['id']} (clock slot "
            f"{entry['id']} for animated assets) but only {MODEL_STATES} "
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
        # 17 significant decimal digits round-trip every finite binary64 value.
        # These arrays include geometry and conservative culling bounds, so
        # lossy formatting can change rendered positions or shrink a bound.
        lines.append("    " + ", ".join(format(value, ".17g") for value in chunk) + ",")
    lines.append("};")


def _int_array(lines: list[str], symbol: str, values: list[int], per_line: int) -> None:
    if not values:
        values = [0]
    lines.append(f"static const int {symbol}[{len(values)}] = {{")
    for start in range(0, len(values), per_line):
        chunk = values[start : start + per_line]
        lines.append("    " + ", ".join(str(value) for value in chunk) + ",")
    lines.append("};")


def _uint_array(lines: list[str], symbol: str, values: list[int], per_line: int) -> None:
    if not values:
        values = [0]
    lines.append(f"static const uint32_t {symbol}[{len(values)}] = {{")
    for start in range(0, len(values), per_line):
        chunk = values[start : start + per_line]
        lines.append("    " + ", ".join(f"0x{value:08x}u" for value in chunk) + ",")
    lines.append("};")


def definitions(*, include_textures: bool = True) -> list[str]:
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
            if entry.get("textured") and include_textures:
                _double_array(lines, symbol + "_textured", entry["textured_data"], 20)
                for index, (width, height, pixels) in enumerate(entry["textures"]):
                    _uint_array(lines, f"{symbol}_texture_{index}", pixels, 8)
                pointers = ", ".join(
                    f"{symbol}_texture_{index}" for index in range(len(entry["textures"]))
                )
                dimensions = ", ".join(
                    f"{width}, {height}" for width, height, _ in entry["textures"]
                )
                lines.append(f"static const uint32_t *const {symbol}_textures[] = {{{pointers}}};")
                lines.append(f"static const int {symbol}_texture_dimensions[] = {{{dimensions}}};")
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
            if entry.get("morph_count"):
                _double_array(lines, symbol + "_morph", entry["morph"], 12)
                _double_array(lines, symbol + "_morph_default", entry["morph_defaults"], 8)
            if entry.get("textured") and include_textures:
                _double_array(lines, symbol + "_textured", entry["textured_data"], 20)
                for index, (width, height, pixels) in enumerate(entry["textures"]):
                    _uint_array(lines, f"{symbol}_texture_{index}", pixels, 8)
                pointers = ", ".join(
                    f"{symbol}_texture_{index}" for index in range(len(entry["textures"]))
                )
                dimensions = ", ".join(
                    f"{width}, {height}" for width, height, _ in entry["textures"]
                )
                lines.append(f"static const uint32_t *const {symbol}_textures[] = {{{pointers}}};")
                lines.append(f"static const int {symbol}_texture_dimensions[] = {{{dimensions}}};")
        elif entry.get("morph_count"):
            lines.append(
                f"/* model: {pathlib.Path(key).name}, {count} morphing triangles, "
                f"{entry['morph_count']} targets */"
            )
            _double_array(lines, symbol, entry["data"], 12)
            _double_array(lines, symbol + "_morph", entry["morph"], 12)
            _int_array(lines, symbol + "_morph_groups", entry["morph_groups"], 12)
            _double_array(lines, symbol + "_morph_bounds", entry["morph_group_bounds"], 4)
            _double_array(lines, symbol + "_morph_default", entry["morph_defaults"], 8)
        elif entry.get("textured"):
            lines.append(
                f"/* model: {pathlib.Path(key).name}, {count} textured triangles */"
            )
            _double_array(lines, symbol, entry["data"], 12)
            if include_textures:
                _double_array(lines, symbol + "_textured", entry["textured_data"], 20)
                for index, (width, height, pixels) in enumerate(entry["textures"]):
                    _uint_array(lines, f"{symbol}_texture_{index}", pixels, 8)
                pointers = ", ".join(
                    f"{symbol}_texture_{index}"
                    for index in range(len(entry["textures"]))
                )
                dimensions = ", ".join(
                    f"{width}, {height}"
                    for width, height, _ in entry["textures"]
                )
                lines.append(
                    f"static const uint32_t *const {symbol}_textures[] = {{{pointers}}};"
                )
                lines.append(
                    f"static const int {symbol}_texture_dimensions[] = {{{dimensions}}};"
                )
        else:
            lines.append(f"/* model: {pathlib.Path(key).name}, {count} triangles */")
            _double_array(lines, symbol, entry["data"], 12)
        lines.append("")
    return lines


def late_models() -> list[str]:
    """Return models discovered while lowering reachable source expressions."""
    return list(_registry)
