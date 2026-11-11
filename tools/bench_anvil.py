"""Measure compile time and executable size for the C and native backends.

Run from the repository root:

    python tools/bench_anvil.py

The numbers are for this machine only. They exist so size and compile-time
claims can be checked instead of guessed; they are not a target to tune against.
"""

from __future__ import annotations

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

BIG = TINY + "\n".join(
    f"fn(helper{i}, n)\n  output var(n) + {i}\nend\n" for i in range(40)
) + "\nfn(unused_extra)\n  output 0\nend\n"


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
    return statistics.median(timings), size


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
    return statistics.median(timings), size


def main() -> int:
    print(f"{'program':<10} {'backend':<8} {'compile s':>10} {'exe bytes':>10}")
    for name, source in (("tiny", TINY), ("texty", TEXTY), ("big", BIG)):
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


if __name__ == "__main__":
    raise SystemExit(main())
