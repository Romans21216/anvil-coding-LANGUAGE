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

import math
import struct

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


ASSET_SCENE = "assets"
ASSET_IMAGES = 8
ASSET_IMAGE_SIDE = 64
ASSET_SOUNDS = 2
ASSET_SOUND_FRAMES = 12000
ASSET_SOUND_RATE = 8000

ASSET_PROGRAM = "\n".join(
    (
        "fn(main)",
        '  set var(a0) = image_load("a0.bmp")',
        '  set var(a1) = image_load("a1.bmp")',
        '  set var(a2) = image_load("a2.bmp")',
        '  set var(a3) = image_load("a3.bmp")',
        '  set var(a4) = image_load("a4.bmp")',
        '  set var(a5) = image_load("a5.bmp")',
        '  set var(a6) = image_load("a6.bmp")',
        '  set var(a7) = image_load("a7.bmp")',
        "  say memory_images()",
        '  set var(s0) = sound_load("tone0.wav")',
        '  set var(s1) = sound_load("tone1.wav")',
        "  say memory_audio()",
        "  say memory_video()",
        "  wait 0.3",
        "  set var(d0) = image_destroy(var(a0))",
        "  set var(d1) = sound_destroy(var(s0))",
        "  say memory_images()",
        "  say memory_audio()",
        "end",
        "call fn(main)",
        "",
    )
)


def write_asset_files(root: pathlib.Path) -> None:
    row = bytes((30, 60, 200)) * ASSET_IMAGE_SIDE
    padding = b"\x00" * ((4 - (ASSET_IMAGE_SIDE * 3) % 4) % 4)
    data = (row + padding) * ASSET_IMAGE_SIDE
    header = b"BM" + struct.pack("<IHHI", 54 + len(data), 0, 0, 54)
    info = struct.pack(
        "<IiiHHIIiiII",
        40,
        ASSET_IMAGE_SIDE,
        ASSET_IMAGE_SIDE,
        1,
        24,
        0,
        len(data),
        2835,
        2835,
        0,
        0,
    )
    for index in range(ASSET_IMAGES):
        (root / f"a{index}.bmp").write_bytes(header + info + data)
    samples = b"".join(
        struct.pack(
            "<h",
            int(9000 * math.sin(2 * math.pi * 240 * i / ASSET_SOUND_RATE)),
        )
        for i in range(ASSET_SOUND_FRAMES)
    )
    riff = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE"
    fmt = b"fmt " + struct.pack(
        "<IHHIIHH", 16, 1, 1, ASSET_SOUND_RATE, ASSET_SOUND_RATE * 2, 2, 16
    )
    for index in range(ASSET_SOUNDS):
        (root / f"tone{index}.wav").write_bytes(
            riff + fmt + b"data" + struct.pack("<I", len(samples)) + samples
        )


def measure_compile(
    name: str, root: pathlib.Path, source_text: str | None = None
) -> dict[str, float]:
    source = root / f"{name}.ANVL"
    executable = root / f"{name}.exe"
    generated = root / f"{name}.c"
    source.write_text(
        source_text if source_text is not None else program(SCENES[name]),
        encoding="utf-8",
    )
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


def measure_run(
    name: str,
    root: pathlib.Path,
    executable: pathlib.Path,
    capture: bool = False,
) -> dict[str, float]:
    process = subprocess.Popen(
        [str(executable)],
        cwd=root,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    peak = 0
    started = time.perf_counter()
    while process.poll() is None and time.perf_counter() - started < RUN_SECONDS:
        peak = max(peak, process_tree_bytes(process.pid))
        time.sleep(RUN_SAMPLE_SECONDS)
    output = ""
    if process.poll() is None:
        process.kill()
    if capture and process.stdout is not None:
        output = process.stdout.read()
    process.wait()
    result = {
        "run_ms": round((time.perf_counter() - started) * 1000.0, 1),
        "run_peak_mb": round(max(peak, 1) / MB, 1),
    }
    if capture:
        result["stdout"] = output
    return result


def measure(name: str) -> dict[str, float]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        root = pathlib.Path(temp)
        if name == ASSET_SCENE:
            write_asset_files(root)
            build = measure_compile(name, root, ASSET_PROGRAM)
        else:
            build = measure_compile(name, root)
        executable = pathlib.Path(build.pop("executable"))
        run = measure_run(name, root, executable, capture=name == ASSET_SCENE)
    if name == ASSET_SCENE:
        numbers = [
            float(line)
            for line in run.pop("stdout", "").splitlines()
            if line.strip() and line.replace(".", "", 1).replace("-", "", 1).isdigit()
        ]
        if len(numbers) < 5:
            raise SystemExit(f"the asset scene did not report five numbers: {numbers}")
        run["image_bytes"] = int(numbers[0])
        run["audio_bytes"] = int(numbers[1])
        run["video_bytes"] = int(numbers[2])
        run["image_bytes_after_destroy"] = int(numbers[3])
        run["audio_bytes_after_destroy"] = int(numbers[4])
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
    asset_budgets = {
        key: int(result[key] * 1.0)
        for result in results
        if result["scene"] == ASSET_SCENE
        for key in ("image_bytes", "audio_bytes", "video_bytes")
    }
    document = {
        "compile_peak_mb": round(compile_peak, 1),
        "run_peak_mb": run_budgets,
        "note": "2.5x the measured peak with floors; re-baseline on new hardware",
    }
    if asset_budgets:
        document["assets"] = asset_budgets
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
        if scene == ASSET_SCENE:
            for key, limit in (budgets.get("assets") or {}).items():
                if result.get(key, 0) > limit:
                    print(f"{scene}: {key} {result[key]} over budget {limit}")
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
        choices=sorted(list(SCENES) + [ASSET_SCENE]),
        help="limit the run to one scene (repeatable)",
    )
    arguments = parser.parse_args(argv)

    names = arguments.scene or list(SCENES) + [ASSET_SCENE]
    results = [measure(name) for name in names]

    print(f"{'scene':<14}{'compile':>10}{'C bytes':>10}{'exe bytes':>12}{'run peak':>10}")
    for result in results:
        suffix = ""
        if "image_bytes" in result:
            suffix = (
                f"  images {result['image_bytes']} B, "
                f"audio {result['audio_bytes']} B, "
                f"video {result['video_bytes']} B"
            )
        print(
            f"{result['scene']:<14}{result['compile_peak_mb']:>8.1f} MB"
            f"{result['generated_bytes']:>10}"
            f"{result['exe_bytes']:>12}"
            f"{result['run_peak_mb']:>8.1f} MB{suffix}"
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
