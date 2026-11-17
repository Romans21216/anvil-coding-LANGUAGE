"""Capture the visual examples so a human can review them and CI can gate them (8.15).

The roadmap asks for a manual visual run. Humans still have to judge the
pictures, but this tool makes sure there *are* pictures and that they are not
blank, black, or missing the example's main content, and it stores one PNG per
example under docs/screenshots/ so the review has something stable to look at.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
BUDGETS = ROOT / "tools" / "visual_budgets.json"
SHOTS = ROOT / "docs" / "screenshots"

sys.path.insert(0, str(ROOT / "tests"))
from test_sprite_draw import WindowReader  # noqa: E402  (shared Win32 capture)

# name -> (example source, settle seconds, minimum distinct colours,
#          minimum fraction of pixels that differ from the top-left pixel)
CASES = {
    "sprite_transform": ("examples/sprite_transform_demo.ANVL", 1.0, 6, 0.02),
    "particles": ("examples/particles_demo.ANVL", 1.0, 6, 0.01),
    "physics_boxes": ("examples/physics_boxes.ANVL", 1.0, 4, 0.01),
    "first_world": ("examples/first_world.ANVL", 1.0, 6, 0.02),
    "textured_cube": ("examples/textured_cube.ANVL", 1.0, 6, 0.02),
    "tilemap": ("examples/tilemap_demo.ANVL", 1.0, 6, 0.02),
}


def write_png(path: pathlib.Path, width: int, height: int, bgra: bytes) -> None:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        row = bgra[y * width * 4:(y + 1) * width * 4]
        rgb = bytearray(width * 3)
        rgb[0::3] = row[2::4]
        rgb[1::3] = row[1::4]
        rgb[2::3] = row[0::4]
        rows += rgb

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


def measure(name: str, source: str, settle: float) -> dict[str, object]:
    example = ROOT / source
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        executable = pathlib.Path(temp) / f"{name}.exe"
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(example), "-o", str(executable)],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=ROOT,
        )
        if build.returncode != 0:
            raise SystemExit(f"{name}: build failed\n{build.stderr}")
        process = subprocess.Popen(
            [str(executable)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            reader = WindowReader(process.pid)
            reader.find(time.monotonic() + 10.0)
            time.sleep(settle)
            left, top, right, bottom = reader.client_rect()
            width, height, raw = reader.grab(0, 0, right - left, bottom - top)
        finally:
            process.kill()
            process.wait()

    counts: dict[tuple[int, int, int], int] = {}
    for at in range(0, len(raw), 4):
        pixel = (raw[at + 2], raw[at + 1], raw[at])
        counts[pixel] = counts.get(pixel, 0) + 1
    total = width * height
    background = max(counts, key=counts.get)
    different = total - counts[background]
    colours = set(counts)
    return {
        "name": name,
        "width": width,
        "height": height,
        "distinct_colours": len(colours),
        "background": list(background),
        "non_background": round(different / total, 4) if total else 0.0,
        "_raw": raw,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", help="case name (repeatable)")
    parser.add_argument("--out", type=pathlib.Path, default=SHOTS)
    parser.add_argument("--json", type=pathlib.Path)
    parser.add_argument("--check", action="store_true", help="fail on a blank or drifted frame")
    parser.add_argument("--write-budgets", action="store_true")
    parser.add_argument("--keep-raw", action="store_true")
    arguments = parser.parse_args()

    names = arguments.only or list(CASES)
    unknown = [name for name in names if name not in CASES]
    if unknown:
        parser.error(f"unknown case(s): {', '.join(unknown)}")
    arguments.out.mkdir(parents=True, exist_ok=True)

    budgets = {}
    if BUDGETS.exists():
        budgets = json.loads(BUDGETS.read_text(encoding="utf-8"))
    results = []
    failures = 0
    for name in names:
        source, settle, min_colours, min_content = CASES[name]
        result = measure(name, source, settle)
        raw = result.pop("_raw")
        write_png(arguments.out / f"{name}.png", result["width"], result["height"], raw)
        # Animated scenes vary frame to frame, so the gate allows 15% drift
        # below the recorded baseline rather than demanding an exact match.
        minimum = (budgets.get(name) or {}).get("distinct_colours", min_colours) * 0.85
        content = (budgets.get(name) or {}).get("non_background", min_content) * 0.85
        problems = []
        if result["distinct_colours"] < minimum:
            problems.append(
                f"only {result['distinct_colours']} distinct colours, expected at least {minimum}"
            )
        if result["non_background"] < content:
            problems.append(
                f"{result['non_background']:.1%} of pixels differ from the corner, "
                f"expected at least {content:.1%}"
            )
        result["problems"] = problems
        failures += len(problems)
        results.append(result)
        note = "; ".join(problems) if problems else "ok"
        print(
            f"{name:<18}{result['width']}x{result['height']}  "
            f"{result['distinct_colours']:>5} colours  "
            f"{result['non_background']:>6.1%} content  {note}"
        )

    if arguments.write_budgets:
        BUDGETS.write_text(
            json.dumps(
                {
                    result["name"]: {
                        "distinct_colours": result["distinct_colours"],
                        "non_background": result["non_background"],
                    }
                    for result in results
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {BUDGETS.relative_to(ROOT)}")
    if arguments.json:
        arguments.json.write_text(
            json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8"
        )
    if arguments.check and failures:
        print(f"{failures} visual check(s) failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
