"""Asset import timing is opt-in and covers WASM media baking."""

from __future__ import annotations

import pathlib
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler import wasm  # noqa: E402


class WasmAssetProfileTests(unittest.TestCase):
    def test_bmp_and_wav_baking_contribute_when_profiling_is_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = pathlib.Path(temporary) / "main.ANVL"
            source.write_text("", encoding="utf-8")
            bmp = bytearray(58)
            bmp[:2] = b"BM"
            struct.pack_into("<I", bmp, 2, len(bmp))
            struct.pack_into("<I", bmp, 10, 54)
            struct.pack_into("<I", bmp, 14, 40)
            struct.pack_into("<ii", bmp, 18, 1, 1)
            struct.pack_into("<HH", bmp, 26, 1, 32)
            bmp[54:] = bytes((10, 20, 30, 255))
            (source.parent / "pixel.bmp").write_bytes(bmp)

            pcm = struct.pack("<4h", 0, 200, -200, 0)
            fmt = struct.pack("<HHIIHH", 1, 1, 8000, 16000, 2, 16)
            wav = b"fmt " + struct.pack("<I", len(fmt)) + fmt
            wav += b"data" + struct.pack("<I", len(pcm)) + pcm
            wav = b"RIFF" + struct.pack("<I", len(wav) + 4) + b"WAVE" + wav
            (source.parent / "tone.wav").write_bytes(wav)

            image_calls = 'image_load("pixel.bmp")'
            sound_calls = 'sound_load("tone.wav")'
            music_calls = 'music_load("tone.wav")'
            wasm.measure_asset_imports(False, reset=True)
            wasm.bake_images(source, image_calls)
            wasm.bake_sounds(source, sound_calls)
            wasm.bake_music(source, music_calls)
            self.assertEqual(wasm.asset_import_time_seconds(), 0.0)

            wasm.measure_asset_imports(True, reset=True)
            wasm.bake_images(source, image_calls)
            wasm.bake_sounds(source, sound_calls)
            wasm.bake_music(source, music_calls)
            self.assertGreater(wasm.asset_import_time_seconds(), 0.0)
            wasm.measure_asset_imports(False)


if __name__ == "__main__":
    unittest.main()
