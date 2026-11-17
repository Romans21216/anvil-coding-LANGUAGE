"""glTF animation: node TRS keys posed at runtime (8.13).

A model with an animation clip is baked in node-local space with its hierarchy
and keyframes, and `model_draw` evaluates the pose each frame from the clock
`model_animate` sets. These tests measure the drawn result: a translated node
must move the triangle's ink, a rotated node must change its bounds, a STEP
track must hold its left key, and the clip must loop at its length.
"""

from __future__ import annotations

import json
import pathlib
import queue
import struct
import subprocess
import sys
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
BLACK = 4278190080


def write_model(
    root: pathlib.Path,
    name: str,
    *,
    path: str = "translation",
    keys: tuple[float, float] = (0.0, 1.0),
    start: tuple[float, float, float] = (0.0, 0.0, 0.0),
    end: tuple[float, float, float] = (2.0, 0.0, 0.0),
    interpolation: str = "LINEAR",
) -> None:
    """A one-triangle model whose single node has one animated channel."""
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2)
    times = struct.pack("<2f", keys[0], keys[1])
    if path == "rotation":
        values = struct.pack("<8f", 0, 0, 0, 1, 0, 0, 0.7071068, 0.7071068)
    else:
        values = struct.pack("<6f", *start, *end)
    rotation_padding = b"\0" * 8 if path == "rotation" else b""
    values_offset = 52 + len(rotation_padding)
    blob = positions + indices + b"\0\0" + times + rotation_padding + values
    (root / "tri.bin").write_bytes(blob)
    document = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "material": 0}]}
        ],
        "materials": [{"pbrMetallicRoughness": {"baseColorFactor": [1, 1, 1, 1]}}],
        "buffers": [{"uri": "tri.bin", "byteLength": len(blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": 36},
            {"buffer": 0, "byteOffset": 36, "byteLength": 6},
            {"buffer": 0, "byteOffset": 44, "byteLength": 8},
            {"buffer": 0, "byteOffset": values_offset, "byteLength": len(values)},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
             "min": [0, 0, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
            {"bufferView": 2, "componentType": 5126, "count": 2, "type": "SCALAR",
             "min": [keys[0]], "max": [keys[1]]},
            {"bufferView": 3, "componentType": 5126, "count": 2,
             "type": "VEC4" if path == "rotation" else "VEC3"},
        ],
        "animations": [
            {
                "channels": [{"sampler": 0, "target": {"node": 0, "path": path}}],
                "samplers": [
                    {"input": 2, "output": 3, "interpolation": interpolation}
                ],
            }
        ],
    }
    (root / name).write_text(json.dumps(document, indent=1), encoding="utf-8")


def pose_program(model: str, poses: list[float]) -> str:
    lines = [
        "scene 3d",
        "set var(n) = 0",
        "",
        "fn(scan)",
        "  set var(cap) = frame_capture()",
        "  set var(minx) = 999",
        "  set var(maxx) = -1",
        "  set var(miny) = 999",
        "  set var(maxy) = -1",
        "  for local(x) = 0 to 959",
        "    for local(y) = 0 to 599",
        f"      set var(v) = image_pixel(var(cap), local(x), local(y)) - {BLACK}",
        "      if var(v) > 0",
        "        if local(x) < var(minx)",
        "          set var(minx) = local(x)",
        "        end",
        "        if local(x) > var(maxx)",
        "          set var(maxx) = local(x)",
        "        end",
        "        if local(y) < var(miny)",
        "          set var(miny) = local(y)",
        "        end",
        "        if local(y) > var(maxy)",
        "          set var(maxy) = local(y)",
        "        end",
        "      end",
        "    end",
        "  end",
        '  say "box " & var(minx) & "," & var(maxx) & "," & var(miny) & "," & var(maxy)',
        "end",
        "",
        "fn(draw)",
        "  add var(n) 1",
        "  clear rgba(0, 0, 0, 255)",
    ]
    frame = 2
    for pose in poses:
        lines.extend(
            [
                f"  if var(n) = {frame}",
                f'    set var(t) = model_animate("{model}", {pose!r})',
                f'    set var(ok) = model_draw("{model}", 0, 0, 0, 1, 0, 0, 0)',
                "    call fn(scan)",
                "  end",
            ]
        )
        frame += 3
    lines.extend(
        [
            f"  if var(n) = {frame}",
            f'    say "len " & model_animation_length("{model}")',
            '    say "done"',
            "  end",
            "end",
            "",
        ]
    )
    return "\n".join(lines)


def run_poses(case: unittest.TestCase, root: pathlib.Path, program: str) -> list[str]:
    """Build and run a pose program; return its printed lines."""
    source = root / "pose.ANVL"
    source.write_text(program, encoding="utf-8")
    executable = root / "pose.exe"
    build = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if build.returncode != 0:
        if "No C compiler found" in build.stderr:
            raise unittest.SkipTest("MSVC is not available")
        case.fail(build.stderr)
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: queue.Queue[str] = queue.Queue()

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line.strip())

    threading.Thread(target=pump, daemon=True).start()
    out: list[str] = []
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=5)
            except queue.Empty:
                break
            out.append(line)
            if line == "done":
                break
    finally:
        process.kill()
        process.wait(timeout=30)
    return out


class GltfAnimationTests(unittest.TestCase):
    def run_poses(self, root: pathlib.Path, program: str) -> list[str]:
        return run_poses(self, root, program)

    def test_a_translation_track_moves_the_triangle(self) -> None:
        with tempfile_dir() as root:
            write_model(root, "tri.gltf")
            out = self.run_poses(root, pose_program("tri.gltf", [0.0, 0.5, 0.25]))
        boxes = [line for line in out if line.startswith("box ")]
        self.assertEqual(len(boxes), 3, out)
        first = [int(v) for v in boxes[0][4:].split(",")]
        middle = [int(v) for v in boxes[1][4:].split(",")]
        quarter = [int(v) for v in boxes[2][4:].split(",")]
        # +2 over one second: half a second moves the triangle by half of that.
        self.assertLess(first[0], middle[0])
        self.assertGreater(middle[0] - first[0], 40)
        # A quarter of the way is between the two poses.
        self.assertGreater(quarter[0], first[0])
        self.assertLess(quarter[0], middle[0])

    def test_a_rotation_track_changes_the_silhouette(self) -> None:
        with tempfile_dir() as root:
            write_model(root, "turn.gltf", path="rotation", keys=(0.0, 2.0))
            out = self.run_poses(root, pose_program("turn.gltf", [0.0, 1.0]))
        boxes = [line for line in out if line.startswith("box ")]
        self.assertEqual(len(boxes), 2, out)
        rest = [int(v) for v in boxes[0][4:].split(",")]
        turned = [int(v) for v in boxes[1][4:].split(",")]
        # A 90-degree turn about Z swaps the triangle's x and y extents.
        self.assertNotEqual(rest[2], turned[2])
        self.assertNotEqual(rest[0], turned[0])

    def test_step_holds_the_left_key_until_the_next_one(self) -> None:
        with tempfile_dir() as root:
            write_model(root, "step.gltf", interpolation="STEP")
            out = self.run_poses(root, pose_program("step.gltf", [0.0, 0.9, 1.0]))
        boxes = [line for line in out if line.startswith("box ")]
        self.assertEqual(len(boxes), 3, out)
        first = [int(v) for v in boxes[0][4:].split(",")]
        almost = [int(v) for v in boxes[1][4:].split(",")]
        wrapped = [int(v) for v in boxes[2][4:].split(",")]
        # STEP keeps the first key until 1.0 s, and the clip wraps at its length.
        self.assertEqual(first, almost)
        self.assertEqual(first, wrapped)

    def test_the_length_is_reported_and_a_static_model_is_refused(self) -> None:
        with tempfile_dir() as root:
            write_model(root, "tri.gltf", keys=(0.0, 2.5))
            out = self.run_poses(root, pose_program("tri.gltf", [0.0]))
            self.assertIn("len 2.5", out)

            # A model without a clip must be rejected with the source line.
            source = root / "bad.ANVL"
            write_model(root, "plain.gltf")
            document = json.loads((root / "plain.gltf").read_text(encoding="utf-8"))
            document.pop("animations")
            (root / "plain.gltf").write_text(json.dumps(document), encoding="utf-8")
            source.write_text(
                "scene 3d\n"
                "fn(draw)\n"
                '  set var(t) = model_animate("plain.gltf", 0)\n'
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
            self.assertIn("the model has no animation clip to play", combined)
            self.assertIn(":3:", combined)

    def test_the_wasm_backend_accepts_an_animated_model(self) -> None:
        with tempfile_dir() as root:
            write_model(root, "tri.gltf")
            source = root / "wasm.ANVL"
            source.write_text(
                "scene 3d\n"
                "fn(draw)\n"
                '  set var(ok) = model_draw("tri.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
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
                    str(root / "anim.wasm"),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            self.assertTrue((root / "anim.wasm").is_file())


class tempfile_dir:
    """TemporaryDirectory with ignore_cleanup_errors, used as a context manager."""

    def __enter__(self) -> pathlib.Path:
        import tempfile

        self._temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        return pathlib.Path(self._temp.name)

    def __exit__(self, *exc) -> None:
        self._temp.cleanup()


if __name__ == "__main__":
    unittest.main()
