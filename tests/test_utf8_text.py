"""UTF-8 text: decoding, measurement and fallback glyphs (8.14).

Anvil source is UTF-8 and GDI draws UTF-16, so the width of a string is the
cheapest honest probe that the conversion happened: four accented `e` glyphs
measure about 36 px, four full-width `日` glyphs about 64 px, and if the bytes
were still being drawn as ANSI the same strings would measure roughly 72 and
96 px (8 and 12 mojibake characters).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
sys.path.insert(0, str(ROOT / "tests"))

WIDTH_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(frame) = 0",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        '  display text("héllo → 日本語 ✓") -l(40, 40) -rgb(255, 255, 255)',
        "  if var(frame) = 3",
        '    say "e " & text_width("éééé")',
        '    say "cjk " & text_width("日日日日")',
        '    say "ascii " & text_width("abcd")',
        '    say "q " & text_width("????")',
        "  end",
        "end",
        "",
    )
)

INK_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(frame) = 0",
        "set var(width) = 0",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        '  display text("日日日日日日") -l(40, 60) -rgb(255, 255, 255)',
        "  if var(frame) = 3",
        '    set var(width) = text_width("日日日日日日")',
        '    say "width " & var(width)',
        "    set var(cap) = frame_capture()",
        "    set var(minx) = 999",
        "    set var(maxx) = -1",
        "    for local(x) = 0 to 300",
        "      for local(y) = 55 to 85",
        # The capture marks every texel opaque, so black is exactly
        # 0xFF000000; subtracting it leaves the RGB value for a comparison.
        "        set var(rgb) = image_pixel(var(cap), local(x), local(y)) - 4278190080",
        "        if var(rgb) > 0",
        "          if local(x) < var(minx)",
        "            set var(minx) = local(x)",
        "          end",
        "          if local(x) > var(maxx)",
        "            set var(maxx) = local(x)",
        "          end",
        "        end",
        "      end",
        "    end",
        '    say "ink " & var(minx) & "," & var(maxx)',
        "  end",
        "end",
        "",
    )
)


def build(root: pathlib.Path, program: str, name: str) -> pathlib.Path:
    source = root / f"{name}.ANVL"
    source.write_text(program, encoding="utf-8")
    executable = root / f"{name}.exe"
    result = subprocess.run(
        [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return executable


def run_until(executable: pathlib.Path, root: pathlib.Path, last_key: str,
              timeout: float = 45.0) -> list[str]:
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    lines: list[str] = []
    assert process.stdout is not None
    deadline = time.monotonic() + timeout
    try:
        for line in process.stdout:
            lines.append(line.rstrip("\r\n"))
            if line.startswith(last_key) or time.monotonic() > deadline:
                break
    finally:
        process.kill()
        process.wait(timeout=30)
    return lines


WRAP_PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(0, 0, 0, 255)",
        "set var(frame) = 0",
        "",
        "fn(draw)",
        "  add var(frame) 1",
        # 24 full-width characters, no spaces: only character-level breaking
        # can wrap this at 160 px.
        '  display text("日本語日本語日本語日本語日本語日本語日本語日本語") -l(40, 40) -wrap(160) -rgb(255, 255, 255)',
        "  if var(frame) = 3",
        "    set var(cap) = frame_capture()",
        "    set var(band1) = 0",
        "    set var(band2) = 0",
        "    set var(band3) = 0",
        "    for local(x) = 40 to 220",
        "      for local(y) = 40 to 62",
        "        set var(v) = image_pixel(var(cap), local(x), local(y)) - 4278190080",
        "        if var(v) > 0",
        "          add var(band1) 1",
        "        end",
        "      end",
        "      for local(y) = 66 to 88",
        "        set var(v2) = image_pixel(var(cap), local(x), local(y)) - 4278190080",
        "        if var(v2) > 0",
        "          add var(band2) 1",
        "        end",
        "      end",
        "      for local(y) = 92 to 114",
        "        set var(v3) = image_pixel(var(cap), local(x), local(y)) - 4278190080",
        "        if var(v3) > 0",
        "          add var(band3) 1",
        "        end",
        "      end",
        "    end",
        '    say "bands " & var(band1) & "," & var(band2) & "," & var(band3)',
        "  end",
        "end",
        "",
    )
)

class Utf8TextTests(unittest.TestCase):
    def test_wide_glyphs_measure_as_wide_and_accented_ones_do_not(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, WIDTH_PROGRAM, "widths")
            lines = run_until(executable, root, "q ")
            values: dict[str, int] = {}
            for line in lines:
                key, _, value = line.partition(" ")
                if key in ("e", "cjk", "ascii", "q"):
                    values[key] = int(float(value))
            self.assertEqual(sorted(values), ["ascii", "cjk", "e", "q"], lines)
            # Four narrow accented glyphs; ANSI mojibake would be about twice this.
            self.assertGreaterEqual(values["e"], 28)
            self.assertLessEqual(values["e"], 46)
            # Four full-width Japanese glyphs; ANSI mojibake (12 chars) would be
            # well over 80 px.
            self.assertGreaterEqual(values["cjk"], 54)
            self.assertLessEqual(values["cjk"], 80)
            self.assertGreater(values["cjk"], values["e"] * 1.4)
            self.assertGreaterEqual(values["ascii"], 28)
            self.assertLessEqual(values["ascii"], 46)

    def test_drawn_glyphs_cover_the_measured_width(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, INK_PROGRAM, "ink")
            lines = run_until(executable, root, "ink ")
            values: dict[str, str] = {}
            for line in lines:
                key, _, value = line.partition(" ")
                if key in ("width", "ink"):
                    values[key] = value
            self.assertEqual(sorted(values), ["ink", "width"], lines)
            width = int(float(values["width"]))
            left, _, right = values["ink"].partition(",")
            left_px, right_px = int(float(left)), int(float(right))
            # Six full-width glyphs start at x=40 and the ink must reach well
            # past half the measured width, inside the measured width plus a
            # little overhang from antialiasing.
            self.assertGreaterEqual(left_px, 38)
            self.assertGreaterEqual(right_px, 40 + width // 2)
            self.assertLessEqual(right_px, 40 + width + 4)


    def test_unspaced_cjk_wraps_at_character_boundaries(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            executable = build(root, WRAP_PROGRAM, "wrap")
            lines = run_until(executable, root, "bands ")
            match = [line for line in lines if line.startswith("bands ")]
            self.assertTrue(match, lines)
            counts = [int(float(part)) for part in match[0].split(" ", 1)[1].split(",")]
            self.assertEqual(len(counts), 3)
            # Every one of the three lines must carry ink; a wrap that gave up
            # would put everything on line 1 and leave 2 and 3 empty.
            for index, count in enumerate(counts, 1):
                self.assertGreater(count, 20, f"line {index} has too little ink: {counts}")


if __name__ == "__main__":
    unittest.main()
