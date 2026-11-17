"""buffer(on) toggles double buffering; it starts on."""

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

CONTENT = (200, 40, 40)

DRAW = "\n".join(
    (
        "",
        "fn(draw)",
        f"  display rect(0, 0, 960, 600) -rgb({CONTENT[0]}, {CONTENT[1]}, {CONTENT[2]})",
        "end",
        "",
    )
)

TOGGLING = "\n".join(
    (
        "scene 2d",
        "clear rgba(20, 40, 60, 255)",
        "# double buffering starts on, so the first call reports 1",
        "set var(p1) = buffer(1)",
        "set var(p2) = buffer(0)",
        "set var(p3) = buffer(0)",
        "set var(p4) = buffer(1)",
        'set var(s1) = save_number("p1", var(p1))',
        'set var(s2) = save_number("p2", var(p2))',
        'set var(s3) = save_number("p3", var(p3))',
        'set var(s4) = save_number("p4", var(p4))',
    )
) + DRAW

DEFAULT = "\n".join(("scene 2d", "clear rgba(20, 40, 60, 255)")) + DRAW


def read_number(path: pathlib.Path) -> float:
    data = path.read_bytes()
    assert data[:8] == b"ANVSAVE1" and data[8] == 1, data[:9]
    return struct.unpack("<d", data[9:17])[0]


@unittest.skipUnless(os.name == "nt", "window capture uses Win32")
class BufferTests(unittest.TestCase):
    def _run(
        self, root: pathlib.Path, program: str
    ) -> tuple[list[float], tuple[int, int, int]]:
        saves = root / "saves"
        source = root / "buffer.ANVL"
        source.write_text(program, encoding="utf-8")
        executable = root / "buffer.exe"
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
            time.sleep(0.8)
            width, height, raw = reader.grab(0, 0, 960, 600)
        finally:
            process.kill()
            process.wait()
        at = (300 * width + 480) * 4
        pixel = (raw[at + 2], raw[at + 1], raw[at])
        values = [
            read_number(saves / f"p{index}.sav")
            for index in range(1, 5)
            if (saves / f"p{index}.sav").exists()
        ]
        return values, pixel

    def test_double_buffering_starts_on_and_reports_previous_state(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            values, pixel = self._run(root, TOGGLING)
            self.assertEqual(values, [1.0, 1.0, 0.0, 0.0])
            self.assertEqual(pixel, CONTENT)

    def test_a_program_that_never_toggles_still_draws(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            values, pixel = self._run(root, DEFAULT)
            self.assertEqual(values, [])
            self.assertEqual(pixel, CONTENT)


if __name__ == "__main__":
    unittest.main()
