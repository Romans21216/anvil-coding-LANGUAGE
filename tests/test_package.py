"""Part 8.14: packaging with a dry run, asset validation and a manifest."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

sys.path.insert(0, str(ROOT))

from compiler import package as package_mod  # noqa: E402

PROGRAM = 'fn(main)\n  say "pack"\nend\ncall fn(main)\n'


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CollectAssetTests(unittest.TestCase):
    def test_declared_and_literal_paths_are_merged_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "assets").mkdir()
            (root / "assets/pic.bmp").write_bytes(b"bmp")
            (root / "assets/snd.wav").write_bytes(b"wav")
            source = root / "main.ANVL"
            source.write_text(
                'fn(main)\n  say image_load("assets/pic.bmp")\nend\n',
                encoding="utf-8",
            )
            found = package_mod.collect_assets(
                root, [source], ["assets/pic.bmp", "assets/snd.wav"]
            )
        self.assertEqual([path.name for path in found], ["pic.bmp", "snd.wav"])

    def test_an_asset_outside_the_project_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp) / "proj"
            root.mkdir()
            source = root / "main.ANVL"
            source.write_text("fn(main)\n  output 0\nend\n", encoding="utf-8")
            with self.assertRaises(Exception):
                package_mod.collect_assets(root, [source], ["../outside.bmp"])


class PackageManifestTests(unittest.TestCase):
    def test_dry_run_prints_the_manifest_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / "assets").mkdir()
            (root / "assets/pic.bmp").write_bytes(b"bmp")
            program = root / "game.exe"
            program.write_bytes(b"MZfake")
            entry = root / "main.ANVL"
            entry.write_text(PROGRAM, encoding="utf-8")
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = package_mod.package(
                    project_root=root,
                    name="Game",
                    backend="native",
                    entry=entry,
                    program=program,
                    declared_assets=["assets/pic.bmp"],
                    sources=[entry],
                    features=["image_load"],
                    compiler={"name": "anvil-native"},
                    target_dir=root / "dist",
                    dry_run=True,
                )
            manifest = json.loads(buffer.getvalue())
            self.assertEqual(code, 0)
            self.assertFalse((root / "dist").exists())
        self.assertEqual(manifest["format"], 1)
        self.assertEqual(manifest["target"], "windows-x64-native")
        self.assertEqual(manifest["features"], ["image_load"])
        self.assertEqual(manifest["program"]["sha256"], hashlib.sha256(b"MZfake").hexdigest())
        self.assertEqual(
            manifest["assets"][0]["sha256"], hashlib.sha256(b"bmp").hexdigest()
        )


class PackageCommandTests(unittest.TestCase):
    def _project(self, root: pathlib.Path) -> pathlib.Path:
        (root / "assets").mkdir(parents=True)
        (root / "assets/pic.bmp").write_bytes(b"BMfake")
        (root / "main.ANVL").write_text(PROGRAM, encoding="utf-8")
        manifest = root / "game.ANVLproj"
        manifest.write_text(
            'name = "Pack Test"\nentry = "main.ANVL"\n\n'
            '[assets]\nfiles = ["assets/pic.bmp"]\n',
            encoding="utf-8",
        )
        return manifest

    def _build(self, manifest: pathlib.Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(COMPILER), str(manifest), *extra],
            capture_output=True,
            text=True,
            timeout=180,
        )

    def test_package_copies_the_program_assets_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            manifest = self._project(root)
            dist = root / "dist"
            result = self._build(manifest, "--package", str(dist))
            if result.returncode != 0:
                if "No C compiler found" in result.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(result.stderr)
            self.assertTrue((dist / "main.exe").is_file())
            self.assertTrue((dist / "assets/pic.bmp").is_file())
            data = json.loads((dist / "anvil-package.json").read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Pack Test")
            self.assertEqual(data["target"], "windows-x64-c")
            self.assertEqual(data["program"]["sha256"], sha256(dist / "main.exe"))
            self.assertEqual(
                data["checksums"]["assets/pic.bmp"], sha256(dist / "assets/pic.bmp")
            )

    def test_missing_asset_fails_the_package_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            manifest = self._project(root)
            (root / "assets/pic.bmp").unlink()
            result = self._build(manifest, "--package", str(root / "dist"), "--package-dry-run")
            if "No C compiler found" in result.stderr:
                raise unittest.SkipTest("MSVC is not available")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing and would not ship", result.stderr)
            self.assertFalse((root / "dist").exists())


if __name__ == "__main__":
    unittest.main()
