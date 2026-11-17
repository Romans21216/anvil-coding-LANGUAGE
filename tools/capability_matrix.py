"""Measure which language features actually build and run on each backend.

Part 8 section 8.16 asks for a generated capability matrix rather than prose
claims. Each case is compiled and executed on the C and native backends; a row
is only marked as running when the build succeeds and the output matches the
expected text exactly.

Usage:
    python tools/capability_matrix.py          # rewrite docs/CAPABILITY_MATRIX.md
    python tools/capability_matrix.py --check  # exit 1 when the file is stale
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "CAPABILITY_MATRIX.md"
sys.path.insert(0, str(ROOT))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.common import CompileError  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402

# A real bundled BMP used by the asset case.
SPRITE_BYTES = (ROOT / "examples" / "assets" / "anvil_sprite.bmp").read_bytes()

CASES = [
    {
        "id": "console-say",
        "source": 'fn(main)\n  say "hello"\nend\ncall fn(main)\n',
        "expect": "hello\n",
    },
    {
        "id": "number-format",
        "source": "fn(main)\n  say 1 / 3\nend\ncall fn(main)\n",
        "expect": "0.333333\n",
    },
    {
        "id": "text-builtins",
        "source": (
            'fn(main)\n  say len("hello")\n  say mid("abcdef", 1, 3)\n'
            '  say upper("ab")\n  say number("2.5") + 1\nend\ncall fn(main)\n'
        ),
        "expect": "5\nbcd\nAB\n3.5\n",
    },
    {
        "id": "text-parameters",
        "source": (
            'fn(greet, who)\n  output "hi " & var(who)\nend\n'
            'fn(main)\n  say call fn(greet, "Ada")\nend\ncall fn(main)\n'
        ),
        "expect": "hi Ada\n",
    },
    {
        "id": "lists",
        "source": (
            "list scores\nfn(main)\n  add scores 4\n  add scores 9\n"
            "  say count(scores)\n  say array(scores, 1)\nend\ncall fn(main)\n"
        ),
        "expect": "2\n9\n",
    },
    {
        "id": "global-arrays",
        "source": (
            "array grid(3)\nfn(main)\n  set array(grid, 1) = 7\n"
            "  say array(grid, 1)\nend\ncall fn(main)\n"
        ),
        "expect": "7\n",
    },
    {
        "id": "enums",
        "source": (
            "enum colour red, green\nfn(main)\n  say green\nend\ncall fn(main)\n"
        ),
        "expect": "1\n",
    },
    {
        "id": "while-loop",
        "source": (
            "fn(main)\n  set var(i) = 0\n  while var(i) < 3\n    add var(i) 1\n  end\n"
            "  say var(i)\nend\ncall fn(main)\n"
        ),
        "expect": "3\n",
    },
    {
        "id": "for-loop-step",
        "source": (
            "fn(main)\n  for local(i) = 3 to 1 step -1\n    say local(i)\n  end\nend\ncall fn(main)\n"
        ),
        "expect": "3\n2\n1\n",
    },
    {
        "id": "recursion",
        "source": (
            "fn(fact, n)\n  if var(n) <= 1\n    output 1\n  end\n"
            "  output var(n) * call fn(fact, var(n) - 1)\nend\n"
            "fn(main)\n  say call fn(fact, 5)\nend\ncall fn(main)\n"
        ),
        "expect": "120\n",
    },
    {
        "id": "math-builtins",
        "source": (
            "fn(main)\n  say sqrt(16)\n  say abs(0 - 2)\n  say min(3, 4)\n"
            "  say max(3, 4)\nend\ncall fn(main)\n"
        ),
        "expect": "4\n2\n3\n4\n",
    },
    {
        "id": "noise",
        "source": "fn(main)\n  say noise(0, 0, 0)\nend\ncall fn(main)\n",
        "expect": "0\n",
    },
    {
        "id": "image-load",
        "source": (
            'fn(main)\n  set var(handle) = image_load("anvil_sprite.bmp")\n'
            "  say image_width(var(handle)) > 0\n"
            "  say image_height(var(handle)) > 0\nend\n"
            "call fn(main)\n"
        ),
        "expect": "1\n1\n",
        "files": {"anvil_sprite.bmp": SPRITE_BYTES},
    },
    {
        "id": "physics-body",
        "source": (
            "fn(main)\n  set var(body) = body_create(0, 0, 1, 1)\n"
            "  say body_active(var(body))\nend\ncall fn(main)\n"
        ),
        "expect": "1\n",
    },
]


def _clean(text: str, workdir: pathlib.Path) -> str:
    """Remove the volatile temp path so the document is reproducible."""
    return text.replace(str(workdir) + os.sep, "").replace(str(workdir), ".")


def _run_case(case: dict, backend: str, workdir: pathlib.Path) -> tuple[str, str]:
    """Return (status, note) for one case on one backend."""
    for name, payload in case.get("files", {}).items():
        (workdir / name).write_bytes(payload)
    source_path = workdir / "case.ANVL"
    source_path.write_text(case["source"], encoding="utf-8")
    try:
        functions, top, variables, arrays = parse(source_path, case["source"])
        executable = workdir / f"case-{backend}.exe"
        if backend == "native":
            executable.write_bytes(
                NativeCodegen(source_path, functions, top, variables, arrays).generate()
            )
        else:
            c_path = workdir / "case.c"
            c_path.write_text(
                emit_c(source_path, functions, top, variables, arrays), encoding="utf-8"
            )
            compiler = find_compiler(None)
            if compiler is None:
                return "skipped", "MSVC is not available"
            build_c(compiler[1], c_path, executable, release=True)
    except CompileError as error:
        first = _clean(str(error).splitlines()[0], workdir)
        return "rejected", first
    except Exception as error:  # toolchain failure
        return "build-error", _clean(
            f"{type(error).__name__}: {error}".splitlines()[0], workdir
        )
    try:
        result = subprocess.run(
            [str(executable)], cwd=workdir, capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        return "timeout", "did not finish in 60 s"
    output = result.stdout.replace("\r\n", "\n")
    if result.returncode != 0:
        detail = (result.stderr or output).strip().splitlines()
        text = detail[0] if detail else f"exit {result.returncode}"
        return "runtime-error", _clean(text, workdir)
    if output != case["expect"]:
        return "wrong-output", f"expected {case['expect']!r}, got {output!r}"
    return "runs", ""


def measure() -> list[dict]:
    rows = []
    for case in CASES:
        row = {"id": case["id"], "backends": {}}
        for backend in ("c", "native"):
            with tempfile.TemporaryDirectory() as temp:
                status, note = _run_case(case, backend, pathlib.Path(temp))
            row["backends"][backend] = {"status": status, "note": note}
        rows.append(row)
    return rows


def render(rows: list[dict]) -> str:
    lines = [
        "# Backend capability matrix",
        "",
        "Generated by `tools/capability_matrix.py`; do not edit by hand.",
        "A case counts as running only when the build succeeds and the program's",
        "output matches the expected text exactly.",
        "",
        "| Case | C backend | Native backend |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        cells = []
        for backend in ("c", "native"):
            entry = row["backends"][backend]
            cell = f"`{entry['status']}`"
            if entry["note"]:
                cell += f": {entry['note']}"
            cells.append(cell.replace("|", "\\|"))
        lines.append(f"| `{row['id']}` | {cells[0]} | {cells[1]} |")
    both = sum(
        1
        for row in rows
        if row["backends"]["c"]["status"] == "runs"
        and row["backends"]["native"]["status"] == "runs"
    )
    lines.extend(
        [
            "",
            f"Summary: {both} of {len(rows)} cases run identically on both backends.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    check = "--check" in sys.argv[1:]
    text = render(measure())
    if check:
        current = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
        if current != text:
            print(f"{DOC} is stale; run python tools/capability_matrix.py")
            return 1
        print(f"{DOC} is current")
        return 0
    DOC.parent.mkdir(parents=True, exist_ok=True)
    DOC.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
