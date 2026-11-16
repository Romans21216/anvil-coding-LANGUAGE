"""Pack sprite BMPs into one atlas sheet plus deterministic JSON metadata.

The runtime already draws an atlas cell with
`image_draw_region(handle, sx, sy, sw, sh, dx, dy, dw, dh)`; this tool produces
the sheet and the rectangles to feed it.

    python tools/pack_atlas.py sheet.bmp --atlas sheet.json sprites/*.bmp

Packing is deterministic: inputs are sorted by height (descending), then width
(descending), then name, and laid out on shelves from left to right. The same
inputs always produce byte-identical output, so atlases can be committed.

Input formats match the runtime loader: uncompressed 24-bit or 32-bit BMP.
Output is 32-bit BGRA, bottom-up, with row padding, and preserves source alpha.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import sys

FORMAT = "anvil-atlas-1"


class AtlasError(Exception):
    pass


def read_bmp(path: pathlib.Path) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    data = path.read_bytes()
    if len(data) < 54 or data[:2] != b"BM":
        raise AtlasError(f"{path}: not a BMP file")
    offset = struct.unpack_from("<I", data, 10)[0]
    header_size = struct.unpack_from("<I", data, 14)[0]
    if header_size < 40:
        raise AtlasError(f"{path}: unsupported BMP header size {header_size}")
    width, height = struct.unpack_from("<ii", data, 18)
    planes, bits = struct.unpack_from("<HH", data, 26)
    compression = struct.unpack_from("<I", data, 30)[0]
    if planes != 1 or compression != 0:
        raise AtlasError(f"{path}: only uncompressed BMP is supported")
    if bits not in (24, 32):
        raise AtlasError(f"{path}: only 24-bit and 32-bit BMP is supported, not {bits}")
    if width <= 0 or height == 0:
        raise AtlasError(f"{path}: invalid dimensions {width}x{height}")
    top_down = height < 0
    height = abs(height)
    stride = ((width * bits + 31) // 32) * 4
    if offset + stride * height > len(data):
        raise AtlasError(f"{path}: truncated pixel data")
    rows: list[list[tuple[int, int, int, int]]] = []
    for row in range(height):
        source_row = row if top_down else height - 1 - row
        start = offset + source_row * stride
        pixels = []
        for column in range(width):
            base = start + column * (bits // 8)
            b, g, r = data[base], data[base + 1], data[base + 2]
            a = data[base + 3] if bits == 32 else 255
            pixels.append((r, g, b, a))
        rows.append(pixels)
    return width, height, rows


def write_bmp(
    path: pathlib.Path, width: int, height: int, rows: list[list[tuple[int, int, int, int]]]
) -> None:
    stride = ((width * 32 + 31) // 32) * 4
    pixels = bytearray(stride * height)
    for row in range(height):
        source_row = height - 1 - row  # bottom-up file order
        base = row * stride
        for column, (r, g, b, a) in enumerate(rows[source_row]):
            offset = base + column * 4
            pixels[offset : offset + 4] = bytes((b, g, r, a))
    header = bytearray(54)
    header[0:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + len(pixels))
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<i", header, 18, width)
    struct.pack_into("<i", header, 22, height)
    struct.pack_into("<H", header, 26, 1)
    struct.pack_into("<H", header, 28, 32)
    struct.pack_into("<I", header, 30, 0)
    struct.pack_into("<I", header, 34, len(pixels))
    path.write_bytes(bytes(header) + bytes(pixels))


def pack(
    images: list[tuple[str, int, int, list[list[tuple[int, int, int, int]]]]],
    max_width: int,
    padding: int,
) -> tuple[int, int, list[dict]]:
    widest = max(item[1] for item in images)
    if widest > max_width:
        raise AtlasError(f"an image is {widest} px wide, over the {max_width} px sheet limit")
    ordered = sorted(images, key=lambda item: (-item[2], -item[1], item[0]))

    placements: list[dict] = []
    x = padding
    y = padding
    shelf_height = 0
    for name, width, height, _ in ordered:
        if x + width + padding > max_width and x > padding:
            x = padding
            y += shelf_height + padding
            shelf_height = 0
        placements.append({"name": name, "x": x, "y": y, "width": width, "height": height})
        x += width + padding
        shelf_height = max(shelf_height, height)
    sheet_height = y + shelf_height + padding
    return max_width, max(1, sheet_height), placements


def build(
    out: pathlib.Path, sources: list[pathlib.Path], max_width: int, padding: int
) -> dict:
    if not sources:
        raise AtlasError("no input images")
    images = []
    seen = set()
    for path in sources:
        name = path.stem
        if name in seen:
            raise AtlasError(f"duplicate sprite name {name!r} (file stems must be unique)")
        seen.add(name)
        width, height, rows = read_bmp(path)
        images.append((name, width, height, rows))

    sheet_width, sheet_height, placements = pack(images, max_width, padding)
    sheet = [[(0, 0, 0, 0) for _ in range(sheet_width)] for _ in range(sheet_height)]
    by_name = {name: (width, height, rows) for name, width, height, rows in images}
    for placement in placements:
        _, _, rows = by_name[placement["name"]]
        for row, pixels in enumerate(rows):
            target = sheet[placement["y"] + row]
            target[placement["x"] : placement["x"] + placement["width"]] = pixels

    write_bmp(out, sheet_width, sheet_height, sheet)

    metadata = {
        "format": FORMAT,
        "image": out.name,
        "width": sheet_width,
        "height": sheet_height,
        "entries": [
            {
                "name": placement["name"],
                "x": placement["x"],
                "y": placement["y"],
                "width": placement["width"],
                "height": placement["height"],
            }
            for placement in sorted(placements, key=lambda entry: entry["name"])
        ],
    }
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=pathlib.Path, help="atlas sheet to write (.bmp)")
    parser.add_argument("sources", type=pathlib.Path, nargs="+", help="sprite BMPs to pack")
    parser.add_argument("--atlas", type=pathlib.Path, help="JSON path (default: output with .json)")
    parser.add_argument("--width", type=int, default=1024, help="maximum sheet width (default 1024)")
    parser.add_argument("--padding", type=int, default=0, help="pixels between sprites (default 0)")
    args = parser.parse_args(argv)

    atlas_path = args.atlas or args.output.with_suffix(".json")
    try:
        metadata = build(args.output, args.sources, args.width, max(0, args.padding))
    except AtlasError as error:
        print(f"pack_atlas: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"pack_atlas: {error}", file=sys.stderr)
        return 1
    atlas_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(
        f"{args.output.name}: {metadata['width']}x{metadata['height']}, "
        f"{len(metadata['entries'])} sprites -> {atlas_path.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
