"""Runtime frame-time benchmarks with enforced budgets (Part 8, 8.15).

Each scene is an ordinary Anvil program: 60 warm-up frames are skipped, then
120 frame times are bucketed at 0.25 ms resolution and reported as p50, p95
and worst. Buckets avoid a runtime sort and keep the program small. The loop runs at a
fixed 60 Hz, so one scene costs about (warm-up + samples) / 60 seconds.

Usage:
    python tools/bench_runtime.py                 # measure, print, no gate
    python tools/bench_runtime.py --check         # exit 1 when a budget is missed
    python tools/bench_runtime.py --write-budgets # re-baseline this machine
"""

from __future__ import annotations

import argparse
import json
import pathlib
import platform
import statistics
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
BUDGETS = ROOT / "tools" / "bench_budgets.json"
SAMPLES = 120
WARMUP = 30
BUCKETS = 400  # 0.25 ms each, so 0..100 ms

TIMING = f"""
array work_buckets({BUCKETS})
array present_buckets({BUCKETS})
set var(frame) = 0
set var(count) = 0
set var(worst) = 0

fn(update)
  add var(frame) 1
  if var(frame) > {WARMUP}
    set var(work) = (frame_tick() + frame_render()) * 1000
    set var(present) = frame_present() * 1000
    set var(slot) = floor(var(work) * 4)
    if var(slot) < 0
      set var(slot) = 0
    end
    if var(slot) > {BUCKETS - 1}
      set var(slot) = {BUCKETS - 1}
    end
    set array(work_buckets, var(slot)) = array(work_buckets, var(slot)) + 1
    set var(pslot) = floor(var(present) * 4)
    if var(pslot) < 0
      set var(pslot) = 0
    end
    if var(pslot) > {BUCKETS - 1}
      set var(pslot) = {BUCKETS - 1}
    end
    set array(present_buckets, var(pslot)) = array(present_buckets, var(pslot)) + 1
    if var(work) > var(worst)
      set var(worst) = var(work)
    end
    add var(count) 1
  end
  if var(count) = {SAMPLES}
    call fn(report)
    stop
  end
end

fn(report)
  set var(running) = 0
  set var(p50) = 0
  set var(p95) = 0
  for local(b) = 0 to {BUCKETS - 1}
    set var(running) = var(running) + array(work_buckets, local(b))
    if var(p50) = 0 and var(running) * 2 >= {SAMPLES}
      set var(p50) = (local(b) + 0.5) / 4
    end
    if var(p95) = 0 and var(running) * 20 >= {SAMPLES} * 19
      set var(p95) = (local(b) + 0.5) / 4
    end
  end
  set var(running) = 0
  set var(pp50) = 0
  set var(pp95) = 0
  for local(b) = 0 to {BUCKETS - 1}
    set var(running) = var(running) + array(present_buckets, local(b))
    if var(pp50) = 0 and var(running) * 2 >= {SAMPLES}
      set var(pp50) = (local(b) + 0.5) / 4
    end
    if var(pp95) = 0 and var(running) * 20 >= {SAMPLES} * 19
      set var(pp95) = (local(b) + 0.5) / 4
    end
  end
  say var(p50)
  say var(p95)
  say var(pp50)
  say var(pp95)
  say var(worst)
end
"""

SCENES = {
    "idle_2d": "\n".join(
        (
            "scene 2d",
            "clear rgba(10, 12, 18, 255)",
            "",
            "fn(draw)",
            "  set var(noop) = 0",
            "end",
        )
    ),
    "overdraw_2d": "\n".join(
        (
            "scene 2d",
            "clear rgba(10, 12, 18, 255)",
            "",
            "fn(draw)",
            "  for local(gx) = 0 to 59",
            "    for local(gy) = 0 to 19",
            "      display rect(local(gx) * 16, local(gy) * 16, 15, 15) -rgb(40, 90, 160)",
            "    end",
            "  end",
            "  for local(c) = 0 to 119",
            "    display circle(480, 300, 40 + local(c) * 0.5) -rgb(200, 120, 60)",
            "  end",
            "end",
        )
    ),
    "text_ui": "\n".join(
        (
            "scene 2d",
            "clear rgba(10, 12, 18, 255)",
            "",
            "fn(draw)",
            "  for local(t) = 0 to 39",
            '    display text("HUD line 0123456789") -l(80, 40 + local(t) * 12) -rgb(220, 230, 240)',
            "  end",
            "end",
        )
    ),
    "particles_2d": "\n".join(
        (
            "scene 2d",
            "clear rgba(10, 12, 18, 255)",
            "",
            "fn(draw)",
            "  for local(i) = 0 to 39",
            "    set var(e) = particle_emit(480, 300, 60, 40, 2, 3, 255, 120, 0)",
            "  end",
            "end",
        )
    ),
    "tilemap_large": "\n".join(
        (
            "scene 2d",
            "clear rgba(10, 12, 18, 255)",
            'set var(sheet) = image_load("tiles.bmp")',
            "set var(map) = tilemap_new(var(sheet), 8, 8, 512, 512)",
            "set var(ok) = tilemap_fill(var(map), -1)",
            "set var(ok) = tilemap_area(var(map), 1, 0, 0, 4, 4)",
            "set var(ok) = tilemap_area(var(map), 2, 200, 300, 40, 40)",
            "",
            "fn(draw)",
            "  set var(drawn) = tilemap_draw(var(map), 0, 0, 1)",
            "end",
        )
    ),
    "cubes_3d": "\n".join(
        (
            "scene 3d",
            "camera perspective 0 3 12",
            "camera fov(70)",
            "clear rgba(11, 16, 27, 255)",
            "",
            "fn(draw)",
            "  display plane(0, -1, 0, 14, 14) -rgb(33, 47, 64)",
            "  for local(x) = 0 to 3",
            "    for local(z) = 0 to 4",
            "      display cube(local(x) * 2 - 3, 0, local(z) * 2 - 4, 1.4) -rgb(88, 164, 255) -rotate(0, local(x) * 10 + local(z) * 5, 0)",
            "    end",
            "  end",
            "end",
        )
    ),
}


def ray_sphere_scene(columns: int, rows: int) -> str:
    """Build a fixed grid of traced spheres for BVH scaling measurements."""
    x_offset = (columns - 1) * 0.65
    y_offset = (rows - 1) * 0.65
    return "\n".join(
        (
            "scene 3d",
            "camera perspective 0 0 12",
            "camera fov(70)",
            "clear rgba(11, 16, 27, 255)",
            "",
            "fn(draw)",
            f"  for local(x) = 0 to {columns - 1}",
            f"    for local(y) = 0 to {rows - 1}",
            f"      display ray_sphere(local(x) * 1.3 - {x_offset:g}, local(y) * 1.3 - {y_offset:g}, -1, 0.45) -rgb(172, 106, 255)",
            "    end",
            "  end",
            "end",
        )
    )


SCENES.update(
    {
        "ray_spheres_1": ray_sphere_scene(1, 1),
        "ray_spheres_8": ray_sphere_scene(4, 2),
        "ray_spheres_32": ray_sphere_scene(8, 4),
    }
)

RUN_TIMEOUT = 120


def program(scene: str) -> str:
    return "language version 1\n" + scene + "\n" + TIMING



def write_tileset(path):
    """An 8x8 grid of 8 px solid tiles, matching the tilemap bench scenes."""
    import struct

    tile, columns, rows = 8, 8, 8
    width, height = tile * columns, tile * rows
    colours = [(200, 60, 60), (60, 180, 90), (70, 110, 220), (220, 200, 80)]
    palette = [colours[(x + y) % len(colours)] for y in range(rows) for x in range(columns)]
    body = bytearray()
    for y in range(height - 1, -1, -1):
        for x in range(width):
            r, g, b = palette[(y // tile) * columns + (x // tile)]
            body += bytes((b, g, r, 255))
    header = bytearray(54)
    header[0:2] = b"BM"
    struct.pack_into("<I", header, 2, 54 + len(body))
    struct.pack_into("<I", header, 10, 54)
    struct.pack_into("<I", header, 14, 40)
    struct.pack_into("<i", header, 18, width)
    struct.pack_into("<i", header, 22, height)
    struct.pack_into("<H", header, 26, 1)
    struct.pack_into("<H", header, 28, 32)
    struct.pack_into("<I", header, 34, len(body))
    path.write_bytes(bytes(header) + bytes(body))


def measure(name: str, runs: int) -> dict[str, float]:
    source_text = program(SCENES[name])
    results = []
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
        write_tileset(root / "tiles.bmp")
        source = root / f"{name}.ANVL"
        source.write_text(source_text, encoding="utf-8")
        executable = root / f"{name}.exe"
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
        )
        if build.returncode != 0:
            raise SystemExit(f"build failed for {name}:\n{build.stderr}")
        for _ in range(runs):
            run = subprocess.run(
                [str(executable)],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=RUN_TIMEOUT,
            )
            if run.returncode != 0:
                raise SystemExit(f"{name} exited {run.returncode}:\n{run.stderr}")
            numbers = [
                float(line)
                for line in run.stdout.splitlines()
                if line.strip() and line.replace(".", "", 1).replace("-", "", 1).isdigit()
            ]
            if len(numbers) < 5:
                raise SystemExit(f"{name} did not report five numbers:\n{run.stdout}")
            results.append(
                {
                    "work_p50": numbers[-5],
                    "work_p95": numbers[-4],
                    "present_p50": numbers[-3],
                    "present_p95": numbers[-2],
                    "max": numbers[-1],
                }
            )
    return {
        "work_p50_ms": round(statistics.median(r["work_p50"] for r in results), 2),
        "work_p95_ms": round(statistics.median(r["work_p95"] for r in results), 2),
        "present_p50_ms": round(statistics.median(r["present_p50"] for r in results), 2),
        "present_p95_ms": round(statistics.median(r["present_p95"] for r in results), 2),
        "max_ms": round(min(r["max"] for r in results), 2),
    }


def load_budgets() -> dict:
    return json.loads(BUDGETS.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when a budget is exceeded")
    parser.add_argument("--write-budgets", action="store_true", help="record measured budgets")
    parser.add_argument("--runs", type=int, default=3, help="repetitions per scene (default 3)")
    parser.add_argument("--scene", action="append", choices=sorted(SCENES), help="limit to a scene")
    args = parser.parse_args(argv)

    names = args.scene or sorted(SCENES)
    budgets = load_budgets().get("runtime", {}).get("scenes", {})
    measured: dict[str, dict[str, float]] = {}
    failures: list[str] = []

    print(
        f"{'scene':<14}{'work p50':>9}{'work p95':>9}{'pres p95':>9}{'max':>7}"
        "   budget work p50/p95, present p95"
    )
    for name in names:
        stats = measure(name, args.runs)
        measured[name] = stats
        budget = budgets.get(name)
        if budget and "work_p50_ms" in budget:
            label = (
                f"{budget['work_p50_ms']}/{budget['work_p95_ms']}/"
                f"{budget['present_p95_ms']}"
            )
        elif budget:
            label = f"{budget.get('p50_ms', '-')}/{budget.get('p95_ms', '-')}/-"
        else:
            label = "-"
        print(
            f"{name:<14}{stats['work_p50_ms']:>9.2f}{stats['work_p95_ms']:>9.2f}"
            f"{stats['present_p95_ms']:>9.2f}{stats['max_ms']:>7.2f}   {label}"
        )
        if args.check and budget and "work_p50_ms" in budget:
            for key in ("work_p50_ms", "work_p95_ms", "present_p95_ms"):
                if stats[key] > budget[key]:
                    failures.append(
                        f"{name} {key} {stats[key]:.2f} > budget {budget[key]:.2f}"
                    )

    if args.write_budgets:
        document = load_budgets()
        runtime = document.setdefault("runtime", {})
        runtime["samples"] = SAMPLES
        runtime["warmup"] = WARMUP
        runtime["machine"] = platform.platform()
        scenes = runtime.setdefault("scenes", {})
        for name, stats in measured.items():
            scenes[name] = {
                "work_p50_ms": max(0.5, round(stats["work_p50_ms"] * 2.5, 2)),
                "work_p95_ms": max(2.0, round(stats["work_p95_ms"] * 2.5, 2)),
                "present_p95_ms": max(3.0, round(stats["present_p95_ms"] * 2.5, 2)),
                "measured_work_p50_ms": stats["work_p50_ms"],
                "measured_work_p95_ms": stats["work_p95_ms"],
                "measured_present_p50_ms": stats["present_p50_ms"],
                "measured_present_p95_ms": stats["present_p95_ms"],
                "measured_max_ms": stats["max_ms"],
            }
        BUDGETS.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"wrote runtime budgets to {BUDGETS.relative_to(ROOT)}")

    if failures:
        print("\nBudget failures:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    if args.check:
        print("runtime budgets: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
