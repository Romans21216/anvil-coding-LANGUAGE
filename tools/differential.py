"""Seeded C-vs-native differential fuzz over the shared language subset.

Part 8 §8.15 asks for seeded C/native differentials. This tool generates
programs from the language features both backends claim to support — numeric
expressions, locals, `if`/`else`, bounded `for` loops and `output` — then builds
and runs each one on both backends and compares the exit code and stdout.

A mismatch is a semantic defect in one backend, not a formatting preference, so
the tool exits 1 and prints the program that disagreed.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPILER = ROOT / "compiler" / "anvil.py"
BACKENDS = ("c", "native")


def _number(rng: random.Random) -> str:
    choice = rng.random()
    if choice < 0.45:
        return str(rng.randint(-20, 40))
    if choice < 0.8:
        return f"{rng.uniform(-12, 12):.4f}"
    return str(rng.randint(0, 3))


def _expression(rng: random.Random, names: list[str], depth: int) -> str:
    if depth <= 0 or (names and rng.random() < 0.25):
        return rng.choice(names + [_number(rng)])
    roll = rng.random()
    if roll < 0.18:
        function = rng.choice(("floor", "ceil", "abs", "round"))
        return f"{function}({_expression(rng, names, depth - 1)})"
    if roll < 0.30:
        # mod is floored on both backends; the divisor stays positive so the
        # only thing under test is the remainder rule.
        return f"mod({_expression(rng, names, depth - 1)}, {rng.randint(1, 9)})"
    if roll < 0.40:
        return (
            f"{rng.choice(('min', 'max'))}"
            f"({_expression(rng, names, depth - 1)}, {_expression(rng, names, depth - 1)})"
        )
    if roll < 0.48:
        return f"twice({_expression(rng, names, depth - 1)})"
    operator = rng.choice(("+", "-", "*", "/", "+", "-", "*"))
    left = _expression(rng, names, depth - 1)
    if operator == "/":
        # Keep the divisor in a range that cannot be zero on either backend:
        # both agree that division by zero is a fatal error, which would test
        # the error path rather than arithmetic.
        right = str(rng.randint(1, 9))
    else:
        right = _expression(rng, names, depth - 1)
    return f"({left} {operator} {right})"


def generate(rng: random.Random) -> str:
    """One program using only features both backends implement."""
    names: list[str] = []
    lines = [
        "fn(twice, value)",
        "  output var(value) * 2",
        "end",
        "fn(main)",
    ]
    for index in range(rng.randint(1, 3)):
        name = f"v{index}"
        lines.append(f"  set local({name}) = {_expression(rng, names, rng.randint(1, 3))}")
        names.append(f"local({name})")
    if rng.random() < 0.4 and len(names) >= 2:
        first, second = rng.sample(names, 2)
        comparator = rng.choice(("<", "<=", ">", ">=", "=", "!="))
        lines.append(f"  if {first} {comparator} {second}")
        lines.append(f"    set local(flag) = {_expression(rng, names, 2)}")
        lines.append("  else")
        lines.append(f"    set local(flag) = {_expression(rng, names, 2)}")
        lines.append("  end")
        names.append("local(flag)")
    if rng.random() < 0.4:
        limit = rng.randint(1, 12)
        lines.append("  set local(total) = 0")
        lines.append(f"  for local(i) = 1 to {limit}")
        lines.append(f"    add local(total) {_expression(rng, names, 2)}")
        lines.append("  end")
        names.append("local(total)")
    lines.append(f"  output {_expression(rng, names, rng.randint(1, 3))}")
    lines.append("end")
    return "\n".join(lines) + "\n"


def _run(source: str, backend: str, workdir: pathlib.Path) -> dict:
    entry = workdir / "case.ANVL"
    entry.write_text(source, encoding="utf-8")
    executable = workdir / "case.exe"
    build = subprocess.run(
        [
            sys.executable,
            str(COMPILER),
            str(entry),
            "--backend",
            backend,
            "--output",
            str(executable),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if build.returncode != 0:
        return {"status": "rejected", "exit": build.returncode, "stdout": "", "detail": _first(build.stderr or build.stdout)}
    run = subprocess.run(
        [str(executable)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return {
        "status": "ran",
        "exit": run.returncode,
        "stdout": run.stdout.replace("\r\n", "\n").strip(),
        "detail": _first(run.stderr),
    }


def _first(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def compare(count: int, seed: int) -> list[dict]:
    """Generate ``count`` programs and return one row per disagreement."""
    rng = random.Random(seed)
    mismatches: list[dict] = []
    for index in range(count):
        source = generate(rng)
        results = {}
        for backend in BACKENDS:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temporary:
                results[backend] = _run(source, backend, pathlib.Path(temporary))
        left, right = results["c"], results["native"]
        if left["status"] != right["status"]:
            verdict = f"c {left['status']} vs native {right['status']}: {right['detail']}"
        elif left["status"] == "rejected":
            continue  # both refused the program; agreement is agreement
        elif (left["exit"], left["stdout"]) != (right["exit"], right["stdout"]):
            verdict = (
                f"c exit {left['exit']} printed {left['stdout']!r}; "
                f"native exit {right['exit']} printed {right['stdout']!r}"
            )
        else:
            continue
        mismatches.append({"index": index, "seed": seed, "verdict": verdict, "source": source})
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=40, help="programs to generate")
    parser.add_argument("--seed", type=int, default=1, help="random seed")
    parser.add_argument("--json", action="store_true", help="print rows as JSON")
    arguments = parser.parse_args()

    mismatches = compare(arguments.count, arguments.seed)
    if arguments.json:
        print(json.dumps(mismatches, indent=2))
    else:
        for row in mismatches:
            print(f"case {row['index']} (seed {row['seed']}): {row['verdict']}")
            print(row["source"])
    print(
        f"{arguments.count} program(s) from seed {arguments.seed}: "
        f"{len(mismatches)} mismatch(es)"
    )
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
