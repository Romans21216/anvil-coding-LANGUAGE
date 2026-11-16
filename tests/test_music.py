"""music_*: streaming WAV playback, position, looping and diagnostics."""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from test_audio import lines_of, run_c, wav_bytes  # noqa: E402


class MusicLoadTests(unittest.TestCase):
    def test_length_volume_and_rejections(self) -> None:
        source = (
            'set var(ok) = music_load("song.wav")\n'
            "\n"
            "fn(main)\n"
            "  say var(ok)\n"
            "  say round(music_length() * 100)\n"
            "  say music_volume(0.5)\n"
            "  say music_volume(2)\n"
            "  say music_volume(0)\n"
            "  say music_playing()\n"
            "  say music_position()\n"
            "  say music_stop()\n"
            "  say music_error()\n"
            "end\n"
            "call fn(main)\n"
        )
        result = run_c(source, {"song.wav": wav_bytes(2.0, 44100, 1, 16)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            lines_of(result), ["1", "200", "0.5", "1", "0", "0", "0", "1", ""]
        )

    def test_bad_files_name_the_reason(self) -> None:
        source = (
            "fn(main)\n"
            '  say music_load("missing.wav")\n'
            "  say music_error()\n"
            '  say music_load("notwav.bin")\n'
            "  say music_error()\n"
            '  say music_load("three.wav")\n'
            "  say music_error()\n"
            '  say music_load("deep.wav")\n'
            "  say music_error()\n"
            '  say music_load("empty.wav")\n'
            "  say music_error()\n"
            "end\n"
            "call fn(main)\n"
        )
        files = {
            "notwav.bin": b"this is not a wave file at all",
            "three.wav": wav_bytes(0.1, 44100, 3, 16),
            "deep.wav": wav_bytes(0.1, 44100, 1, 24),
            "empty.wav": wav_bytes(0.001, 44100, 1, 16)[:44],
        }
        result = run_c(source, files)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        self.assertEqual(lines[0], "0")
        self.assertEqual(lines[1], "cannot open the file")
        self.assertEqual(lines[2], "0")
        self.assertEqual(lines[3], "not a readable WAV file")
        self.assertEqual(lines[4], "0")
        self.assertEqual(lines[5], "only mono and stereo music is supported")
        self.assertEqual(lines[6], "0")
        self.assertEqual(lines[7], "music must be 8-bit or 16-bit PCM")


class MusicPlaybackTests(unittest.TestCase):
    def test_play_reports_position_and_stop_rewinds(self) -> None:
        source = (
            'set var(ok) = music_load("song.wav")\n'
            "\n"
            "fn(main)\n"
            "  set var(started) = music_play()\n"
            "  if var(started) = 0\n"
            '    say "no device"\n'
            "  else\n"
            "    wait 0.25\n"
            "    say music_playing()\n"
            "    say music_position()\n"
            "    say music_stop()\n"
            "    say music_playing()\n"
            "    say music_position()\n"
            "  end\n"
            "end\n"
            "call fn(main)\n"
        )
        result = run_c(source, {"song.wav": wav_bytes(1.0, 48000, 1, 16)})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        if lines == ["no device"]:
            self.skipTest("no audio device on this machine")
        self.assertEqual(lines[0], "1")
        position = float(lines[1])
        self.assertGreater(position, 0.1)
        self.assertLess(position, 0.45)
        self.assertEqual(lines[2:], ["1", "0", "0"])

    def test_a_short_track_finishes_and_a_loop_keeps_playing(self) -> None:
        finish = (
            'set var(ok) = music_load("short.wav")\n'
            "\n"
            "fn(main)\n"
            "  set var(started) = music_play()\n"
            "  if var(started) = 0\n"
            '    say "no device"\n'
            "    stop\n"
            "  end\n"
            "  wait 0.5\n"
            "  say music_playing()\n"
            "end\n"
            "call fn(main)\n"
        )
        result = run_c(finish, {"short.wav": wav_bytes(0.2, 48000, 1, 16)})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        if lines == ["no device"]:
            self.skipTest("no audio device on this machine")
        self.assertEqual(lines, ["0"], "a finished track should stop itself")

        loop = (
            'set var(ok) = music_load("short.wav")\n'
            "\n"
            "fn(main)\n"
            "  set var(started) = music_play_loop()\n"
            "  if var(started) = 0\n"
            '    say "no device"\n'
            "    stop\n"
            "  end\n"
            "  wait 0.5\n"
            "  say music_playing()\n"
            "  say music_position()\n"
            "end\n"
            "call fn(main)\n"
        )
        result = run_c(loop, {"short.wav": wav_bytes(0.2, 48000, 1, 16)})
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = lines_of(result)
        self.assertEqual(lines[0], "1", "a looping track must keep playing")
        self.assertLess(float(lines[1]), 0.2, "position should wrap on each loop")


if __name__ == "__main__":
    unittest.main()
