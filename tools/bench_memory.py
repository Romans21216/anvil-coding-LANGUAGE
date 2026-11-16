"""Memory benchmarks with enforced budgets (Part 8, 8.15).

Measures the two costs the frame-time benchmarks cannot see:

* the peak working set of a cold compile, sampled across the compiler and its
  ``cl.exe`` children, plus the generated C and executable size;
* the peak working set of each benchmark scene while it runs.

Sampling every 20 ms (compile) and 50 ms (runtime) undercounts short spikes, so
budgets are set from measured medians with generous headroom rather than treated
as exact measurements.

Usage:
    python tools/bench_memory.py                  # measure, print, no gate
    python tools/bench_memory.py --check          # exit 1 when a budget is missed
    python tools/bench_memory.py --write-budgets  # re-baseline this machine
    python tools/bench_memory.py --scene idle_2d  # one scene only
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time

import psutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
BUDGETS = ROOT / "tools" / "mem_budgets.json"
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from bench_runtime import SCENES, program  # noqa: E402

COMPILE_SAMPLE_SECONDS = 0.02
RUN_SAMPLE_SECONDS = 0.05
RUN_SECONDS = 4.0
MB = 1024.0 * 1024.0
BUDGET_HEADROOM = 2.5
COMPILE_FLOOR_MB = 200.0
RUN_FLOOR_MB = 60.0


def process_tree_bytes(root_pid: int) -> int:
    """Resident bytes of a process and its descendants, or 0 if it is gone."""
    try:
        parent = psutil.Process(root_pid)
        total = parent.memory_info().rss
    except psutil.Error:
        return 0
    try:
        children = parent.children(recursive=True)
    except psutil.Error:
        children = []
    for child in children:
        try:
            total += child.memory_info().rss
        except psutil.Error:
            continue
    return total


def measure_compile(name: str, root: pathlib.Path) -> dict[str, float]:
    source = root / f"{name}.ANVL"
    executable = root / f"{name}.exe"
    generated = root / f"{name}.c"
    source.write_text(program(SCENES[name]), encoding="utf-8")
    command = [
        sys.executable,
        str(COMPILER),
        str(source),
        "--generated-c",
        str(generated),
        "-o",
        str(executable),
    ]
    started = time.perf_counter()
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    peak = 0
    while process.poll() is None:
        peak = max(peak, process_tree_bytes(process.pid))
        time.sleep(COMPILE_SAMPLE_SECONDS)
    _, error = process.communicate()
    elapsed = time.perf_counter() - started
    if process.returncode != 0:
        raise SystemExit(f"build failed for {name}:\n{error}")
    return {
        "compile_ms": round(elapsed * 1000.0, 1),
        "compile_peak_mb": round(max(peak, 1) / MB, 1),
        "generated_bytes": generated.stat().st_size if generated.exists() else 0,
        "exe_bytes": executable.stat().st_size if executable.exists() else 0,
        "executable": str(executable),
    }


def measure_run(name: str, root: pathlib.Path, executable: pathlib.Path) -> dict[str, float]:
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    peak = 0
    started = time.perf_counter()
    while process.poll() is None and time.perf_counter() - started < RUN_SECONDS:
        peak = max(peak, process_tree_bytes(process.pid))
        time.sleep(RUN_SAMPLE_SECONDS)
    if process.poll() is None:
        process.kill()
    process.wait()
    return {
        "run_ms": round((time.perf_counter() - started) * 1000.0, 1),
        "run_peak_mb": round(max(peak, 1) / MB, 1),
    }


def measure(name: str) -> dict[str, float]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        root = pathlib.Path(temp)
        build = measure_compile(name, root)
        executable = pathlib.Path(build.pop("executable"))
        run = measure_run(name, root, executable)
    return {"scene": name, **build, **run}


def load_budgets() -> dict:
    if not BUDGETS.exists():
        return {"compile_peak_mb": COMPILE_FLOOR_MB, "run_peak_mb": {}}
    return json.loads(BUDGETS.read_text(encoding="utf-8"))


def write_budgets(results: list[dict[str, float]]) -> None:
    compile_peak = max(
        COMPILE_FLOOR_MB,
        max(result["compile_peak_mb"] for result in results) * BUDGET_HEADROOM,
    )
    run_budgets = {
        result["scene"]: round(
            max(RUN_FLOOR_MB, result["run_peak_mb"] * BUDGET_HEADROOM), 1
        )
        for result in results
    }
    document = {
        "compile_peak_mb": round(compile_peak, 1),
        "run_peak_mb": run_budgets,
        "note": "2.5x the measured peak with floors; re-baseline on new hardware",
    }
    BUDGETS.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {BUDGETS.relative_to(ROOT)}")


def check(results: list[dict[str, float]], budgets: dict) -> int:
    failures = 0
    compile_budget = float(budgets.get("compile_peak_mb", COMPILE_FLOOR_MB))
    run_budgets = budgets.get("run_peak_mb", {})
    for result in results:
        scene = result["scene"]
        if result["compile_peak_mb"] > compile_budget:
            print(
                f"{scene}: compile peak {result['compile_peak_mb']} MB over budget "
                f"{compile_budget} MB"
            )
            failures += 1
        budget = float(run_budgets.get(scene, RUN_FLOOR_MB))
        if result["run_peak_mb"] > budget:
            print(
                f"{scene}: run peak {result['run_peak_mb']} MB over budget {budget} MB"
            )
            failures += 1
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 on a budget miss")
    parser.add_argument(
        "--write-budgets", action="store_true", help="re-baseline mem_budgets.json"
    )
    parser.add_argument("--json", type=pathlib.Path, help="write results to a file")
    parser.add_argument(
        "--scene",
        action="append",
        choices=sorted(SCENES),
        help="limit the run to one scene (repeatable)",
    )
    arguments = parser.parse_args(argv)

    names = arguments.scene or list(SCENES)
    results = [measure(name) for name in names]

    print(f"{'scene':<14}{'compile':>10}{'C bytes':>10}{'exe bytes':>12}{'run peak':>10}")
    for result in results:
        print(
            f"{result['scene']:<14}{result['compile_peak_mb']:>8.1f} MB"
            f"{result['generated_bytes']:>10}"
            f"{result['exe_bytes']:>12}"
            f"{result['run_peak_mb']:>8.1f} MB"
        )

    if arguments.write_budgets:
        write_budgets(results)

    if arguments.json:
        arguments.json.write_text(
            json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8"
        )
        print(f"wrote {arguments.json}")

    if arguments.check:
        failures = check(results, load_budgets())
        if failures:
            print(f"{failures} memory budget(s) missed")
            return 1
        print("memory budgets hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
