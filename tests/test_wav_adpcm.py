"""IMA ADPCM WAV support for sound_load and streaming music (8.14)."""

from __future__ import annotations

import math
import pathlib
import struct
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_audio import lines_of, run_c, wav_bytes  # noqa: E402

IMA_STEP = [
    7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
    50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
    253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
    1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327,
    3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487,
    12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767,
]
IMA_INDEX = [-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8]


def encode_sample(sample: int, state: list[int]) -> int:
    predictor, index = state
    step = IMA_STEP[index]
    diff = sample - predictor
    nibble = 0
    if diff < 0:
        nibble = 8
        diff = -diff
    if diff >= step:
        nibble |= 4
        diff -= step
    if diff >= step >> 1:
        nibble |= 2
        diff -= step >> 1
    if diff >= step >> 2:
        nibble |= 1
    delta = step >> 3
    if nibble & 1:
        delta += step >> 2
    if nibble & 2:
        delta += step >> 1
    if nibble & 4:
        delta += step
    if nibble & 8:
        delta = -delta
    predictor = max(-32768, min(32767, predictor + delta))
    index = max(0, min(88, index + IMA_INDEX[nibble]))
    state[0], state[1] = predictor, index
    return nibble


def adpcm_wav(seconds: float = 2.0, rate: int = 44100, channels: int = 1, block_align: int = 256) -> bytes:
    frames_per_block = (block_align - 4 * channels) * 2 // channels + 1
    total = int(rate * seconds)
    sine = [int(12000.0 * math.sin(2.0 * math.pi * 440.0 * i / rate)) for i in range(total)]
    blocks = bytearray()
    position = 0
    while position < total:
        chunk = sine[position : position + frames_per_block]
        chunk += [0] * (frames_per_block - len(chunk))
        states = [[chunk[0], 0] for _ in range(channels)]
        header = b"".join(struct.pack("<hBB", state[0], 0, 0) for state in states)
        data = bytearray()
        frame = 1
        while frame < frames_per_block:
            for channel in range(channels):
                for byte in range(4):
                    value = 0
                    for half in range(2):
                        index = frame + byte * 2 + half
                        sample = chunk[index] if index < len(chunk) else 0
                        nibble = encode_sample(sample, states[channel])
                        value |= nibble << (4 * half)
                    data.append(value)
            frame += 8
        blocks += header + data
        position += frames_per_block
    header_size = 44 + 6
    fmt = struct.pack(
        "<HHIIHHHH",
        0x0011,
        channels,
        rate,
        rate * block_align // frames_per_block,
        block_align,
        4,
        2,
        frames_per_block,
    )
    data_bytes = bytes(blocks)
    riff = b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data_bytes)) + b"WAVE"
    fmt_chunk = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    data_chunk = b"data" + struct.pack("<I", len(data_bytes)) + data_bytes
    return riff + fmt_chunk + data_chunk


class AdpcmSoundTests(unittest.TestCase):
    def test_sound_load_decodes_and_plays_adpcm(self) -> None:
        source = (
            'set var(ok) = sound_load("compressed.wav")\n'
            "\n"
            "fn(main)\n"
            "  say var(ok)\n"
            "  say sound_error()\n"
            "  set var(voice) = sound_play(var(ok))\n"
            "  say sound_active()\n"
            "  say sound_stop(var(voice))\n"
            "  say sound_active()\n"
            "end\n"
            "call fn(main)\n"
        )
        result = run_c(source, {"compressed.wav": adpcm_wav(0.5)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines_of(result), ["1", "", "1", "1", "0"])


class AdpcmAmplitudeTests(unittest.TestCase):
    def test_decoded_adpcm_keeps_the_pcm_amplitude(self) -> None:
        source = '\n'.join(
            (
                'set var(c) = sound_load("compressed.wav")',
                'set var(p) = sound_load("plain.wav")',
                "",
                "fn(main)",
                "  say round(sound_duration(var(c)) * 100)",
                "  say round(sound_rms(var(c)))",
                "  say round(sound_rms(var(p)))",
                "end",
                "call fn(main)",
                "",
            )
        )
        result = run_c(
            source,
            {
                "compressed.wav": adpcm_wav(0.5),
                "plain.wav": wav_bytes(0.5, 44100, 1, 16),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        self.assertEqual(lines[0], "50")
        adpcm_rms = float(lines[1])
        pcm_rms = float(lines[2])
        self.assertGreater(pcm_rms, 7000, "the reference sine should be audible")
        self.assertLess(
            abs(adpcm_rms - pcm_rms), 600, "ADPCM should track the PCM amplitude"
        )

class AdpcmMusicTests(unittest.TestCase):
    def test_music_streams_adpcm_with_the_right_length(self) -> None:
        source = (
            'set var(ok) = music_load("track.wav")\n'
            "\n"
            "fn(main)\n"
            "  say var(ok)\n"
            "  say music_error()\n"
            "  say round(music_length() * 10)\n"
            "  set var(started) = music_play()\n"
            "  if var(started) = 0\n"
            '    say "no device"\n'
            "    stop\n"
            "  end\n"
            "  wait 0.25\n"
            "  say music_playing()\n"
            "  say music_position()\n"
            "end\n"
            "call fn(main)\n"
        )
        result = run_c(source, {"track.wav": adpcm_wav(2.0)})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        self.assertEqual(lines[0], "1")
        self.assertEqual(lines[1], "")
        self.assertEqual(lines[2], "20", "2 s of ADPCM should report ~2.0 s")
        if lines[3] == "no device":
            self.skipTest("no audio device on this machine")
        self.assertEqual(lines[3], "1")
        position = float(lines[4])
        self.assertGreater(position, 0.05)
        self.assertLess(position, 0.5)


class AdpcmRejectionTests(unittest.TestCase):
    def test_wrong_bit_depth_is_named(self) -> None:
        broken = bytearray(adpcm_wav(0.2))
        # Patch the bits-per-sample field in the fmt chunk (offset 34).
        struct.pack_into("<H", broken, 34, 8)
        source = (
            "fn(main)\n"
            '  say sound_load("bad.wav")\n'
            "  say sound_error()\n"
            '  say music_load("bad.wav")\n'
            "  say music_error()\n"
            "end\n"
            "call fn(main)\n"
        )
        result = run_c(source, {"bad.wav": bytes(broken)})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        self.assertEqual(lines[0], "0")
        self.assertEqual(lines[1], "IMA ADPCM WAV files must be 4-bit")
        self.assertEqual(lines[2], "0")
        self.assertEqual(lines[3], "IMA ADPCM music must be 4-bit")


if __name__ == "__main__":
    unittest.main()
