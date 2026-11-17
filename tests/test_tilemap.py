"""Tilemaps: a grid of atlas cells drawn from one image (8.14).

The first half is a headless API test (bounds, fill, set/get, free). The second
draws a 3x2 map into a real window, captures the frame with frame_capture() and
reads pixels back with image_pixel(), so the assertions are about the pixels the
renderer actually produced rather than the arguments it was given.
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
import time
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

RED = 0xFF0000
GREEN = 0x00FF00
BLUE = 0x0000FF
WHITE = 0xFFFFFF


def tiles_bmp(colours: list[tuple[int, int, int]], tile: int = 8) -> bytes:
    """A horizontal strip of solid tiles, 32-bit BMP (bottom-up rows)."""
    width = tile * len(colours)
    height = tile
    header = bytearray(54)
    header[0:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + width * height * 4)
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<i", header, 18, width)
    struct.pack_into("<i", header, 22, height)
    struct.pack_into("<H", header, 26, 1)
    struct.pack_into("<H", header, 28, 32)
    struct.pack_into("<I", header, 34, width * height * 4)
    row = bytearray()
    for colour in colours:
        b, g, r = colour[2], colour[1], colour[0]
        row += bytes((b, g, r, 255)) * tile
    return bytes(header) + bytes(row) * height


API_PROGRAM = "\n".join(
    (
        "fn(main)",
        '  set var(sheet) = image_load("tiles.bmp")',
        "  set var(map) = tilemap_new(var(sheet), 8, 8, 3, 2)",
        "  set var(none) = 0",
        '  say "cols " & tilemap_columns(var(map))',
        '  say "rows " & tilemap_rows(var(map))',
        '  say "new " & var(map)',
        "  say tilemap_fill(var(map), 0)",
        "  say tilemap_set(var(map), 1, 0, 1)",
        "  say tilemap_set(var(map), 2, 0, 2)",
        "  say tilemap_set(var(map), 2, 1, 3)",
        '  say "get " & tilemap_get(var(map), 2, 0)',
        '  say "empty " & tilemap_get(var(map), 9, 9)',
        "  say tilemap_set(var(map), 9, 0, 1)",
        "  say tilemap_set(var(map), 0, 0, 9)",
        "  say tilemap_set(var(map), 0, 0, -1)",
        '  say "cleared " & tilemap_get(var(map), 0, 0)',
        "  say tilemap_fill(var(map), -1)",
        '  say "fill-empty " & tilemap_get(var(map), 1, 1)',
        "  say tilemap_draw(var(map), 10, 10, 1)",
        "  say tilemap_free(var(map))",
        "  say tilemap_free(var(map))",
        "  say tilemap_columns(var(map))",
        "  say tilemap_new(var(none), 8, 8, 2, 2)",
        "  say tilemap_new(var(sheet), 0, 8, 2, 2)",
        "  say tilemap_new(var(sheet), 8, 8, 999, 2)",
        "end",
        "call fn(main)",
        "",
    )
)

PIXEL_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        'set var(sheet) = image_load("tiles.bmp")',
        "set var(map) = tilemap_new(var(sheet), 8, 8, 3, 2)",
        "set var(frame) = 0",
        "set var(done) = 0",
        "set var(ok) = tilemap_fill(var(map), 0)",
        "set var(ok2) = tilemap_set(var(map), 1, 0, 1)",
        "set var(ok3) = tilemap_set(var(map), 2, 0, 2)",
        "set var(ok4) = tilemap_set(var(map), 2, 1, 3)",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  if var(frame) = 4",
        "    if var(done) = 0",
        "      set var(done) = 1",
        "      set var(drawn) = tilemap_draw(var(map), 100, 50, 4)",
        '      say "drawn " & var(drawn)',
        "      set var(cap) = frame_capture()",
        '      say "red " & image_pixel(var(cap), 101, 51)',
        '      say "green " & image_pixel(var(cap), 133, 51)',
        '      say "blue " & image_pixel(var(cap), 165, 51)',
        '      say "white " & image_pixel(var(cap), 165, 83)',
        '      say "filled " & image_pixel(var(cap), 101, 83)',
        '      say "edge-a " & image_pixel(var(cap), 131, 51)',
        '      say "edge-b " & image_pixel(var(cap), 132, 51)',
        '      say "outside " & image_pixel(var(cap), 200, 51)',
        "    end",
        "  end",
        "end",
        "",
    )
)


def build(root: pathlib.Path, program: str, name: str) -> pathlib.Path:
    (root / "tiles.bmp").write_bytes(
        tiles_bmp([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)])
    )
    source = root / f"{name}.ANVL"
    source.write_text(program, encoding="utf-8")
    executable = root / f"{name}.exe"
    result = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return executable


class TilemapApiTests(unittest.TestCase):
    def test_bounds_and_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, API_PROGRAM, "api")
            run = subprocess.run(
                [str(executable)], cwd=root, capture_output=True, text=True, timeout=60
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            lines = run.stdout.splitlines()
            self.assertEqual(lines[0], "cols 3")
            self.assertEqual(lines[1], "rows 2")
            handle = lines[2].split()[1]
            self.assertGreaterEqual(int(handle), 1)
            self.assertEqual(lines[3:7], ["1", "1", "1", "1"])
            self.assertEqual(lines[7], "get 2")
            self.assertEqual(lines[8], "empty -1")
            # Out-of-range cell, a tile outside the 4-tile sheet, then a clear.
            self.assertEqual(lines[9], "0")
            self.assertEqual(lines[10], "0")
            self.assertEqual(lines[11], "1")
            self.assertEqual(lines[12], "cleared -1")
            self.assertEqual(lines[13], "1")
            self.assertEqual(lines[14], "fill-empty -1")
            # No window in this program: there is no framebuffer to draw into.
            self.assertEqual(lines[15], "0")
            self.assertEqual(lines[16], "1")
            self.assertEqual(lines[17], "0")
            self.assertEqual(lines[18], "0")
            self.assertEqual(lines[19], "0")
            self.assertEqual(lines[20], "0")
            self.assertEqual(lines[21], "0")


COLLISION_PROGRAM = "\n".join(
    (
        "fn(main)",
        '  set var(sheet) = image_load("tiles.bmp")',
        "  set var(map) = tilemap_new(var(sheet), 8, 8, 4, 3)",
        "  say tilemap_fill(var(map), 0)",
        "  say tilemap_set(var(map), 1, 1, 2)",
        # Nothing is solid yet, so the query over the future-solid cell misses.
        "  say tilemap_collide(var(map), 16, 16, 8, 8, 2)",
        "  say tilemap_solid(var(map), 2, 1)",
        "  say tilemap_is_solid(var(map), 2)",
        "  say tilemap_is_solid(var(map), 0)",
        "  say tilemap_solid(var(map), -1, 1)",
        "  say tilemap_solid(var(map), 9, 1)",
        "  say tilemap_solid(var(map), 3, 1)",
        "  say tilemap_is_solid(var(map), 3)",
        "  say tilemap_solid(var(map), 3, 0)",
        "  say tilemap_is_solid(var(map), 3)",
        '  say "cell " & tilemap_cell(var(map), 20, 20, 2)',
        '  say "cell " & tilemap_cell(var(map), 0, 0, 2)',
        '  say "cell " & tilemap_cell(var(map), 80, 20, 2)',
        '  say "cell " & tilemap_cell(var(map), -1, 20, 2)',
        "  say tilemap_collide(var(map), 16, 16, 8, 8, 2)",
        "  say tilemap_collide(var(map), 0, 0, 8, 8, 2)",
        "  say tilemap_collide(var(map), 8, 20, 16, 8, 2)",
        "  say tilemap_collide(var(map), 20, 20, 0, 8, 2)",
        "  say tilemap_collide(var(map), 16, 16, 8, 8, 0)",
        "  say tilemap_free(var(map))",
        "  say tilemap_collide(var(map), 16, 16, 8, 8, 2)",
        '  say "cell " & tilemap_cell(var(map), 20, 20, 2)',
        "end",
        "call fn(main)",
        "",
    )
)

EXPECTED_COLLISION = [
    "1",   # fill
    "1",   # set
    "0",   # nothing is solid yet
    "1",   # solid(2, 1)
    "1",   # is_solid(2)
    "0",   # is_solid(0)
    "0",   # solid(-1, 1): the empty tile cannot be solid
    "0",   # solid(9, 1): the sheet holds four tiles
    "1",   # solid(3, 1)
    "1",   # is_solid(3)
    "1",   # solid(3, 0)
    "0",   # is_solid(3) after clearing
    "cell 2",
    "cell 0",
    "cell -1",
    "cell -1",
    "1",
    "0",
    "1",
    "0",
    "0",
    "1",
    "0",
    "cell -1",
]

ANIMATION_PROGRAM = "\n".join(
    (
        "fn(main)",
        '  set var(sheet) = image_load("tiles.bmp")',
        "  set var(map) = tilemap_new(var(sheet), 8, 8, 4, 3)",
        # A tiny frame rate pins frame 0, so the headless values are stable.
        "  say tilemap_animate(var(map), 3, 2, 0.000001)",
        '  say "frame " & tilemap_frame(var(map), 3)',
        '  say "frame " & tilemap_frame(var(map), 0)',
        "  say tilemap_animate(var(map), 3, 0, 6)",
        "  say tilemap_animate(var(map), 3, 5, 6)",
        "  say tilemap_animate(var(map), 70, 2, 6)",
        "  say tilemap_animate(var(map), -1, 2, 6)",
        "  say tilemap_animate(var(map), 3, 2, 0)",
        "  say tilemap_animate(var(map), 3, 1, 6)",
        '  say "frame " & tilemap_frame(var(map), 3)',
        "  say tilemap_free(var(map))",
        '  say "frame " & tilemap_frame(var(map), 3)',
        "end",
        "call fn(main)",
        "",
    )
)

EXPECTED_ANIMATION = [
    "1",
    "frame 3",
    "frame 0",
    "0",
    "0",  # five frames do not fit a four-tile row
    "0",
    "0",
    "0",
    "1",
    "frame 3",
    "1",
    "frame -1",
]

ANIMATED_DRAW_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        'set var(sheet) = image_load("tiles.bmp")',
        "set var(map) = tilemap_new(var(sheet), 8, 8, 1, 1)",
        "set var(ok) = tilemap_set(var(map), 0, 0, 3)",
        # One frame per second, two frames: white (tile 3) at t<1, then the
        # row wraps to red (tile 0) for the rest of the run. The samples are
        # chosen by the program clock, not by a frame number, so a fast or
        # slow message loop cannot move them onto the wrong side of the flip.
        "set var(anim) = tilemap_animate(var(map), 3, 2, 1)",
        "set var(early) = -1",
        "set var(late) = -1",
        "",
        "fn(draw)",
        "  set var(drawn) = tilemap_draw(var(map), 0, 0, 8)",
        "  if var(early) = -1",
        "    if time() < 0.4",
        "      set var(cap) = frame_capture()",
        "      set var(early) = image_pixel(var(cap), 10, 10)",
        "    end",
        "  end",
        "  if var(late) = -1",
        "    if time() > 1.2",
        "      set var(cap2) = frame_capture()",
        "      set var(late) = image_pixel(var(cap2), 10, 10)",
        '      say "early " & var(early)',
        '      say "late " & var(late)',
        "    end",
        "  end",
        "end",
        "",
    )
)

LARGE_PROGRAM = "\n".join(
    (
        "fn(main)",
        '  set var(sheet) = image_load("tiles.bmp")',
        "  set var(big) = tilemap_new(var(sheet), 8, 8, 512, 512)",
        "  say tilemap_columns(var(big))",
        "  say tilemap_rows(var(big))",
        "  say tilemap_set(var(big), 511, 511, 3)",
        "  say tilemap_get(var(big), 511, 511)",
        "  say tilemap_new(var(sheet), 8, 8, 513, 512)",
        "  say tilemap_free(var(big))",
        "end",
        "call fn(main)",
        "",
    )
)

LARGE_DRAW_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        'set var(sheet) = image_load("tiles.bmp")',
        "set var(map) = tilemap_new(var(sheet), 8, 8, 512, 512)",
        "set var(ok) = tilemap_fill(var(map), -1)",
        "set var(ok) = tilemap_set(var(map), 0, 0, 1)",
        "set var(ok) = tilemap_set(var(map), 400, 400, 2)",
        "set var(frame) = 0",
        "set var(near) = -1",
        "set var(far) = -1",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        "  set var(drawn) = tilemap_draw(var(map), 0, 0, 8)",
        "  if var(frame) = 5",
        "    set var(cap) = frame_capture()",
        "    set var(near) = image_pixel(var(cap), 8, 8)",
        "  end",
        "  if var(frame) = 7",
        "    set var(p) = camera2d(25600, 25600, 1)",
        "  end",
        "  if var(frame) = 9",
        "    set var(cap2) = frame_capture()",
        "    set var(far) = image_pixel(var(cap2), 8, 8)",
        '    say "near " & var(near)',
        '    say "far " & var(far)',
        "  end",
        "end",
        "",
    )
)

class TilemapDrawTests(unittest.TestCase):
    def test_cells_land_on_the_expected_pixels(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, PIXEL_PROGRAM, "pixels")
            # A scene program keeps its window open, so read until the last
            # sample arrives and then close it instead of waiting for an exit
            # that never comes.
            process = subprocess.Popen(
                [str(executable)],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            lines: list[str] = []
            deadline = time.monotonic() + 45
            assert process.stdout is not None
            try:
                for line in process.stdout:
                    lines.append(line.rstrip("\r\n"))
                    if line.startswith("outside") or time.monotonic() > deadline:
                        break
            finally:
                process.kill()
                process.wait(timeout=30)
            values: dict[str, int] = {}
            for line in lines:
                key, _, value = line.partition(" ")
                if key in ("drawn", "red", "green", "blue", "white", "filled",
                           "edge-a", "edge-b", "outside"):
                    values[key] = int(float(value))
            self.assertEqual(
                sorted(values),
                ["blue", "drawn", "edge-a", "edge-b", "filled", "green",
                 "outside", "red", "white"],
                lines,
            )
            self.assertEqual(values["drawn"], 1)
            # The capture marks every texel opaque, so mask to the RGB bytes.
            self.assertEqual(values["red"] & 0xFFFFFF, RED)
            self.assertEqual(values["green"] & 0xFFFFFF, GREEN)
            self.assertEqual(values["blue"] & 0xFFFFFF, BLUE)
            self.assertEqual(values["white"] & 0xFFFFFF, WHITE)
            self.assertEqual(values["filled"] & 0xFFFFFF, RED)
            # 8 px tiles at scale 4: cell 0 spans x=100..131, cell 1 starts
            # at 132, so each side of the boundary must name its own tile.
            self.assertEqual(values["edge-a"] & 0xFFFFFF, RED)
            self.assertEqual(values["edge-b"] & 0xFFFFFF, GREEN)
            # Nothing was drawn past the 3x2 grid (black, opaque after capture).
            self.assertEqual(values["outside"] & 0xFFFFFF, 0)


class TilemapCollisionTests(unittest.TestCase):
    def test_solid_tiles_and_collision_queries(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, COLLISION_PROGRAM, "collision")
            run = subprocess.run(
                [str(executable)], cwd=root, capture_output=True, text=True, timeout=60
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), EXPECTED_COLLISION)

    def test_wasm_refuses_tilemap_collision(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "refuse.ANVL"
            source.write_text("\n".join((
                "scene 2d",
                "clear rgba(0, 0, 0, 255)",
                "set var(map) = tilemap_collide(0, 0, 0, 8, 8, 1)",
                "fn(draw)",
                "  display rect(0, 0, 40, 40) -rgb(255, 0, 0)",
                "end",
                "",
            )), encoding="utf-8")
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "--backend", "wasm",
                 "-o", str(root / "refuse.wasm")],
                capture_output=True, text=True, timeout=180,
            )
            self.assertNotEqual(build.returncode, 0)
            combined = build.stdout + build.stderr
            self.assertIn("'tilemap_collide' is not available in the wasm backend yet", combined)
            self.assertIn(":3:", combined)



class TilemapAnimationTests(unittest.TestCase):
    def test_animation_bounds_and_disabling(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, ANIMATION_PROGRAM, "anim")
            run = subprocess.run(
                [str(executable)], cwd=root, capture_output=True, text=True, timeout=60
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), EXPECTED_ANIMATION)

    def test_the_current_frame_is_drawn_and_wraps_at_the_row_end(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, ANIMATED_DRAW_PROGRAM, "animdraw")
            process = subprocess.Popen(
                [str(executable)],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            lines: list[str] = []
            assert process.stdout is not None
            deadline = time.monotonic() + 60
            try:
                for line in process.stdout:
                    lines.append(line.rstrip("\r\n"))
                    if line.startswith("late") or time.monotonic() > deadline:
                        break
            finally:
                process.kill()
                process.wait(timeout=30)
            values: dict[str, int] = {}
            for line in lines:
                key, _, value = line.partition(" ")
                if key in ("early", "late"):
                    values[key] = int(float(value))
            self.assertEqual(sorted(values), ["early", "late"], lines)
            # Frame 5 is under one second: the base tile, white.
            self.assertEqual(values["early"] & 0xFFFFFF, WHITE)
            # Frame 75 is past one second: frame 1 wraps to tile 0, red.
            self.assertEqual(values["late"] & 0xFFFFFF, RED)



class TilemapLargeMapTests(unittest.TestCase):
    def test_a_512_cell_map_is_accepted_and_513_is_not(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, LARGE_PROGRAM, "large")
            run = subprocess.run(
                [str(executable)], cwd=root, capture_output=True, text=True, timeout=90
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(
                run.stdout.splitlines(),
                ["512", "512", "1", "3", "0", "1"],
            )

    def test_drawing_follows_the_camera_into_a_far_corner(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, LARGE_DRAW_PROGRAM, "largedraw")
            process = subprocess.Popen(
                [str(executable)],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            lines: list[str] = []
            assert process.stdout is not None
            deadline = time.monotonic() + 45
            try:
                for line in process.stdout:
                    lines.append(line.rstrip("\r\n"))
                    if line.startswith("far") or time.monotonic() > deadline:
                        break
            finally:
                process.kill()
                process.wait(timeout=30)
            values: dict[str, int] = {}
            for line in lines:
                key, _, value = line.partition(" ")
                if key in ("near", "far"):
                    values[key] = int(float(value))
            self.assertEqual(sorted(values), ["far", "near"], lines)
            # Cell (0,0) is green; cell (400,400) is blue and only visible once
            # the camera pans to the cell (8 px tiles at 8x = 64 px cells).
            self.assertEqual(values["near"] & 0xFFFFFF, GREEN)
            self.assertEqual(values["far"] & 0xFFFFFF, BLUE)



if __name__ == "__main__":
    unittest.main()
