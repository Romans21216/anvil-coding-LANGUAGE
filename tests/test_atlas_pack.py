"""tools/pack_atlas.py builds a byte-deterministic sheet that matches its JSON."""

from __future__ import annotations

import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "pack_atlas.py"


def write_solid_bmp(path: pathlib.Path, width: int, height: int, colour: tuple[int, int, int]) -> None:
    r, g, b = colour
    stride = ((width * 24 + 31) // 32) * 4
    row = bytes((b, g, r)) * width + b"\x00" * (stride - width * 3)
    pixels = row * height
    header = bytearray(54)
    header[0:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + len(pixels))
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<i", header, 18, width)
    struct.pack_into("<i", header, 22, height)
    struct.pack_into("<H", header, 26, 1)
    struct.pack_into("<H", header, 28, 24)
    struct.pack_into("<I", header, 34, len(pixels))
    path.write_bytes(bytes(header) + pixels)


def read_bmp(path: pathlib.Path) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    data = path.read_bytes()
    offset = struct.unpack_from("<I", data, 10)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    bits = struct.unpack_from("<H", data, 28)[0]
    top_down = height < 0
    height = abs(height)
    stride = ((width * bits + 31) // 32) * 4
    rows = []
    for row in range(height):
        source = row if top_down else height - 1 - row
        start = offset + source * stride
        pixels = []
        for column in range(width):
            base = start + column * (bits // 8)
            b, g, r = data[base], data[base + 1], data[base + 2]
            a = data[base + 3] if bits == 32 else 255
            pixels.append((r, g, b, a))
        rows.append(pixels)
    return width, height, rows


def run(*args: pathlib.Path | str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), *[str(a) for a in args]],
        capture_output=True,
        text=True,
        timeout=120,
    )


class AtlasPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        write_solid_bmp(self.root / "red.bmp", 5, 3, (255, 0, 0))
        write_solid_bmp(self.root / "green.bmp", 7, 2, (0, 255, 0))
        write_solid_bmp(self.root / "blue.bmp", 4, 4, (0, 0, 255))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_sheet_contents_match_the_manifest(self) -> None:
        sheet = self.root / "sheet.bmp"
        atlas = self.root / "sheet.json"
        result = run(sheet, "--atlas", atlas, self.root / "red.bmp", self.root / "green.bmp", self.root / "blue.bmp")
        self.assertEqual(result.returncode, 0, result.stderr)

        metadata = json.loads(atlas.read_text(encoding="utf-8"))
        self.assertEqual(metadata["format"], "anvil-atlas-1")
        self.assertEqual(metadata["image"], "sheet.bmp")
        self.assertEqual([entry["name"] for entry in metadata["entries"]], ["blue", "green", "red"])

        width, height, rows = read_bmp(sheet)
        self.assertEqual((width, height), (metadata["width"], metadata["height"]))
        expected = {"red": (5, 3, (255, 0, 0)), "green": (7, 2, (0, 255, 0)), "blue": (4, 4, (0, 0, 255))}
        covered = set()
        for entry in metadata["entries"]:
            source_width, source_height, colour = expected[entry["name"]]
            self.assertEqual((entry["width"], entry["height"]), (source_width, source_height))
            for y in range(entry["height"]):
                for x in range(entry["width"]):
                    pixel = rows[entry["y"] + y][entry["x"] + x]
                    self.assertEqual(pixel[:3], colour, f"{entry['name']} at {x},{y}")
                    self.assertEqual(pixel[3], 255)
                    covered.add((entry["x"] + x, entry["y"] + y))
        # Padding and unused sheet area stay transparent black.
        self.assertLessEqual(len(covered), width * height)

    def test_rectangles_do_not_overlap(self) -> None:
        sheet = self.root / "sheet.bmp"
        atlas = self.root / "sheet.json"
        result = run(sheet, "--atlas", atlas, "--padding", "2", self.root / "red.bmp", self.root / "green.bmp", self.root / "blue.bmp")
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = json.loads(atlas.read_text(encoding="utf-8"))
        boxes = [
            (entry["x"], entry["y"], entry["x"] + entry["width"], entry["y"] + entry["height"])
            for entry in metadata["entries"]
        ]
        for index, first in enumerate(boxes):
            for second in boxes[index + 1 :]:
                overlap = (
                    first[0] < second[2]
                    and second[0] < first[2]
                    and first[1] < second[3]
                    and second[1] < first[3]
                )
                self.assertFalse(overlap, f"{first} overlaps {second}")

    def test_packing_is_byte_deterministic(self) -> None:
        first_dir = self.root / "one"
        second_dir = self.root / "two"
        first_dir.mkdir()
        second_dir.mkdir()
        for directory in (first_dir, second_dir):
            result = run(
                directory / "sheet.bmp",
                "--atlas",
                directory / "sheet.json",
                self.root / "red.bmp",
                self.root / "green.bmp",
                self.root / "blue.bmp",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((first_dir / "sheet.bmp").read_bytes(), (second_dir / "sheet.bmp").read_bytes())
        self.assertEqual((first_dir / "sheet.json").read_bytes(), (second_dir / "sheet.json").read_bytes())

    def test_duplicate_names_and_oversized_images_are_refused(self) -> None:
        duplicate = self.root / "dup"
        duplicate.mkdir()
        write_solid_bmp(duplicate / "red.bmp", 2, 2, (1, 2, 3))
        result = run(self.root / "s.bmp", self.root / "red.bmp", duplicate / "red.bmp")
        self.assertEqual(result.returncode, 1)
        self.assertIn("duplicate sprite name", result.stderr)

        result = run(self.root / "s.bmp", "--width", "4", self.root / "red.bmp")
        self.assertEqual(result.returncode, 1)
        self.assertIn("over the 4 px sheet limit", result.stderr)


if __name__ == "__main__":
    unittest.main()
