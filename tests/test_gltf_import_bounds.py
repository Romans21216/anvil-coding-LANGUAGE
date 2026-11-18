"""glTF import bounds: optional skin data, bad indices and clock slots.

These pin the fixes for the skin/morph import audit. A conforming skin may omit
`inverseBindMatrices`; the importer used to raise a raw KeyError on it. A
negative mesh index is not a Python from-end index, a skinned primitive with
morph targets cannot be posed, and a posed model past the runtime's 32 clock
slots would silently read clock 0 forever.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import struct
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_gltf_animation import pose_program, run_poses, tempfile_dir  # noqa: E402
from test_gltf_model import write_glb  # noqa: E402
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
    def test_nodes_without_scenes_walk_only_parentless_roots(self) -> None:
        from compiler import gltf

        with tempfile_dir() as root:
            write_static_model(root, "hierarchy.gltf")
            path = root / "hierarchy.gltf"
            document = json.loads(path.read_text(encoding="utf-8"))
            document.pop("scenes")
            document.pop("scene")
            document["nodes"] = [
                {"translation": [3, 0, 0], "children": [1]},
                {"mesh": 0, "translation": [2, 0, 0]},
            ]
            path.write_text(json.dumps(document), encoding="utf-8")
            gltf.reset()
            gltf.set_asset_root(root)
            triangles = gltf.load_triangles(path)
            gltf.reset()
        self.assertEqual(len(triangles), 12)
        self.assertEqual(min(triangles[0::12]), 5.0)

    def test_model_and_buffer_paths_cannot_escape_project_root(self) -> None:
        with tempfile_dir() as parent:
            project = parent / "project"
            outside_dir = parent / "outside_dir"
            project.mkdir()
            outside_dir.mkdir()
            write_static_model(parent, "outside.gltf")
            write_static_model(outside_dir, "outside.gltf")
            model_escape = build(project, draw_program(["../outside.gltf"]))
            self.assertNotEqual(model_escape.returncode, 0)
            self.assertIn("inside the project folder", model_escape.stdout + model_escape.stderr)
            absolute_escape = build(
                project,
                draw_program([str(parent / "outside.gltf").replace("\\", "/")]),
            )
            self.assertNotEqual(absolute_escape.returncode, 0)
            self.assertIn("inside the project folder", absolute_escape.stdout + absolute_escape.stderr)

            models = project / "models"
            models.mkdir()
            write_static_model(models, "inside.gltf")
            allowed = build(project, draw_program(["models/inside.gltf"]))
            self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)

            try:
                os.symlink(parent / "outside.gltf", project / "escape.gltf")
            except (OSError, NotImplementedError):
                if os.name == "nt":
                    junction = project / "escape_dir"
                    linked = subprocess.run(
                        ["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside_dir)],
                        capture_output=True,
                        text=True,
                    )
                    if linked.returncode == 0:
                        symlink_escape = build(
                            project, draw_program(["escape_dir/outside.gltf"])
                        )
                        self.assertNotEqual(symlink_escape.returncode, 0)
                        self.assertIn(
                            "inside the project folder",
                            symlink_escape.stdout + symlink_escape.stderr,
                        )
            else:
                symlink_escape = build(project, draw_program(["escape.gltf"]))
                self.assertNotEqual(symlink_escape.returncode, 0)
                self.assertIn("inside the project folder", symlink_escape.stdout + symlink_escape.stderr)

            write_static_model(project, "mesh.gltf")
            model = project / "mesh.gltf"
            document = json.loads(model.read_text(encoding="utf-8"))
            document["buffers"][0]["uri"] = "../outside.bin"
            model.write_text(json.dumps(document), encoding="utf-8")
            buffer_escape = build(project, draw_program(["mesh.gltf"]))
            self.assertNotEqual(buffer_escape.returncode, 0)
            self.assertIn("inside the project folder", buffer_escape.stdout + buffer_escape.stderr)
            document["buffers"][0]["uri"] = "%2e%2e/outside.bin"
            model.write_text(json.dumps(document), encoding="utf-8")
            encoded_escape = build(project, draw_program(["mesh.gltf"]))
            self.assertNotEqual(encoded_escape.returncode, 0)
            self.assertIn("inside the project folder", encoded_escape.stdout + encoded_escape.stderr)

    def test_malformed_buffer_uri_is_a_located_model_error(self) -> None:
        with tempfile_dir() as root:
            write_static_model(root, "mesh.gltf")
            model = root / "mesh.gltf"
            document = json.loads(model.read_text(encoding="utf-8"))
            document["buffers"][0]["uri"] = 7
            model.write_text(json.dumps(document), encoding="utf-8")
            result = build(root, draw_program(["mesh.gltf"]))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("uri must be a string", combined)
        self.assertIn("bounds.ANVL:5:", combined)
        self.assertNotIn("Traceback", combined)

    def test_index_accessors_require_unsigned_integer_scalar_data(self) -> None:
        for component, normalized, diagnostic in (
            (5126, False, "unsigned byte, short or int"),
            (5122, False, "unsigned byte, short or int"),
            (5123, True, "cannot be normalized"),
        ):
            with self.subTest(component=component, normalized=normalized), tempfile_dir() as root:
                write_static_model(root, "mesh.gltf")
                model = root / "mesh.gltf"
                document = json.loads(model.read_text(encoding="utf-8"))
                accessor = document["accessors"][1]
                accessor["componentType"] = component
                if normalized:
                    accessor["normalized"] = True
                model.write_text(json.dumps(document), encoding="utf-8")
                result = build(root, draw_program(["mesh.gltf"]))
                combined = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(diagnostic, combined)
                self.assertIn("bounds.ANVL:5:", combined)

    def test_triangle_budget_is_checked_before_index_accessor_expansion(self) -> None:
        from compiler import gltf

        doc = {
            "accessors": [{"type": "SCALAR", "componentType": 5123,
                           "count": (gltf.MAX_TRIANGLES + 1) * 3}],
        }
        with self.assertRaisesRegex(gltf.ModelError, "triangle budget"):
            gltf._primitive(
                doc,
                {"attributes": {"POSITION": 0}, "indices": 0},
                gltf._identity(), pathlib.Path("."),
            )

    def test_triangle_budget_accepts_exact_limit_and_locates_over_limit(self) -> None:
        from compiler import gltf

        exact_count = gltf.MAX_TRIANGLES * 3
        document = {
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
            "accessors": [{"count": exact_count}],
        }
        with mock.patch.object(
            gltf, "_primitive", return_value=[0.0] * (gltf.MAX_TRIANGLES * 12)
        ):
            triangles, _ = gltf._static_walk(document, None, pathlib.Path("."))
        self.assertEqual(len(triangles) // 12, gltf.MAX_TRIANGLES)

        with tempfile_dir() as root:
            write_static_model(root, "over.gltf")
            path = root / "over.gltf"
            over = json.loads(path.read_text(encoding="utf-8"))
            over["accessors"][1]["count"] = (gltf.MAX_TRIANGLES + 1) * 3
            path.write_text(json.dumps(over), encoding="utf-8")
            result = build(root, draw_program(["over.gltf"]))
        self.assertNotEqual(result.returncode, 0)
        combined = result.stdout + result.stderr
        self.assertIn("triangle budget", combined)
        self.assertIn("bounds.ANVL:5:", combined)
        self.assertNotIn("Traceback", combined)

    def test_model_container_and_external_buffer_are_read_once_per_import(self) -> None:
        from compiler import gltf

        with tempfile_dir() as root:
            write_static_model(root, "cached.gltf")
            model = (root / "cached.gltf").resolve()
            buffer = (root / "cached.gltf.bin").resolve()
            original = pathlib.Path.read_bytes
            reads: dict[pathlib.Path, int] = {}

            def counted_read(path: pathlib.Path) -> bytes:
                resolved = path.resolve()
                reads[resolved] = reads.get(resolved, 0) + 1
                return original(path)

            gltf.reset()
            gltf.set_asset_root(root)
            try:
                with mock.patch.object(pathlib.Path, "read_bytes", counted_read):
                    gltf.ensure_model("cached.gltf", root / "main.ANVL")
            finally:
                gltf.reset()
        self.assertEqual(reads.get(model), 1)
        self.assertEqual(reads.get(buffer), 1)

    def test_container_and_buffer_size_limits_reject_before_reading(self) -> None:
        from compiler import gltf

        with tempfile_dir() as root:
            model = root / "large.gltf"
            buffer = root / "large.bin"
            model.write_bytes(b"{}")
            buffer.write_bytes(b"")
            original_stat = pathlib.Path.stat

            def oversized_stat(path: pathlib.Path, *args, **kwargs):
                if path.resolve() in {model.resolve(), buffer.resolve()}:
                    return SimpleNamespace(st_size=(
                        gltf.MAX_CONTAINER_BYTES + 1
                        if path.resolve() == model.resolve()
                        else gltf.MAX_BUFFER_BYTES + 1
                    ))
                return original_stat(path, *args, **kwargs)

            gltf.reset()
            gltf.set_asset_root(root)
            try:
                with mock.patch.object(pathlib.Path, "stat", oversized_stat), \
                     mock.patch.object(pathlib.Path, "read_bytes", side_effect=AssertionError("must not read")):
                    with self.assertRaisesRegex(gltf.ModelError, "model import limit"):
                        gltf._container(model)
                    with self.assertRaisesRegex(gltf.ModelError, "buffer exceeds"):
                        gltf._buffer_bytes(
                            {"buffers": [{"uri": "large.bin", "byteLength": 1}]},
                            0,
                            root,
                        )
                    accessor_document = {
                        "buffers": [{"uri": "large.bin", "byteLength": 4}],
                        "bufferViews": [{"buffer": 0, "byteLength": 4}],
                        "accessors": [{
                            "bufferView": 0, "componentType": 5126,
                            "count": gltf.MAX_TRIANGLES * 3 + 3, "type": "VEC3",
                        }],
                    }
                    with self.assertRaisesRegex(gltf.ModelError, "element import limit"):
                        gltf._accessor(accessor_document, 0, root)
            finally:
                gltf.reset()

    def test_model_path_resolution_failures_use_model_error_contract(self) -> None:
        from compiler import gltf

        with tempfile_dir() as root:
            gltf.reset()
            gltf.set_asset_root(root)
            original_resolve = pathlib.Path.resolve

            def broken_resolve(path: pathlib.Path, *args, **kwargs):
                if path.name == "loop.gltf":
                    raise RuntimeError("symlink loop")
                return original_resolve(path, *args, **kwargs)

            try:
                with mock.patch.object(pathlib.Path, "resolve", broken_resolve):
                    with self.assertRaisesRegex(gltf.ModelError, "cannot resolve model path"):
                        gltf._resolve("loop.gltf", root / "main.ANVL")
            finally:
                gltf.reset()

    def test_data_buffer_uri_scheme_and_base64_marker_are_case_insensitive(self) -> None:
        from compiler import gltf

        payload = b"glb-binary-payload"
        encoded = base64.b64encode(payload).decode("ascii")
        document = {
            "buffers": [{
                "uri": f"DATA:application/octet-stream;BASE64,{encoded}",
                "byteLength": len(payload),
            }],
        }
        self.assertEqual(gltf._buffer_bytes(document, 0, pathlib.Path(".")), payload)

    def test_manifest_nested_entry_resolves_glb_assets_from_project_root(self) -> None:
        with tempfile_dir() as root:
            (root / "src").mkdir()
            models = root / "models"
            models.mkdir()
            write_glb(models, "mesh.glb", (1.0, 0.0, 0.0))
            (root / "src" / "main.ANVL").write_text(
                draw_program(["models/mesh.glb"]), encoding="utf-8"
            )
            manifest = root / "game.ANVLproj"
            manifest.write_text('entry = "src/main.ANVL"\n', encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(COMPILER), str(manifest),
                    "--backend", "wasm", "--check",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("main.ANVL: ok", result.stdout)

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

    def test_accessor_ranges_stay_inside_declared_parent_views_and_buffers(self) -> None:
        cases = (
            ("adjacent_view", lambda doc: doc["bufferViews"][0].update(byteLength=32), "declared bufferView"),
            ("short_declared_buffer", lambda doc: doc["buffers"][0].update(byteLength=41), "declared buffer"),
            ("misaligned_offset", lambda doc: doc["accessors"][0].update(byteOffset=2), "aligned"),
            ("short_stride", lambda doc: doc["bufferViews"][0].update(byteStride=8), "byteStride"),
            ("empty_count", lambda doc: doc["accessors"][0].update(count=0), "count"),
            ("stride_not_multiple_of_four", lambda doc: doc["bufferViews"][0].update(byteStride=6), "byteStride"),
            ("stride_larger_than_view", lambda doc: doc["bufferViews"][0].update(byteStride=40), "byteStride"),
            ("stride_on_indices", lambda doc: doc["bufferViews"][1].update(byteStride=4), "only valid for vertex attribute"),
            ("normalized_not_boolean", lambda doc: doc["accessors"][0].update(normalized="false"), "normalized value must be a boolean"),
            ("normalized_float", lambda doc: doc["accessors"][0].update(normalized=True), "only valid for BYTE"),
            ("normalized_unsigned_int", lambda doc: doc["accessors"][1].update(componentType=5125, count=1, normalized=True), "only valid for BYTE"),
        )
        for name, mutate, diagnostic in cases:
            with self.subTest(name=name), tempfile_dir() as root:
                write_static_model(root, "mesh.gltf")
                model_path = root / "mesh.gltf"
                document = json.loads(model_path.read_text(encoding="utf-8"))
                mutate(document)
                model_path.write_text(json.dumps(document), encoding="utf-8")
                result = build(root, draw_program(["mesh.gltf"]))
                combined = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, name)
                self.assertIn(diagnostic, combined, name)
                self.assertIn("bounds.ANVL:5:", combined, name)
                self.assertFalse((root / "bounds.exe").exists(), name)

    def test_malformed_nested_documents_are_located_compile_errors(self) -> None:
        cases = (
            ("wrong_scenes_type", lambda doc: doc.update(scenes={}), "glTF scenes must be an array"),
            ("scene_out_of_range", lambda doc: doc.update(scene=9), "scene index is out of range"),
            ("mesh_out_of_range", lambda doc: doc["nodes"][0].update(mesh=9), "mesh index is out of range"),
            ("primitive_wrong_type", lambda doc: doc["meshes"][0].update(primitives="bad"), "primitives must be an array"),
            ("accessor_view_out_of_range", lambda doc: doc["accessors"][0].update(bufferView=9), "invalid bufferView"),
            ("node_transform_wrong_type", lambda doc: doc["nodes"][0].update(translation=[{}, 0, 0]), "malformed glTF structure"),
            ("root_wrong_type", lambda doc: None, "root must be a JSON object"),
        )
        for name, mutate, diagnostic in cases:
            with self.subTest(name=name), tempfile_dir() as root:
                write_static_model(root, "mesh.gltf")
                model_path = root / "mesh.gltf"
                if name == "root_wrong_type":
                    model_path.write_text("[]", encoding="utf-8")
                else:
                    document = json.loads(model_path.read_text(encoding="utf-8"))
                    mutate(document)
                    model_path.write_text(json.dumps(document), encoding="utf-8")
                result = build(root, draw_program(["mesh.gltf"]))
                combined = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0, name)
                self.assertIn(diagnostic, combined, name)
                self.assertIn("bounds.ANVL:5:", combined, name)
                self.assertNotIn("Traceback", combined, name)
                self.assertFalse((root / "bounds.exe").exists(), name)

    def test_normalized_joint_indices_are_rejected_at_the_model_call(self) -> None:
        with tempfile_dir() as root:
            write_skinned_model(root, "skin.gltf")
            model_path = root / "skin.gltf"
            document = json.loads(model_path.read_text(encoding="utf-8"))
            document["accessors"][2]["normalized"] = True
            model_path.write_text(json.dumps(document), encoding="utf-8")
            result = build(root, draw_program(["skin.gltf"]))
            combined = result.stdout + result.stderr
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("JOINTS_0 accessors cannot be normalized", combined)
            self.assertIn("bounds.ANVL:5:", combined)
            self.assertFalse((root / "bounds.exe").exists())

    def test_malformed_animation_and_skin_structures_raise_model_errors(self) -> None:
        from compiler import gltf
        from test_gltf_animation import write_model

        with tempfile_dir() as root:
            write_model(root, "animation.gltf")
            document = json.loads((root / "animation.gltf").read_text(encoding="utf-8"))
            document["animations"][0]["samplers"] = [None]
            (root / "animation.gltf").write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(gltf.ModelError, "sampler must be an object"):
                gltf.load_animated(root / "animation.gltf")

            write_skinned_model(root, "skin.gltf")
            document = json.loads((root / "skin.gltf").read_text(encoding="utf-8"))
            document["skins"][0]["joints"] = [99]
            (root / "skin.gltf").write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(gltf.ModelError, "skin joint is not a node"):
                gltf.load_skinned(root / "skin.gltf")


if __name__ == "__main__":
    unittest.main()
