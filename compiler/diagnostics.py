"""Render compiler errors with the offending source line and a caret.

The lexer, parser, semantic pass and code generators all report errors as
``path:line: message`` strings. Rather than change every raise site, this module
turns such a message into a block that shows the source line and points at the
token that caused it:

    main.ANVL:12: undefined variable 'hp'
       12 |     health = hp - 1
          |              ^^

Quoted tokens in the message are used to position the caret, so a message like
``unknown function 'foo'`` points at ``foo`` even without a column number.
"""

from __future__ import annotations

import pathlib
import re

__all__ = ["render", "TAB_WIDTH"]

TAB_WIDTH = 4

_LOCATION = re.compile(
    r"^(?P<path>[^\r\n]+?):(?P<line>\d+)(?::(?P<col>\d+))?:[ ](?P<msg>.+)$", re.S
)
_QUOTED = re.compile(r"'([^'\r\n]{1,80})'")
_CARET_STRIP = " \t"


def _read_line(path: pathlib.Path, line_no: int) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = text.splitlines()
    if line_no < 1 or line_no > len(lines):
        return None
    return lines[line_no - 1].replace("\t", " " * TAB_WIDTH)


def _caret_column(msg: str, source: str) -> int:
    """0-based index of the token the message refers to, or 0."""
    for token in _QUOTED.findall(msg):
        if not token:
            continue
        start = 0
        while True:
            index = source.find(token, start)
            if index == -1:
                break
            # Prefer a whole-word hit so 'a' does not match inside 'array'.
            before = source[index - 1] if index else " "
            after_index = index + len(token)
            after = source[after_index] if after_index < len(source) else " "
            if not (before.isalnum() or before == "_") and not (
                after.isalnum() or after == "_"
            ):
                return index
            start = index + 1
        index = source.find(token)
        if index != -1:
            return index
    return 0


def render(message: str, max_width: int = 160) -> str:
    """Return ``message`` annotated with its source line, or unchanged."""
    stripped = message.rstrip("\r\n")
    match = _LOCATION.match(stripped.strip())
    if not match:
        return stripped

    path = pathlib.Path(match.group("path"))
    line_no = int(match.group("line"))
    body = match.group("msg").strip()
    header = stripped.strip()

    source = _read_line(path, line_no)
    if source is None:
        return header
    if len(source) > max_width:
        source = source[: max_width - 1] + "…"

    column = 0
    if match.group("col"):
        column = max(0, int(match.group("col")) - 1)
    else:
        column = _caret_column(body, source)
    column = min(column, max(0, len(source) - 1))

    # Do not point at trailing whitespace.
    while column > 0 and source[column] in _CARET_STRIP:
        column -= 1
    caret_pad = len(source[:column].replace("\t", " " * TAB_WIDTH))

    gutter = f"{line_no:>5} | "
    return f"{header}\n{gutter}{source}\n{' ' * len(gutter)}{' ' * caret_pad}^"
