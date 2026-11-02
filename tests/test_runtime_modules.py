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

    def test_duplicate_markers_select_module_once(self):
        generated = "\n".join(
            ["/* ANVIL_RUNTIME_MODULE: networking */"] * 2
        )
        self.assertEqual(select_runtime_modules(generated), (MODULES["networking"],))

    def test_unknown_marker_fails_explicitly(self):
        with self.assertRaisesRegex(CompileError, "unknown runtime module.*physics"):
            select_runtime_modules("/* ANVIL_RUNTIME_MODULE: physics */")


if __name__ == "__main__":
    unittest.main()
