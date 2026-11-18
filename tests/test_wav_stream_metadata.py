"""Shared acceptance rules for baked and streamed PCM WAV music."""

from __future__ import annotations

import pathlib
import struct
import tempfile
import unittest

from compiler.wasm import _wav_pcm, _wav_stream_info


PCM_GUID = bytes.fromhex("0100000000001000800000aa00389b71")


def wave_bytes(*, extensible: bool = False, subtype: bytes = PCM_GUID,
               byte_rate: int = 32000, block_align: int = 2,
               payload: bytes = b"\x00\x00\x01\x00") -> bytes:
    rate, channels, bits = 16000, 1, 16
    if extensible:
        fmt = (struct.pack("<HHIIHHHHI", 0xFFFE, channels, rate, byte_rate,
                           block_align, bits, 22, bits, 0) + subtype)
    else:
        fmt = struct.pack("<HHIIHH", 1, channels, rate, byte_rate,
                          block_align, bits)
    chunks = (b"fmt " + struct.pack("<I", len(fmt)) + fmt
              + b"data" + struct.pack("<I", len(payload)) + payload)
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


class WavStreamMetadataTests(unittest.TestCase):
    def _read_both(self, data: bytes) -> tuple[object, object]:
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "music.wav"
            path.write_bytes(data)
            results = []
            for reader in (_wav_pcm, _wav_stream_info):
                try:
                    value = reader(path)
                except ValueError as error:
                    value = (type(error), str(error))
                else:
                    value = ("ok", value[:3])
                results.append(value)
            return results[0], results[1]

    def test_pcm_and_extensible_pcm_have_matching_frame_metadata(self) -> None:
        for extensible in (False, True):
            with self.subTest(extensible=extensible):
                baked, streamed = self._read_both(wave_bytes(extensible=extensible))
                self.assertEqual(baked, ("ok", (1, 16000, 2)))
                self.assertEqual(streamed, baked)

    def test_both_readers_reject_unsupported_extensible_subformat_guid(self) -> None:
        non_pcm_guid = bytes.fromhex("0300000000001000800000aa00389b71")
        baked, streamed = self._read_both(
            wave_bytes(extensible=True, subtype=non_pcm_guid)
        )
        self.assertEqual(baked, streamed)
        self.assertEqual(baked[0], ValueError)
        self.assertIn("must contain PCM samples", baked[1])

    def test_both_readers_reject_inconsistent_rate_alignment_and_partial_frames(self) -> None:
        cases = (
            wave_bytes(byte_rate=32001),
            wave_bytes(block_align=4),
            wave_bytes(payload=b"\x00\x00\x01"),
        )
        for data in cases:
            with self.subTest(data_size=len(data)):
                baked, streamed = self._read_both(data)
                self.assertEqual(baked, streamed)
                self.assertEqual(baked[0], ValueError)


if __name__ == "__main__":
    unittest.main()
