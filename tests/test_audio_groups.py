"""sound_group*: mixer groups, master gain and per-group stop."""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_audio import lines_of, run_c, wav_bytes  # noqa: E402


class SoundGroupApiTests(unittest.TestCase):
    def test_group_assignment_gain_and_clamping(self) -> None:
        source = (
            'set var(s) = sound_load("tone.wav")\n'
            "\n"
            "fn(main)\n"
            "  say sound_group(var(s), 2)\n"
            "  say sound_group(var(s), 4)\n"
            "  say sound_group(var(s), 2.5)\n"
            "  say sound_group(99, 1)\n"
            "  say sound_group_volume(2, 0.5)\n"
            "  say sound_group_volume(2, 4)\n"
            "  say sound_group_volume(7, 0.5)\n"
            "  say sound_group_gain(2)\n"
            "  say sound_group_mute(2, 1)\n"
            "  say sound_group_gain(2)\n"
            "  say sound_group_mute(2, 0)\n"
            "  say sound_group_gain(2)\n"
            "  say sound_group_volume(0, 0.8)\n"
            "  say sound_group_gain(0)\n"
            "  say sound_group_mute(0, 1)\n"
            "  say sound_group_gain(0)\n"
            "  say sound_group_mute(0, 0)\n"
            "end\n"
            "call fn(main)\n"
        )
        result = run_c(source, {"tone.wav": wav_bytes(0.1)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            lines_of(result),
            ["2", "0", "0", "0", "0.5", "1", "0", "1", "1", "0", "0", "1", "0.8", "0.8", "1", "0", "0"],
        )


class SoundGroupStopTests(unittest.TestCase):
    def test_stop_only_affects_the_named_group(self) -> None:
        source = (
            'set var(a) = sound_load("tone.wav")\n'
            'set var(b) = sound_load("tone2.wav")\n'
            "\n"
            "fn(main)\n"
            "  say sound_group(var(a), 1)\n"
            "  say sound_group(var(b), 2)\n"
            "  set var(v1) = sound_play_loop(var(a))\n"
            "  set var(v2) = sound_play_loop(var(b))\n"
            "  if var(v1) = 0 or var(v2) = 0\n"
            '    say "no device"\n'
            "  else\n"
            "    say sound_active()\n"
            "    say sound_group_stop(1)\n"
            "    say sound_active()\n"
            "    say sound_group_stop(2)\n"
            "    say sound_active()\n"
            "  end\n"
            "end\n"
            "call fn(main)\n"
        )
        payload = wav_bytes(0.5)
        result = run_c(source, {"tone.wav": payload, "tone2.wav": payload})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        if lines == ["no device"]:
            self.skipTest("no audio device on this machine")
        self.assertEqual(lines, ["1", "2", "2", "1", "1", "1", "0"])

    def test_group_zero_stops_every_voice(self) -> None:
        source = (
            'set var(a) = sound_load("tone.wav")\n'
            'set var(b) = sound_load("tone2.wav")\n'
            "\n"
            "fn(main)\n"
            "  set var(g1) = sound_group(var(a), 1)\n"
            "  set var(g2) = sound_group(var(b), 3)\n"
            "  set var(v1) = sound_play_loop(var(a))\n"
            "  set var(v2) = sound_play_loop(var(b))\n"
            "  if var(v1) = 0 or var(v2) = 0\n"
            '    say "no device"\n'
            "  else\n"
            "    say sound_active()\n"
            "    say sound_group_stop(0)\n"
            "    say sound_active()\n"
            "  end\n"
            "end\n"
            "call fn(main)\n"
        )
        payload = wav_bytes(0.5)
        result = run_c(source, {"tone.wav": payload, "tone2.wav": payload})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        if lines == ["no device"]:
            self.skipTest("no audio device on this machine")
        self.assertEqual(lines, ["2", "2", "0"])


if __name__ == "__main__":
    unittest.main()
