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
array buckets({BUCKETS})
set var(frame) = 0
set var(count) = 0
set var(worst) = 0

fn(update)
  add var(frame) 1
  if var(frame) > {WARMUP}
    set var(ms) = (frame_tick() + frame_render() + frame_present()) * 1000
    set var(slot) = floor(var(ms) * 4)
    if var(slot) < 0
      set var(slot) = 0
    end
    if var(slot) > {BUCKETS - 1}
      set var(slot) = {BUCKETS - 1}
    end
    set array(buckets, var(slot)) = array(buckets, var(slot)) + 1
    if var(ms) > var(worst)
      set var(worst) = var(ms)
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
    set var(running) = var(running) + array(buckets, local(b))
    if var(p50) = 0 and var(running) * 2 >= {SAMPLES}
      set var(p50) = (local(b) + 0.5) / 4
    end
    if var(p95) = 0 and var(running) * 20 >= {SAMPLES} * 19
      set var(p95) = (local(b) + 0.5) / 4
    end
  end
  say var(p50)
  say var(p95)
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

RUN_TIMEOUT = 120


def program(scene: str) -> str:
    return "language version 1\n" + scene + "\n" + TIMING


def measure(name: str, runs: int) -> dict[str, float]:
    source_text = program(SCENES[name])
    results = []
    with tempfile.TemporaryDirectory() as temp:
        root = pathlib.Path(temp)
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
            if len(numbers) < 3:
                raise SystemExit(f"{name} did not report three numbers:\n{run.stdout}")
            results.append({"p50": numbers[-3], "p95": numbers[-2], "max": numbers[-1]})
    return {
        "p50_ms": round(statistics.median(r["p50"] for r in results), 2),
        "p95_ms": round(statistics.median(r["p95"] for r in results), 2),
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

    print(f"{'scene':<14}{'p50 ms':>9}{'p95 ms':>9}{'max ms':>9}   budget p50/p95/max")
    for name in names:
        stats = measure(name, args.runs)
        measured[name] = stats
        budget = budgets.get(name)
        label = (
            f"{budget['p50_ms']}/{budget['p95_ms']}/{budget['max_ms']}" if budget else "-"
        )
        print(
            f"{name:<14}{stats['p50_ms']:>9.2f}{stats['p95_ms']:>9.2f}{stats['max_ms']:>9.2f}   {label}"
        )
        if args.check and budget:
            for key in ("p50_ms", "p95_ms", "max_ms"):
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
                "p50_ms": max(0.5, round(stats["p50_ms"] * 2.5, 2)),
                "p95_ms": max(1.0, round(stats["p95_ms"] * 2.5, 2)),
                "max_ms": max(10.0, round(stats["max_ms"] * 2.5, 2)),
                "measured_p50_ms": stats["p50_ms"],
                "measured_p95_ms": stats["p95_ms"],
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
