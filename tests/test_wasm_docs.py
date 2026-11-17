"""Keep the wasm limits section aligned with documented backend support."""

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class WasmDocsTests(unittest.TestCase):
    def test_limits_do_not_contradict_capability_sections(self) -> None:
        document = (ROOT / "docs" / "WASM.md").read_text(encoding="utf-8")
        limits = document.split("## Limits", 1)[1]
        self.assertNotIn("Input, audio, storage and 3D are not there yet", document)
        self.assertNotIn("`scene 3d`, `camera` and `engine` statements", document)
        self.assertIn("**IndexedDB**", document)
        self.assertIn("`tan` is available", limits)
        self.assertIn("`display ray_sphere(...)` is supported in `scene 3d`", document)
        self.assertIn("`model_draw(...)` and `ray_mesh(...)` are supported in `scene 3d`", document)
        self.assertIn("share a 16,384-triangle frame budget across\nstatic and animated submissions", document)
        self.assertIn("`model_morph(path,index,weight)` overrides that target", document)
        self.assertIn("static\nand animated unskinned models", document)
        self.assertIn("supports one skin with up to 64 joints", document)
        self.assertIn("skinned `ray_mesh` receives a located diagnostic", document)
        self.assertIn("unskinned model clips\n  are sampled", document)
        self.assertIn("`light(x,y,z)` vector points toward the light", document)
        self.assertIn("`light_ambient(level)`\nsets the 0–1 floor", document)
        self.assertIn("light, ambient and intensity setting", document)
        self.assertIn("Primitive triangles are one-sided", document)
        self.assertIn("second\nprimitive fixture checks one-sided cube shading", document)
        self.assertIn("intersecting, rotated-cube fixture compares C and Chrome", document)
        self.assertIn("two tilted GLTF quads\nthrough `model_draw`", document)
        self.assertIn("animated+morphed ray-mesh comparison uses an offset, oblique camera", document)
        self.assertNotIn("Wasm animated and skinned model calls are refused", document)
        self.assertNotIn("`ray_sphere` remain C-backend only", document)
        self.assertNotIn("3D uses a painter's algorithm rather than a depth buffer", limits)
        self.assertNotIn("No Web Audio, IndexedDB", limits)
        self.assertNotIn("`tan`, `asin`, `acos` and `atan` are not available", limits)
        self.assertNotIn("4-bit BMPs are not supported", limits)

    def test_runtime_diagnostics_describe_statement_level_locations(self) -> None:
        document = (ROOT / "docs" / "WASM.md").read_text(encoding="utf-8")
        self.assertIn("active Anvil function and statement line", document)
        self.assertIn("not a DWARF debugger", document)
        self.assertNotIn("This is a function-level map, not instruction-level", document)


if __name__ == "__main__":
    unittest.main()
