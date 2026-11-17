"""Indexed BMP loading: 4-bit and 8-bit palettes on both backends (8.12)."""

from __future__ import annotations

import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
HOST = ROOT / "tools" / "wasm_host.mjs"

RED = 0xFFFF0000
GREEN = 0xFF00FF00
BLUE = 0xFF0000FF
WHITE = 0xFFFFFFFF


def palette_bmp(path: pathlib.Path, bits: int, rows: list[list[int]],
                palette: list[tuple[int, int, int]]) -> None:
    height = len(rows)
    width = len(rows[0])
    stride = ((width * bits + 7) // 8 + 3) & ~3
    data = bytearray()
    for row in rows:
        line = bytearray(stride)
        if bits == 4:
            for index, value in enumerate(row):
                if index % 2 == 0:
                    line[index // 2] = value << 4
                else:
                    line[index // 2] |= value & 0x0F
        else:
            for index, value in enumerate(row):
                line[index] = value
        data += line
    table = b"".join(bytes((blue, green, red, 0)) for red, green, blue in palette)
    offset = 54 + len(table)
    header = b"BM" + struct.pack("<IHHI", offset + len(data), 0, 0, offset)
    info = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        bits,
        0,
        len(data),
        2835,
        2835,
        len(palette),
        0,
    )
    path.write_bytes(header + info + table + bytes(data))


PROGRAM = "\n".join(
    (
        "fn(main)",
        '  set var(a) = image_load("four.bmp")',
        '  set var(b) = image_load("eight.bmp")',
        "  say image_width(var(a))",
        "  say image_height(var(b))",
        "  set var(y) = 0",
        "  while var(y) < 2",
        "    set var(x) = 0",
        "    while var(x) < 2",
        "      say image_pixel(var(a), var(x), var(y))",
        "      say image_pixel(var(b), var(x), var(y))",
        "      set var(x) = compute(var(x) + 1)",
        "    end",
        "    set var(y) = compute(var(y) + 1)",
        "  end",
        "  say image_pixel(var(a), 5, 5)",
        "end",
        "call fn(main)",
        "",
    )
)

# Bottom row first in a BMP, so (0,0) is the last row supplied to the writer.
# BMP rows run bottom-up, so y=0 shows the last row written.
EXPECTED = [
    "2",
    "2",
    str(BLUE),
    str(GREEN),
    str(WHITE),
    str(BLUE),
    str(RED),
    str(RED),
    str(GREEN),
    str(RED),
    "0",
]


class IndexedBmpTests(unittest.TestCase):
    def _write_assets(self, root: pathlib.Path) -> None:
        palette_bmp(
            root / "four.bmp",
            4,
            [[0, 1], [2, 3]],
            [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)],
        )
        palette_bmp(
            root / "eight.bmp",
            8,
            [[0, 0], [1, 2]],
            [(255, 0, 0), (0, 255, 0), (0, 0, 255)],
        )

    def _build(self, root: pathlib.Path, backend: str) -> pathlib.Path:
        source = root / "palette.ANVL"
        source.write_text(PROGRAM, encoding="utf-8")
        if backend == "wasm":
            out = root / "palette.wasm"
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "--backend", "wasm", "-o", str(out)],
                capture_output=True,
                text=True,
                timeout=180,
            )
        else:
            out = root / "palette.exe"
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(out)],
                capture_output=True,
                text=True,
                timeout=180,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return out

    def test_four_and_eight_bit_bmps_load_on_c(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            self._write_assets(root)
            executable = self._build(root, "c")
            run = subprocess.run(
                [str(executable)], cwd=root, capture_output=True, text=True, timeout=60
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), EXPECTED)

    def test_four_and_eight_bit_bmps_load_in_wasm(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            self._write_assets(root)
            out = self._build(root, "wasm")
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
                env={**os.environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), EXPECTED)


if __name__ == "__main__":
    unittest.main()
