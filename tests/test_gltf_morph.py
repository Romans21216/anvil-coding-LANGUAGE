"""glTF morph targets: per-vertex deltas blended by weight (8.13).

A static model with `targets` keeps one delta vector per vertex per target; the
runtime adds the weighted deltas before placing and shading the triangle. These
tests measure the drawn ink, so a wrong delta stride, an unapplied default
weight or an unclamped weight all show up as the mesh sitting in the wrong
place.
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

from test_gltf_animation import run_poses, tempfile_dir  # noqa: E402


def write_morph_model(root: pathlib.Path, name: str, *, defaults: tuple[float, ...] = (0.0,)) -> None:
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    deltas = struct.pack("<9f", 2, 0, 0, 2, 0, 0, 2, 0, 0)
    blob = b""
    views = []
    for payload in (positions, indices, deltas):
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

    def test_the_wasm_backend_refuses_morph_targets(self) -> None:
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
        self.assertNotEqual(build.returncode, 0)
        combined = build.stdout + build.stderr
        self.assertIn("morph targets are not available in the wasm backend yet", combined)


if __name__ == "__main__":
    unittest.main()
