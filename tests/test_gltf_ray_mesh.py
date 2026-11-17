"""Animated and morphed glTF meshes in the deferred ray renderer."""

from __future__ import annotations

import json
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_sprite_draw import WindowReader  # noqa: E402


def write_animated_morph_glb(root: pathlib.Path) -> pathlib.Path:
    """Write one triangle with a node translation track and an X morph delta."""
    blob = bytearray()
    views: list[dict[str, int]] = []

    def add(payload: bytes) -> int:
        while len(blob) % 4:
            blob.append(0)
        index = len(views)
        views.append(
            {"buffer": 0, "byteOffset": len(blob), "byteLength": len(payload)}
        )
        blob.extend(payload)
        return index

    position_view = add(struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0))
    index_view = add(struct.pack("<3H", 0, 1, 2))
    morph_view = add(struct.pack("<9f", 2, 0, 0, 2, 0, 0, 2, 0, 0))
    time_view = add(struct.pack("<2f", 0, 1))
    translation_view = add(struct.pack("<6f", 0, 0, 0, 2, 0, 0))
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "weights": [0.0],
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "targets": [{"POSITION": 2}],
                    }
                ],
            }
        ],
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": position_view, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": index_view, "componentType": 5123, "count": 3, "type": "SCALAR"},
            {"bufferView": morph_view, "componentType": 5126, "count": 3, "type": "VEC3"},
            {
                "bufferView": time_view,
                "componentType": 5126,
                "count": 2,
                "type": "SCALAR",
                "min": [0],
                "max": [1],
            },
            {"bufferView": translation_view, "componentType": 5126, "count": 2, "type": "VEC3"},
        ],
        "animations": [
            {
                "channels": [
                    {"sampler": 0, "target": {"node": 0, "path": "translation"}}
                ],
                "samplers": [
                    {"input": 3, "output": 4, "interpolation": "LINEAR"}
                ],
            }
        ],
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    while len(blob) % 4:
        blob.append(0)
    total_length = 12 + 8 + len(json_chunk) + 8 + len(blob)
    data = bytearray(b"glTF" + struct.pack("<II", 2, total_length))
    data.extend(struct.pack("<II", len(json_chunk), 0x4E4F534A))
    data.extend(json_chunk)
    data.extend(struct.pack("<II", len(blob), 0x004E4942))
    data.extend(blob)
    path = root / "animated_morph.glb"
    path.write_bytes(data)
    return path


def build_ray_program(root: pathlib.Path, statements: list[str], name: str) -> pathlib.Path:
    source = root / f"{name}.ANVL"
    source.write_text(
        "scene 3d\n"
        "camera perspective 0 0 12\n"
        "camera fov(70)\n"
        "clear rgba(0, 0, 0, 255)\n"
        "fn(draw)\n"
        + "\n".join(f"  {line}" for line in statements)
        + "\nend\n",
        encoding="utf-8",
    )
    executable = root / f"{name}.exe"
    result = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode:
        if "No C compiler found" in result.stderr:
            raise unittest.SkipTest("MSVC is not available")
        raise AssertionError(result.stdout + result.stderr)
    return executable


def rendered_bounds(executable: pathlib.Path) -> tuple[int, int, int, int]:
    process = subprocess.Popen([str(executable)], stdout=subprocess.DEVNULL)
    try:
        reader = WindowReader(process.pid)
        if reader.find(time.monotonic() + 10) is None:
            raise AssertionError("ray mesh window did not open")
        reader.force_client_size(960, 600)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            bounds = reader.bounding_box(0, 0, 960, 600)
            if bounds is not None:
                return bounds
            time.sleep(0.05)
        raise AssertionError("ray mesh produced no visible pixels")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def pose_statements(asset: str, animation_time: float, morph_weight: float) -> list[str]:
    return [
        f'set var(t) = model_animate("{asset}", {animation_time})',
        f'set var(w) = model_morph("{asset}", 0, {morph_weight})',
        f'set var(ok) = ray_mesh("{asset}", -4, 0, -1, 1, 0, 0, 0)',
    ]


@unittest.skipUnless(sys.platform == "win32", "ray-mesh pixel checks use Win32")
class AnimatedRayMeshTests(unittest.TestCase):
    def test_static_ray_mesh_and_static_morph_render_visible_pixels(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            shutil.copy2(ROOT / "examples" / "ray_mesh.glb", root / "static.glb")
            shutil.copy2(
                ROOT / "examples" / "ray_mesh_morph.glb", root / "morph.glb"
            )
            static = rendered_bounds(
                build_ray_program(
                    root,
                    ['set var(ok) = ray_mesh("static.glb", 0, 0, -1, 3, 0, 0, 0)'],
                    "static_mesh",
                )
            )
            morphed = rendered_bounds(
                build_ray_program(
                    root,
                    [
                        'set var(w) = model_morph("morph.glb", 0, 1)',
                        'set var(ok) = ray_mesh("morph.glb", 0, 0, -1, 3, 0, 0, 0)',
                    ],
                    "static_morph",
                )
            )
        for bounds in (static, morphed):
            self.assertGreater(bounds[2] - bounds[0], 20, bounds)
            self.assertGreater(bounds[3] - bounds[1], 20, bounds)

    def test_node_animation_and_morph_each_change_ray_mesh_pixels(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_animated_morph_glb(root)
            rest = rendered_bounds(
                build_ray_program(root, pose_statements("animated_morph.glb", 0, 0), "rest")
            )
            animated = rendered_bounds(
                build_ray_program(root, pose_statements("animated_morph.glb", 0.5, 0), "animated")
            )
            morphed = rendered_bounds(
                build_ray_program(root, pose_statements("animated_morph.glb", 0, 1), "morphed")
            )
        self.assertGreater(animated[0] - rest[0], 20, (rest, animated))
        self.assertGreater(morphed[0] - rest[0], 40, (rest, morphed))

    def test_same_asset_pose_is_snapshotted_per_queued_instance(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_animated_morph_glb(root)
            single = rendered_bounds(
                build_ray_program(
                    root,
                    pose_statements("animated_morph.glb", 0.5, 0),
                    "single_pose",
                )
            )
            both_statements = pose_statements("animated_morph.glb", 0, 0)[:2]
            both_statements.append(
                'set var(a) = ray_mesh("animated_morph.glb", -4, 0, -1, 1, 0, 0, 0)'
            )
            both_statements.extend(
                [
                    'set var(t) = model_animate("animated_morph.glb", 0.5)',
                    'set var(b) = ray_mesh("animated_morph.glb", -4, 0, -1, 1, 0, 0, 0)',
                ]
            )
            both = rendered_bounds(
                build_ray_program(root, both_statements, "two_poses")
            )
        single_width = single[2] - single[0]
        both_width = both[2] - both[0]
        self.assertGreater(both_width, single_width + 20, (single, both))


if __name__ == "__main__":
    unittest.main()
