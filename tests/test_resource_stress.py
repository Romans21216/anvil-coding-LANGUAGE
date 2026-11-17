"""Resource lifetime stress: repeated load/destroy cycles must not leak (8.15)."""

from __future__ import annotations

import math
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
HOST = ROOT / "tools" / "wasm_host.mjs"

WIDTH, HEIGHT = 8, 8
CYCLES = 200
SOUND_FRAMES = 400
SOUND_RATE = 8000


def write_bmp(path: pathlib.Path) -> None:
    row = bytes((30, 60, 200)) * WIDTH
    padding = b"\x00" * ((4 - (WIDTH * 3) % 4) % 4)
    data = (row + padding) * HEIGHT
    header = b"BM" + struct.pack("<IHHI", 54 + len(data), 0, 0, 54)
    info = struct.pack(
        "<IiiHHIIiiII", 40, WIDTH, HEIGHT, 1, 24, 0, len(data), 2835, 2835, 0, 0
    )
    path.write_bytes(header + info + data)


def write_wave(path: pathlib.Path) -> None:
    samples = b"".join(
        struct.pack("<h", int(9000 * math.sin(2 * math.pi * 440 * i / SOUND_RATE)))
        for i in range(SOUND_FRAMES)
    )
    header = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE"
    fmt = b"fmt " + struct.pack(
        "<IHHIIHH", 16, 1, 1, SOUND_RATE, SOUND_RATE * 2, 2, 16
    )
    path.write_bytes(header + fmt + b"data" + struct.pack("<I", len(samples)) + samples)


PROGRAM = "\n".join(
    (
        "fn(main)",
        "  set var(i) = 0",
        "  set var(peak) = 0",
        f"  while var(i) < {CYCLES}",
        '    set var(img) = image_load("pic.bmp")',
        "    set var(m) = memory_images()",
        "    if var(m) > var(peak)",
        "      set var(peak) = var(m)",
        "    end",
        "    set var(d) = image_destroy(var(img))",
        '    set var(snd) = sound_load("tone.wav")',
        "    set var(a) = memory_audio()",
        "    set var(d2) = sound_destroy(var(snd))",
        "    set var(i) = compute(var(i) + 1)",
        "  end",
        "  say var(peak)",
        "  say memory_images()",
        "  say memory_audio()",
        "  set var(j) = 0",
        "  while var(j) < 300",
        "    set var(b) = body_create(0, 0, 1, 1)",
        "    set var(k) = body_destroy(var(b))",
        "    set var(j) = compute(var(j) + 1)",
        "  end",
        "  say physics_capacity(128)",
        "  set var(p) = 0",
        "  while var(p) < 100",
        "    set var(e) = particle_emit(0, 0, 1, 1, 1, 2, 255, 0, 0)",
        "    set var(p) = compute(var(p) + 1)",
        "  end",
        "  say particle_count()",
        "  set var(cl) = particle_clear()",
        "  say particle_count()",
        "  set var(s) = 0",
        "  while var(s) < 100",
        '    set var(w) = save_number("stress", var(s))',
        '    set var(x) = save_delete("stress")',
        "    set var(s) = compute(var(s) + 1)",
        "  end",
        '  say save_exists("stress")',
        "end",
        "call fn(main)",
        "",
    )
)


class ResourceStressTests(unittest.TestCase):
    def _expected(self) -> list[str]:
        image_bytes = WIDTH * HEIGHT * 4
        return [
            str(image_bytes),
            "0",
            "0",
            "128",
            "100",
            "0",
            "0",
        ]

    def test_repeated_load_destroy_cycles_leak_nothing_on_c(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_bmp(root / "pic.bmp")
            write_wave(root / "tone.wav")
            source = root / "stress.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            executable = root / "stress.exe"
            build = subprocess.run(
                [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                [str(executable)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
                env={"ANVIL_SAVE_DIR": str(root / "saves")},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), self._expected())

    @unittest.skipUnless(
        subprocess.run(
            ["node", "--version"], capture_output=True, text=True
        ).returncode
        == 0,
        "node is required",
    )
    def test_repeated_load_destroy_cycles_leak_nothing_in_wasm(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
            root = pathlib.Path(temp)
            write_bmp(root / "pic.bmp")
            write_wave(root / "tone.wav")
            source = root / "stress.ANVL"
            source.write_text(PROGRAM, encoding="utf-8")
            out = root / "stress.wasm"
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
                timeout=180,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                ["node", str(HOST), str(out)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
                env={**__import__("os").environ, "ANVIL_WASM_FRAMES": "1"},
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(run.stdout.splitlines(), self._expected())


if __name__ == "__main__":
    unittest.main()
