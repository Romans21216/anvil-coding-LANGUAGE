"""Rust-style rendering for Anvil compiler errors and lints.

The compiler raises `path:line: message` strings.  This module turns one into
the shape programmers expect from rustc: the message, the exact location, the
source line with a caret under the offending token, and a `help:` line that
says what to write instead.  Diagnostics stay one line of plain data, so
`--emit-c`, tests and tooling keep working; only the display is enriched.
"""

from __future__ import annotations

import difflib
import pathlib
import re
import sys

_LOCATION = re.compile(r"(?P<path>.*?):(?P<line>\d+): (?P<message>.*)", re.S)
_QUOTED = re.compile(r"'([^']{1,80})'")

# Longest source line shown in a diagnostic; longer lines are windowed around
# the caret so one runaway line cannot flood the terminal.
LINE_WINDOW = 100

# Words a programmer can legitimately reach for that Anvil does not have.
MISSING_LANGUAGE = {
    "print": None,  # exists now; kept out of the hint table
    "break": "Anvil has no `break`; use a flag variable and test it in the loop condition.",
    "continue": "Anvil has no `continue`; wrap the rest of the body in an `if`.",
    "switch": "Anvil has no `switch`; write `if` / `else` / `else if`.",
    "match": "Anvil has no `match`; write `if` / `else` / `else if`.",
    "return": "`output` returns a value from a function; there is no `return`.",
    "say": None,  # exists as an alias of print
    "let": "Anvil declares globals with `set var(name) = ...` and locals with `set local(name) = ...`.",
    "const": "Anvil has no constants; assign once and do not reassign.",
    "struct": "Anvil has no structs; use parallel arrays (fixed size, numeric only).",
    "class": "Anvil has no classes; use functions plus arrays.",
    "enum": "Anvil has no enums; name numbers with `set var(name) = ...`.",
    "try": "Anvil has no exceptions; a failed call returns 0 or -1.",
    "throw": "Anvil has no exceptions; a failed call returns 0 or -1.",
    "import": "Libraries are loaded with `library import <name>`.",
    "use": "Libraries are loaded with `library import <name>`.",
    "goto": "Anvil has no `goto`; use a loop.",
}

STATEMENT_LIST = (
    "statements start with set, add, sub, call, output, if, while, for, display, "
    "print, scene, camera, clear, seed, library import, include, net"
)


def _read_line(path: str, line: int) -> str | None:
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1]
    return None


def _find_span(code: str, message: str, needle: str | None) -> tuple[int, int] | None:
    """Locate the caret (0-based column, length) inside the source line."""
    candidates: list[str] = []
    if needle:
        candidates.append(needle)
    for quoted in _QUOTED.findall(message):
        candidates.append(quoted.strip())
    if "unsupported statement: " in message:
        candidates.append(message.split("unsupported statement: ", 1)[1].strip())
    for candidate in candidates:
        if candidate and candidate in code:
            return code.index(candidate), len(candidate)
    return None


def hint_for(message: str) -> str | None:
    """The `help:` line for a message, when one can be said usefully."""
    text = message.strip()
    lowered = text.lower()

    if "else if" in lowered and "unsupported" in lowered:
        return "write `else`, then start an `if` on the next line inside that block"
    if "functions must be top-level" in lowered:
        return "move the nested function out so it starts at column 1"
    if "unclosed" in lowered and "'end'" in lowered:
        return "every block (fn, if, while, for) is closed by a line containing only `end`"
    if "expected a number, got a string" in lowered or "expected text, got a number" in lowered:
        return "text appears only in `display text(...)` and `print`; numbers are everywhere else"
    if "expected a string, got a number" in lowered:
        return "this slot takes a quoted string, for example \"hello\""
    if "invalid expression near" in lowered:
        if "^" in text:
            return "Anvil has no power operator; call pow(base, exponent) or power(base, exponent)"
        if "&" in text or "|" in text or "<<" in text or ">>" in text:
            return "Anvil has no bitwise operators"
        return "check the operators: + - * / %, comparisons, and/or, and parentheses"
    if "division by zero" in lowered:
        return "guard the divisor with an `if` before dividing"
    if "numeric overflow or non-finite" in lowered:
        return "keep every intermediate finite; sqrt() needs a value >= 0"
    if "unknown function" in lowered:
        name = _QUOTED.search(text)
        if name:
            close = difflib.get_close_matches(name.group(1), _known_functions, n=1, cutoff=0.6)
            if close:
                return f"did you mean fn({close[0]})?"
        return "declare it with `fn(name) ... end`; functions are top-level and typed by position"
    if "unknown local variable" in lowered:
        name = _QUOTED.search(text)
        if name:
            return (
                f"declare it first with `set local({name.group(1)}) = ...`; "
                f"a global of that name is read with varl({name.group(1)})"
            )
        return "locals must be declared with `set local(name) = ...` inside the function"
    if "unknown name" in lowered:
        name = _QUOTED.search(text)
        if name:
            close = difflib.get_close_matches(name.group(1), _known_builtins, n=1, cutoff=0.6)
            if close:
                return f"did you mean `{close[0]}(...)`?"
        return "variables are read as var(name), local(name) or varl(name); builtins are called as name(...)"
    if "expected 'end'" in lowered:
        return "add the missing `end` line for the block that is still open"
    if "invalid arguments for display text" in lowered:
        return "text needs a position and a quoted string: display text(\"hi\") -l(x, y)"
    if "malformed display command" in lowered:
        return "shapes are rect, circle, line, text, cube, sphere, plane, ray_sphere"
    if "array index" in lowered:
        return "indexes are whole numbers from 0 to size-1"
    if "never called" in lowered:
        return "remove the function or call it from fn(main)/fn(update)/fn(draw)"
    if "is not supported by the native x64 backend" in lowered:
        return "build with the default C backend (drop --backend native), or remove this statement"
    if "native text expects one string literal" in lowered:
        return "the native backend cannot format text yet; build this program with the C backend"
    if "unused" in lowered:
        return "remove the import, or call one of its functions"
    if "unsupported statement: " in text:
        word = text.split("unsupported statement: ", 1)[1].strip().split()
        if word:
            known = MISSING_LANGUAGE.get(word[0].lower())
            if known:
                return known
        return STATEMENT_LIST
    return None


_known_builtins: list[str] = []
_known_functions: list[str] = []


def set_hints(builtins=None, functions=None) -> None:
    """Give the hint table the vocabulary it needs for did-you-mean."""
    if builtins:
        _known_builtins[:] = sorted(builtins)
    if functions:
        _known_functions[:] = sorted(functions)


def as_dict(message: str, hint: str | None = None, needle: str | None = None,
            severity: str = "error") -> dict:
    """Return one diagnostic as structured data for editors and build servers."""
    match = _LOCATION.match(message.strip())
    if not match:
        return {"severity": severity, "message": message, "help": hint}
    path, line_text, text = match.group("path"), int(match.group("line")), match.group("message")
    column = 1
    code = _read_line(path, line_text)
    if code is not None:
        span = _find_span(code, text, needle)
        if span:
            column = len(code[:span[0]].replace("\t", "    ")) + 1
    if hint is None:
        hint = hint_for(text)
    return {
        "severity": severity,
        "file": path,
        "line": line_text,
        "column": column,
        "message": text,
        "help": hint,
    }


def _window(shown: str, column: int, caret: int) -> tuple[str, int, int]:
    """Trim a long source line to a window around the caret.

    Returns ``(displayed_text, displayed_column, displayed_caret)``. The column
    reported on the `-->` line stays absolute so editors can jump to it; only
    the excerpt is shortened, with `…` marking each removed end.
    """
    if len(shown) <= LINE_WINDOW:
        return shown, column, caret
    offset = column - 1
    start = max(0, min(offset - LINE_WINDOW // 2, len(shown) - LINE_WINDOW))
    text = shown[start:start + LINE_WINDOW]
    display_offset = offset - start
    if start > 0:
        text = "…" + text
        display_offset += 1
    if start + LINE_WINDOW < len(shown):
        text = text + "…"
    display_column = display_offset + 1
    display_caret = max(1, min(caret, len(text) - display_offset))
    return text, display_column, display_caret


def render(message: str, hint: str | None = None, needle: str | None = None,
           length: int | None = None, severity: str = "error",
           color: bool | None = None) -> str:
    """Render one diagnostic exactly as it will be shown to the programmer."""
    match = _LOCATION.match(message.strip())
    if not match:
        return f"{severity}: {message}"

    path, line_text, text = match.group("path"), int(match.group("line")), match.group("message")
    code = _read_line(path, line_text)
    if code is None:
        return f"{severity}: {text}\n  --> {path}:{line_text}"

    span = _find_span(code, text, needle)
    # Tabs are shown as four spaces; keep the caret aligned with what is drawn.
    shown = code.replace("\t", "    ")
    column = 0
    caret = 1
    if span:
        prefix, width = span
        column = len(code[:prefix].replace("\t", "    "))
        caret = max(1, width)
    column += 1

    if hint is None:
        hint = hint_for(text)

    if color is None:
        color = sys.stderr.isatty()
    head = f"\x1b[1;31m{severity}\x1b[0m" if color and severity == "error" else \
           f"\x1b[1;33m{severity}\x1b[0m" if color else severity
    gutter = len(str(line_text))
    pad = " " * (gutter + 1)
    display_text, display_column, display_caret = _window(shown, column, caret)
    out = [
        f"{head}: {text}",
        f"{pad}--> {path}:{line_text}:{column}",
        f"{pad}|",
        f"{line_text:>{gutter}} | {display_text}",
        f"{pad}| {' ' * (display_column - 1)}{'^' * display_caret}",
    ]
    if hint:
        out.append(f"{pad}|")
        out.append(f"{pad}= help: {hint}")
    return "\n".join(out)
