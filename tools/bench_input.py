"""Input-latency benchmark with budgets (Part 8, 8.15).

Posts key messages to a running Anvil window and compares the wall-clock time
of the post with the program's ``time()`` stamp at the moment the frame observed
``pressed(A)``. The two clocks do not share an origin: ``time()`` counts from the
program's start while the harness counts from just before ``Popen``, so the
absolute number carries a few milliseconds of start-up offset. The distribution
is still the useful part, and the budget is wide enough that the offset cannot
explain a failure.

Usage:
    python tools/bench_input.py                 # measure and print
    python tools/bench_input.py --check         # exit 1 when a budget is missed
    python tools/bench_input.py --write-budgets # re-baseline this machine
"""

from __future__ import annotations

import argparse
import ctypes
import json
import pathlib
import queue
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from ctypes import wintypes

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPILER = ROOT / "compiler" / "anvil.py"
BUDGETS = ROOT / "tools" / "input_budgets.json"
DEFAULT_SAMPLES = 15
KEY_A = 0x41
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101

user32 = ctypes.WinDLL("user32", use_last_error=True)
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def program(samples: int) -> str:
    return "\n".join(
        (
            "scene 2d",
            "clear rgba(10, 12, 18, 255)",
            "set var(count) = 0",
            "set var(ready) = 0",
            "",
            "fn(update)",
            "  if var(ready) = 0",
            "    say time()",
            "    set var(ready) = 1",
            "  end",
            "  if pressed(A)",
            "    say time()",
            "    set var(count) = compute(var(count) + 1)",
            f"    if var(count) >= {samples}",
            "      stop",
            "    end",
            "  end",
            "end",
            "",
            "fn(draw)",
            "  display rect(0, 0, 4, 4) -rgb(255, 0, 0)",
            "end",
            "",
        )
    )


def window_for(pid: int):
    found: list[int] = []

    def callback(hwnd, _lparam):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found[0] if found else None


def wait_for_window(pid: int, timeout: float = 10.0):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        hwnd = window_for(pid)
        if hwnd:
            return hwnd
        time.sleep(0.05)
    return None


def measure(samples: int) -> dict[str, float]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
        root = pathlib.Path(temp)
        source = root / "latency.ANVL"
        executable = root / "latency.exe"
        source.write_text(program(samples), encoding="utf-8")
        build = subprocess.run(
            [sys.executable, str(COMPILER), str(source), "-o", str(executable)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if build.returncode != 0:
            raise SystemExit(f"build failed:\n{build.stderr}")

        started = time.perf_counter()
        process = subprocess.Popen(
            [str(executable)],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        lines: queue.Queue[str] = queue.Queue()

        def read_lines() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line.strip())

        reader = threading.Thread(target=read_lines, daemon=True)
        reader.start()

        hwnd = wait_for_window(process.pid)
        if hwnd is None:
            process.kill()
            raise SystemExit("the program did not open a window")

        latencies: list[float] = []
        try:
            # The first line calibrates the program clock against ours: time()
            # counts from the program's own start, which is tens of ms after
            # Popen returns because the loader and window creation run first.
            # Read it before any sleep, otherwise the wait itself is charged to
            # the calibration and every latency comes out hundreds of ms late.
            first = lines.get(timeout=10.0)
            calibrated = time.perf_counter() - float(first)
            time.sleep(0.3)
            for _ in range(samples):
                time.sleep(random.uniform(0.10, 0.22))
                posted = time.perf_counter()
                user32.PostMessageW(hwnd, WM_KEYDOWN, KEY_A, 1)
                user32.PostMessageW(hwnd, WM_KEYUP, KEY_A, 1)
                line = lines.get(timeout=10.0)
                stamp = float(line)
                latencies.append((calibrated + stamp - posted) * 1000.0)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()

    ordered = sorted(latencies)
    return {
        "samples": len(ordered),
        "p50_ms": round(statistics.median(ordered), 2),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))], 2),
        "max_ms": round(max(ordered), 2),
    }


def load_budgets() -> dict:
    if not BUDGETS.exists():
        return {"p50_ms": 34.0, "p95_ms": 50.0, "max_ms": 90.0}
    return json.loads(BUDGETS.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-budgets", action="store_true")
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    parser.add_argument("--json", type=pathlib.Path)
    parser.add_argument("--runs", type=int, default=2, help="repeat the measurement")
    arguments = parser.parse_args(argv)

    runs = [measure(arguments.samples) for _ in range(max(1, arguments.runs))]
    result = {
        "samples": arguments.samples,
        "runs": runs,
        "p50_ms": round(statistics.median(run["p50_ms"] for run in runs), 2),
        "p95_ms": round(max(run["p95_ms"] for run in runs), 2),
        "max_ms": round(max(run["max_ms"] for run in runs), 2),
    }
    print(
        f"input latency ({arguments.samples} presses, {len(runs)} runs): "
        f"p50 {result['p50_ms']} ms, p95 {result['p95_ms']} ms, "
        f"worst {result['max_ms']} ms"
    )

    if arguments.json:
        arguments.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {arguments.json}")

    if arguments.write_budgets:
        p50 = max(20.0, result["p50_ms"] * 2.0)
        p95 = max(34.0, result["p95_ms"] * 1.6, p50)
        worst = max(60.0, result["max_ms"] * 1.5, p95)
        document = {
            "p50_ms": round(p50, 1),
            "p95_ms": round(p95, 1),
            "max_ms": round(worst, 1),
            "note": "measured with headroom; re-baseline on new hardware",
        }
        BUDGETS.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {BUDGETS.relative_to(ROOT)}")

    if arguments.check:
        budgets = load_budgets()
        missed = [
            f"{key} {result[key]} ms over {budgets[key]} ms"
            for key in ("p50_ms", "p95_ms", "max_ms")
            if result[key] > float(budgets[key])
        ]
        if missed:
            for line in missed:
                print(line)
            return 1
        print("input latency budgets hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
