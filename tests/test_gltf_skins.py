"""glTF skins: joint matrices and vertex weights fused per draw (8.13).

A skinned model keeps its vertices in mesh space with four joint indices and
four weights each; the runtime composes each joint as
`nodeWorld * inverseBindMatrix` and blends the four influences. These tests
drive the skin through an animated joint and measure the drawn ink, so a wrong
joint order, a missing bind matrix or an unnormalised weight shows up as the
mesh landing in the wrong place.
"""

from __future__ import annotations

import json
import pathlib
import struct
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_gltf_animation import pose_program, run_poses, tempfile_dir  # noqa: E402


def write_skinned_model(
    root: pathlib.Path,
    name: str,
    *,
    weights: tuple[float, float] = (1.0, 0.0),
    with_clip: bool = True,
    joints: int = 1,
) -> None:
    """A one-triangle model skinned to `joints` joint nodes.

    Joint 0 is animated from x=0 to x=2 over one second; a second joint stays
    at the origin, so a 50/50 weight must land half way.
    """
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    joint_row = bytes([0, 1, 0, 0] if joints == 2 else [0, 0, 0, 0])
    joint_bytes = joint_row * 3
    weight_row = struct.pack("<4f", weights[0], weights[1], 0.0, 0.0)
    weight_bytes = weight_row * 3
    times = struct.pack("<2f", 0.0, 1.0)
    values = struct.pack("<6f", 0, 0, 0, 2, 0, 0)
    identity = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    bind = struct.pack("<" + "16f" * joints, *identity * joints)

    parts = [
        ("pos", positions),
        ("idx", indices),
        ("joints", joint_bytes),
        ("weights", weight_bytes),
        ("bind", bind),
    ]
    if with_clip:
        parts.extend([("times", times), ("values", values)])
    blob = b""
    views = []
    for _, payload in parts:
        if len(blob) % 4 and payload in (joint_bytes, weight_bytes, bind, times, values):
            blob += b"\0" * (-len(blob) % 4)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(payload)})
        blob += payload
    (root / "skin.bin").write_bytes(blob)

    nodes = [{"mesh": 0, "skin": 0}, {"translation": [0, 0, 0]}]
    if joints == 2:
        nodes.append({"translation": [0, 0, 0]})
    skin = {"joints": [1, 2] if joints == 2 else [1], "inverseBindMatrices": 4}
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
         "min": [0, 0, 0], "max": [1, 1, 0]},
        {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        {"bufferView": 2, "componentType": 5121, "count": 3, "type": "VEC4"},
        {"bufferView": 3, "componentType": 5126, "count": 3, "type": "VEC4"},
        {"bufferView": 4, "componentType": 5126, "count": joints, "type": "MAT4"},
    ]
    if with_clip:
        accessors.extend(
            [
                {"bufferView": 5, "componentType": 5126, "count": 2, "type": "SCALAR",
                 "min": [0], "max": [1]},
                {"bufferView": 6, "componentType": 5126, "count": 2, "type": "VEC3"},
            ]
        )
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": nodes,
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "JOINTS_0": 2,
                            "WEIGHTS_0": 3,
                        },
                        "indices": 1,
                        "material": 0,
                    }
                ]
            }
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "skins": [skin],
        "buffers": [{"uri": "skin.bin", "byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
    }
    if with_clip:
        document["animations"] = [
            {
                "channels": [{"sampler": 0, "target": {"node": 1, "path": "translation"}}],
                "samplers": [{"input": 5, "output": 6, "interpolation": "LINEAR"}],
            }
        ]
    (root / name).write_text(json.dumps(document, indent=1), encoding="utf-8")


class GltfSkinTests(unittest.TestCase):
    def test_one_joint_with_full_weight_follows_the_joint(self) -> None:
        with tempfile_dir() as root:
            write_skinned_model(root, "skin.gltf")
            out = run_poses(self, root, pose_program("skin.gltf", [0.0, 0.5]))
        boxes = [line for line in out if line.startswith("box ")]
        self.assertEqual(len(boxes), 2, out)
        rest = [int(v) for v in boxes[0][4:].split(",")]
        moved = [int(v) for v in boxes[1][4:].split(",")]
        self.assertGreater(moved[0] - rest[0], 40)

    def test_half_weights_between_two_joints_land_half_way(self) -> None:
        with tempfile_dir() as root:
            write_skinned_model(root, "half.gltf", weights=(0.5, 0.5), joints=2)
            out = run_poses(self, root, pose_program("half.gltf", [0.0, 0.5]))
            full_root = root / "full"
            full_root.mkdir()
            write_skinned_model(full_root, "full.gltf")
            full = run_poses(self, full_root, pose_program("full.gltf", [0.0, 0.5]))
        half_boxes = [line for line in out if line.startswith("box ")]
        full_boxes = [line for line in full if line.startswith("box ")]
        half_rest = [int(v) for v in half_boxes[0][4:].split(",")]
        half_moved = [int(v) for v in half_boxes[1][4:].split(",")]
        full_rest = [int(v) for v in full_boxes[0][4:].split(",")]
        full_moved = [int(v) for v in full_boxes[1][4:].split(",")]
        self.assertEqual(half_rest, full_rest)
        half_shift = half_moved[0] - half_rest[0]
        full_shift = full_moved[0] - full_rest[0]
        # 0.5 of a joint translation must move about half as far as 1.0.
        self.assertAlmostEqual(half_shift / full_shift, 0.5, delta=0.08)

    def test_a_skinned_model_without_a_clip_draws_at_rest(self) -> None:
        program = "\n".join(
            (
                "scene 3d",
                "set var(n) = 0",
                "",
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
                '  say "box " & var(minx) & "," & var(maxx) & ",0,0"',
                "end",
                "",
                "fn(draw)",
                "  add var(n) 1",
                "  clear rgba(0, 0, 0, 255)",
                "  if var(n) = 2",
                '    set var(ok) = model_draw("rest.gltf", 0, 0, 0, 1, 0, 0, 0)',
                "    call fn(scan)",
                '    say "done"',
                "  end",
                "end",
                "",
            )
        )
        with tempfile_dir() as root:
            write_skinned_model(root, "rest.gltf", with_clip=False)
            out = run_poses(self, root, program)
        boxes = [line for line in out if line.startswith("box ")]
        self.assertEqual(len(boxes), 1, out)
        rest = [int(v) for v in boxes[0][4:].split(",")]
        self.assertLess(rest[0], rest[1])

    def test_a_primitive_without_weights_is_refused(self) -> None:
        with tempfile_dir() as root:
            write_skinned_model(root, "skin.gltf")
            document = json.loads((root / "skin.gltf").read_text(encoding="utf-8"))
            del document["meshes"][0]["primitives"][0]["attributes"]["WEIGHTS_0"]
            (root / "skin.gltf").write_text(json.dumps(document), encoding="utf-8")
            source = root / "bad.ANVL"
            source.write_text(
                "scene 3d\n"
                "fn(draw)\n"
                '  set var(ok) = model_draw("skin.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
                "end\n",
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
        self.assertIn("a skinned primitive needs WEIGHTS_0", combined)
        self.assertIn(":3:", combined)

    def test_wasm_draws_skinned_ray_mesh_and_c_locates_its_refusal(self) -> None:
        with tempfile_dir() as root:
            write_skinned_model(root, "skin.gltf")
            source = root / "wasm.ANVL"
            source.write_text(
                "scene 3d\n"
                "fn(draw)\n"
                '  set var(ok) = model_draw("skin.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
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
                    str(root / "skin.wasm"),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            source.write_text(
                "scene 3d\n"
                "fn(draw)\n"
                '  set var(ok) = ray_mesh("skin.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
                "end\n",
                encoding="utf-8",
            )
            ray_build = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "-o",
                    str(root / "ray.wasm"),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(ray_build.returncode, 0, ray_build.stdout + ray_build.stderr)
            c_build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(root / "ray.exe")],
                capture_output=True,
                text=True,
                timeout=300,
            )
        self.assertNotEqual(c_build.returncode, 0)
        combined = c_build.stdout + c_build.stderr
        self.assertIn("ray_mesh does not support skinned meshes yet", combined)
        self.assertIn(":3:", combined)


if __name__ == "__main__":
    unittest.main()
