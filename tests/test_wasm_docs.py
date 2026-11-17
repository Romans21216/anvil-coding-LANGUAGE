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
        self.assertIn("16,384 ray-mesh", document)
        self.assertIn("`model_morph(path,index,weight)` overrides that target", document)
        self.assertIn("Both calls use the same WebGL depth-tested triangle path", document)
        self.assertIn("static or\nanimated unskinned models", document)
        self.assertIn("unskinned model clips\nare sampled", document)
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
