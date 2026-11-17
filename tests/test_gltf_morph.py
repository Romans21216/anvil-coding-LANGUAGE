"""glTF morph targets: per-vertex deltas blended by weight (8.13).

A static model with `targets` keeps one delta vector per vertex per target; the
runtime adds the weighted deltas before placing and shading the triangle. These
tests measure the drawn ink, so a wrong delta stride, an unapplied default
weight or an unclamped weight all show up as the mesh sitting in the wrong
place.
"""

from __future__ import annotations

import json
import math
import pathlib
import struct
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_gltf_animation import run_poses, tempfile_dir  # noqa: E402
from compiler import gltf  # noqa: E402


def write_morph_model(root: pathlib.Path, name: str, *, defaults: tuple[float, ...] = (0.0,)) -> None:
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    deltas = struct.pack("<9f", 2, 0, 0, 2, 0, 0, 2, 0, 0)
    blob = b""
    views = []
    for payload in (positions, indices, deltas):
        if payload is deltas and len(blob) % 4:
            blob += b"\0" * (-len(blob) % 4)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(payload)})
        blob += payload
    (root / "morph.bin").write_bytes(blob)
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "weights": list(defaults),
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "material": 0,
                        "targets": [{"POSITION": 2}],
                    }
                ],
            }
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "buffers": [{"uri": "morph.bin", "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [0, 0, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
            {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC3"},
        ],
    }
    (root / name).write_text(json.dumps(document, indent=1), encoding="utf-8")


def write_two_target_morph_model(
    root: pathlib.Path,
    name: str,
    *,
    defaults: tuple[float, float] = (0.0, 0.0),
    group_translations: tuple[tuple[float, float, float], ...] = ((0.0, 0.0, 0.0),),
    target_deltas: tuple[tuple[float, float, float], tuple[float, float, float]] = (
        (-40.0, 0.0, 0.0),
        (0.0, -40.0, 0.0),
    ),
) -> pathlib.Path:
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    delta_payloads = tuple(
        struct.pack("<9f", *(list(delta) * 3)) for delta in target_deltas
    )
    payloads = (positions, indices, *delta_payloads)
    blob = b""
    views = []
    for payload in payloads:
        if payload in delta_payloads and len(blob) % 4:
            blob += b"\0" * (-len(blob) % 4)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(payload)})
        blob += payload
    (root / "two_morph.bin").write_bytes(blob)
    nodes = [{"mesh": 0, "translation": list(value)} for value in group_translations]
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": [
            {
                "weights": list(defaults),
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "material": 0,
                        "targets": [{"POSITION": 2}, {"POSITION": 3}],
                    }
                ],
            }
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "buffers": [{"uri": "two_morph.bin", "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
            {"bufferView": 2, "componentType": 5126, "count": 3, "type": "VEC3"},
            {"bufferView": 3, "componentType": 5126, "count": 3, "type": "VEC3"},
        ],
    }
    path = root / name
    path.write_text(json.dumps(document, indent=1), encoding="utf-8")
    return path


def write_morph_glb(root: pathlib.Path, name: str, document: dict) -> pathlib.Path:
    binary = (root / "morph.bin").read_bytes()
    document = json.loads(json.dumps(document))
    document["buffers"] = [{"byteLength": len(binary)}]
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    binary_chunk = binary + b"\0" * ((-len(binary)) % 4)
    total = 12 + 8 + len(json_chunk) + 8 + len(binary_chunk)
    contents = bytearray(b"glTF" + struct.pack("<II", 2, total))
    contents.extend(struct.pack("<II", len(json_chunk), 0x4E4F534A))
    contents.extend(json_chunk)
    contents.extend(struct.pack("<II", len(binary_chunk), 0x004E4942))
    contents.extend(binary_chunk)
    path = root / name
    path.write_bytes(contents)
    return path


SCAN = [
    "fn(scan)",
    "  set var(cap) = frame_capture()",
    "  set var(minx) = 999",
    "  set var(maxx) = -1",
    "  for local(x) = 0 to 959",
    "    for local(y) = 0 to 599",
    "      set var(v) = image_pixel(var(cap), local(x), local(y)) - 4278190080",
    "      if var(v) > 0",
    "        if local(x) < var(minx)",
    "          set var(minx) = local(x)",
    "        end",
    "        if local(x) > var(maxx)",
    "          set var(maxx) = local(x)",
    "        end",
    "      end",
    "    end",
    "  end",
    '  say "box " & var(minx) & "," & var(maxx)',
    "end",
    "",
]


def weight_program(model: str, weights: list[float]) -> str:
    lines = ["scene 3d", "set var(n) = 0", ""] + SCAN
    lines += ["fn(draw)", "  add var(n) 1", "  clear rgba(0, 0, 0, 255)"]
    frame = 2
    for weight in weights:
        lines.extend(
            [
                f"  if var(n) = {frame}",
                f'    set var(prev) = model_morph("{model}", 0, {weight!r})',
                f'    say "prev " & var(prev)',
                f'    set var(ok) = model_draw("{model}", 0, 0, 0, 1, 0, 0, 0)',
                "    call fn(scan)",
                "  end",
            ]
        )
        frame += 3
    lines.extend([f"  if var(n) = {frame}", '    say "done"', "  end", "end", ""])
    return "\n".join(lines)


def draw_only_program(model: str) -> str:
    lines = ["scene 3d", "set var(n) = 0", ""] + SCAN
    lines += [
        "fn(draw)",
        "  add var(n) 1",
        "  clear rgba(0, 0, 0, 255)",
        "  if var(n) = 2",
        f'    set var(ok) = model_draw("{model}", 0, 0, 0, 1, 0, 0, 0)',
        "    call fn(scan)",
        '    say "done"',
        "  end",
        "end",
        "",
    ]
    return "\n".join(lines)


def run_headless(case: unittest.TestCase, root: pathlib.Path, program: str) -> str:
    source = root / "headless.ANVL"
    source.write_text(program, encoding="utf-8")
    build = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(root / "headless.exe")],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if build.returncode != 0:
        if "No C compiler found" in build.stderr:
            raise unittest.SkipTest("MSVC is not available")
        case.fail(build.stderr)
    run = subprocess.run(
        [str(root / "headless.exe")], cwd=root, capture_output=True, text=True, timeout=60
    )
    case.assertEqual(run.returncode, 0, run.stderr)
    return run.stdout


class GltfMorphTests(unittest.TestCase):
    def test_instance_morph_weights_are_isolated_between_draws(self) -> None:
        with tempfile_dir() as root:
            write_morph_model(root, "instance.gltf")
            program = "\n".join(
                [
                    "scene 3d",
                    "",
                ]
                + [
                    "fn(draw)",
                    "  add var(n) 1",
                    "  if var(n) = 1",
                    '    set var(a) = model_instance("instance.gltf")',
                    '    set var(b) = model_instance("instance.gltf")',
                    "    clear rgba(0, 0, 0, 255)",
                    '    set var(pa) = model_instance_morph("instance.gltf", var(a), 0, 1)',
                    '    set var(pb) = model_instance_morph("instance.gltf", var(b), 0, 0)',
                    '    say "prev_b " & var(pb)',
                    '    set var(db) = model_draw_instance("instance.gltf", var(b), 0, 0, 0, 1, 0, 0, 0)',
                    '    set var(da) = model_draw_instance("instance.gltf", var(a), 0, 0, 0, 1, 0, 0, 0)',
                    '    say "draws " & var(da) & "," & var(db)',
                    '    set var(pa) = model_instance_morph("instance.gltf", var(a), 0, 0)',
                    '    say "prev_a " & var(pa)',
                    '    say "done"',
                    "  end",
                    "end",
                    "",
                ]
            )
            output = run_poses(self, root, program)
        self.assertIn("prev_b 0", output)
        self.assertIn("prev_a 1", output)
        self.assertIn("draws 1,1", output)


    def test_instance_handles_reject_stale_values_after_reuse(self) -> None:
        with tempfile_dir() as root:
            write_morph_model(root, "instance.gltf")
            program = "\n".join(
                [
                    "scene 3d",
                    "",
                    "fn(draw)",
                    '  set var(old) = model_instance("instance.gltf")',
                    '  set var(destroyed) = model_instance_destroy("instance.gltf", var(old))',
                    "  for local(i) = 0 to 69",
                    '    set var(new) = model_instance("instance.gltf")',
                    '    set var(destroyed) = model_instance_destroy("instance.gltf", var(new))',
                    "  end",
                    '  set var(new) = model_instance("instance.gltf")',
                    '  set var(stale) = model_instance_morph("instance.gltf", var(old), 0, 1)',
                    '  set var(live) = model_instance_morph("instance.gltf", var(new), 0, 1)',
                    '  set var(stale_draw) = model_draw_instance("instance.gltf", var(old), 0, 0, 0, 1, 0, 0, 0)',
                    '  set var(live_draw) = model_draw_instance("instance.gltf", var(new), 0, 0, 0, 1, 0, 0, 0)',
                    '  say "state " & var(destroyed) & "," & var(stale) & "," & var(live) & "," & var(stale_draw) & "," & var(live_draw)',
                    '  say "done"',
                    "end",
                    "",
                ]
            )
            output = run_poses(self, root, program)
        self.assertIn("state 1,0,0,0,1", output)

    def test_instance_draw_requires_a_stored_handle(self) -> None:
        with tempfile_dir() as root:
            write_morph_model(root, "instance.gltf")
            source = root / "nested.ANVL"
            source.write_text(
                "scene 3d\n\nfn(draw)\n"
                '  set var(d) = model_draw_instance("instance.gltf", '
                'model_instance("instance.gltf"), 0, 0, 0, 1, 0, 0, 0)\n'
                "end\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(root / "nested.exe")],
                capture_output=True,
                text=True,
                timeout=300,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("store a model instance handle in a variable", result.stderr)

    def test_morph_group_bounds_cover_defaults_and_all_override_combinations(self) -> None:
        with tempfile_dir() as root:
            model = write_two_target_morph_model(
                root, "two-target.gltf", defaults=(-0.5, 1.5)
            )
            baked = gltf.load_morphed(model)
        cx, cy, cz, radius = baked["morph_group_bounds"]
        vertices = baked["vertices"]
        deltas = baked["morph"]
        poses = [(-0.5, 1.5)] + [
            (first, second)
            for first in (0.0, 0.5, 1.0)
            for second in (0.0, 0.5, 1.0)
        ]
        for weight0, weight1 in poses:
            for vertex in range(3):
                start = vertex * 6
                point = tuple(
                    vertices[vertex * 3 + axis]
                    + deltas[start + axis] * weight0
                    + deltas[start + 3 + axis] * weight1
                    for axis in range(3)
                )
                distance = math.sqrt(
                    (point[0] - cx) ** 2
                    + (point[1] - cy) ** 2
                    + (point[2] - cz) ** 2
                )
                self.assertLessEqual(distance, radius, (weight0, weight1, point, baked))

    def test_import_rejects_non_finite_morph_deltas(self) -> None:
        with tempfile_dir() as root:
            model = root / "non_finite.gltf"
            write_morph_model(root, model.name)
            binary = bytearray((root / "morph.bin").read_bytes())
            struct.pack_into("<f", binary, 44, float("nan"))
            (root / "morph.bin").write_bytes(binary)

            with self.assertRaisesRegex(
                gltf.ModelError, "morph target contains a non-finite value"
            ):
                gltf.load_morphed(model)

    def test_mesh_groups_keep_their_own_default_weights(self) -> None:
        with tempfile_dir() as root:
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
            per_mesh = run_poses(self, root, draw_only_program(model.name))
            override_program = draw_only_program(model.name).replace(
                f'    set var(ok) = model_draw("{model.name}", 0, 0, 0, 1, 0, 0, 0)',
                f'    set var(prev) = model_morph("{model.name}", 0, 0)\n'
                f'    set var(ok) = model_draw("{model.name}", 0, 0, 0, 1, 0, 0, 0)',
            )
            overridden = run_poses(self, root, override_program)

            second_mesh["weights"] = [0.0]
            document["meshes"][1] = second_mesh
            baseline = write_morph_glb(root, "same-default.glb", document)
            same_default = run_poses(
                self, root, draw_only_program(baseline.name)
            )

        def span(output: list[str]) -> int:
            line = next(line for line in output if line.startswith("box "))
            minimum, maximum = (int(value) for value in line[4:].split(","))
            return maximum - minimum

        self.assertGreater(span(per_mesh) - span(same_default), 80)
        self.assertLessEqual(abs(span(overridden) - span(same_default)), 5)

    def test_node_weights_override_mesh_defaults_per_instance(self) -> None:
        with tempfile_dir() as root:
            base = root / "base.gltf"
            write_morph_model(root, base.name, defaults=(0.25,))
            document = json.loads(base.read_text(encoding="utf-8"))
            document["nodes"] = [
                {"mesh": 0, "weights": [0.0]},
                {"mesh": 0, "weights": [1.0]},
            ]
            document["scenes"][0]["nodes"] = [0, 1]
            model = write_morph_glb(root, "per-node.glb", document)
            per_node = run_poses(self, root, draw_only_program(model.name))

            document["nodes"][1]["weights"] = [0.0]
            baseline = write_morph_glb(root, "same-node-default.glb", document)
            same_default = run_poses(
                self, root, draw_only_program(baseline.name)
            )

        def span(output: list[str]) -> int:
            line = next(line for line in output if line.startswith("box "))
            minimum, maximum = (int(value) for value in line[4:].split(","))
            return maximum - minimum

        self.assertGreater(
            span(per_node) - span(same_default), 80,
            (per_node, same_default, span(per_node), span(same_default)),
        )

    def test_the_weight_scales_the_delta(self) -> None:
        with tempfile_dir() as root:
            write_morph_model(root, "morph.gltf")
            out = run_poses(self, root, weight_program("morph.gltf", [0.0, 1.0, 0.5]))
        boxes = [line for line in out if line.startswith("box ")]
        self.assertEqual(len(boxes), 3, out)
        rest = [int(v) for v in boxes[0][4:].split(",")]
        full = [int(v) for v in boxes[1][4:].split(",")]
        half = [int(v) for v in boxes[2][4:].split(",")]
        self.assertGreater(full[0] - rest[0], 100)
        # Half the weight moves the mesh about half as far.
        self.assertAlmostEqual(
            (half[0] - rest[0]) / (full[0] - rest[0]), 0.5, delta=0.06
        )
        # The previous weight comes back, so a caller can restore it.
        self.assertIn("prev 0", out)

    def test_the_mesh_default_weight_is_applied_on_the_first_draw(self) -> None:
        with tempfile_dir() as root:
            write_morph_model(root, "default.gltf", defaults=(1.0,))
            out = run_poses(self, root, draw_only_program("default.gltf"))
            plain_root = root / "plain"
            plain_root.mkdir()
            write_morph_model(plain_root, "plain.gltf", defaults=(0.0,))
            plain = run_poses(self, plain_root, draw_only_program("plain.gltf"))
        default_box = next(line for line in out if line.startswith("box "))
        plain_box = next(line for line in plain if line.startswith("box "))
        default_rest = int(default_box[4:].split(",")[0])
        plain_rest = int(plain_box[4:].split(",")[0])
        self.assertGreater(default_rest - plain_rest, 100)

    def test_weights_are_clamped_and_the_previous_value_is_returned(self) -> None:
        with tempfile_dir() as root:
            write_morph_model(root, "clamp.gltf")
            program = "\n".join(
                (
                    "fn(main)",
                    '  say model_morph("clamp.gltf", 0, 5)',
                    '  say model_morph("clamp.gltf", 0, -3)',
                    '  say model_morph("clamp.gltf", 0, 0.25)',
                    '  say model_morph("clamp.gltf", 0, 0.75)',
                    "end",
                    "",
                    "call fn(main)",
                    "",
                )
            )
            source = root / "clamp.ANVL"
            source.write_text(program, encoding="utf-8")
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(root / "clamp.exe")],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if build.returncode != 0:
                if "No C compiler found" in build.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(build.stderr)
            run = subprocess.run(
                [str(root / "clamp.exe")], cwd=root, capture_output=True, text=True, timeout=60
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        # Every returned value matches the stored weight before the clamp.
        self.assertEqual(run.stdout.splitlines(), ["0", "1", "0", "0.25"])

    def test_a_weight_set_before_the_first_draw_keeps_the_other_defaults(self) -> None:
        with tempfile_dir() as root:
            write_morph_model(root, "pre.gltf", defaults=(0.5,))
            program = "\n".join(
                (
                    "fn(main)",
                    '  say model_morph("pre.gltf", 0, 1)',
                    '  say model_morph("pre.gltf", 0, 1)',
                    "end",
                    "",
                    "call fn(main)",
                    "",
                )
            )
            out = run_headless(self, root, program)
        # The first call must see the mesh default (0.5), not a zeroed table,
        # even though no draw has happened yet.
        self.assertEqual(out.splitlines(), ["0.5", "1"])

    def test_a_model_without_targets_refuses_model_morph(self) -> None:
        with tempfile_dir() as root:
            # A plain triangle with no morph targets.
            positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
            indices = struct.pack("<3H", 0, 1, 2)
            blob = positions + indices
            (root / "plain.bin").write_bytes(blob)
            plain = {
                "asset": {"version": "2.0"},
                "scene": 0,
                "scenes": [{"nodes": [0]}],
                "nodes": [{"mesh": 0}],
                "meshes": [
                    {"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}
                ],
                "buffers": [{"uri": "plain.bin", "byteLength": len(blob)}],
                "bufferViews": [
                    {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                    {"buffer": 0, "byteOffset": 36, "byteLength": 6},
                ],
                "accessors": [
                    {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"},
                    {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
                ],
            }
            (root / "plain.gltf").write_text(json.dumps(plain), encoding="utf-8")
            source = root / "bad.ANVL"
            source.write_text(
                "fn(main)\n"
                '  say model_morph("plain.gltf", 0, 1)\n'
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(root / "bad.exe")],
                capture_output=True,
                text=True,
                timeout=300,
            )
        self.assertNotEqual(build.returncode, 0)
        combined = build.stdout + build.stderr
        self.assertIn("the model has no morph targets", combined)
        self.assertIn(":2:", combined)

    def test_the_wasm_backend_accepts_morph_targets(self) -> None:
        with tempfile_dir() as root:
            write_morph_model(root, "morph.gltf")
            source = root / "wasm.ANVL"
            source.write_text(
                "scene 3d\n"
                "fn(draw)\n"
                '  set var(ok) = model_draw("morph.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
                "end\n",
                encoding="utf-8",
            )
            build = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "-o",
                    str(root / "morph.wasm"),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            self.assertTrue((root / "morph.wasm").is_file())


if __name__ == "__main__":
    unittest.main()
