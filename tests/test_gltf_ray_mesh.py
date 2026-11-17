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
from test_gltf_morph import write_morph_glb, write_morph_model  # noqa: E402
from compiler import gltf  # noqa: E402


def write_animated_morph_glb(
    root: pathlib.Path,
    node_weights: tuple[float, float] | None = None,
    duplicate_primitive: bool = False,
) -> pathlib.Path:
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
        "scenes": [{"nodes": [0] if node_weights is None else [0, 1]}],
        "nodes": ([{"mesh": 0}] if node_weights is None else [
            {"mesh": 0, "weights": [node_weights[0]]},
            {"mesh": 0, "weights": [node_weights[1]]},
        ]),
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
    if duplicate_primitive:
        document["meshes"][0]["primitives"].append(
            json.loads(json.dumps(document["meshes"][0]["primitives"][0]))
        )
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

    def test_static_ray_mesh_keeps_per_group_defaults(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            base = root / "base.gltf"
            write_morph_model(root, base.name, defaults=(0.0,))
            document = json.loads(base.read_text(encoding="utf-8"))
            second_mesh = json.loads(json.dumps(document["meshes"][0]))
            second_mesh["weights"] = [1.0]
            document["meshes"].append(second_mesh)
            document["nodes"] = [
                {"mesh": 0, "translation": [-3, 0, 0]},
                {"mesh": 1, "translation": [3, 0, 0]},
            ]
            document["scenes"][0]["nodes"] = [0, 1]
            model = write_morph_glb(root, "per-mesh.glb", document)
            per_group = rendered_bounds(
                build_ray_program(
                    root,
                    [f'set var(ok) = ray_mesh("{model.name}", 0, 0, -1, 1, 0, 0, 0)'],
                    "static_per_group",
                )
            )

            second_mesh["weights"] = [0.0]
            document["meshes"][1] = second_mesh
            baseline_model = write_morph_glb(root, "same-default.glb", document)
            baseline = rendered_bounds(
                build_ray_program(
                    root,
                    [f'set var(ok) = ray_mesh("{baseline_model.name}", 0, 0, -1, 1, 0, 0, 0)'],
                    "static_same_default",
                )
            )
        self.assertGreater(
            (per_group[2] - per_group[0]) - (baseline[2] - baseline[0]),
            40,
            (per_group, baseline),
        )

    def test_grouped_ray_mesh_capacity_failure_does_not_consume_last_slot(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_morph_model(root, "single.gltf", defaults=(0.0,))
            base = root / "single.gltf"
            document = json.loads(base.read_text(encoding="utf-8"))
            second_mesh = json.loads(json.dumps(document["meshes"][0]))
            second_mesh["weights"] = [1.0]
            document["meshes"].append(second_mesh)
            document["nodes"] = [{"mesh": 0}, {"mesh": 1}]
            document["scenes"][0]["nodes"] = [0, 1]
            grouped = write_morph_glb(root, "grouped.glb", document)

            statements = [
                'set var(fill) = ray_mesh("single.gltf", 0, 0, -1, 1, 0, 0, 0)'
                for _ in range(39)
            ]
            # The two-group registration is intentionally offscreen. With one
            # queue slot left it must fail atomically, leaving that slot for the
            # visible single-group mesh submitted afterward.
            statements.append(
                f'set var(failed) = ray_mesh("{grouped.name}", 100, 0, -1, 1, 0, 0, 0)'
            )
            statements.append(
                'set var(visible) = ray_mesh("single.gltf", 0, 0, -1, 1, 0, 0, 0)'
            )
            bounds = rendered_bounds(
                build_ray_program(root, statements, "grouped_capacity_atomic")
            )
        self.assertGreater(bounds[2] - bounds[0], 20, bounds)

    def test_animated_ray_mesh_keeps_node_level_default_weights(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            asset = write_animated_morph_glb(
                root, (0.0, 1.0), duplicate_primitive=True
            )
            baked = gltf.load_animated(asset)
            self.assertEqual(len(baked["groups"]) // 3, 2)
            self.assertEqual(baked["morph_defaults"], [0.0, 1.0])
            self.assertEqual([baked["groups"][i + 2] for i in (0, 3)], [2, 2])
            per_node = rendered_bounds(
                build_ray_program(
                    root,
                    [
                        'set var(t) = model_animate("animated_morph.glb", 0)',
                        'set var(ok) = ray_mesh("animated_morph.glb", -4, 0, -1, 1, 0, 0, 0)',
                    ],
                    "animated_per_node_default",
                )
            )
            write_animated_morph_glb(root, (0.0, 0.0))
            baseline = rendered_bounds(
                build_ray_program(
                    root,
                    [
                        'set var(t) = model_animate("animated_morph.glb", 0)',
                        'set var(ok) = ray_mesh("animated_morph.glb", -4, 0, -1, 1, 0, 0, 0)',
                    ],
                    "animated_same_node_default",
                )
            )
        self.assertGreater(
            (per_node[2] - per_node[0]) - (baseline[2] - baseline[0]),
            20,
            (per_node, baseline),
        )

    def test_animated_morph_model_draw_supports_all_pose_controls(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_animated_morph_glb(
                root, (0.0, 1.0), duplicate_primitive=True
            )

            def draw(time_value: float, weight: float | None, name: str):
                statements = [
                    f'set var(t) = model_animate("animated_morph.glb", {time_value})'
                ]
                if weight is not None:
                    statements.append(
                        f'set var(w) = model_morph("animated_morph.glb", 0, {weight})'
                    )
                statements.append(
                    'set var(ok) = model_draw("animated_morph.glb", -4, 0, -1, 3, 0, 0, 0)'
                )
                return rendered_bounds(build_ray_program(root, statements, name))

            rest = draw(0, None, "model_draw_rest")
            animated = draw(0.5, None, "model_draw_animated")
            morphed = draw(0, 1, "model_draw_morphed")
            combined = draw(0.5, 1, "model_draw_combined")

        rest_width = rest[2] - rest[0]
        morph_width = morphed[2] - morphed[0]
        combined_width = combined[2] - combined[0]
        self.assertGreater(animated[0], rest[0], (rest, animated))
        self.assertGreater(rest_width - morph_width, 40, (rest, morphed))
        self.assertGreater(combined[2], morphed[2], (morphed, combined))
        self.assertGreater(combined_width - morph_width, 20, (morphed, combined))

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
