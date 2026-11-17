"""-wrap(width) and text_width() lay text out by measured width (8.14)."""

from __future__ import annotations

import os
import pathlib
import struct
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"

sys.path.insert(0, str(ROOT / "tests"))
from test_sprite_draw import WindowReader  # noqa: E402

MESSAGE = "The quick brown fox jumps over the lazy dog and keeps running"
BACKGROUND = (10, 12, 18)

PROGRAM = "\n".join(
    (
        "scene 2d",
        "clear rgba(10, 12, 18, 255)",
        f'set var(msg) = "{MESSAGE}"',
        "",
        "fn(draw)",
        "  display text(var(msg)) -l(40, 40) -wrap(300) -rgb(230, 240, 250)",
        '  set var(saved) = save_number("width", text_width(var(msg)))',
        "end",
        "",
    )
)


def read_number(path: pathlib.Path) -> float:
    data = path.read_bytes()
    assert data[:8] == b"ANVSAVE1" and data[8] == 1
    return struct.unpack("<d", data[9:17])[0]


@unittest.skipUnless(os.name == "nt", "window capture uses Win32")
class TextWrapTests(unittest.TestCase):
    def test_a_long_line_wraps_and_reports_its_width(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            saves = root / "saves"
            source = root / "wrap.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "wrap.exe"
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            process = subprocess.Popen(
                [str(executable)],
                cwd=root,
                stdout=subprocess.DEVNULL,
                env={**os.environ, "ANVIL_SAVE_DIR": str(saves)},
            )
            try:
                reader = WindowReader(process.pid)
                reader.find(time.monotonic() + 10.0)
                time.sleep(1.0)
                width, height, raw = reader.grab(0, 0, 960, 600)
            finally:
                process.kill()
                process.wait()

            def ink_in_band(top: int, bottom: int) -> int:
                count = 0
                for y in range(top, bottom):
                    for x in range(30, 400):
                        at = (y * width + x) * 4
                        pixel = (raw[at + 2], raw[at + 1], raw[at])
                        if pixel != BACKGROUND:
                            count += 1
                return count

            # The wrapped block draws at y=40 and y=67 (20 px font, 1.35 spacing).
            self.assertGreater(ink_in_band(40, 62), 50, "first wrapped line is missing")
            self.assertGreater(ink_in_band(66, 90), 50, "second wrapped line is missing")

            measured = read_number(saves / "width.sav")
            self.assertGreater(measured, 380.0)
            self.assertLess(measured, 620.0)

    def test_the_modifier_and_builtin_are_refused_in_wasm(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "wrap.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            build = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "-o",
                    str(root / "wrap.wasm"),
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertNotEqual(build.returncode, 0)
            self.assertIn("wasm", build.stderr)


if __name__ == "__main__":
    unittest.main()
