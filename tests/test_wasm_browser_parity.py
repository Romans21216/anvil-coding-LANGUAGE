"""Cross-renderer silhouette parity for the static wasm model path."""

from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
CAPTURE = ROOT / "tools" / "capture_wasm_mask.mjs"
CHROME = pathlib.Path(
    os.environ.get(
        "CHROME_PATH", "C:/Program Files/Google/Chrome/Application/chrome.exe"
    )
)
NEEDS_BROWSER = sys.platform == "win32" and CHROME.is_file() and shutil.which("node")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_gltf_morph import write_morph_model  # noqa: E402
from test_gltf_ray_mesh import write_animated_morph_glb  # noqa: E402
from test_sprite_draw import WindowReader  # noqa: E402


def _program() -> str:
    return "\n".join(
        (
            "scene 3d",
            "camera perspective 0 0 12",
            "camera fov(70)",
            "clear rgba(0, 0, 0, 255)",
            "fn(draw)",
            '  set var(weight) = model_morph("morph.gltf", 0, 0.5)',
            '  set var(ok) = model_draw("morph.gltf", 0, 0, 0, 1, 0, 0, 0)',
            "end",
            "",
        )
    )


def _animated_program() -> str:
    return "\n".join(
        (
            "scene 3d",
            "camera perspective 0 0 12",
            "camera fov(70)",
            "clear rgba(0, 0, 0, 255)",
            "fn(draw)",
            '  set var(t) = model_animate("animated_morph.glb", 0.5)',
            '  set var(weight) = model_morph("animated_morph.glb", 0, 1)',
            '  set var(ok) = ray_mesh("animated_morph.glb", 0, 0, 0, 1, 0, 0, 0)',
            "end",
            "",
        )
    )


def _compile(source: pathlib.Path, output: pathlib.Path, backend: str | None = None) -> None:
    command = [sys.executable, str(COMPILER), str(source), "-o", str(output)]
    if backend:
        command.extend(("--backend", backend))
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if result.returncode:
        if "No C compiler found" in result.stderr:
            raise unittest.SkipTest("MSVC is not available")
        raise AssertionError(result.stdout + result.stderr)


def _native_mask(executable: pathlib.Path) -> bytes:
    process = subprocess.Popen([str(executable)], stdout=subprocess.DEVNULL)
    try:
        reader = WindowReader(process.pid)
        if reader.find(time.monotonic() + 10) is None:
            raise AssertionError("C model window did not open")
        reader.force_client_size(960, 600)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            width, height, pixels = reader.grab(0, 0, 960, 600)
            mask = bytearray((width * height + 7) // 8)
            visible = 0
            for pixel in range(width * height):
                offset = pixel * 4
                if pixels[offset] > 2 or pixels[offset + 1] > 2 or pixels[offset + 2] > 2:
                    mask[pixel >> 3] |= 1 << (pixel & 7)
                    visible += 1
            if visible:
                return bytes(mask)
            time.sleep(0.05)
        raise AssertionError("C model produced no visible pixels")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@unittest.skipUnless(
    NEEDS_BROWSER, "cross-renderer mask checks need Windows, Node and Chrome"
)
class WasmBrowserParityTests(unittest.TestCase):
    def test_static_morph_model_draw_matches_c_silhouette(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            for directory in (c_dir, wasm_dir):
                write_morph_model(directory, "morph.gltf", defaults=(0.0,))
                (directory / "program.ANVL").write_text(_program(), encoding="utf-8")

            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")

            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            self.assertEqual((page["width"], page["height"]), (960, 600))
            wasm_mask = base64.b64decode(page["mask"], validate=True)
            c_mask = _native_mask(c_output)
            self.assertEqual(len(c_mask), len(wasm_mask))

        intersection = sum((left & right).bit_count() for left, right in zip(c_mask, wasm_mask))
        union = sum((left | right).bit_count() for left, right in zip(c_mask, wasm_mask))
        iou = intersection / union if union else 0.0
        self.assertGreater(iou, 0.92, f"C/WASM visible-pixel IoU {iou:.4f}")

    def test_animated_morphed_ray_mesh_matches_c_silhouette(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            c_dir = root / "c"
            wasm_dir = root / "wasm"
            c_dir.mkdir()
            wasm_dir.mkdir()
            for directory in (c_dir, wasm_dir):
                write_animated_morph_glb(directory)
                (directory / "program.ANVL").write_text(
                    _animated_program(), encoding="utf-8"
                )

            c_output = c_dir / "program.exe"
            _compile(c_dir / "program.ANVL", c_output)
            wasm_output = wasm_dir / "program.wasm"
            _compile(wasm_dir / "program.ANVL", wasm_output, "wasm")
            browser = subprocess.run(
                ["node", str(CAPTURE), str(wasm_dir), "program.html"],
                capture_output=True,
                text=True,
                timeout=90,
                env={**os.environ, "CHROME_PATH": str(CHROME)},
            )
            self.assertEqual(browser.returncode, 0, browser.stderr)
            page = json.loads(browser.stdout.strip().splitlines()[-1])
            wasm_mask = base64.b64decode(page["mask"], validate=True)
            c_mask = _native_mask(c_output)
            self.assertEqual(len(c_mask), len(wasm_mask))

        intersection = sum((left & right).bit_count() for left, right in zip(c_mask, wasm_mask))
        union = sum((left | right).bit_count() for left, right in zip(c_mask, wasm_mask))
        iou = intersection / union if union else 0.0
        self.assertGreater(iou, 0.92, f"animated C/WASM silhouette IoU {iou:.4f}")


if __name__ == "__main__":
    unittest.main()
