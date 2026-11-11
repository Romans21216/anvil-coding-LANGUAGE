#!/usr/bin/env python3
"""Score the Anvil language against a beginner-focused rubric.

Every line of the rubric is backed by a program that is compiled and executed (or
a command that is really run), so the grade is reproducible rather than asserted:
`python tools/grade_anvil.py`.

The rubric weights add up to 100; the score is the weight of the checks that pass.
"""

from __future__ import annotations

import io
import contextlib
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler.build import build_c, find_compiler  # noqa: E402
from compiler.codegen import emit_c  # noqa: E402
from compiler.native_codegen import NativeCodegen  # noqa: E402
from compiler.parser import parse  # noqa: E402
from compiler.repl import hello_main, repl_main  # noqa: E402

RUBRIC: list[tuple[str, int, str, str, str]] = []


def check(category: str, weight: int, name: str, program: str, expected: str) -> None:
    RUBRIC.append((category, weight, name, program, expected))


# --- 1. First contact: the greeting path (15) -------------------------------
check("first contact", 5, "lesson 1 hello world runs",
      'fn(main)\n  say "Hello, world!"\nend\ncall fn(main)\n', "Hello, world!\n")
check("first contact", 5, "the greeting program greets the player",
      'fn(main)\n  ask "What is your name? ", var(name)\n'
      '  say "Hello, " & trim(var(name)) & "!"\nend\ncall fn(main)\n',
      "What is your name? Hello, Ada!\n")
check("first contact", 5, "names, joins and arithmetic in the first minute",
      'fn(main)\n  set var(score) = 10\n  add var(score) 5\n'
      '  say "Score: " & var(score)\nend\ncall fn(main)\n', "Score: 15\n")

# --- 2. Core syntax (20) ----------------------------------------------------
check("core syntax", 4, "arithmetic respects precedence",
      "fn(main)\n  say 3 + 4 * 2\nend\ncall fn(main)\n", "11\n")
check("core syntax", 4, "remainder works",
      "fn(main)\n  say 7 % 3\n  say 7.5 % 2\nend\ncall fn(main)\n", "1\n1.5\n")
check("core syntax", 4, "if / elif / else",
      "fn(main)\n  set var(age) = 15\n  if var(age) >= 18\n    say \"adult\"\n"
      '  elif var(age) >= 13\n    say "teen"\n  else\n    say "child"\n  end\n'
      "end\ncall fn(main)\n", "teen\n")
check("core syntax", 4, "for, while and repeat",
      "fn(main)\n  repeat 2\n    say \"hip\"\n  end\n"
      '  for local(i) = 1 to 2\n    say "n " & local(i)\n  end\n'
      "  set var(k) = 2\n  while var(k) > 0\n    say var(k)\n    add var(k) -1\n"
      "  end\nend\ncall fn(main)\n", "hip\nhip\nn 1\nn 2\n2\n1\n")
check("core syntax", 4, "functions return values",
      "fn(double, value)\n  output var(value) * 2\nend\n"
      "fn(main)\n  say call fn(double, 21)\nend\ncall fn(main)\n", "42\n")

# --- 3. Text toolkit (20) ---------------------------------------------------
check("text toolkit", 3, "join and length",
      'fn(main)\n  set var(n) = "ada"\n  say "hi " & var(n)\n  say len(var(n))\n'
      "end\ncall fn(main)\n", "hi ada\n3\n")
check("text toolkit", 3, "upper and lower",
      'fn(main)\n  say upper("ada")\n  say lower("LOUD")\nend\ncall fn(main)\n',
      "ADA\nloud\n")
check("text toolkit", 2, "left and right",
      'fn(main)\n  say left("Anvil", 3)\n  say right("Anvil", 3)\n'
      "end\ncall fn(main)\n", "Anv\nvil\n")
check("text toolkit", 2, "mid and char",
      'fn(main)\n  say mid("Anvil", 2, 2)\n  say char("Anvil", 0)\n'
      "end\ncall fn(main)\n", "vi\nA\n")
check("text toolkit", 2, "trim and number",
      'fn(main)\n  set var(w) = "  x  "\n  say "[" & trim(var(w)) & "]"\n'
      '  say number("42") + 8\nend\ncall fn(main)\n', "[x]\n50\n")
check("text toolkit", 2, "chr and ord",
      "fn(main)\n  say chr(65)\n  say ord(\"A\")\nend\ncall fn(main)\n", "A\n65\n")
check("text toolkit", 3, "contains, starts_with, ends_with",
      'fn(main)\n  say contains("anvil", "vil")\n  say starts_with("anvil", "an")\n'
      '  say ends_with("anvil", "il")\nend\ncall fn(main)\n', "1\n1\n1\n")
check("text toolkit", 3, "text comparison and equality",
      'fn(main)\n  if "abc" < "abd"\n    say "ordered"\n  end\n'
      '  if "yes" = "yes"\n    say "equal"\n  end\nend\ncall fn(main)\n',
      "ordered\nequal\n")

# --- 4. Data (15) -----------------------------------------------------------
check("data", 5, "arrays store and read",
      "array scores(3)\nfn(main)\n  set array(scores, 0) = 10\n"
      "  set array(scores, 1) = 20\n  set array(scores, 2) = 30\n"
      "  set var(t) = 0\n  for local(i) = 0 to 2\n"
      "    add var(t) array(scores, local(i))\n  end\n  say var(t)\n"
      "end\ncall fn(main)\n", "60\n")
check("data", 5, "text-returning functions",
      'fn(greet)\n  output "hello"\nend\nfn(main)\n  say call fn(greet)\n'
      "end\ncall fn(main)\n", "__C__hello\n")
check("data", 5, "growable lists",
      "list nums\nfn(main)\n  add nums 5\n  add nums 7\n  say count(nums)\n"
      "  say array(nums, 1)\nend\ncall fn(main)\n", "2\n7\n")

# --- 5. Diagnostics (15) ----------------------------------------------------
check("diagnostics", 5, "undefined variable points at the line",
      'fn(main)\n  set var(total) = 1\n  say missing\nend\ncall fn(main)\n',
      "__DIAG__missing")
check("diagnostics", 5, "bare name offers the var(...) spelling",
      'fn(main)\n  set var(total) = 1\n  say total\nend\ncall fn(main)\n',
      "__DIAG__var(")
check("diagnostics", 5, "text returns also work on the native backend",
      'fn(greet)\n  output "hello"\nend\nfn(main)\n  say call fn(greet)\n'
      "end\ncall fn(main)\n", "__NATIVE__hello\n")

# --- 6. Shell (8) -----------------------------------------------------------
check("shell", 4, "assignment echo and reuse",
      "__REPL__x = 2\nsay x * 3\n:quit\n", "x = 2|6")
check("shell", 4, "blocks run in the shell",
      '__REPL__repeat 2\nsay "ho"\nend\n:quit\n', "ho|ho")

# --- 7. Learning path (7) ---------------------------------------------------
check("learning path", 7, "ten tutorial lessons exist", "__TUTORIAL__", "__TUTORIAL__")

WEIGHT_TOTAL = sum(entry[1] for entry in RUBRIC)
assert WEIGHT_TOTAL == 100, WEIGHT_TOTAL


def _run(program: str, backend: str) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as temp:
        temp_path = pathlib.Path(temp)
        source = temp_path / "check.ANVL"
        source.write_text(program, encoding="utf-8")
        functions, top, variables, arrays = parse(source, program)
        executable = temp_path / "check.exe"
        with contextlib.redirect_stdout(io.StringIO()):
            if backend == "native":
                executable.write_bytes(
                    NativeCodegen(source, functions, top, variables, arrays).generate()
                )
            else:
                c_file = temp_path / "check.c"
                c_file.write_text(
                    emit_c(source, functions, top, variables, arrays), encoding="utf-8"
                )
                compiler = find_compiler(None)
                if compiler is None:
                    raise RuntimeError("MSVC is not available")
                build_c(compiler[1], c_file, executable, release=True)
        result = subprocess.run(
            [str(executable)],
            input="Ada\n",
            capture_output=True,
            text=True,
            timeout=25,
        )
        return result.returncode, result.stdout.replace("\r\n", "\n"), result.stderr


def _diagnose(program: str) -> tuple[int, str]:
    """Run the real CLI so the caret-rendered diagnostic is what gets checked."""
    with tempfile.TemporaryDirectory() as temp:
        source = pathlib.Path(temp) / "check.ANVL"
        source.write_text(program, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "compiler" / "anvil.py"), str(source), "--emit-c", str(pathlib.Path(temp) / "check.c")],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode, result.stderr + result.stdout


def evaluate() -> tuple[float, list[tuple[str, int, str, bool, str]]]:
    rows = []
    for category, weight, name, program, expected in RUBRIC:
        passed, detail = False, ""
        try:
            if program.startswith("__REPL__"):
                stdout = io.StringIO()
                repl_main(stdin=io.StringIO(program[8:]), stdout=stdout)
                text = stdout.getvalue()
                passed = all(part in text for part in expected.split("|"))
                detail = "shell output"
            elif program == "__TUTORIAL__":
                lessons = sorted((ROOT / "examples" / "tutorial").glob("*.ANVL"))
                passed = len(lessons) >= 10
                detail = f"{len(lessons)} lessons"
            elif expected.startswith("__NATIVE__"):
                native_code, native_out, native_err = _run(program, "native")
                passed = native_code == 0 and native_out == expected[10:]
                if not passed:
                    first = (native_err or native_out).strip().splitlines()
                    detail = f"native: {first[0] if first else 'no output'}"
            elif expected.startswith("__C__"):
                code, out, err = _run(program, "c")
                passed = code == 0 and out == expected[5:]
                if not passed:
                    detail = f"c: {out!r}"
            elif expected.startswith("__DIAG__"):
                code, text = _diagnose(program)
                passed = code != 0 and expected[8:] in text and "^" in text
                detail = "caret diagnostic" if passed else text.strip().splitlines()[0]
            else:
                code, out, err = _run(program, "c")
                native_code, native_out, native_err = _run(program, "native")
                passed = (
                    code == 0
                    and out == expected
                    and native_code == 0
                    and native_out == expected
                )
                if not passed:
                    detail = f"c={out!r} native={native_out!r}"
        except Exception as error:  # noqa: BLE001 - report, never crash the grader
            detail = f"{type(error).__name__}: {error}"
        rows.append((category, weight, name, passed, detail))
    score = sum(weight for _, weight, _, passed, _ in rows if passed)
    return float(score), rows


def main() -> int:
    devnull = os.open(os.devnull, os.O_WRONLY)
    saved = os.dup(1)
    os.dup2(devnull, 1)
    try:
        score, rows = evaluate()
    finally:
        os.dup2(saved, 1)
        os.close(saved)
        os.close(devnull)
    print("Anvil beginner-language rubric\n")
    current = None
    for category, weight, name, passed, detail in rows:
        if category != current:
            current = category
            print(f"[{category}]")
        mark = "PASS" if passed else "FAIL"
        print(f"  {mark} ({weight:>2}) {name}" + (f"  -- {detail}" if detail else ""))
    print(f"\nScore: {score:.0f}/100  ->  {score / 10:.1f}/10")
    return 0 if score >= 80 else 1


if __name__ == "__main__":
    raise SystemExit(main())
