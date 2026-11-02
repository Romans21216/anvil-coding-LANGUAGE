"""MSVC helper and object-file ownership regressions."""

from __future__ import annotations

import os
import pathlib
import tempfile
import unittest
from unittest import mock

from compiler.build import build_c


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
