"""Measure the language surface each backend actually supports.

Part 8.7 item 3 asks for one published backend feature matrix and one semantic
conformance suite. This script is both: every case below is compiled and run on
each declared backend, and the observed result becomes the matrix row. Nothing
here is inferred from source; a capability counts as supported only when the
build succeeds and the program prints the expected value.

Run from the repository root:

    python tools/backend_matrix.py            # regenerate docs/BACKEND_MATRIX.md
    python tools/backend_matrix.py --json     # print the machine-readable rows
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKENDS = ("c", "native")

LIBRARY = "fn(twice, n)\n output var(n) * 2\nend\n"

# Every case is (name, category, source, expected_stdout). ``expected`` is the
# exact console text the program must print; None means the case is a graphical
# program that is compiled but not launched (a window would block the run).
CASES = [
    (
        "sound-api",
        "audio",
        "fn(main)\n set var(s) = sound_load(\"missing.wav\")\n output var(s)\nend\n",
        "0",
    ),
    (
        "expect-assertions",
        "tests",
        "fn(main)\n expect(2 + 2, 4)\n expect_text(upper(\"ok\"), \"OK\")\n output 42\nend\n",
        "42",
    ),
    (
        "arithmetic-precedence",
        "expressions",
        "fn(main)\n output 2 + 3 * 4\nend\n",
        "14",
    ),
    (
        "parentheses",
        "expressions",
        "fn(main)\n output (2 + 3) * 4\nend\n",
        "20",
    ),
    (
        "division-fraction",
        "expressions",
        "fn(main)\n output 7 / 2\nend\n",
        "3.5",
    ),
    (
        "comparison",
        "expressions",
        "fn(main)\n if 3 < 4 and 4 <= 4\n  output 1\n else\n  output 0\n end\nend\n",
        "1",
    ),
    (
        "short-circuit",
        "expressions",
        "fn(main)\n if 0 and 1 / 0\n  output 0\n else\n  output 1\n end\nend\n",
        "1",
    ),
    (
        "if-else",
        "control flow",
        "fn(main)\n set var(n) = 4\n if var(n) > 5\n  output 1\n else\n  output 7\n end\nend\n",
        "7",
    ),
    (
        "else-if-chain",
        "control flow",
        "fn(main)\n set var(n) = 2\n if var(n) == 1\n  output 10\n else if var(n) == 2\n  output 20\n else\n  output 30\n end\nend\n",
        "20",
    ),
    (
        "while-loop",
        "control flow",
        "fn(main)\n set local(n) = 0\n while local(n) < 5\n  add local(n) 1\n end\n output local(n)\nend\n",
        "5",
    ),
    (
        "for-ascending",
        "control flow",
        "fn(main)\n set local(total) = 0\n for local(i) = 1 to 3\n  add local(total) local(i)\n end\n output local(total)\nend\n",
        "6",
    ),
    (
        "for-descending",
        "control flow",
        "fn(main)\n set local(total) = 0\n for local(i) = 3 to 1 step -1\n  add local(total) local(i)\n end\n output local(total)\nend\n",
        "6",
    ),
    (
        "function-call",
        "functions",
        "fn(add3, a, b, c)\n output var(a) + var(b) + var(c)\nend\nfn(main)\n output call fn(add3, 2, 4, 6)\nend\n",
        "12",
    ),
    (
        "recursion",
        "functions",
        "fn(fact, n)\n if var(n) <= 1\n  output 1\n end\n output var(n) * call fn(fact, var(n) - 1)\nend\nfn(main)\n output call fn(fact, 5)\nend\n",
        "120",
    ),
    (
        "global-local-namespaces",
        "functions",
        "fn(main)\n set var(x) = 7\n set local(x) = 2\n output var(x) + local(x)\nend\n",
        "9",
    ),
    (
        "global-array",
        "data",
        "array values(3)\nfn(main)\n set array(values,0) = 4\n set array(values,1) = 5\n set array(values,2) = 6\n output array(values,0) + array(values,2)\nend\n",
        "10",
    ),
    (
        "array-runtime-index",
        "data",
        "array values(3)\nfn(main)\n set local(i) = 2\n set array(values,local(i)) = 9\n output array(values,local(i))\nend\n",
        "9",
    ),
    (
        "include-library",
        "modules",
        'include "lib.ANVL"\nfn(main)\n output call fn(twice, 4)\nend\n',
        "8",
    ),
    (
        "sqrt-abs-min-max",
        "builtins",
        "fn(main)\n output sqrt(16) + abs(0 - 2) + min(3,4) + max(3,4)\nend\n",
        "13",
    ),
    (
        "mod-builtin",
        "builtins",
        "fn(main)\n output mod(7, 3)\nend\n",
        "1",
    ),
    (
        "round-builtin",
        "builtins",
        "fn(main)\n output round(2.4)\nend\n",
        "2",
    ),
    (
        "text-format-number",
        "text",
        "fn(main)\n output 1 / 3\nend\n",
        "0.333333333333333",
    ),
    (
        "text-dynamic",
        "text",
        'fn(main)\n set var(score) = 7\n display text("score " + var(score)) -l(10, 10)\nend\n',
        None,
    ),
    (
        "print-statement",
        "text",
        'fn(main)\n set var(score) = 7\n print "score = " + var(score)\nend\n',
        "score = 7\n0",
    ),
    (
        "print-literal",
        "text",
        'fn(main)\n print "hello"\nend\n',
        "hello\n0",
    ),
    (
        "print-toplevel",
        "text",
        'print "booting"\nfn(main)\n output 0\nend\n',
        "booting\n0",
    ),
    (
        "text-builtins",
        "text",
        'fn(main)\n output len("anvil")\nend\n',
        "5",
    ),
    (
        "utf8-codepoints",
        "text",
        'fn(main)\n print utf8_char("aé🙂", 1)\n output utf8_len("🙂")\nend\n',
        "é\n1",
    ),
    (
        "clear-inside-draw",
        "graphics",
        "scene 2d\nfn(draw)\n clear rgba(0,0,0,255)\n display rect(10,10,40,40) -rgb(255,0,0)\nend\n",
        None,
    ),
    (
        "display-rect",
        "graphics",
        "scene 2d\nclear rgba(0,0,0,255)\nfn(draw)\n display rect(10,10,40,40) -rgb(255,0,0)\nend\n",
        None,
    ),
    (
        "display-circle",
        "graphics",
        "scene 2d\nclear rgba(0,0,0,255)\nfn(draw)\n display circle(40,40,20) -rgb(0,255,0)\nend\n",
        None,
    ),
    (
        "display-line",
        "graphics",
        "scene 2d\nclear rgba(0,0,0,255)\nfn(draw)\n display line(0,0,80,80) -rgb(0,0,255)\nend\n",
        None,
    ),
    (
        "display-rgba-blend",
        "graphics",
        "scene 2d\nclear rgba(0,0,0,255)\nfn(draw)\n display rect(10,10,40,40) -rgba(255,0,0,128)\nend\n",
        None,
    ),
]


def _first_error(text: str) -> str:
    """Return the first ``error:`` line of a compiler diagnostic, if any."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("error:"):
            return stripped
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "build failed"


def _run_case(source: str, backend: str, workdir: pathlib.Path) -> dict:
    """Build one case on one backend and run it when it is a console program."""
    entry = workdir / f"case-{backend}.ANVL"
    entry.write_text(source, encoding="utf-8")
    library = workdir / "lib.ANVL"
    library.write_text(LIBRARY, encoding="utf-8")
    output = workdir / f"case-{backend}.exe"
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "compiler.anvil",
            str(entry),
            "--backend",
            backend,
            "--output",
            str(output),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if build.returncode != 0:
        return {"status": "rejected", "detail": _first_error(build.stdout + build.stderr)}
    if not output.exists():
        return {"status": "rejected", "detail": "build reported success but wrote no executable"}
    return {"status": "built", "detail": ""}


def _run_program(output: pathlib.Path, timeout: int = 10) -> dict:
    try:
        run = subprocess.run(
            [str(output)], capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "detail": "program did not exit"}
    text = run.stdout.strip()
    if run.returncode != 0:
        return {"status": "crashed", "detail": _first_error(run.stdout + run.stderr) or f"exit {run.returncode}"}
    return {"status": "ran", "detail": text}


def measure() -> list[dict]:
    rows = []
    for name, category, source, expected in CASES:
        row = {
            "name": name,
            "category": category,
            "expected": expected,
            "backends": {},
        }
        for backend in BACKENDS:
            with tempfile.TemporaryDirectory() as temporary:
                workdir = pathlib.Path(temporary)
                result = _run_case(source, backend, workdir)
                if result["status"] == "built" and expected is not None:
                    program = _run_program(workdir / f"case-{backend}.exe")
                    if program["status"] == "ran":
                        if program["detail"] == expected:
                            result = {"status": "ok", "detail": program["detail"]}
                        else:
                            result = {
                                "status": "mismatch",
                                "detail": f"expected {expected!r}, printed {program['detail']!r}",
                            }
                    else:
                        result = program
                elif result["status"] == "built":
                    result = {"status": "builds", "detail": "graphical program not launched"}
                row["backends"][backend] = result
        rows.append(row)
    return rows


def _cell(result: dict) -> str:
    status = result["status"]
    if status == "ok":
        return "supported"
    if status == "builds":
        return "builds"
    if status == "rejected":
        return "rejected"
    if status == "mismatch":
        return "wrong value"
    return status


def render_markdown(rows: list[dict]) -> str:
    lines = [
        "# Backend feature matrix",
        "",
        "Generated by `python tools/backend_matrix.py` from real builds and runs on",
        "this machine. A row counts as supported only when the build succeeds and the",
        "program prints the expected value; `rejected` means the backend refused the",
        "source with a diagnostic. Regenerate after changing either backend, and run",
        "`python -m pytest tests/test_backend_matrix.py` to keep this file honest.",
        "",
        "| Feature | Category | C backend | Native x64 backend |",
        "|---|---|---|---|",
    ]
    for row in rows:
        c = _cell(row["backends"]["c"])
        native = _cell(row["backends"]["native"])
        lines.append(f"| `{row['name']}` | {row['category']} | {c} | {native} |")
    lines.append("")

    shared = [row for row in rows if row["backends"]["c"]["status"] == "ok"]
    agreed = [
        row
        for row in shared
        if row["backends"]["native"]["status"] == "ok"
    ]
    native_only_rejects = [
        row
        for row in shared
        if row["backends"]["native"]["status"] == "rejected"
    ]
    lines.extend(
        [
            "## Summary",
            "",
            f"- Cases where both backends build and print the same value: **{len(agreed)}**"
            f" of {len(rows)}.",
            f"- Cases the C backend supports but the native backend rejects: **{len(native_only_rejects)}**.",
            "- Cases the native backend rejects: "
            + ", ".join(f"`{row['name']}`" for row in native_only_rejects)
            + ".",
            "",
            "## Rejected-case diagnostics",
            "",
        ]
    )
    for row in rows:
        for backend in BACKENDS:
            result = row["backends"][backend]
            if result["status"] == "rejected":
                lines.append(f"- `{row['name']}` on `{backend}`: {result['detail']}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print measured rows as JSON")
    parser.add_argument(
        "--write",
        type=pathlib.Path,
        default=ROOT / "docs" / "BACKEND_MATRIX.md",
        help="markdown path to write (default docs/BACKEND_MATRIX.md)",
    )
    args = parser.parse_args()

    rows = measure()
    if args.json:
        json.dump(rows, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    text = render_markdown(rows)
    args.write.write_text(text, encoding="utf-8")
    print(text)
    print(f"wrote {args.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
