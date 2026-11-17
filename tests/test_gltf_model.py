"""glTF import: compile-time baking and on-screen pixels (8.13)."""

from __future__ import annotations

import json
import pathlib
import queue
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from compiler import gltf  # noqa: E402
from test_sprite_draw import WindowReader  # noqa: E402

LIGHT = (-0.35, 0.8, 0.55)


def expected_red() -> int:
    norm = (LIGHT[0] ** 2 + LIGHT[1] ** 2 + LIGHT[2] ** 2) ** 0.5
    brightness = 0.28 + 0.72 * abs(LIGHT[2] / norm)
    return int(255 * brightness)


def quad_document(colour: tuple[float, float, float], translation: tuple[float, float, float] = (0, 0, 0)) -> dict:
    return {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "translation": list(translation)}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [*colour, 1.0]}}],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": 6, "type": "SCALAR"},
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 48},
            {"buffer": 0, "byteOffset": 48, "byteLength": 12},
        ],
        "buffers": [{"uri": "quad.bin", "byteLength": 60}],
    }


def write_quad(root: pathlib.Path, name: str, colour: tuple[float, float, float], translation=(0, 0, 0)) -> pathlib.Path:
    positions = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)]
    payload = b"".join(struct.pack("<3f", *p) for p in positions) + struct.pack("<6H", 0, 1, 2, 0, 2, 3)
    (root / "quad.bin").write_bytes(payload)
    path = root / name
    path.write_text(json.dumps(quad_document(colour, translation), indent=2), encoding="utf-8")
    return path


def write_glb(root: pathlib.Path, name: str, colour: tuple[float, float, float]) -> pathlib.Path:
    """The same quad as an embedded .glb container."""
    positions = [(-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0)]
    binary = b"".join(struct.pack("<3f", *p) for p in positions) + struct.pack("<6H", 0, 1, 2, 0, 2, 3)
    document = quad_document(colour)
    document["buffers"] = [{"byteLength": len(binary)}]
    payload = json.dumps(document).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    binary += bytes((4 - len(binary) % 4) % 4)
    total = 12 + 8 + len(payload) + 8 + len(binary)
    header = b"glTF" + struct.pack("<II", 2, total)
    chunks = struct.pack("<II", len(payload), 0x4E4F534A) + payload
    chunks += struct.pack("<II", len(binary), 0x004E4942) + binary
    path = root / name
    path.write_bytes(header + chunks)
    return path


def build(root: pathlib.Path, source_text: str, name: str = "model.ANVL") -> tuple[subprocess.CompletedProcess, pathlib.Path]:
    source = root / name
    source.write_text(source_text, encoding="utf-8")
    executable = root / "model.exe"
    result = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result, executable


class GltfLoaderTests(unittest.TestCase):
    def test_a_quad_becomes_two_coloured_triangles(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            path = write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            triangles = gltf.load_triangles(path)
            self.assertEqual(len(triangles), 24)
            self.assertEqual(triangles[:9], [-1.0, -1.0, 0.0, 1.0, -1.0, 0.0, 1.0, 1.0, 0.0])
            self.assertEqual(triangles[9:12], [255.0, 0.0, 0.0])

    def test_node_translation_moves_vertices(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            path = write_quad(root, "moved.gltf", (0.0, 1.0, 0.0), translation=(2.0, 3.0, 0.0))
            triangles = gltf.load_triangles(path)
            self.assertEqual(triangles[:3], [1.0, 2.0, 0.0])

    def test_a_glb_container_loads_the_same_triangles(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            gltf_path = write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            glb_path = write_glb(root, "quad.glb", (1.0, 0.0, 0.0))
            self.assertEqual(
                gltf.load_triangles(gltf_path), gltf.load_triangles(glb_path)
            )

    def test_a_broken_glb_is_reported(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            path = root / "broken.glb"
            path.write_bytes(b"glTF" + struct.pack("<II", 2, 12))
            with self.assertRaises(gltf.ModelError):
                gltf.load_triangles(path)

    def test_missing_and_unsupported_inputs_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            with self.assertRaises(gltf.ModelError):
                gltf.load_triangles(root / "nope.gltf")
            broken = root / "broken.gltf"
            broken.write_text("{not json", encoding="utf-8")
            with self.assertRaises(gltf.ModelError):
                gltf.load_triangles(broken)


class GltfCompileTests(unittest.TestCase):
    def test_missing_model_is_a_located_compile_error(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            result, _ = build(
                root,
                "fn(draw)\n"
                '  set var(ok) = model_draw("absent.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
                "end\n",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot find model", result.stderr)
            self.assertIn('absent.gltf', result.stderr)


class GltfPixelTests(unittest.TestCase):
    def run_and_sample(self, root: pathlib.Path, marker_colour) -> None:
        executable = root / "model.exe"
        process = subprocess.Popen(
            [str(executable)],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        reader = WindowReader(process.pid)
        try:
            self.assertIsNotNone(reader.find(time.monotonic() + 10), "no window")
            reader.force_client_size(960, 600)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                pixel = reader.pixel(480, 324)
                if marker_colour(pixel):
                    return
                time.sleep(0.05)
            self.fail(f"centre pixel never matched, last {reader.pixel(480, 324)}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    def test_a_gltf_quad_paints_shaded_triangles(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            result, executable = build(
                root,
                "scene 3d\n"
                "camera perspective 0 0 5\n"
                "camera fov(60)\n"
                "clear rgba(0, 0, 0, 255)\n"
                "set var(frame) = 0\n"
                "\n"
                "fn(draw)\n"
                "  add var(frame) 1\n"
                "  if var(frame) > 900\n"
                "    stop\n"
                "  end\n"
                '  set var(ok) = model_draw("quad.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
                "end\n",
            )
            if result.returncode != 0:
                if "No C compiler found" in result.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(result.stderr)
            expected = expected_red()
            self.run_and_sample(
                root,
                lambda pixel: abs(pixel[0] - expected) <= 3 and pixel[1] == 0 and pixel[2] == 0,
            )

    def test_a_glb_model_renders_like_a_gltf_one(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_glb(root, "quad.glb", (1.0, 0.0, 0.0))
            source_text = '\n'.join(
                (
                    "scene 3d",
                    "camera perspective 0 0 5",
                    "camera fov(60)",
                    "clear rgba(0, 0, 0, 255)",
                    "set var(frame) = 0",
                    "",
                    "fn(draw)",
                    "  add var(frame) 1",
                    "  if var(frame) > 900",
                    "    stop",
                    "  end",
                    '  set var(ok) = model_draw("quad.glb", 0, 0, 0, 1, 0, 0, 0)',
                    "end",
                    "",
                )
            )
            result, _ = build(root, source_text)
            if result.returncode != 0:
                if "No C compiler found" in result.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(result.stderr)
            expected = expected_red()
            self.run_and_sample(
                root,
                lambda pixel: abs(pixel[0] - expected) <= 3 and pixel[1] == 0 and pixel[2] == 0,
            )

    def test_a_nearer_model_wins_the_depth_test(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "far.gltf", (1.0, 0.0, 0.0))
            write_quad(root, "near.gltf", (0.0, 0.0, 1.0), translation=(0.0, 0.0, 1.0))
            result, _ = build(
                root,
                "scene 3d\n"
                "camera perspective 0 0 5\n"
                "camera fov(60)\n"
                "clear rgba(0, 0, 0, 255)\n"
                "set var(frame) = 0\n"
                "\n"
                "fn(draw)\n"
                "  add var(frame) 1\n"
                "  if var(frame) > 900\n"
                "    stop\n"
                "  end\n"
                '  set var(a) = model_draw("far.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
                '  set var(b) = model_draw("near.gltf", 0, 0.5, 0, 1, 0, 0, 0)\n'
                "end\n",
            )
            if result.returncode != 0:
                if "No C compiler found" in result.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(result.stderr)
            self.run_and_sample(
                root,
                lambda pixel: pixel[2] > 100 and pixel[0] == 0 and pixel[1] == 0,
            )



class GltfCullingTests(unittest.TestCase):
    def test_offscreen_models_are_culled_and_can_be_forced(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_quad(root, "quad.gltf", (1.0, 0.0, 0.0))
            source_text = chr(10).join(
                (
                    "scene 3d",
                    "camera perspective 0 0 5",
                    "camera fov(60)",
                    "clear rgba(0, 0, 0, 255)",
                    "set var(frame) = 0",
                    "",
                    "fn(draw)",
                    "  add var(frame) 1",
                    "  if var(frame) = 2",
                    '    set var(a) = model_draw("quad.gltf", 0, 0, 20, 1, 0, 0, 0)',
                    '    say "behind"',
                    "    say mesh_culled()",
                    "    say mesh_drawn()",
                    "  end",
                    "  if var(frame) = 10",
                    '    set var(b) = model_draw("quad.gltf", 0, 0, 0, 1, 0, 0, 0)',
                    '    say "front"',
                    "    say mesh_culled()",
                    "    say mesh_drawn()",
                    "  end",
                    "  if var(frame) = 20",
                    "    set var(off) = mesh_culling(0)",
                    '    set var(c) = model_draw("quad.gltf", 0, 0, 20, 1, 0, 0, 0)',
                    '    say "off"',
                    "    say mesh_culled()",
                    "    say mesh_drawn()",
                    "  end",
                    "  if var(frame) = 30",
                    '    say "done"',
                    "    stop",
                    "  end",
                    "end",
                    "",
                )
            )
            result, _ = build(root, source_text)
            if result.returncode != 0:
                if "No C compiler found" in result.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(result.stderr)
            completed = subprocess.run(
                [str(root / "model.exe")],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            out = completed.stdout
            lines = [line for line in out.replace(chr(13) + chr(10), chr(10)).splitlines() if line]
            self.assertEqual(
                lines,
                ["behind", "1", "0", "front", "0", "1", "off", "0", "1", "done"],
            )


if __name__ == "__main__":
    unittest.main()
