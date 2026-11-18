from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from compiler import expressions  # noqa: E402
from compiler.verify import MODEL_CALLS, _asset_calls  # noqa: E402
from test_gltf_model import write_glb  # noqa: E402


def run_verify(source: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), "verify", str(source), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


class VerifyCommandTests(unittest.TestCase):
    def test_asset_scanner_covers_every_gltf_model_api(self) -> None:
        compiler_model_calls = {
            name
            for name in expressions.BUILTINS
            if name.startswith("model_") or name == "ray_mesh"
        }
        self.assertEqual(MODEL_CALLS, compiler_model_calls)
        source = " ".join(
            f'{name}("mesh.glb", 0)' for name in (
                "model_draw",
                "model_draw_instance",
                "model_animate",
                "model_animation_length",
                "model_morph",
                "model_instance",
                "model_instance_destroy",
                "model_instance_morph",
                "ray_mesh",
            )
        )
        found = list(_asset_calls(source))
        self.assertEqual({name for name, _path in found}, MODEL_CALLS)
        self.assertEqual(len(found), len(MODEL_CALLS))
        self.assertTrue(all(path == "mesh.glb" for _name, path in found))

    def test_aggregates_reachable_bmp_wav_and_gltf_failures_as_versioned_json(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = pathlib.Path(temporary)
            source = root / "main.ANVL"
            source.write_text(
                "scene 3d\n"
                "fn(draw)\n"
                '  set var(i) = image_load("missing.bmp")\n'
                '  set var(j) = image_load("malformed.bmp")\n'
                '  set var(s) = sound_load("broken.wav")\n'
                '  set var(m) = model_draw("broken.gltf", 0, 0, 0, 1, 0, 0, 0)\n'
                "end\n",
                encoding="utf-8",
            )
            (root / "malformed.bmp").write_bytes(b"BM")
            (root / "broken.wav").write_bytes(b"not a wave")
            (root / "broken.gltf").write_text("{broken", encoding="utf-8")
            result = run_verify(source, "--format", "json")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stderr, "")
            report = json.loads(result.stdout)
            self.assertEqual(report["version"], 1)
            self.assertFalse(report["ok"])
            self.assertEqual({item["asset"] for item in report["diagnostics"]}, {
                "missing.bmp", "malformed.bmp", "broken.wav", "broken.gltf"
            })
            self.assertTrue(all(item["path"] == str(source.resolve()) for item in report["diagnostics"]))
            self.assertTrue(all(item["line"] in {3, 4, 5, 6} for item in report["diagnostics"]))
            self.assertFalse((root / "main.exe").exists())
            text_result = run_verify(source)
            self.assertEqual(text_result.returncode, 1)
            self.assertEqual(text_result.stdout, "")
            self.assertEqual(len(text_result.stderr.splitlines()), 4)
            for asset in ("missing.bmp", "malformed.bmp", "broken.wav", "broken.gltf"):
                self.assertIn(asset, text_result.stderr)

    def test_ignores_comment_and_unreachable_asset_calls(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = pathlib.Path(temporary)
            source = root / "main.ANVL"
            source.write_text(
                '# image_load("comment.bmp")\n'
                "fn(main)\n"
                "  say 1\n"
                "end\n"
                "fn(dead)\n"
                '  set var(i) = image_load("unreachable.bmp")\n'
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            result = run_verify(source)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), f"{source.resolve()}: ok")
            self.assertEqual(result.stderr, "")
            self.assertFalse((root / "main.exe").exists())

    def test_reports_reachable_dynamic_asset_paths_as_unverifiable(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = pathlib.Path(temporary)
            source = root / "main.ANVL"
            source.write_text(
                'set var(path) = "dynamic.bmp"\n'
                "fn(main)\n"
                '  set var(a) = image_load(var(path))\n'
                '  set var(b) = image_load("part" & "ial.bmp")\n'
                "end\n"
                "call fn(main)\n",
                encoding="utf-8",
            )
            result = run_verify(source, "--format", "json")
            self.assertEqual(result.returncode, 1)
            diagnostics = json.loads(result.stdout)["diagnostics"]
            self.assertEqual(len(diagnostics), 2)
            self.assertTrue(all("literal path" in item["message"] for item in diagnostics))

    def test_reports_lowering_errors_without_linking(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = pathlib.Path(temporary)
            source = root / "bad.ANVL"
            source.write_text(
                "fn(main)\n  set var(value) = missing_builtin(1)\nend\ncall fn(main)\n",
                encoding="utf-8",
            )
            result = run_verify(source, "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertEqual(len(report["diagnostics"]), 1)
            self.assertEqual(report["diagnostics"][0]["path"], str(source.resolve()))
            self.assertEqual(report["diagnostics"][0]["line"], 2)
            self.assertFalse((root / "bad.exe").exists())

    def test_reports_project_manifest_errors_without_linking(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = pathlib.Path(temporary)
            project = root / "game.ANVLproj"
            project.write_text('entry = "missing.ANVL"\n', encoding="utf-8")
            result = run_verify(project, "--format", "json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertEqual(report["version"], 1)
            self.assertEqual(len(report["diagnostics"]), 1)
            self.assertIn("cannot read", report["diagnostics"][0]["message"])
            self.assertFalse(list(root.glob("*.exe")))

    def test_manifest_errors_match_project_check_rules(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = pathlib.Path(temporary)
            (root / "main.ANVL").write_text(
                "fn(main)\n  say 1\nend\ncall fn(main)\n", encoding="utf-8"
            )
            invalid_manifests = (
                'entry = "main.ANVL"\nname = 7\n',
                'entry = "main.ANVL"\n[engine]\nfixed_hz = 0\n',
                'entry = "main.ANVL"\n[engine]\nextra = 1\n',
                'entry = "main.ANVL"\n[assets]\nfiles = "bad.bmp"\n',
                'entry = "../outside.ANVL"\n',
                'entry = "main.ANVL"\nunknown = true\n',
            )
            for index, text in enumerate(invalid_manifests):
                with self.subTest(manifest=text):
                    project = root / f"invalid-{index}.ANVLproj"
                    project.write_text(text, encoding="utf-8")
                    verify_result = run_verify(project, "--format", "json")
                    check_result = subprocess.run(
                        [
                            sys.executable,
                            str(CLI),
                            str(project),
                            "--check",
                            "--backend",
                            "wasm",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    self.assertEqual(verify_result.returncode, 1)
                    self.assertEqual(check_result.returncode, 1)
                    self.assertEqual(
                        len(json.loads(verify_result.stdout)["diagnostics"]), 1
                    )

    def test_declared_project_assets_resolve_from_manifest_directory(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = pathlib.Path(temporary)
            (root / "nested").mkdir()
            (root / "nested" / "main.ANVL").write_text(
                "fn(main)\n  say 1\nend\ncall fn(main)\n", encoding="utf-8"
            )
            (root / "bad.bmp").write_bytes(b"BM")
            project = root / "game.ANVLproj"
            project.write_text(
                'entry = "nested/main.ANVL"\n[assets]\nfiles = ["bad.bmp"]\n',
                encoding="utf-8",
            )
            result = run_verify(project, "--format", "json")
            self.assertEqual(result.returncode, 1)
            diagnostic = json.loads(result.stdout)["diagnostics"][0]
            self.assertEqual(diagnostic["asset"], "bad.bmp")
            self.assertIn("not a BMP", diagnostic["message"])

    def test_nested_project_verify_resolves_embedded_glb_from_manifest_root(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
            root = pathlib.Path(temporary)
            (root / "src").mkdir()
            models = root / "models"
            models.mkdir()
            write_glb(models, "quad.glb", (1.0, 0.0, 0.0))
            (root / "src" / "main.ANVL").write_text(
                'scene 3d\nfn(draw)\n'
                '  set var(ok) = model_draw("models/quad.glb", 0, 0, 0, 1, 0, 0, 0)\n'
                "end\n",
                encoding="utf-8",
            )
            manifest = root / "game.ANVLproj"
            manifest.write_text('entry = "src/main.ANVL"\n', encoding="utf-8")
            result = run_verify(manifest, "--format", "json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["diagnostics"], [])


if __name__ == "__main__":
    unittest.main()
