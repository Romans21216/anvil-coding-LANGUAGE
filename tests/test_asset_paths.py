"""Asset paths computed at runtime, on both backends (8.12).

The C backend resolves `image_load`/`sound_load`/`music_load` paths at run time,
so a path built from a variable works. The browser build bakes assets at compile
time and can only match a literal path, so a computed path there must fail with
a named reason instead of a silent miss - that difference is what these tests
pin, because it is the reason the roadmap lists non-literal paths as a browser
gap rather than a language gap.
"""

from __future__ import annotations

import math
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
HOST = ROOT / "tools" / "wasm_host.mjs"
NEEDS_WASM = all(shutil.which(tool) for tool in ("clang", "node", "wasm-ld"))

PROGRAM = "\n".join(
    (
        "fn(main)",
        "  set var(n) = 1",
        '  set var(name) = "pic" & var(n) & ".bmp"',
        "  set var(a) = image_load(var(name))",
        "  say image_width(var(a))",
        '  say "[" & image_error() & "]"',
        '  set var(sound) = "tone" & var(n) & ".wav"',
        "  set var(s) = sound_load(var(sound))",
        "  say var(s)",
        '  say "[" & sound_error() & "]"',
        "end",
        "call fn(main)",
        "",
    )
)


def write_assets(root: pathlib.Path) -> None:
    side = 8
    row = bytes((20, 40, 200)) * side
    padding = b"\x00" * ((4 - (side * 3) % 4) % 4)
    data = (row + padding) * side
    header = b"BM" + struct.pack("<IHHI", 54 + len(data), 0, 0, 54)
    info = struct.pack(
        "<IiiHHIIiiII", 40, side, side, 1, 24, 0, len(data), 2835, 2835, 0, 0
    )
    (root / "pic1.bmp").write_bytes(header + info + data)

    frames = 4800
    samples = b"".join(
        struct.pack("<h", int(9000 * math.sin(2 * math.pi * 240 * i / 48000)))
        for i in range(frames)
    )
    riff = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE"
    fmt = b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, 48000, 48000 * 2, 2, 16)
    (root / "tone1.wav").write_bytes(
        riff + fmt + b"data" + struct.pack("<I", len(samples)) + samples
    )


def lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").strip().splitlines()


class RuntimeAssetPathTests(unittest.TestCase):
    def test_the_c_backend_loads_a_computed_path(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_assets(root)
            source = root / "paths.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(root / "paths.exe")],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if build.returncode != 0:
                if "No C compiler found" in build.stderr:
                    raise unittest.SkipTest("MSVC is not available")
                self.fail(build.stderr)
            run = subprocess.run(
                [str(root / "paths.exe")],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(lines(run.stdout), ["8", "[]", "1", "[]"])

    @unittest.skipUnless(NEEDS_WASM, "clang, wasm-ld and node are required")
    def test_the_browser_backend_names_a_computed_path(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_assets(root)
            source = root / "paths.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            out = root / "paths.wasm"
            build = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "-o",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        reported = lines(run.stdout)
        self.assertEqual(len(reported), 4, reported)
        self.assertEqual(reported[0], "0")  # no image
        self.assertIn("only literal image_load()", reported[1])
        self.assertEqual(reported[2], "0")  # no sound
        self.assertIn("only literal sound_load()", reported[3])

    @unittest.skipUnless(NEEDS_WASM, "clang, wasm-ld and node are required")
    def test_the_browser_backend_names_a_computed_music_path(self) -> None:
        program = "\n".join(
            (
                "fn(main)",
                "  set var(n) = 1",
                '  set var(name) = "song" & var(n) & ".wav"',
                "  say music_load(var(name))",
                '  say "[" & music_error() & "]"',
                "end",
                "call fn(main)",
                "",
            )
        )
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            source = root / "music.ANVL"
            source.write_text(program, encoding="utf-8")
            out = root / "music.wasm"
            build = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "-o",
                    str(out),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        reported = lines(run.stdout)
        self.assertEqual(reported[0], "0")
        self.assertIn("only the literal music_load()", reported[1])


if __name__ == "__main__":
    unittest.main()
