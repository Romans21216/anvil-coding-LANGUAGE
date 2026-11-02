"""Optional source metadata retained in a versioned UTF-8 image marker."""

from __future__ import annotations

import json
import struct

from compiler.common import CompileError

MARKER = b"ANVL-METADATA-1\0"
END_MARKER = b"\0ANVL-METADATA-END\0"
FIELDS = frozenset(("name", "author", "version"))


def metadata_value(raw: str, path, line: int) -> str:
    """Decode and validate a quoted metadata string from source."""
    try:
        value = json.loads(raw)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("expected a non-empty string")
        if any(ord(char) < 32 for char in value):
            raise ValueError("control characters are not allowed")
        value.encode("utf-8")
    except (ValueError, UnicodeError) as error:
        raise CompileError(
            f"{path}:{line}: metadata expects a quoted Unicode string "
            "without control characters"
        ) from error
    return value


def extract(top) -> dict[str, str]:
    """Return declared metadata from top-level syntax nodes."""
    return {node.name: node.value for node in top if node.kind == "metadata"}


def pack(metadata: dict[str, str]) -> bytes:
    """Encode metadata as a marker, little-endian length, and compact UTF-8 JSON."""
    if not metadata:
        return b""
    payload = json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return MARKER + struct.pack("<I", len(payload)) + payload + END_MARKER


def unpack(image: bytes) -> dict[str, str]:
    """Read a metadata payload from a compiled image, if present."""
    position = 0
    while True:
        position = image.find(MARKER, position)
        if position < 0:
            return {}
        start = position + len(MARKER)
        position = start
        if start + 4 > len(image):
            continue
        size = struct.unpack_from("<I", image, start)[0]
        payload_start = start + 4
        payload_end = payload_start + size
        trailer_end = payload_end + len(END_MARKER)
        if trailer_end > len(image) or image[payload_end:trailer_end] != END_MARKER:
            # A user string or other binary data can contain the prefix. Only
            # accept a complete framed payload as the compiler-owned record.
            continue
        payload = image[payload_start:payload_end]
        try:
            result = json.loads(payload.decode("utf-8"))
            if not isinstance(result, dict) or any(
                key not in FIELDS or not isinstance(value, str)
                for key, value in result.items()
            ):
                raise ValueError("invalid metadata fields")
            return result
        except (ValueError, UnicodeError) as error:
            raise CompileError("invalid Anvil metadata payload") from error
