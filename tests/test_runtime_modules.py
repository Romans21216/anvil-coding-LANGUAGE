"""C runtime module selection from generated feature markers."""

from __future__ import annotations

import unittest

from compiler.common import CompileError
from compiler.runtime_modules import MODULES, select_runtime_modules


class RuntimeModuleSelectionTests(unittest.TestCase):
    def test_core_program_selects_no_optional_runtime_module(self):
        self.assertEqual(select_runtime_modules("int main(void) { return 0; }"), ())

    def test_network_marker_selects_network_translation_unit_and_library(self):
        modules = select_runtime_modules(
            "/* ANVIL_RUNTIME_MODULE: networking */\nint main(void) { return 0; }"
        )
        self.assertEqual(modules, (MODULES["networking"],))
        self.assertEqual(modules[0].source.name, "anvil_network.c")
        self.assertIn("-lws2_32", modules[0].gcc_libraries)

    def test_physics_marker_selects_its_translation_unit(self):
        modules = select_runtime_modules(
            "/* ANVIL_RUNTIME_MODULE: physics */\nint main(void) { return 0; }"
        )
        self.assertEqual(modules, (MODULES["physics"],))
        self.assertEqual(modules[0].source.name, "anvil_physics.c")
        self.assertEqual(modules[0].gcc_libraries, ())

    def test_images_marker_selects_image_translation_unit(self):
        modules = select_runtime_modules(
            "/* ANVIL_RUNTIME_MODULE: images */\nint main(void) { return 0; }"
        )
        self.assertEqual(modules, (MODULES["images"],))
        self.assertEqual(modules[0].source.name, "anvil_image.c")
        self.assertEqual(modules[0].gcc_libraries, ())

    def test_modules_declare_reachable_call_triggers(self):
        self.assertTrue(MODULES["networking"].trigger_patterns)
        self.assertTrue(MODULES["physics"].trigger_patterns)
        self.assertTrue(MODULES["images"].trigger_patterns)

    def test_duplicate_markers_select_module_once(self):
        generated = "\n".join(
            ["/* ANVIL_RUNTIME_MODULE: physics */"] * 2
        )
        self.assertEqual(select_runtime_modules(generated), (MODULES["physics"],))

    def test_unknown_marker_fails_explicitly(self):
        with self.assertRaisesRegex(CompileError, "unknown runtime module.*audio"):
            select_runtime_modules("/* ANVIL_RUNTIME_MODULE: audio */")


if __name__ == "__main__":
    unittest.main()
