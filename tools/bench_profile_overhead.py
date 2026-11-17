"""Measure disabled timing-hook overhead across representative compile work.

This compares the in-process parse/lower/emit/import pipeline with and without
the `Timings(False)` object and its normal CLI boundary calls. It excludes
subprocess startup and linker noise. Detailed JSON tracing is disabled in both
paths. The median paired overhead must stay below 2 percent.
"""

from __future__ import annotations

import argparse
import pathlib
import statistics
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from bench_build_profiles import SOURCES, _write_assets  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.timing import DISABLED_TIMINGS, Timings  # noqa: E402
from compiler import gltf, wasm  # noqa: E402

BATCH_SIZE = 100


def _compile_once(case: str, source_path: pathlib.Path, with_disabled_hooks: bool) -> None:
    timings = DISABLED_TIMINGS if with_disabled_hooks else None
    if timings:
        timings.mark("read")
    source = source_path.read_text(encoding="utf-8")
    if timings:
        timings.set_metadata(source_bytes=source_path.stat().st_size)
    functions, top, variables, arrays = parse(source_path, source)
    if timings:
        timings.mark("parse")
    wasm.validate(source_path, functions, top)
    generated = emit_c(
        source_path,
        functions,
        top,
        variables,
        arrays,
        runtime_header="anvil_wasm.h",
        minimal_includes=True,
    )
    generated += wasm.bake_images(source_path, source)
    generated += wasm.bake_sounds(source_path, source)
    generated += wasm.bake_music(source_path, source)
    if timings:
        timings.mark("generate")
        timings.report()
    # Keep the generated result live through the measured function boundary.
    if not generated:
        raise RuntimeError("compiler generated no source")


def measure_case(case: str, runs: int) -> dict:
    ratios = []
    baseline_ms = []
    hooks_ms = []
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        _write_assets(root, case)
        source_path = root / f"{case}.ANVL"
        source_path.write_text(SOURCES[case], encoding="utf-8")
        # Warm imports and filesystem paths before collecting pairs.
        _compile_once(case, source_path, False)
        for index in range(runs):
            order = (False, True) if index % 2 == 0 else (True, False)
            pair = {}
            for enabled in order:
                gltf.reset_import_time()
                gltf.measure_import_time(False)
                wasm.measure_asset_imports(False, reset=True)
                start = time.perf_counter()
                for _ in range(BATCH_SIZE):
                    _compile_once(case, source_path, enabled)
                pair[enabled] = (time.perf_counter() - start) * 1000 / BATCH_SIZE
            baseline_ms.append(pair[False])
            hooks_ms.append(pair[True])
            ratios.append((pair[True] - pair[False]) / pair[False] * 100)
    return {
        "runs": runs,
        "median_baseline_ms": round(statistics.median(baseline_ms), 3),
        "median_disabled_hooks_ms": round(statistics.median(hooks_ms), 3),
        "median_paired_overhead_percent": round(statistics.median(ratios), 3),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=20, help="paired batches per workload")
    parser.add_argument("--check", action="store_true", help="fail when median overhead reaches 2 percent")
    args = parser.parse_args(argv)
    if args.runs < 10:
        parser.error("--runs must be at least 10 for a meaningful paired median")
    print("workload      baseline ms  disabled hooks ms  overhead")
    failures = []
    for case in SOURCES:
        result = measure_case(case, args.runs)
        overhead = result["median_paired_overhead_percent"]
        print(
            f"{case:<13}{result['median_baseline_ms']:>12.3f}"
            f"{result['median_disabled_hooks_ms']:>18.3f}{overhead:>9.3f}%"
        )
        if overhead >= 2.0:
            failures.append(f"{case}: {overhead:.3f}%")
    if args.check:
        if failures:
            print("OVERHEAD LIMIT EXCEEDED: " + ", ".join(failures))
            return 1
        print("Disabled timing-hook overhead: below 2% for all workloads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
