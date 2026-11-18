"""C/Chrome color, camera, lighting and depth parity for the wasm renderer."""

from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
CAPTURE = ROOT / "tools" / "capture_wasm_mask.mjs"
CHROME = pathlib.Path(
    os.environ.get(
        "CHROME_PATH", "C:/Program Files/Google/Chrome/Application/chrome.exe"
    )
)
NEEDS_BROWSER = sys.platform == "win32" and CHROME.is_file() and shutil.which("node")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_gltf_morph import (  # noqa: E402
    write_morph_model,
    write_two_target_morph_model,
)
from test_gltf_ray_mesh import write_animated_morph_glb  # noqa: E402
from test_gltf_model import write_glb, write_quad  # noqa: E402
from test_gltf_skins import write_skinned_model  # noqa: E402
from test_sprite_draw import WindowReader  # noqa: E402


def _program() -> str:
    return "\n".join(
        (
            "scene 3d",
            "camera perspective 0 0 12",
            "camera fov(70)",
            "clear rgba(0, 0, 0, 255)",
            "fn(draw)",
            '  set var(weight) = model_morph("morph.gltf", 0, 0.5)',
            '  set var(ok) = model_draw("morph.gltf", 0, 0, 0, 1, 0, 0, 0)',
            "end",
            "",
        )
    )


def _animated_program() -> str:
    return "\n".join(
        (
            "scene 3d",
            "camera perspective 1 1 12",
            "camera fov(58)",
            "clear rgba(0, 0, 0, 255)",
            "fn(draw)",
            "  set var(camera_ok) = camera_angle(-8, 6)",
            '  set var(t) = model_animate("animated_morph.glb", 0.5)',
            '  set var(weight) = model_morph("animated_morph.glb", 0, 1)',
            '  set var(ok) = ray_mesh("animated_morph.glb", 0, 0, 0, 1, 0, 0, 0)',
            "end",
            "",
        )
    )


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    content = kind + payload
    return struct.pack(">I", len(payload)) + content + struct.pack(">I", zlib.crc32(content) & 0xFFFFFFFF)


def _write_textured_near_plane_glb(
    path: pathlib.Path, alpha_values: tuple[int, int] = (255, 255)
) -> None:
    """Make four UV-gradient cases plus a farther overlapping depth control."""
    centers = (-0.4, -0.13, 0.13, 0.4)
    depths = ((0.8, 0.8, 0.8), (0.8, 0.8, 0.02), (0.8, 0.02, 0.02), (0.02, 0.02, 0.02))
    offsets = ((-0.07, -0.06), (0.07, -0.06), (0.0, 0.08))
    uv_triangle = ((0.0, 0.0), (1.0, 0.0), (0.5, 1.0))
    positions = []
    texcoords = []
    for center, triangle_depths in zip(centers, depths):
        for (dx, dy), depth, uv in zip(offsets, triangle_depths, uv_triangle):
            positions.append(((center + dx) * depth, dy * depth, 5.0 - depth))
            texcoords.append(uv)
    # This later submitted triangle occupies the same projected footprint as
    # the front case but is farther away and samples a different texel.
    for (dx, dy), uv in zip(offsets, ((0.75, 0.25),) * 3):
        depth = 1.2
        positions.append(((centers[0] + dx) * depth, dy * depth, 5.0 - depth))
        texcoords.append(uv)
    position_bytes = b"".join(struct.pack("<3f", *point) for point in positions)
    uv_bytes = b"".join(struct.pack("<2f", *uv) for uv in texcoords)
    index_bytes = struct.pack("<15H", *range(15))
    rows = (
        b"\x00" + bytes((245, 30, 20, alpha_values[0], 20, 235, 40, alpha_values[1]))
        + b"\x00" + bytes((25, 70, 245, 255, 250, 225, 20, 255))
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(rows))
        + _png_chunk(b"IEND", b"")
    )
    image_offset = len(position_bytes) + len(uv_bytes) + len(index_bytes)
    binary = position_bytes + uv_bytes + index_bytes + png
    binary += bytes((-len(binary)) % 4)
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "TEXCOORD_0": 1}, "indices": 2, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1], "baseColorTexture": {"index": 0}}}],
        "textures": [{"source": 0}],
        "images": [{"bufferView": 3, "mimeType": "image/png"}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(position_bytes)},
            {"buffer": 0, "byteOffset": len(position_bytes), "byteLength": len(uv_bytes)},
            {"buffer": 0, "byteOffset": len(position_bytes) + len(uv_bytes), "byteLength": len(index_bytes)},
            {"buffer": 0, "byteOffset": image_offset, "byteLength": len(png)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 15, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5126, "count": 15, "type": "VEC2"},
            {"bufferView": 2, "componentType": 5123, "count": 15, "type": "SCALAR"},
        ],
    }
    json_bytes = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(binary)
    path.write_bytes(
        b"glTF" + struct.pack("<II", 2, total)
        + struct.pack("<II", len(json_bytes), 0x4E4F534A) + json_bytes
        + struct.pack("<II", len(binary), 0x004E4942) + binary
    )


def _compile(source: pathlib.Path, output: pathlib.Path, backend: str | None = None) -> None:
    command = [sys.executable, str(COMPILER), str(source), "-o", str(output)]
    if backend:
        command.extend(("--backend", backend))
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if result.returncode:
        if "No C compiler found" in result.stderr:
            raise unittest.SkipTest("MSVC is not available")
        raise AssertionError(result.stdout + result.stderr)


def _native_rgba(executable: pathlib.Path) -> bytes:
    process = subprocess.Popen([str(executable)], stdout=subprocess.DEVNULL)
    try:
        reader = WindowReader(process.pid)
        if reader.find(time.monotonic() + 10) is None:
            raise AssertionError("C model window did not open")
        reader.force_client_size(960, 600)
        deadline = time.monotonic() + 8
        previous: bytes | None = None
        stable = 0
        while time.monotonic() < deadline:
            width, height, pixels = reader.grab(0, 0, 960, 600)
            visible_pixels = sum(
                pixels[offset] > 2 or pixels[offset + 1] > 2 or pixels[offset + 2] > 2
                for offset in range(0, len(pixels), 4)
            )
            sampled_tones = {
                pixels[offset : offset + 3]
                for offset in range(0, len(pixels), 16)
            }
            ready = visible_pixels > 100 and len(sampled_tones) > 1
            if ready and pixels == previous:
                stable += 1
            elif ready:
                stable = 0
            else:
                stable = 0
            if ready and stable >= 1:
                # GDI's 32-bit DIB is BGRA; Chrome ImageData is RGBA.
                rgba = bytearray(pixels)
                for offset in range(0, len(rgba), 4):
                    rgba[offset], rgba[offset + 2] = rgba[offset + 2], rgba[offset]
                return bytes(rgba)
            previous = pixels if ready else None
            time.sleep(0.05)
        raise AssertionError("C model produced no visible pixels")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@unittest.skipUnless(
    NEEDS_BROWSER, "cross-renderer mask checks need Windows, Node and Chrome"
)
class WasmBrowserParityTests(unittest.TestCase):
    def test_ray_sphere_impostors_match_c_silhouette_and_shading(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 12",
                    "camera fov(70)",
                    "clear rgba(0, 0, 0, 255)",
                    "fn(draw)",
                    "  display ray_sphere(-0.7, 0, 0, 1) -rgb(210, 70, 40)",
                    "  display ray_sphere(0.7, 0, 1, 1) -rgb(60, 100, 230)",
                    "end",
                    "",
                )
            )
            for directory in (c_dir, wasm_dir):
                (directory / "program.ANVL").write_text(program, encoding="utf-8")
            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME), "ANVIL_REQUIRE_SPHERE_IMPOSTOR": "1"},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            c_rgba = _native_rgba(c_output)
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
            self.assertEqual(len(c_rgba), len(wasm_rgba))

        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.90)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 20.0, metrics)
        self.assertGreater(metrics["within_32_visible"], 0.90, metrics)

    def test_ray_sphere_impostors_match_c_with_oblique_camera(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 1 1 12",
                    "camera fov(58)",
                    "clear rgba(0, 0, 0, 255)",
                    "fn(draw)",
                    "  set var(camera_ok) = camera_angle(-8, 6)",
                    "  display ray_sphere(-0.7, 0, 0, 1) -rgb(210, 70, 40)",
                    "  display ray_sphere(0.7, 0, 1, 1) -rgb(60, 100, 230)",
                    "end",
                    "",
                )
            )
            for directory in (c_dir, wasm_dir):
                (directory / "program.ANVL").write_text(program, encoding="utf-8")
            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME), "ANVIL_REQUIRE_SPHERE_IMPOSTOR": "1"},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            c_rgba = _native_rgba(c_output)
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
            self.assertEqual(len(c_rgba), len(wasm_rgba))

        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.90)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 20.0, metrics)
        self.assertGreater(metrics["within_32_visible"], 0.90, metrics)

    def test_ray_sphere_depth_order_matches_c_for_both_submission_orders(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            captures: dict[tuple[str, str], bytes] = {}
            pair = (
                "display ray_sphere(0, 0, 0, 1.5) -rgb(30, 70, 240)",
                "display ray_sphere(0, 0, 1, 1.5) -rgb(240, 50, 30)",
            )
            for order in ("far_near", "near_far"):
                c_dir = root / f"c_{order}"
                wasm_dir = root / f"wasm_{order}"
                c_dir.mkdir()
                wasm_dir.mkdir()
                draws = pair if order == "far_near" else pair[::-1]
                program = "\n".join(
                    (
                        "scene 3d",
                        "camera perspective 0 0 8",
                        "clear rgba(11, 16, 27, 255)",
                        "fn(draw)",
                        *(f"  {draw}" for draw in draws),
                        "end",
                        "",
                    )
                )
                for directory in (c_dir, wasm_dir):
                    (directory / "program.ANVL").write_text(program, encoding="utf-8")
                c_output = c_dir / "program.exe"
                _compile(c_dir / "program.ANVL", c_output)
                wasm_output = wasm_dir / "program.wasm"
                _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
                browser = subprocess.run(
                    ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env={**os.environ, "CHROME_PATH": str(CHROME), "ANVIL_REQUIRE_SPHERE_IMPOSTOR": "1"},
                )
                self.assertEqual(browser.returncode, 0, browser.stderr)
                page = json.loads(browser.stdout.strip().splitlines()[-1])
                captures[("C", order)] = _native_rgba(c_output)
                captures[("wasm", order)] = base64.b64decode(
                    page["rgba"], validate=True
                )

        for order in ("far_near", "near_far"):
            c_rgba = captures[("C", order)]
            wasm_rgba = captures[("wasm", order)]
            self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.90)
            metrics = self._color_metrics(c_rgba, wasm_rgba)
            self.assertLess(metrics["mae_visible_pixels"], 20.0, metrics)
            self.assertGreater(metrics["within_32_visible"], 0.90, metrics)
        for backend in ("C", "wasm"):
            self.assertLess(
                self._color_metrics(
                    captures[(backend, "far_near")],
                    captures[(backend, "near_far")],
                )["mae_all_pixels"],
                0.5,
            )

    def test_ray_sphere_shadow_matches_c_for_an_overlapping_occluder(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            captures: dict[tuple[str, str], bytes] = {}
            scenes = {
                "receiver": [
                    "display ray_sphere(0, 0, 0, 1) -rgb(220, 70, 40)",
                ],
                "shadow": [
                    "display ray_sphere(0, 0, 0, 1) -rgb(220, 70, 40)",
                    "display ray_sphere(-0.8, 1.4, 1.1, 0.7) -rgb(40, 80, 240)",
                ],
            }
            for scene, draws in scenes.items():
                for backend in ("C", "wasm"):
                    directory = root / f"{backend}_{scene}"
                    directory.mkdir()
                    program = "\n".join(
                        (
                            "scene 3d",
                            "camera perspective 0 0 12",
                            "camera fov(70)",
                            "clear rgba(0, 0, 0, 255)",
                            "fn(draw)",
                            *(f"  {draw}" for draw in draws),
                            "end",
                            "",
                        )
                    )
                    source = directory / "program.ANVL"
                    source.write_text(program, encoding="utf-8")
                    output = directory / ("program.exe" if backend == "C" else "program.wasm")
                    _compile(source, output, "wasm" if backend == "wasm" else None)
                    if backend == "C":
                        captures[(backend, scene)] = _native_rgba(output)
                        continue
                    browser = subprocess.run(
                        ["node", str(CAPTURE), str(directory), "program.html"],
                        capture_output=True,
                        text=True,
                        timeout=90,
                        env={**os.environ, "CHROME_PATH": str(CHROME), "ANVIL_REQUIRE_SPHERE_IMPOSTOR": "1"},
                    )
                    self.assertEqual(browser.returncode, 0, browser.stderr)
                    page = json.loads(browser.stdout.strip().splitlines()[-1])
                    captures[(backend, scene)] = base64.b64decode(
                        page["rgba"], validate=True
                    )

        def shadowed_receiver_pixels(baseline: bytes, shaded: bytes) -> int:
            count = 0
            for offset in range(0, len(baseline), 4):
                base_r, base_g, base_b = baseline[offset : offset + 3]
                shade_r, shade_g, shade_b = shaded[offset : offset + 3]
                base_is_receiver = base_r > base_g * 1.5 and base_r > base_b * 1.5
                shaded_is_receiver = shade_r > shade_g * 1.5 and shade_r > shade_b * 1.5
                if base_is_receiver and shaded_is_receiver and base_r - shade_r > 24:
                    count += 1
            return count

        c_shadow_pixels = shadowed_receiver_pixels(
            captures[("C", "receiver")], captures[("C", "shadow")]
        )
        wasm_shadow_pixels = shadowed_receiver_pixels(
            captures[("wasm", "receiver")], captures[("wasm", "shadow")]
        )
        self.assertGreater(c_shadow_pixels, 10, c_shadow_pixels)
        self.assertGreater(wasm_shadow_pixels, 10, wasm_shadow_pixels)
        c_wasm = self._color_metrics(
            captures[("C", "shadow")], captures[("wasm", "shadow")]
        )
        self.assertLess(c_wasm["mae_visible_pixels"], 20.0, c_wasm)
        self.assertGreater(c_wasm["within_32_visible"], 0.90, c_wasm)

    def test_independent_morph_instances_render_distinct_c_and_wasm_poses(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            captures: dict[tuple[str, int], bytes] = {}
            for assignment in (0, 1):
                c_dir = root / f"c{assignment}"
                wasm_dir = root / f"wasm{assignment}"
                c_dir.mkdir()
                wasm_dir.mkdir()
                program = "\n".join(
                    (
                        "scene 3d",
                        "camera perspective 0 0 8",
                        "camera fov(70)",
                        "set var(frame) = 0",
                        "fn(update)",
                        "  add var(frame) 1",
                        "  if var(frame) = 1",
                        '    set var(a) = model_instance("instance.gltf")',
                        '    set var(b) = model_instance("instance.gltf")',
                        f'    set var(wa) = model_instance_morph("instance.gltf", var(a), 0, {1 - assignment})',
                        f'    set var(wb) = model_instance_morph("instance.gltf", var(b), 0, {assignment})',
                        "  end",
                        "end",
                        "fn(draw)",
                        "  clear rgba(0, 0, 0, 255)",
                        '  set var(db) = model_draw_instance("instance.gltf", var(b), 2, 0, 0, 1, 0, 0, 0)',
                        '  set var(da) = model_draw_instance("instance.gltf", var(a), -2, 0, 0, 1, 0, 0, 0)',
                        "end",
                        "",
                    )
                )
                for directory in (c_dir, wasm_dir):
                    write_morph_model(directory, "instance.gltf", defaults=(0.0,))
                    (directory / "program.ANVL").write_text(program, encoding="utf-8")
                c_output = c_dir / "program.exe"
                _compile(c_dir / "program.ANVL", c_output)
                wasm_output = wasm_dir / "program.wasm"
                _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
                browser = subprocess.run(
                    ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env={**os.environ, "CHROME_PATH": str(CHROME)},
                )
                self.assertEqual(browser.returncode, 0, browser.stderr)
                page = json.loads(browser.stdout.strip().splitlines()[-1])
                captures[("C", assignment)] = _native_rgba(c_output)
                captures[("wasm", assignment)] = base64.b64decode(
                    page["rgba"], validate=True
                )

        for assignment in (0, 1):
            self.assertGreater(
                self._silhouette_iou(
                    captures[("C", assignment)], captures[("wasm", assignment)]
                ),
                0.90,
            )
        self.assertNotEqual(captures[("C", 0)], captures[("C", 1)])
        self.assertNotEqual(captures[("wasm", 0)], captures[("wasm", 1)])

    def test_static_morph_model_draw_matches_c_silhouette(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            for directory in (c_dir, wasm_dir):
                write_morph_model(directory, "morph.gltf", defaults=(0.0,))
                (directory / "program.ANVL").write_text(_program(), encoding="utf-8")

            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")

            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            self.assertEqual((page["width"], page["height"]), (960, 600))
            wasm_mask = base64.b64decode(page["rgba"], validate=True)
            c_mask = _native_rgba(c_output)
            self.assertEqual(len(c_mask), len(wasm_mask))

        self.assertGreater(self._silhouette_iou(c_mask, wasm_mask), 0.92)
        metrics = self._color_metrics(c_mask, wasm_mask)
        self.assertLess(metrics["mae_visible_pixels"], 10.0, metrics)
        self.assertGreater(metrics["within_16_visible"], 0.90, metrics)

    def test_embedded_glb_model_draw_is_visible_in_chromium(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            program = "\n".join((
                "scene 3d",
                "camera perspective 0 0 5",
                "camera fov(60)",
                "clear rgba(0, 0, 0, 255)",
                "fn(draw)",
                '  set var(ok) = model_draw("quad.glb", 0, 0, 0, 1, 0, 0, 0)',
                "end",
                "",
            ))
            for directory in (c_dir, wasm_dir):
                write_glb(directory, "quad.glb", (1.0, 0.0, 0.0))
                (directory / "program.ANVL").write_text(program, encoding="utf-8")

            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            self.assertEqual((page["width"], page["height"]), (960, 600))
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
            c_rgba = _native_rgba(c_output)
            self.assertEqual(len(c_rgba), len(wasm_rgba))

        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.92)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 10.0, metrics)
        self.assertGreater(metrics["within_16_visible"], 0.90, metrics)

    def test_bundled_textured_glb_example_matches_c_in_chromium(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir, wasm_dir = root / "c", root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            template = (ROOT / "examples" / "glb_textured_model.ANVL").read_text(encoding="utf-8")
            template = template.replace(
                '  set var(model_visible) = model_draw("glb_textured_quad.glb", 0, 0, 0, 1, 0, 20, 0)',
                '  set var(left_visible) = model_draw("glb_textured_quad.glb", -1.5, 0, 0, 0.55, 0, 20, 0)\n'
                '  set var(middle_visible) = model_draw("middle.glb", 0, 0, 0, 0.55, 0, 20, 0)\n'
                '  set var(right_visible) = model_draw("glb_textured_quad.glb", 1.5, 0, 0, 0.55, 0, 20, 0)',
            )
            asset = ROOT / "examples" / "glb_textured_quad.glb"
            for directory in (c_dir, wasm_dir):
                shutil.copy2(asset, directory / asset.name)
                shutil.copy2(asset, directory / "middle.glb")
            for yaw, pitch in ((0, 0), (20, -12), (-28, 14)):
                with self.subTest(camera_angle=(yaw, pitch)):
                    program = template.replace(
                        "camera_angle(20, -12)", f"camera_angle({yaw}, {pitch})"
                    )
                    for directory in (c_dir, wasm_dir):
                        (directory / "program.ANVL").write_text(program, encoding="utf-8")

                    c_output = c_dir / "program.exe"
                    wasm_output = wasm_dir / "program.wasm"
                    _compile(c_dir / "program.ANVL", c_output)
                    _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
                    browser = subprocess.run(
                        ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                        capture_output=True,
                        text=True,
                        timeout=90,
                        env={**os.environ, "CHROME_PATH": str(CHROME)},
                    )
                    self.assertEqual(browser.returncode, 0, browser.stderr)
                    page = json.loads(browser.stdout.strip().splitlines()[-1])
                    wasm_rgba = base64.b64decode(page["rgba"], validate=True)
                    c_rgba = _native_rgba(c_output)
                    self.assertEqual(len(c_rgba), len(wasm_rgba))
                    self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.92)
                    metrics = self._color_metrics(c_rgba, wasm_rgba)
                    self.assertLess(metrics["mae_visible_pixels"], 10.0, metrics)
                    self.assertGreater(metrics["within_16_visible"], 0.90, metrics)

    def test_textured_glb_batches_render_in_painter_and_no_webgl_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            asset = ROOT / "examples" / "glb_textured_quad.glb"
            shutil.copy2(asset, root / asset.name)
            source = root / "program.ANVL"
            source.write_text("\n".join((
                "scene 3d",
                "camera perspective 0 0 6",
                "camera fov(60)",
                "clear rgba(11, 16, 27, 255)",
                "fn(draw)",
                '  set var(left) = model_draw("glb_textured_quad.glb", -1.25, 0, 0, 0.7, 0, 20, 0)',
                '  set var(right) = model_draw("glb_textured_quad.glb", 1.25, 0, 0, 0.7, 0, 20, 0)',
                "end",
                "",
            )), encoding="utf-8")
            output = root / "program.wasm"
            _compile(source, output, "wasm")
            for fallback in ("ANVIL_WASM_PAINTER", "ANVIL_WASM_NO_WEBGL"):
                with self.subTest(fallback=fallback):
                    browser = subprocess.run(
                        ["node", str(CAPTURE), str(root), "program.html"],
                        capture_output=True,
                        text=True,
                        timeout=90,
                        env={**os.environ, "CHROME_PATH": str(CHROME), fallback: "1"},
                    )
                    self.assertEqual(browser.returncode, 0, browser.stderr)
                    page = json.loads(browser.stdout.strip().splitlines()[-1])
                    rgba = base64.b64decode(page["rgba"], validate=True)
                    colored = [0, 0]
                    colors = set()
                    for y in range(600):
                        for x in range(960):
                            at = (y * 960 + x) * 4
                            pixel = tuple(rgba[at:at + 3])
                            if max(abs(pixel[channel] - (11, 16, 27)[channel]) for channel in range(3)) > 12:
                                colored[x // 480] += 1
                                colors.add(pixel)
                    self.assertGreater(colored[0], 100, (fallback, colored))
                    self.assertGreater(colored[1], 100, (fallback, colored))
                    self.assertGreater(len(colors), 3, (fallback, len(colors)))

    def test_textured_glb_cutout_and_partial_alpha_match_c_and_chromium(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir, wasm_dir = root / "c", root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            program = "\n".join((
                "scene 3d",
                "camera perspective 0 0 5",
                "camera fov(60)",
                "clear rgba(40, 80, 120, 255)",
                "fn(draw)",
                '  set var(ok) = model_draw("alpha.glb", 0, 0, 0, 1, 0, 0, 0)',
                "end",
                "",
            ))
            for directory in (c_dir, wasm_dir):
                _write_textured_near_plane_glb(directory / "alpha.glb", (0, 128))
                (directory / "program.ANVL").write_text(program, encoding="utf-8")
            c_output = c_dir / "program.exe"
            wasm_output = wasm_dir / "program.wasm"
            _compile(c_dir / "program.ANVL", c_output)
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            c_rgba = _native_rgba(c_output)
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.90)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 12.0, metrics)
        self.assertGreater(metrics["within_32_visible"], 0.88, metrics)

    def test_embedded_glb_texture_clips_at_near_plane_with_uv_and_depth_parity(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir, wasm_dir = root / "c", root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            program = "\n".join((
                "scene 3d",
                "camera perspective 0 0 5",
                "camera fov(60)",
                "clear rgba(0, 0, 0, 255)",
                "fn(draw)",
                '  set var(ok) = model_draw("near.glb", 0, 0, 0, 1, 0, 0, 0)',
                "end",
                "",
            ))
            for directory in (c_dir, wasm_dir):
                _write_textured_near_plane_glb(directory / "near.glb")
                (directory / "program.ANVL").write_text(program, encoding="utf-8")

            c_output = c_dir / "program.exe"
            wasm_output = wasm_dir / "program.wasm"
            _compile(c_dir / "program.ANVL", c_output)
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            c_rgba = _native_rgba(c_output)
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
            self.assertEqual((page["width"], page["height"]), (960, 600))

        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.90)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 12.0, metrics)
        self.assertGreater(metrics["within_16_visible"], 0.85, metrics)
        for left, right in ((90, 210), (310, 430), (525, 650)):
            visible = sum(
                c_rgba[(y * 960 + x) * 4] > 2
                or c_rgba[(y * 960 + x) * 4 + 1] > 2
                or c_rgba[(y * 960 + x) * 4 + 2] > 2
                for y in range(260, 390)
                for x in range(left, right)
            )
            self.assertGreater(visible, 20, (left, right, visible))
        behind_visible = sum(
            c_rgba[(y * 960 + x) * 4] > 2
            or c_rgba[(y * 960 + x) * 4 + 1] > 2
            or c_rgba[(y * 960 + x) * 4 + 2] > 2
            for y in range(260, 390)
            for x in range(740, 840)
        )
        self.assertEqual(behind_visible, 0)

    def test_custom_model_lighting_matches_c_color_and_rejects_zero_direction(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 1 1 12",
                    "camera fov(58)",
                    "clear rgba(0, 0, 0, 255)",
                    "fn(draw)",
                    "  set var(camera_ok) = camera_angle(-8, 6)",
                    "  set var(light_ok) = light(0, 0, 1)",
                    "  set var(zero_ok) = light(0, 0, 0)",
                    "  set var(old_ambient) = light_ambient(0.1)",
                    "  set var(old_intensity) = light_intensity(0.5)",
                    '  set var(weight) = model_morph("morph.gltf", 0, 0.5)',
                    '  set var(ok) = model_draw("morph.gltf", 0, 0, 0, 1, 0, 0, 0)',
                    "end",
                    "",
                )
            )
            for directory in (c_dir, wasm_dir):
                write_morph_model(directory, "morph.gltf", defaults=(0.0,))
                (directory / "program.ANVL").write_text(program, encoding="utf-8")
            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            c_rgba = _native_rgba(c_output)
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
            self.assertEqual(len(c_rgba), len(wasm_rgba))
        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.92)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 10.0, metrics)

    def test_primitive_lighting_matches_c_one_sided_shading(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 0 0 12",
                    "camera fov(70)",
                    "clear rgba(0, 0, 0, 255)",
                    "fn(draw)",
                    "  set var(light_ok) = light(0, 0, -1)",
                    "  set var(ambient_old) = light_ambient(0.1)",
                    "  set var(intensity_old) = light_intensity(1)",
                    "  display cube(-2, 0, 0, 2) -rgb(200, 60, 60)",
                    "  display sphere(2, 0, 0, 1) -rgb(200, 60, 60)",
                    "end",
                    "",
                )
            )
            for directory in (c_dir, wasm_dir):
                (directory / "program.ANVL").write_text(program, encoding="utf-8")
            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            c_rgba = _native_rgba(c_output)
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
            self.assertEqual(len(c_rgba), len(wasm_rgba))
        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.90)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 20.0, metrics)
        self.assertGreater(metrics["within_32_visible"], 0.90, metrics)

    def test_ray_sphere_lighting_controls_match_c(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            captures: dict[tuple[str, str], bytes] = {}
            settings = {
                "ambient": ["set var(old_ambient) = light_ambient(0.65)"],
                "intensity": ["set var(old_intensity) = light_intensity(0.45)"],
                "direction": ["set var(light_ok) = light(0.4, 0.7, 1)"],
                "combined": [
                    "set var(light_ok) = light(0.4, 0.7, 1)",
                    "set var(old_ambient) = light_ambient(0.65)",
                    "set var(old_intensity) = light_intensity(0.45)",
                ],
            }
            for mode, calls in settings.items():
                for backend in ("C", "wasm"):
                    directory = root / f"{backend}_{mode}"
                    directory.mkdir()
                    program = "\n".join(
                        (
                            "scene 3d",
                            "camera perspective 1 -1 12",
                            "camera fov(61)",
                            "clear rgba(11, 16, 27, 255)",
                            "fn(draw)",
                            "  set var(camera_ok) = camera_angle(-11, 8)",
                            *(f"  {call}" for call in calls),
                            "  display ray_sphere(-0.7, 0, 0, 1) -rgb(210, 70, 40)",
                            "  display ray_sphere(0.7, 0, 1, 1) -rgb(60, 100, 230)",
                            "end",
                            "",
                        )
                    )
                    source = directory / "program.ANVL"
                    source.write_text(program, encoding="utf-8")
                    output = directory / ("program.exe" if backend == "C" else "program.wasm")
                    _compile(source, output, "wasm" if backend == "wasm" else None)
                    if backend == "C":
                        captures[(backend, mode)] = _native_rgba(output)
                    else:
                        browser = subprocess.run(
                            ["node", str(CAPTURE), str(directory), "program.html"],
                            capture_output=True,
                            text=True,
                            timeout=90,
                            env={**os.environ, "CHROME_PATH": str(CHROME), "ANVIL_REQUIRE_SPHERE_IMPOSTOR": "1"},
                        )
                        self.assertEqual(browser.returncode, 0, browser.stderr)
                        page = json.loads(browser.stdout.strip().splitlines()[-1])
                        captures[(backend, mode)] = base64.b64decode(page["rgba"], validate=True)

        for mode in settings:
            c_rgba = captures[("C", mode)]
            wasm_rgba = captures[("wasm", mode)]
            self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.90)
            metrics = self._color_metrics(c_rgba, wasm_rgba)
            self.assertLess(metrics["mae_visible_pixels"], 20.0, (mode, metrics))
            self.assertGreater(metrics["within_32_visible"], 0.90, (mode, metrics))

    def test_intersecting_primitive_depth_order_matches_c(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            captures: dict[tuple[str, str], bytes] = {}
            for order in ((0, 1), (1, 0)):
                c_dir = root / f"c_{order[0]}_{order[1]}"
                wasm_dir = root / f"wasm_{order[0]}_{order[1]}"
                c_dir.mkdir()
                wasm_dir.mkdir()
                cubes = (
                    "display cube(0, 0, 0, 3) -rgb(200, 35, 25) -rotate(0, 0, 23)",
                    "display cube(0.1, 0, 0, 3) -rgb(20, 55, 210) -rotate(0, 37, 0)",
                )
                program = "\n".join(
                    (
                        "scene 3d",
                        "camera perspective 0 0 12",
                        "camera fov(70)",
                        "clear rgba(0, 0, 0, 255)",
                        "fn(draw)",
                        "  set var(flat) = light_ambient(1)",
                        f"  {cubes[order[0]]}",
                        f"  {cubes[order[1]]}",
                        "end",
                        "",
                    )
                )
                for directory in (c_dir, wasm_dir):
                    (directory / "program.ANVL").write_text(program, encoding="utf-8")
                c_output = c_dir / "program.exe"
                _compile(c_dir / "program.ANVL", c_output)
                wasm_output = wasm_dir / "program.wasm"
                _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
                browser = subprocess.run(
                    ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env={**os.environ, "CHROME_PATH": str(CHROME)},
                )
                self.assertEqual(browser.returncode, 0, browser.stderr)
                page = json.loads(browser.stdout.strip().splitlines()[-1])
                captures[("C", str(order))] = _native_rgba(c_output)
                captures[("wasm", str(order))] = base64.b64decode(
                    page["rgba"], validate=True
                )

        c_far_near = captures[("C", str((0, 1)))]
        c_near_far = captures[("C", str((1, 0)))]
        wasm_far_near = captures[("wasm", str((0, 1)))]
        wasm_near_far = captures[("wasm", str((1, 0)))]
        for c_image, wasm_image in (
            (c_far_near, wasm_far_near),
            (c_near_far, wasm_near_far),
        ):
            self.assertGreater(self._silhouette_iou(c_image, wasm_image), 0.92)
            metrics = self._color_metrics(c_image, wasm_image)
            self.assertLess(metrics["mae_visible_pixels"], 8.0, metrics)
        self.assertLess(
            self._color_metrics(c_far_near, c_near_far)["mae_all_pixels"], 0.5
        )
        self.assertLess(
            self._color_metrics(wasm_far_near, wasm_near_far)["mae_all_pixels"], 0.5
        )

    def test_intersecting_model_depth_order_matches_c(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            captures: dict[tuple[str, str], bytes] = {}
            for order in ((0, 1), (1, 0)):
                c_dir = root / f"model_c_{order[0]}_{order[1]}"
                wasm_dir = root / f"model_wasm_{order[0]}_{order[1]}"
                c_dir.mkdir()
                wasm_dir.mkdir()
                for directory in (c_dir, wasm_dir):
                    write_quad(directory, "red.gltf", (1.0, 0.0, 0.0))
                    write_quad(directory, "blue.gltf", (0.0, 0.0, 1.0))
                models = (
                    'model_draw("red.gltf", 0, 0, 0, 2, 0, -35, 0)',
                    'model_draw("blue.gltf", 0, 0, 0, 2, 0, 35, 0)',
                )
                program = "\n".join(
                    (
                        "scene 3d",
                        "camera perspective 0 0 12",
                        "camera fov(70)",
                        "clear rgba(0, 0, 0, 255)",
                        "fn(draw)",
                        "  set var(flat) = light_ambient(1)",
                        f"  set var(first) = {models[order[0]]}",
                        f"  set var(second) = {models[order[1]]}",
                        "end",
                        "",
                    )
                )
                for directory in (c_dir, wasm_dir):
                    (directory / "program.ANVL").write_text(program, encoding="utf-8")
                c_output = c_dir / "program.exe"
                _compile(c_dir / "program.ANVL", c_output)
                wasm_output = wasm_dir / "program.wasm"
                _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
                browser = subprocess.run(
                    ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env={**os.environ, "CHROME_PATH": str(CHROME)},
                )
                self.assertEqual(browser.returncode, 0, browser.stderr)
                page = json.loads(browser.stdout.strip().splitlines()[-1])
                captures[("C", str(order))] = _native_rgba(c_output)
                captures[("wasm", str(order))] = base64.b64decode(
                    page["rgba"], validate=True
                )

        c_first = captures[("C", str((0, 1)))]
        c_second = captures[("C", str((1, 0)))]
        wasm_first = captures[("wasm", str((0, 1)))]
        wasm_second = captures[("wasm", str((1, 0)))]
        for c_image, wasm_image in ((c_first, wasm_first), (c_second, wasm_second)):
            self.assertGreater(self._silhouette_iou(c_image, wasm_image), 0.90)
            metrics = self._color_metrics(c_image, wasm_image)
            self.assertLess(metrics["mae_visible_pixels"], 10.0, metrics)
            self.assertGreater(metrics["within_16_visible"], 0.90, metrics)
        self.assertLess(self._color_metrics(c_first, c_second)["mae_all_pixels"], 0.5)
        self.assertLess(self._color_metrics(wasm_first, wasm_second)["mae_all_pixels"], 0.5)

    def test_animated_skinned_model_draw_matches_c(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            program = "\n".join(
                (
                    "scene 3d",
                    "camera perspective 1 1 12",
                    "camera fov(58)",
                    "clear rgba(0, 0, 0, 255)",
                    "fn(draw)",
                    "  set var(camera_ok) = camera_angle(-8, 6)",
                    "  set var(light_ok) = light(0.4, 0.7, 1)",
                    "  set var(ambient_old) = light_ambient(0.22)",
                    "  set var(intensity_old) = light_intensity(0.78)",
                    '  set var(t) = model_animate("skin.gltf", 0.5)',
                    '  set var(ok) = model_draw("skin.gltf", 0.25, -0.1, 0, 1.25, 15, -8, 23)',
                    "end",
                    "",
                )
            )
            for directory in (c_dir, wasm_dir):
                write_skinned_model(
                    directory, "skin.gltf", weights=(0.5, 0.5), joints=2
                )
                (directory / "program.ANVL").write_text(program, encoding="utf-8")
            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            c_rgba = _native_rgba(c_output)
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
            self.assertEqual(len(c_rgba), len(wasm_rgba))
        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.88)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 20.0, metrics)
        self.assertGreater(metrics["within_32_visible"], 0.88, metrics)

    def test_animated_skinned_ray_mesh_matches_c_model_draw(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            common = (
                "scene 3d",
                "camera perspective 1 1 12",
                "camera fov(58)",
                "clear rgba(0, 0, 0, 255)",
                "fn(draw)",
                "  set var(camera_ok) = camera_angle(-8, 6)",
                "  set var(light_ok) = light(0.4, 0.7, 1)",
                "  set var(ambient_old) = light_ambient(0.22)",
                "  set var(intensity_old) = light_intensity(0.78)",
                '  set var(t) = model_animate("skin.gltf", 0.5)',
            )
            programs = {
                c_dir: "\n".join(
                    (
                        *common,
                        '  set var(ok) = model_draw("skin.gltf", 0.25, -0.1, 0, 1.25, 15, -8, 23)',
                        "end",
                        "",
                    )
                ),
                wasm_dir: "\n".join(
                    (
                        *common,
                        '  set var(ok) = ray_mesh("skin.gltf", 0.25, -0.1, 0, 1.25, 15, -8, 23)',
                        "end",
                        "",
                    )
                ),
            }
            for directory, program in programs.items():
                write_skinned_model(
                    directory, "skin.gltf", weights=(0.5, 0.5), joints=2
                )
                (directory / "program.ANVL").write_text(program, encoding="utf-8")
            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            c_rgba = _native_rgba(c_output)
            wasm_rgba = base64.b64decode(page["rgba"], validate=True)
            self.assertEqual(len(c_rgba), len(wasm_rgba))
        self.assertGreater(self._silhouette_iou(c_rgba, wasm_rgba), 0.88)
        metrics = self._color_metrics(c_rgba, wasm_rgba)
        self.assertLess(metrics["mae_visible_pixels"], 20.0, metrics)
        self.assertGreater(metrics["within_32_visible"], 0.88, metrics)

    def test_animated_skinned_mesh_crossing_depth_is_order_independent(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            captures: dict[tuple[str, str], bytes] = {}
            draws = (
                'model_draw("skin.gltf", -1, 0, 0, 2, 0, 0, 0)',
                'model_draw("blue.gltf", 0, 0, 0, 2, 0, 35, 0)',
            )
            for order in ((0, 1), (1, 0)):
                for backend in ("c", "wasm"):
                    directory = root / f"{backend}_{order[0]}_{order[1]}"
                    directory.mkdir()
                    write_skinned_model(
                        directory,
                        "skin.gltf",
                        weights=(0.5, 0.5),
                        joints=2,
                    )
                    write_quad(directory, "blue.gltf", (0.0, 0.0, 1.0))
                    program = "\n".join(
                        (
                            "scene 3d",
                            "camera perspective 0 0 12",
                            "camera fov(70)",
                            "clear rgba(0, 0, 0, 255)",
                            "fn(draw)",
                            "  set var(flat) = light_ambient(1)",
                            '  set var(t) = model_animate("skin.gltf", 0.5)',
                            f"  set var(first) = {draws[order[0]]}",
                            f"  set var(second) = {draws[order[1]]}",
                            "end",
                            "",
                        )
                    )
                    source = directory / "program.ANVL"
                    source.write_text(program, encoding="utf-8")
                    output = directory / ("program.exe" if backend == "c" else "program.wasm")
                    _compile(source, output, "wasm" if backend == "wasm" else "c")
                    if backend == "c":
                        rgba = _native_rgba(output)
                    else:
                        browser = subprocess.run(
                            ["node", str(CAPTURE), str(directory), "program.html"],
                            capture_output=True,
                            text=True,
                            timeout=90,
                            env={**os.environ, "CHROME_PATH": str(CHROME)},
                        )
                        self.assertEqual(browser.returncode, 0, browser.stderr)
                        page = json.loads(browser.stdout.strip().splitlines()[-1])
                        rgba = base64.b64decode(page["rgba"], validate=True)
                    captures[(backend, str(order))] = rgba

        c_skin_first = captures[("c", str((0, 1)))]
        c_blue_first = captures[("c", str((1, 0)))]
        wasm_skin_first = captures[("wasm", str((0, 1)))]
        wasm_blue_first = captures[("wasm", str((1, 0)))]
        for c_image, wasm_image in (
            (c_skin_first, wasm_skin_first),
            (c_blue_first, wasm_blue_first),
        ):
            self.assertGreater(self._silhouette_iou(c_image, wasm_image), 0.88)
            metrics = self._color_metrics(c_image, wasm_image)
            self.assertLess(metrics["mae_visible_pixels"], 20.0, metrics)
            self.assertGreater(metrics["within_32_visible"], 0.88, metrics)
        self.assertLess(
            self._color_metrics(c_skin_first, c_blue_first)["mae_all_pixels"], 0.5
        )
        self.assertLess(
            self._color_metrics(wasm_skin_first, wasm_blue_first)["mae_all_pixels"], 0.5
        )

    def test_morph_culling_matches_unculled_pixels_for_all_weight_combinations(self) -> None:
        poses = tuple(
            (weight0, weight1)
            for weight0 in (0.0, 0.5, 1.0)
            for weight1 in (0.0, 0.5, 1.0)
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            captures: dict[bool, list[bytes]] = {}
            for culling in (True, False):
                directory = root / ("culled" if culling else "unculled")
                directory.mkdir()
                write_two_target_morph_model(
                    directory,
                    "groups.gltf",
                    group_translations=((0.0, 0.0, 0.0),),
                    target_deltas=((-4.0, 0.0, 0.0), (0.0, -4.0, 0.0)),
                )
                program = [
                    "scene 3d",
                    "camera perspective 0 0 12",
                    "camera fov(70)",
                    "set var(frame) = 0",
                    "fn(update)",
                    "  add var(frame) 1",
                    "end",
                    "fn(draw)",
                    "  clear rgba(0, 0, 0, 255)",
                    f"  set var(culling) = mesh_culling({1 if culling else 0})",
                ]
                for frame, (weight0, weight1) in enumerate(poses, 1):
                    program.extend(
                        (
                            f"  if var(frame) = {frame}",
                            f'    set var(w0) = model_morph("groups.gltf", 0, {weight0})',
                            f'    set var(w1) = model_morph("groups.gltf", 1, {weight1})',
                            "  end",
                        )
                    )
                program.extend(
                    (
                        '  set var(ok) = model_draw("groups.gltf", 0, 0, 0, 1, 0, 0, 0)',
                        "end",
                        "",
                    )
                )
                source = directory / "program.ANVL"
                source.write_text("\n".join(program), encoding="utf-8")
                output = directory / "program.wasm"
                _compile(source, output, "wasm")
                page_path = output.with_suffix(".html")
                page_html = page_path.read_text(encoding="utf-8")
                disabled_ticks = page_html.count("requestAnimationFrame(tick);")
                self.assertEqual(disabled_ticks, 2)
                page_path.write_text(
                    page_html.replace(
                        "requestAnimationFrame(tick);",
                        "// deterministic manual frame capture",
                    ),
                    encoding="utf-8",
                )
                browser = subprocess.run(
                    ["node", str(CAPTURE), str(directory), "program.html"],
                    capture_output=True,
                    text=True,
                    timeout=90,
                    env={
                        **os.environ,
                        "CHROME_PATH": str(CHROME),
                        "ANVIL_WASM_CAPTURE_FRAMES": str(len(poses)),
                    },
                )
                self.assertEqual(browser.returncode, 0, browser.stderr)
                page = json.loads(browser.stdout.strip().splitlines()[-1])
                self.assertEqual(len(page["frames"]), len(poses))
                captures[culling] = [
                    base64.b64decode(frame, validate=True) for frame in page["frames"]
                ]

        for index, (culled, unculled) in enumerate(zip(captures[True], captures[False])):
            if culled != unculled:
                offset = next(
                    offset
                    for offset, (left, right) in enumerate(zip(culled, unculled))
                    if left != right
                )
                pixel = offset // 4
                self.fail(
                    f"morph frame {index + 1} differs at ({pixel % 960}, {pixel // 960}): "
                    f"culled={culled[offset:offset + 4]} unculled={unculled[offset:offset + 4]}"
                )
        self.assertTrue(
            all(any(max(frame[offset : offset + 3]) > 2 for offset in range(0, len(frame), 4))
                for frame in captures[True]),
            "each morph pose should leave visible pixels in the frame",
        )

    def test_animated_morphed_ray_mesh_matches_c_silhouette(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            for directory in (c_dir, wasm_dir):
                write_animated_morph_glb(directory)
                (directory / "program.ANVL").write_text(
                    _animated_program(), encoding="utf-8"
                )

            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            wasm_mask = base64.b64decode(page["rgba"], validate=True)
            c_mask = _native_rgba(c_output)
            self.assertEqual(len(c_mask), len(wasm_mask))

        self.assertGreater(self._silhouette_iou(c_mask, wasm_mask), 0.92)
        metrics = self._color_metrics(c_mask, wasm_mask)
        self.assertLess(metrics["mae_visible_pixels"], 25.0, metrics)
        self.assertGreater(metrics["within_32_visible"], 0.90, metrics)

    @staticmethod
    def _silhouette_iou(c_rgba: bytes, wasm_rgba: bytes) -> float:
        intersection = union = 0
        for offset in range(0, len(c_rgba), 4):
            c_visible = max(c_rgba[offset : offset + 3]) > 2
            wasm_visible = max(wasm_rgba[offset : offset + 3]) > 2
            intersection += c_visible and wasm_visible
            union += c_visible or wasm_visible
        return intersection / union if union else 0.0

    @staticmethod
    def _color_metrics(c_rgba: bytes, wasm_rgba: bytes) -> dict[str, float]:
        absolute_error = visible_error = 0
        exact = visible_exact = within_16 = within_32 = 0
        visible_count = 0
        pixel_count = len(c_rgba) // 4
        for offset in range(0, len(c_rgba), 4):
            c_pixel = c_rgba[offset : offset + 4]
            wasm_pixel = wasm_rgba[offset : offset + 4]
            same = c_pixel == wasm_pixel
            exact += same
            c_visible = max(c_pixel[:3]) > 2
            wasm_visible = max(wasm_pixel[:3]) > 2
            if c_visible or wasm_visible:
                visible_count += 1
                visible_exact += same
                errors = [abs(a - b) for a, b in zip(c_pixel[:3], wasm_pixel[:3])]
                visible_error += sum(errors)
                within_16 += max(errors) <= 16
                within_32 += max(errors) <= 32
            absolute_error += sum(abs(a - b) for a, b in zip(c_pixel[:3], wasm_pixel[:3]))
        return {
            "mae_all_pixels": absolute_error / (pixel_count * 3),
            "mae_visible_pixels": visible_error / (max(visible_count, 1) * 3),
            "exact_all_pixels": exact / pixel_count,
            "exact_visible_pixels": visible_exact / max(visible_count, 1),
            "visible_pixels": visible_count,
            "within_16_visible": within_16 / max(visible_count, 1),
            "within_32_visible": within_32 / max(visible_count, 1),
        }



if __name__ == "__main__":
    unittest.main()
