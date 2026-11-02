"""MSVC helper and object-file ownership regressions."""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from compiler.build import _gcc_arguments, _msvc_arguments, build_c
from compiler.runtime_modules import MODULES


class LinkerGarbageCollectionTests(unittest.TestCase):
    def test_network_module_is_only_compiled_and_linked_when_selected(self):
        module = MODULES["networking"]
        base = _gcc_arguments(
            "gcc", pathlib.Path("program.c"), pathlib.Path("program.exe"), True
        )
        with_network = _gcc_arguments(
            "gcc",
            pathlib.Path("program.c"),
            pathlib.Path("program.exe"),
            True,
            (module,),
        )
        self.assertNotIn(str(module.source), base)
        self.assertNotIn("-lws2_32", base)
        self.assertIn(str(module.source), with_network)
        self.assertIn("-lws2_32", with_network)

    def test_gcc_build_arguments_include_both_selected_modules(self):
        modules = (MODULES["physics"], MODULES["networking"])
        args = _gcc_arguments(
            "gcc",
            pathlib.Path("program.c"),
            pathlib.Path("program.exe"),
            True,
            modules,
        )
        self.assertIn(str(MODULES["physics"].source), args)
        self.assertIn(str(MODULES["networking"].source), args)
        self.assertEqual(args.count("-lws2_32"), 1)

    def test_msvc_physics_module_is_an_explicit_translation_unit(self):
        module = MODULES["physics"]
        args = _msvc_arguments(
            "cl.exe",
            pathlib.Path("program.c"),
            pathlib.Path("program.exe"),
            pathlib.Path("objects"),
            release=True,
            runtime_modules=(module,),
        )
        self.assertIn(str(module.source), args)

    def test_msvc_network_module_is_an_explicit_translation_unit(self):
        module = MODULES["networking"]
        args = _msvc_arguments(
            "cl.exe",
            pathlib.Path("program.c"),
            pathlib.Path("program.exe"),
            pathlib.Path("objects"),
            release=True,
            runtime_modules=(module,),
        )
        self.assertIn(str(module.source), args)

    def test_msvc_release_packages_functions_and_data_for_linker_pruning(self):
        args = _msvc_arguments(
            "cl.exe",
            pathlib.Path("program.c"),
            pathlib.Path("program.exe"),
            pathlib.Path("objects"),
            release=True,
        )
        self.assertIn("/Gy", args)
        self.assertIn("/Gw", args)
        self.assertEqual(args[args.index("/link") + 1], "/OPT:REF")

    def test_msvc_debug_does_not_enable_release_linker_pruning(self):
        args = _msvc_arguments(
            "cl.exe",
            pathlib.Path("program.c"),
            pathlib.Path("program.exe"),
            pathlib.Path("objects"),
            release=False,
        )
        self.assertIn("/Od", args)
        self.assertNotIn("/Gy", args)
        self.assertNotIn("/Gw", args)
        self.assertNotIn("/OPT:REF", args)

    def test_gcc_release_enables_function_and_data_section_gc(self):
        args = _gcc_arguments(
            "gcc", pathlib.Path("program.c"), pathlib.Path("program.exe"), True
        )
        self.assertIn("-ffunction-sections", args)
        self.assertIn("-fdata-sections", args)
        self.assertIn("-Wl,--gc-sections", args)

    def test_gcc_debug_keeps_release_section_gc_disabled(self):
        args = _gcc_arguments(
            "gcc", pathlib.Path("program.c"), pathlib.Path("program.exe"), False
        )
        self.assertIn("-O0", args)
        self.assertNotIn("-ffunction-sections", args)
        self.assertNotIn("-fdata-sections", args)
        self.assertNotIn("-Wl,--gc-sections", args)


@unittest.skipUnless(os.name == "nt", "MSVC helper wrapping is Windows-specific")
class MsvcBuildTests(unittest.TestCase):
    def test_environment_helper_uses_owned_temporary_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            install = root / "Microsoft Visual Studio" / "2022" / "BuildTools"
            compiler = (
                install
                / "VC"
                / "Tools"
                / "MSVC"
                / "14.0"
                / "bin"
                / "Hostx64"
                / "x64"
                / "cl.exe"
            )
            compiler.parent.mkdir(parents=True)
            devcmd = install / "Common7" / "Tools" / "VsDevCmd.bat"
            devcmd.parent.mkdir(parents=True)
            devcmd.write_text("@echo off\r\n", encoding="utf-8")

            generated = root / "program.c"
            generated.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            output_dir = root / "output"
            output_dir.mkdir()
            output = output_dir / "game.exe"
            existing_helper = output_dir / "game.build.cmd"
            sentinel = b"@echo existing caller-owned helper\r\n"
            existing_helper.write_bytes(sentinel)

            observed = {}

            def fake_run(command, check):
                self.assertEqual(check, True)
                self.assertEqual(command[:3], ["cmd.exe", "/d", "/c"])
                generated_helper = pathlib.Path(command[3])
                self.assertTrue(generated_helper.is_file())
                self.assertNotEqual(generated_helper, existing_helper)
                self.assertNotEqual(generated_helper.parent, output_dir)
                observed["helper"] = generated_helper

            with mock.patch("compiler.build.subprocess.run", side_effect=fake_run):
                build_c(str(compiler), generated, output, release=False)

            self.assertEqual(existing_helper.read_bytes(), sentinel)
            self.assertFalse(observed["helper"].exists())
            self.assertFalse(output_dir.joinpath("game_obj").exists())


if __name__ == "__main__":
    unittest.main()
