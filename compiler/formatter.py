"""Re-indent Anvil source without changing what it means.

Anvil ends blocks with the word ``end`` and treats indentation as cosmetic, so a
formatter only needs to rewrite leading whitespace. The rules mirror the parser:
``fn``, ``if``, ``else if``, ``while`` and ``for`` open a block, ``else`` closes
and reopens the same depth, and ``end`` closes one. Everything else keeps the
current depth. Blank lines stay blank and trailing whitespace is removed.

    python -m compiler.anvil game.ANVL --format        # rewrite in place
    python -m compiler.anvil game.ANVL --format-check  # exit 1 when unformatted
"""

from __future__ import annotations

import re

INDENT = "  "

_OPENER = re.compile(r"^(?:fn\s*\(|if\s+|else\s+if\s+|while\s+|for\s+local\s*\()")
_CLOSE = re.compile(r"^end\b")
_ELSE = re.compile(r"^else\b")


def format_source(text: str) -> str:
    """Return ``text`` with canonical two-space block indentation."""
    depth = 0
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        if _CLOSE.match(line):
            depth = max(0, depth - 1)
            lines.append(INDENT * depth + line)
            continue
        if _ELSE.match(line):
            depth = max(0, depth - 1)
            lines.append(INDENT * depth + line)
            depth += 1
            continue
        lines.append(INDENT * depth + line)
        if _OPENER.match(line):
            depth += 1
    return "\n".join(lines)


def is_formatted(text: str) -> bool:
    return format_source(text) == text
