"""Measure compiler JSON profiles for tiny, media-heavy and glTF builds.

Run `python tools/bench_build_profiles.py --check` to enforce the published
limits in tools/bench_budgets.json, or `--write-budgets` to rebaseline locally.
"""

from __future__ import annotations

import json
import pathlib
import statistics
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
BUDGETS = ROOT / "tools" / "bench_budgets.json"
RUNS = 3

SOURCES = {
    "tiny": 'fn(main)\n  say "hello"\nend\ncall fn(main)\n',
    "asset_heavy": (
        'fn(main)\n  set var(image) = image_load("asset.bmp")\n'
        '  set var(sound) = sound_load("tone.wav")\n'
        '  set var(music) = music_load("tone.wav")\n'
        '  say "media ready"\nend\ncall fn(main)\n'
    ),
    "3d_model": (
        'fn(main)\n  set var(ok) = model_draw("mesh.glb", 0, 0, 0, 1, 0, 0, 0)\n'
        '  say "model ready"\nend\ncall fn(main)\n'
    ),
}


def _write_assets(root: pathlib.Path, case: str) -> None:
    if case == "asset_heavy":
        width = height = 64
        pixels = bytes((40, 90, 180, 255)) * width * height
        header = bytearray(54)
        header[:2] = b"BM"
        struct.pack_into("<I", header, 2, 54 + len(pixels))
        struct.pack_into("<I", header, 10, 54)
        struct.pack_into("<I", header, 14, 40)
        struct.pack_into("<ii", header, 18, width, height)
        struct.pack_into("<HH", header, 26, 1, 32)
        (root / "asset.bmp").write_bytes(header + pixels)

        pcm = struct.pack("<800h", *[int(12000 * ((i % 32) - 16) / 16) for i in range(800)])
        fmt = struct.pack("<HHIIHH", 1, 1, 8000, 16000, 2, 16)
        body = b"WAVEfmt " + struct.pack("<I", len(fmt)) + fmt
        body += b"data" + struct.pack("<I", len(pcm)) + pcm
        (root / "tone.wav").write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    elif case == "3d_model":
        from bench_runtime import write_ray_mesh

        write_ray_mesh(root / "mesh.glb", quads=24)


def measure(case: str, repeats: int = RUNS) -> dict[str, float | int]:
    samples = []
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary)
        _write_assets(root, case)
        source = root / f"{case}.ANVL"
        source.write_text(SOURCES[case], encoding="utf-8")
        for index in range(repeats):
            profile = root / f"profile-{index}.json"
            output = root / f"output-{index}.wasm"
            result = subprocess.run(
                [
                    sys.executable,
                    str(COMPILER),
                    str(source),
                    "--backend",
                    "wasm",
                    "--output",
                    str(output),
                    "--profile-json",
                    str(profile),
                ],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"{case} profile build failed:\n{result.stderr}")
            report = json.loads(profile.read_text(encoding="utf-8"))
            phases = {phase["name"]: phase["value"] for phase in report["phases"]}
            if "generate" not in phases or "toolchain_link" not in phases:
                raise RuntimeError(f"{case} profile omits generation or toolchain/link phase")
            if report["artifacts"].get("build_state") != "cold_build":
                raise RuntimeError(f"{case} expected a cold WebAssembly build")
            samples.append(
                {
                    "total_ms": report["total"]["value"],
                    "toolchain_link_ms": phases.get("toolchain_link", 0),
                    "asset_import_ms": report["asset_import"]["value"],
                    "peak_bytes": report["memory"]["peak_bytes"],
                    "peak_working_set_bytes": report["memory"]["peak_working_set_bytes"],
                    "child_peak_working_set_bytes": report["memory"]["child_peak_working_set_bytes"],
                    "toolchain_process_tree_peak_working_set_bytes": report["memory"]["toolchain_process_tree_peak_working_set_bytes"],
                    "source_bytes": report["artifacts"]["source_bytes"],
                    "generated_bytes": report["artifacts"]["generated_bytes"],
                    "output_bytes": report["artifacts"]["output_bytes"],
                }
            )
    result = {}
    for key in samples[0]:
        present = [s[key] for s in samples if s[key] is not None]
        result[key] = int(statistics.median(present)) if present else None
    return result


def measurements(repeats: int = RUNS) -> dict[str, dict[str, float | int]]:
    return {case: measure(case, repeats) for case in SOURCES}


def write_budgets(path: pathlib.Path = BUDGETS, multiplier: float = 5.0) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    measured = measurements()
    document["build_profiles"] = {
        "runs": RUNS,
        "multiplier": multiplier,
        "cases": {
            case: {
                **values,
                "budget_total_ms": max(10, int(values["total_ms"] * multiplier)),
                "budget_asset_import_ms": max(2, int(values["asset_import_ms"] * multiplier)),
                "budget_toolchain_link_ms": max(2, int(values["toolchain_link_ms"] * multiplier)),
                "budget_peak_bytes": int(values["peak_bytes"] * multiplier),
                "budget_peak_working_set_bytes": (
                    int(values["peak_working_set_bytes"] * multiplier)
                    if values["peak_working_set_bytes"] is not None
                    else None
                ),
                "budget_child_peak_working_set_bytes": (
                    int(values["child_peak_working_set_bytes"] * multiplier)
                    if values["child_peak_working_set_bytes"] is not None
                    else None
                ),
                "budget_toolchain_process_tree_peak_working_set_bytes": (
                    int(values["toolchain_process_tree_peak_working_set_bytes"] * multiplier)
                    if values["toolchain_process_tree_peak_working_set_bytes"] is not None
                    else None
                ),
            }
            for case, values in measured.items()
        },
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document["build_profiles"]


def check(path: pathlib.Path = BUDGETS) -> list[str]:
    section = json.loads(path.read_text(encoding="utf-8")).get("build_profiles", {})
    cases = section.get("cases", {})
    problems = []
    for name, values in measurements().items():
        budget = cases.get(name)
        if budget is None:
            problems.append(f"missing build-profile budget for {name}")
            continue
        for measured, limit in (
            ("total_ms", "budget_total_ms"),
            ("asset_import_ms", "budget_asset_import_ms"),
            ("toolchain_link_ms", "budget_toolchain_link_ms"),
            ("peak_bytes", "budget_peak_bytes"),
        ):
            if values[measured] > budget[limit]:
                problems.append(
                    f"{name} {measured} {values[measured]} exceeds {budget[limit]}"
                )
        process_memory = values["peak_working_set_bytes"]
        process_budget = budget.get("budget_peak_working_set_bytes")
        if process_memory is not None and process_budget is not None and process_memory > process_budget:
            problems.append(
                f"{name} peak working set {process_memory} exceeds {process_budget}"
            )
        child_memory = values["child_peak_working_set_bytes"]
        child_budget = budget.get("budget_child_peak_working_set_bytes")
        if child_memory is not None and child_budget is not None and child_memory > child_budget:
            problems.append(
                f"{name} child peak working set {child_memory} exceeds {child_budget}"
            )
        tree_memory = values["toolchain_process_tree_peak_working_set_bytes"]
        tree_budget = budget.get("budget_toolchain_process_tree_peak_working_set_bytes")
        if tree_memory is not None and tree_budget is not None and tree_memory > tree_budget:
            problems.append(
                f"{name} toolchain process-tree peak working set {tree_memory} exceeds {tree_budget}"
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--write-budgets", action="store_true")
    args = parser.parse_args(argv)
    if args.write_budgets:
        profile_budgets = write_budgets()
        print(f"Wrote build-profile budgets to {BUDGETS}")
        for case, row in profile_budgets["cases"].items():
            print(
                f"{case:<14} {row['total_ms']:>6} ms total, "
                f"{row['asset_import_ms']:>6} ms import, "
                f"{row['toolchain_link_ms']:>6} ms link"
            )
        return 0
    if args.check:
        problems = check()
        for problem in problems:
            print(f"BUDGET EXCEEDED: {problem}")
        if not problems:
            print("Compiler build-profile budgets: ok")
        return bool(problems)
    for case, values in measurements().items():
        print(f"{case:<14} {values}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
