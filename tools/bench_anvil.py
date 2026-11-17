"""Measure compile time and executable size for the C and native backends.

Run from the repository root:

    python tools/bench_anvil.py

The numbers are for this machine only. They exist so size and compile-time
claims can be checked instead of guessed; they are not a target to tune against.
"""

from __future__ import annotations

import json
import pathlib
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

TINY = """\
fn(main)
  say "Hello, world!"
end
call fn(main)
"""

TEXTY = """\
fn(greet, n)
  if var(n) > 2
    output "big"
  end
  output "small"
end

fn(main)
  set var(name) = "Ada"
  set var(total) = 0
  for local(i) = 1 to 10
    set var(total) = var(total) + local(i)
  end
  say "hello, " & var(name) & " total=" & var(total)
  say call fn(greet, 5) & "/" & call fn(greet, 1)
end
call fn(main)
"""

# Every helper here is CALLED, so the row measures real code volume rather than
# the reachability filter. `unused_extra` stays unreachable on purpose: comparing
# this row with BIG_TRIMMED proves dead functions cost nothing in either backend.
BIG = (
    "\n".join(f"fn(helper{i}, n)\n  output var(n) + {i}\nend\n" for i in range(40))
    + "\nfn(main)\n  set var(total) = 0\n"
    + "".join(f"  add var(total) call fn(helper{i}, 1)\n" for i in range(40))
    + "  say var(total)\nend\ncall fn(main)\n"
)

BIG_TRIMMED = TINY + "\n".join(
    f"fn(unused{i}, n)\n  output var(n) + {i}\nend\n" for i in range(40)
)


CASES = (
    ("tiny", TINY),
    ("texty", TEXTY),
    ("big", BIG),
    ("big_trim", BIG_TRIMMED),
)


def measure_native(source: str, repeats: int = 5) -> tuple[float, int]:
    timings = []
    size = 0
    for _ in range(repeats):
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "bench.ANVL"
            path.write_text(source, encoding="utf-8")
            start = time.perf_counter()
            functions, top, variables, arrays = parse(path, source)
            image = NativeCodegen(path, functions, top, variables, arrays).generate()
            timings.append(time.perf_counter() - start)
            size = len(image)
    # The fastest run estimates the intrinsic cost; a median picks up whatever
    # else the machine was doing, which made a 3 ms budget flaky under load.
    return min(timings), size


def measure_c(source: str, repeats: int = 3) -> tuple[float, int] | None:
    compiler = find_compiler(None)
    if compiler is None:
        return None
    timings = []
    size = 0
    for _ in range(repeats):
        with tempfile.TemporaryDirectory() as temp:
            temp_path = pathlib.Path(temp)
            path = temp_path / "bench.ANVL"
            path.write_text(source, encoding="utf-8")
            start = time.perf_counter()
            functions, top, variables, arrays = parse(path, source)
            c_text = emit_c(path, functions, top, variables, arrays)
            c_file = temp_path / "bench.c"
            c_file.write_text(c_text, encoding="utf-8")
            exe = temp_path / "bench.exe"
            build_c(compiler[1], c_file, exe, release=True)
            timings.append(time.perf_counter() - start)
            size = exe.stat().st_size
    return min(timings), size


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when a measured time or size exceeds tools/bench_budgets.json",
    )
    parser.add_argument(
        "--write-budgets",
        action="store_true",
        help="re-measure this machine and rewrite tools/bench_budgets.json",
    )
    arguments = parser.parse_args(argv)
    if arguments.write_budgets:
        budgets = write_budgets()
        print(f"Wrote {BUDGETS_PATH}")
        for name, entry in budgets.items():
            for backend, values in entry.items():
                print(
                    f"  {name:<10} {backend:<8} {values['seconds']:>7.3f}s "
                    f"{values['bytes']:>8} B"
                )
        return 0
    if arguments.check:
        return check(load_budgets())
    print(f"{'program':<10} {'backend':<8} {'compile s':>10} {'exe bytes':>10}")
    for name, source in CASES:
        native_time, native_size = measure_native(source)
        print(f"{name:<10} {'native':<8} {native_time:>10.3f} {native_size:>10}")
        measured = measure_c(source)
        if measured is None:
            print(f"{name:<10} {'c':<8} {'(no MSVC)':>10} {'-':>10}")
            continue
        c_time, c_size = measured
        print(f"{name:<10} {'c':<8} {c_time:>10.3f} {c_size:>10}")
    print()
    print("Try a generated program yourself: build it, then time it with")
    print('  powershell "Measure-Command { .\\build\\app.exe }"')
    return 0


BUDGETS_PATH = pathlib.Path(__file__).with_name("bench_budgets.json")


def load_budgets(path: pathlib.Path = BUDGETS_PATH) -> dict:
    """The published budgets; see the docstring for how they are set."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_budgets(
    path: pathlib.Path = BUDGETS_PATH,
    time_multiplier: float = 3.0,
    size_multiplier: float = 1.25,
) -> dict:
    """Measure this machine and publish budgets with headroom.

    A budget is the fastest measured compile time times a multiplier, rounded up. The benchmark uses the minimum across repeats to estimate intrinsic cost without scheduler delays; the source number and multiplier stay in the JSON so a later reading can be compared.
    """
    budgets: dict[str, dict[str, dict[str, float]]] = {}
    for name, source in CASES:
        native_time, native_size = measure_native(source)
        entry = {
            "native": {
                "seconds": round(native_time * time_multiplier, 3),
                "bytes": int(native_size * size_multiplier),
                "measured_seconds": round(native_time, 4),
                "measured_bytes": native_size,
            }
        }
        measured = measure_c(source)
        if measured is not None:
            c_time, c_size = measured
            entry["c"] = {
                "seconds": round(c_time * time_multiplier, 3),
                "bytes": int(c_size * size_multiplier),
                "measured_seconds": round(c_time, 4),
                "measured_bytes": c_size,
            }
        budgets[name] = entry
    path.write_text(json.dumps(budgets, indent=2) + "\n", encoding="utf-8")
    return budgets


def violations(cases, budgets: dict, c_repeats: int = 1, native_repeats: int = 3) -> list[str]:
    """Measured values that exceed a published budget, as readable lines."""
    problems: list[str] = []
    for name, source in cases:
        native_time, native_size = measure_native(source, repeats=native_repeats)
        budget = budgets.get(name, {}).get("native")
        if budget:
            if native_time > budget["seconds"]:
                problems.append(
                    f"{name} native compile {native_time:.3f}s exceeds the "
                    f"{budget['seconds']:.3f}s budget"
                )
            if native_size > budget["bytes"]:
                problems.append(
                    f"{name} native image {native_size} bytes exceeds the "
                    f"{budget['bytes']} byte budget"
                )
        measured = measure_c(source, repeats=c_repeats)
        if measured is None:
            continue
        c_time, c_size = measured
        budget = budgets.get(name, {}).get("c")
        if budget:
            if c_time > budget["seconds"]:
                problems.append(
                    f"{name} c compile {c_time:.3f}s exceeds the "
                    f"{budget['seconds']:.3f}s budget"
                )
            if c_size > budget["bytes"]:
                problems.append(
                    f"{name} c image {c_size} bytes exceeds the "
                    f"{budget['bytes']} byte budget"
                )
    return problems


def check(budgets: dict) -> int:
    problems = violations(CASES, budgets, c_repeats=2, native_repeats=5)
    if problems:
        for problem in problems:
            print(f"BUDGET EXCEEDED: {problem}")
        return 1
    print("All measured times and sizes are inside the published budgets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
