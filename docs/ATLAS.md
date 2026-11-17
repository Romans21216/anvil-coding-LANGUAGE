# Sprite atlases

Anvil draws a rectangle out of an image with
`image_draw_region(handle, sx, sy, sw, sh, dx, dy, dw, dh)`. A sprite sheet is
just one image plus a table of rectangles, so the workflow has two steps: pack
the sheet with a tool, then draw cells with the numbers the tool reports.

## Pack a sheet

```sh
python tools/pack_atlas.py assets/sheet.bmp --atlas assets/sheet.json sprites/*.bmp
```

Options:

| Option | Meaning |
| --- | --- |
| `--atlas PATH` | JSON path (default: the sheet path with a `.json` suffix) |
| `--width N` | Maximum sheet width in pixels (default 1024) |
| `--padding N` | Pixels of gutter between sprites and at the edges (default 0) |

Inputs are uncompressed 24-bit or 32-bit BMP — the same formats `image_load`
accepts. The sheet is 32-bit BGRA and keeps source alpha. Sprite names come from
file stems and must be unique.

Packing is deterministic: images are ordered by height (descending), then width
(descending), then name, and placed on shelves left to right. The same inputs
always produce byte-identical sheet and JSON, so generated atlases can be
committed and diffed.

## Manifest

```json
{
  "format": "anvil-atlas-1",
  "image": "sheet.bmp",
  "width": 256,
  "height": 128,
  "entries": [
    { "name": "hero", "x": 0, "y": 0, "width": 32, "height": 48 }
  ]
}
```

Entries are sorted by name. The file has no timestamps, so it is stable across
runs and machines.

## Draw a cell

```anvil
set var(sheet) = image_load("assets/sheet.bmp")

fn(draw)
  # hero is at 0,0 and 32x48 in the sheet; draw it at 100,80 at 2x.
  set var(d) = image_draw_region(var(sheet), 0, 0, 32, 48, 100, 80, 64, 96)
end
```

`image_flip` and `image_tint` still apply, and flipping mirrors inside the cell.
A rectangle that does not lie fully inside the sheet returns 0 and draws
nothing, so a wrong atlas rectangle is visible during development rather than
silently clamped.

The runtime has no JSON reader, so the numbers from the manifest are copied
into constants (or generated into an include by your build step). The manifest
exists to make that mechanical: it is small, sorted, and stable.
