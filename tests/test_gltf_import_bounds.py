"""glTF import bounds: optional skin data, bad indices and clock slots.

These pin the fixes for the skin/morph import audit. A conforming skin may omit
`inverseBindMatrices`; the importer used to raise a raw KeyError on it. A
negative mesh index is not a Python from-end index, a skinned primitive with
morph targets cannot be posed, and a posed model past the runtime's 32 clock
slots would silently read clock 0 forever.
"""

from __future__ import annotations

import json
import pathlib
import re
import struct
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_gltf_animation import pose_program, run_poses, tempfile_dir  # noqa: E402
from test_gltf_morph import write_morph_model  # noqa: E402
from test_gltf_skins import write_skinned_model  # noqa: E402


def write_static_model(root: pathlib.Path, name: str) -> None:
    """A one-triangle static model with no skin, clip or morph targets."""
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    blob = positions + indices
    (root / (name + ".bin")).write_bytes(blob)
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "buffers": [{"uri": name + ".bin", "byteLength": len(blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 6},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [0, 0, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
    }
    (root / name).write_text(json.dumps(document, indent=1), encoding="utf-8")


def build(root: pathlib.Path, source_text: str) -> subprocess.CompletedProcess:
    source = root / "bounds.ANVL"
    source.write_text(source_text, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(root / "bounds.exe")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0 and "No C compiler found" in result.stderr:
        raise unittest.SkipTest("MSVC is not available")
    return result


def draw_program(models: list[str]) -> str:
    lines = ["scene 3d", "", "fn(draw)", "  clear rgba(0, 0, 0, 255)"]
    for index, model in enumerate(models):
        lines.append(
            f'  set var(m{index}) = model_draw("{model}", 0, 0, 0, 1, 0, 0, 0)'
        )
    lines.extend(["end", ""])
    return "\n".join(lines)


class GltfImportBoundsTests(unittest.TestCase):
    def test_a_skin_without_inverse_bind_matrices_binds_identity(self) -> None:
        # Khronos marks inverseBindMatrices optional. Without it every joint
        # binds in mesh space, so a joint that moves must still carry the mesh.
        with tempfile_dir() as root:
            write_skinned_model(root, "nobind.gltf")
            document = json.loads((root / "nobind.gltf").read_text(encoding="utf-8"))
            del document["skins"][0]["inverseBindMatrices"]
            (root / "nobind.gltf").write_text(json.dumps(document), encoding="utf-8")
            out = run_poses(self, root, pose_program("nobind.gltf", [0.0, 0.5]))
        boxes = [line for line in out if line.startswith("box ")]
        self.assertEqual(len(boxes), 2, out)
        rest = [int(v) for v in boxes[0][4:].split(",")]
        moved = [int(v) for v in boxes[1][4:].split(",")]
        self.assertGreater(moved[0] - rest[0], 40)

    def test_a_mirrored_ancestor_matrix_is_refused(self) -> None:
        # Matrix-to-TRS decomposition takes a positive scale per column, so a
        # mirrored matrix would lose its reflection and pose a different shape.
        # The importer refuses it instead of silently changing the geometry.
        from test_gltf_animation import write_model

        with tempfile_dir() as root:
            write_model(root, "mirror.gltf")
            document = json.loads((root / "mirror.gltf").read_text(encoding="utf-8"))
            document["nodes"] = [
                {
                    "matrix": [-1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
                    "children": [1],
                },
                {"mesh": 0},
            ]
            document["scenes"] = [{"nodes": [0]}]
            document["animations"][0]["channels"][0]["target"]["node"] = 1
            (root / "mirror.gltf").write_text(json.dumps(document), encoding="utf-8")
            result = build(root, draw_program(["mirror.gltf"]))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("mirrors an axis", combined)

    def test_a_negative_mesh_index_is_refused(self) -> None:
        with tempfile_dir() as root:
            write_static_model(root, "neg.gltf")
            document = json.loads((root / "neg.gltf").read_text(encoding="utf-8"))
            document["nodes"][0]["mesh"] = -1
            (root / "neg.gltf").write_text(json.dumps(document), encoding="utf-8")
            result = build(root, draw_program(["neg.gltf"]))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("a mesh index is out of range", combined)

    def test_a_skinned_mesh_with_morph_targets_is_refused(self) -> None:
        with tempfile_dir() as root:
            write_skinned_model(root, "combined.gltf")
            document = json.loads((root / "combined.gltf").read_text(encoding="utf-8"))
            document["meshes"][0]["primitives"][0]["targets"] = [{"POSITION": 0}]
            (root / "combined.gltf").write_text(json.dumps(document), encoding="utf-8")
            result = build(root, draw_program(["combined.gltf"]))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("morph targets is not supported", combined)

    def test_the_importer_matches_the_runtime_clock_slots(self) -> None:
        # The importer mirrors a runtime table size. If the runtime grows the
        # table and the importer does not, models are refused for no reason.
        from compiler import gltf

        runtime = (ROOT / "runtime" / "anvil_runtime.c").read_text(encoding="utf-8")
        match = re.search(r"#define ANVIL_MODEL_STATES (\d+)", runtime)
        self.assertIsNotNone(match, "ANVIL_MODEL_STATES moved out of anvil_runtime.c")
        self.assertEqual(int(match.group(1)), gltf.MODEL_STATES)

    def test_static_models_past_the_clock_slots_still_build(self) -> None:
        # Static models never touch a clip clock, so a project may register
        # more than MODEL_STATES of them.
        with tempfile_dir() as root:
            names = []
            for index in range(33):
                name = f"s{index}.gltf"
                write_static_model(root, name)
                names.append(name)
            result = build(root, draw_program(names))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_posed_model_past_the_clock_slots_is_refused(self) -> None:
        with tempfile_dir() as root:
            names = []
            for index in range(32):
                name = f"s{index}.gltf"
                write_static_model(root, name)
                names.append(name)
            write_skinned_model(root, "posed.gltf")
            names.append("posed.gltf")
            result = build(root, draw_program(names))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("clock slot 32", combined)
        self.assertIn("bounds.ANVL:", combined)

    def test_a_morphing_model_past_the_runtime_state_slots_is_refused(self) -> None:
        with tempfile_dir() as root:
            names = []
            for index in range(32):
                name = f"s{index}.gltf"
                write_static_model(root, name)
                names.append(name)
            write_morph_model(root, "morphed.gltf")
            names.append("morphed.gltf")
            result = build(root, draw_program(names))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("runtime state slot 32", combined)
        self.assertIn("bounds.ANVL:", combined)


if __name__ == "__main__":
    unittest.main()
