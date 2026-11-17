"""Measure the baseline a contributor can reproduce.

Part 8 GATE 0 requires checked-in benchmark inputs and machine/build metadata,
not adjectives. This script compiles a representative console workload on both
backends, runs it, and records build latency, artifact size, run time and the
checksum so changes can be compared on the same workload.

    python tools/benchmark.py                # write docs/BENCHMARKS.md
    python tools/benchmark.py --runs 20      # more samples
    python tools/benchmark.py --check-budget # fail if a metric regressed
    python tools/benchmark.py --write-budget # re-record the agreed budget

Part 8 GATE 6 also asks for regression budgets that fail CI when a measured
metric moves past the agreed threshold. The budget lives in
`tools/benchmarks/budgets.json` and is compared against medians, never single
runs, so ordinary scheduling noise does not break the build.
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
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
WORKLOAD = ROOT / "tools" / "benchmarks" / "console_workload.ANVL"
BUDGETS = ROOT / "tools" / "benchmarks" / "budgets.json"
STARTUP_SOURCE = "fn(main)\n output 1\nend\n"
BACKENDS = ("c", "native")

# Part 8 GATE 6: "Set regression budgets; fail CI when agreed thresholds
# regress beyond noise." Timings are noisy, so each metric gets a ratio plus an
# absolute slack. Byte size is deterministic, so it gets a tight ratio and no
# slack. A budget is the *allowed* value, not the observed median.
METRICS = {
    "build_seconds": {"tolerance": 1.35, "slack": 0.05, "unit": "s"},
    "run_seconds": {"tolerance": 1.50, "slack": 0.010, "unit": "s"},
    "startup_seconds": {"tolerance": 1.50, "slack": 0.005, "unit": "s"},
    "exe_bytes": {"tolerance": 1.02, "slack": 0.0, "unit": "B"},
}


def _machine() -> dict:
    from compiler.build import find_compiler

    entry: dict[str, object] = {
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "python": platform.python_version(),
        "bytes_per_pointer": 8,
    }
    try:
        entry["cpu_count"] = __import__("os").cpu_count()
    except NotImplementedError:
        pass
    compiler = find_compiler(None)
    entry["c_compiler"] = compiler[1] if compiler else "not found"
    return entry


def _timed_build(source: pathlib.Path, backend: str, output: pathlib.Path) -> float:
    start = time.perf_counter()
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "compiler.anvil",
            str(source),
            "--backend",
            backend,
            "--output",
            str(output),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if build.returncode != 0:
        raise SystemExit(f"{backend} build failed:\n{build.stdout}{build.stderr}")
    return time.perf_counter() - start


def _timed_run(executable: pathlib.Path, timeout: int = 120) -> tuple[float, str]:
    start = time.perf_counter()
    run = subprocess.run(
        [str(executable)], capture_output=True, text=True, timeout=timeout
    )
    elapsed = time.perf_counter() - start
    if run.returncode != 0:
        raise SystemExit(f"{executable} exited {run.returncode}:\n{run.stdout}{run.stderr}")
    return elapsed, run.stdout.strip()


def _frontend_phases(source: pathlib.Path) -> dict:
    """Time the compiler phases in-process on one source file.

    These are the front-end costs a programmer waits on before the toolchain
    starts: parsing, linting, and lowering to C or to machine code.
    """
    from compiler.codegen import emit_c
    from compiler.lint import lint
    from compiler.native_codegen import NativeCodegen
    from compiler.parser import parse

    text = source.read_text(encoding="utf-8")

    def timed(fn, count: int = 5):
        samples = []
        value = None
        for _ in range(count):
            start = time.perf_counter()
            value = fn()
            samples.append(time.perf_counter() - start)
        return statistics.median(samples), value

    parse_seconds, parsed = timed(lambda: parse(source, text))
    functions, top, variables, arrays = parsed
    lint_seconds, _ = timed(lambda: lint(functions, top))
    c_seconds, _ = timed(lambda: emit_c(source, functions, top, variables, arrays))
    native_seconds, _ = timed(
        lambda: NativeCodegen(source, functions, top, variables, arrays).generate()
    )
    return {
        "parse_seconds": parse_seconds,
        "lint_seconds": lint_seconds,
        "c_codegen_seconds": c_seconds,
        "native_codegen_seconds": native_seconds,
    }


def _samples(fn, count: int) -> list[float]:
    return [fn() for _ in range(count)]


def measure(runs: int) -> dict:
    results: dict[str, object] = {"machine": _machine(), "runs": runs, "backends": {}}
    phases = _frontend_phases(WORKLOAD)
    with tempfile.TemporaryDirectory() as temporary:
        work = pathlib.Path(temporary)
        startup = work / "startup.ANVL"
        startup.write_text(STARTUP_SOURCE, encoding="utf-8")
        for backend in BACKENDS:
            exe = work / f"workload-{backend}.exe"
            builds = _samples(lambda: _timed_build(WORKLOAD, backend, exe), 3)
            size = exe.stat().st_size
            print_checksum = None
            times = []
            for _ in range(runs):
                elapsed, output = _timed_run(exe)
                times.append(elapsed)
                print_checksum = output
            start_exe = work / f"startup-{backend}.exe"
            _timed_build(startup, backend, start_exe)
            startup_times = []
            for _ in range(runs):
                elapsed, _ = _timed_run(start_exe)
                startup_times.append(elapsed)
            results["backends"][backend] = {
                "build_seconds": {
                    "median": statistics.median(builds),
                    "min": min(builds),
                    "max": max(builds),
                    "samples": builds,
                },
                "exe_bytes": size,
                "run_seconds": {
                    "median": statistics.median(times),
                    "min": min(times),
                    "max": max(times),
                    "samples": times,
                },
                "startup_seconds": {
                    "median": statistics.median(startup_times),
                    "min": min(startup_times),
                    "max": max(startup_times),
                    "samples": startup_times,
                },
                "checksum": print_checksum,
                "phases": {
                    "parse_seconds": phases["parse_seconds"],
                    "lint_seconds": phases["lint_seconds"],
                    "codegen_seconds": phases[
                        "c_codegen_seconds" if backend == "c" else "native_codegen_seconds"
                    ],
                },
            }
    return results


def render(results: dict) -> str:
    machine = results["machine"]
    lines = [
        "# Baseline benchmarks",
        "",
        "Generated by `python tools/benchmark.py` from the checked-in workload",
        "`tools/benchmarks/console_workload.ANVL`. Timings are wall-clock on this",
        "machine; compare medians, not single runs. Re-run after runtime or",
        "codegen changes to see whether the workload moved.",
        "",
        "## Machine and toolchain",
        "",
        f"- Platform: {machine['platform']}",
        f"- Processor: {machine['processor']}",
        f"- Python: {machine['python']}",
        f"- C compiler: {machine['c_compiler']}",
        f"- Runs per measurement: {results['runs']}",
        "",
        "## Results",
        "",
        "| Backend | Build median (s) | Build min–max (s) | EXE bytes | Run median (s) | Run min–max (s) | Startup median (s) | Checksum |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for backend, data in results["backends"].items():
        build = data["build_seconds"]
        run = data["run_seconds"]
        startup = data["startup_seconds"]
        lines.append(
            f"| {backend} | {build['median']:.3f} | {build['min']:.3f}–{build['max']:.3f} | "
            f"{data['exe_bytes']} | {run['median']:.3f} | {run['min']:.3f}–{run['max']:.3f} | "
            f"{startup['median']:.3f} | `{data['checksum']}` |"
        )
    lines.append("")
    lines.append("## Compiler phases")
    lines.append("")
    lines.append(
        "Medians over five in-process runs of the same workload, so they exclude "
        "interpreter start-up and the external toolchain."
    )
    lines.append("")
    lines.append(
        "| Backend | Parse (s) | Lint (s) | Codegen (s) | Front end (s) | Toolchain (s) |"
    )
    lines.append("|---|---|---|---|---|---|")
    for backend, data in results["backends"].items():
        phases = data.get("phases") or {}
        if not phases:
            continue
        front = (
            phases["parse_seconds"] + phases["lint_seconds"] + phases["codegen_seconds"]
        )
        toolchain = max(0.0, data["build_seconds"]["median"] - front)
        lines.append(
            f"| {backend} | {phases['parse_seconds']:.4f} | {phases['lint_seconds']:.4f} | "
            f"{phases['codegen_seconds']:.4f} | {front:.4f} | {toolchain:.4f} |"
        )
    lines.append("")
    checksums = {data["checksum"] for data in results["backends"].values()}
    if len(checksums) > 1:
        lines.append(
            "**The backends printed different checksums for the same workload; "
            "that is a semantic defect, not a timing difference.**"
        )
        lines.append("")
    if BUDGETS.exists():
        budget = load_budgets()
        rows, missing = compare_budget(results, budget)
        lines.append(
            render_budget(rows, missing, budget, check_checksums(results, budget))
        )
    return "\n".join(lines)


def _metric_value(backend: dict, metric: str) -> float:
    value = backend[metric]
    if isinstance(value, dict):
        return float(value["median"])
    return float(value)


def flatten(results: dict) -> dict[str, dict[str, float]]:
    """Return ``{backend: {metric: median}}`` from a :func:`measure` result."""
    return {
        backend: {metric: _metric_value(data, metric) for metric in METRICS}
        for backend, data in results["backends"].items()
    }


def load_budgets(path: pathlib.Path = BUDGETS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_budget(
    results: dict,
    path: pathlib.Path = BUDGETS,
    metrics: dict = METRICS,
) -> dict:
    """Record the current medians as the regression budget."""
    budget = {
        "note": (
            "Regression budget for Part 8 GATE 6. Backend values are medians "
            "measured by `python tools/benchmark.py --write-budget`; a metric is "
            "allowed `median * tolerance + slack`. Re-record deliberately when a "
            "change is meant to move the baseline, and keep the same workload, "
            "build settings and machine when comparing."
        ),
        "machine": results["machine"],
        "metrics": {name: dict(spec) for name, spec in metrics.items()},
        "backends": flatten(results),
        "checksums": {
            backend: data.get("checksum")
            for backend, data in results["backends"].items()
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(budget, indent=2) + "\n", encoding="utf-8")
    return budget


def allowed_value(base: float, spec: dict) -> float:
    """Return the allowed value for a budget base under one metric's spec."""
    return float(base) * float(spec.get("tolerance", 1.35)) + float(spec.get("slack", 0.0))


def compare_budget(results: dict, budget: dict) -> tuple[list[dict], list[str]]:
    """Compare measured medians against the budget.

    Returns ``(rows, missing)`` where each row records one metric comparison and
    ``missing`` names backends the budget does not cover. A row is ``ok`` when
    ``actual <= budget * tolerance + slack``.
    """
    declared = budget.get("backends") or {}
    metrics = budget.get("metrics") or METRICS
    rows: list[dict] = []
    missing: list[str] = []
    for backend, measured in flatten(results).items():
        base = declared.get(backend)
        if not base:
            missing.append(backend)
            continue
        for metric in METRICS:
            if metric not in base:
                continue
            spec = metrics.get(metric) or METRICS[metric]
            allowed = allowed_value(base[metric], spec)
            actual = measured[metric]
            rows.append(
                {
                    "backend": backend,
                    "metric": metric,
                    "unit": spec.get("unit", ""),
                    "budget": float(base[metric]),
                    "allowed": allowed,
                    "actual": actual,
                    "ok": actual <= allowed,
                }
            )
    return rows, missing


def check_checksums(results: dict, budget: dict) -> list[str]:
    """Return one line per backend whose printed checksum drifted from the budget."""
    expected = budget.get("checksums") or {}
    mismatches: list[str] = []
    for backend, data in results["backends"].items():
        want = expected.get(backend)
        if want is None:
            continue
        got = data.get("checksum")
        if got != want:
            mismatches.append(f"{backend}: printed {got!r}, budget expects {want!r}")
    return mismatches


def render_budget(
    rows: list[dict],
    missing: list[str],
    budget: dict,
    checksum_mismatches: list[str] | None = None,
) -> str:
    metrics = budget.get("metrics") or METRICS
    lines = [
        "## Regression budgets",
        "",
        "Checked by `python tools/benchmark.py --check-budget`, which exits non-zero",
        "when a measured median exceeds its allowed value. A metric is allowed",
        "`median * tolerance + slack`, so ordinary scheduling noise does not fail",
        "the build.",
        "",
        "| Metric | Tolerance | Slack |",
        "|---|---|---|",
    ]
    for metric, spec in metrics.items():
        lines.append(
            f"| {metric} | ×{float(spec.get('tolerance', 1.35)):.2f} | "
            f"{float(spec.get('slack', 0.0)):g} {spec.get('unit', '')} |"
        )
    lines.append("")
    lines.append("| Backend | Metric | Budget | Allowed | Measured | Status |")
    lines.append("|---|---|---|---|---|---|")
    for row in rows:
        lines.append(
            f"| {row['backend']} | {row['metric']} | {row['budget']:.4g} | "
            f"{row['allowed']:.4g} | {row['actual']:.4g} | "
            f"{'ok' if row['ok'] else '**over budget**'} |"
        )
    for backend in missing:
        lines.append(f"| {backend} | *all* | — | — | — | **no budget recorded** |")
    if not rows and not missing:
        lines.append("| *none* | *none* | — | — | — | no budget file |")
    lines.append("")
    for mismatch in checksum_mismatches or []:
        lines.append(f"**Checksum regression:** {mismatch}")
    if checksum_mismatches:
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10, help="samples per measurement")
    parser.add_argument("--json", action="store_true", help="print raw results as JSON")
    parser.add_argument(
        "--write",
        type=pathlib.Path,
        default=ROOT / "docs" / "BENCHMARKS.md",
        help="markdown report to write",
    )
    parser.add_argument(
        "--budget",
        type=pathlib.Path,
        default=BUDGETS,
        help="regression budget file",
    )
    parser.add_argument(
        "--write-budget",
        action="store_true",
        help="record the current medians as the regression budget",
    )
    parser.add_argument(
        "--check-budget",
        action="store_true",
        help="fail when a measured median exceeds the recorded budget",
    )
    args = parser.parse_args()

    results = measure(args.runs)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        report = render(results)
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(report, encoding="utf-8")
        print(report)
        print(f"wrote {args.write}")

    if args.write_budget:
        budget = write_budget(results, args.budget)
        print(f"wrote budget {args.budget} from {len(budget['backends'])} backend(s)")
        return 0

    if args.check_budget:
        if not args.budget.exists():
            print(
                f"no budget file at {args.budget}; record one with --write-budget",
                file=sys.stderr,
            )
            return 2
        budget = load_budgets(args.budget)
        rows, missing = compare_budget(results, budget)
        checksum_failures = check_checksums(results, budget)
        failures = [row for row in rows if not row["ok"]]
        for row in rows:
            state = "ok" if row["ok"] else "OVER BUDGET"
            print(
                f"{row['backend']:8} {row['metric']:16} "
                f"budget {row['budget']:.4g} allowed {row['allowed']:.4g} "
                f"measured {row['actual']:.4g}  {state}"
            )
        for backend in missing:
            print(f"{backend:8} *                no budget recorded", file=sys.stderr)
        for mismatch in checksum_failures:
            print(f"checksum regression: {mismatch}", file=sys.stderr)
        if failures or missing or checksum_failures:
            print(
                f"benchmark budget failed: {len(failures)} metric(s) over budget, "
                f"{len(missing)} backend(s) unrecorded, "
                f"{len(checksum_failures)} checksum regression(s)",
                file=sys.stderr,
            )
            return 1
        print(f"benchmark budget ok: {len(rows)} metric(s) within budget")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
