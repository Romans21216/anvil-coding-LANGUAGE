"""Conservative source formatter for the stable `format` command (8.14).

Indentation is not significant in Anvil, so the formatter can safely re-indent
by block depth. It never rewrites a line's tokens: it only normalises line
endings, trailing whitespace, blank-line runs, the final newline and leading
indentation.
"""

from __future__ import annotations

INDENT = "  "
BLOCK_STARTERS = ("fn", "if", "while", "for", "repeat")


def _opens_block(stripped: str) -> bool:
    head = stripped.split()[0] if stripped.split() else ""
    for starter in BLOCK_STARTERS:
        if head == starter:
            return True
        if head.startswith(starter) and len(head) > len(starter) and head[len(starter)] in "( ":
            return True
    return False


def format_source(text: str) -> str:
    """Return the file with normalised whitespace and block indentation."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    depth = 0
    for raw in normalized.split("\n"):
        stripped = raw.strip()
        if not stripped:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        keyword = stripped.split()[0]
        if keyword == "end":
            depth = max(0, depth - 1)
            lines.append(INDENT * depth + stripped)
        elif keyword == "else":
            depth = max(0, depth - 1)
            lines.append(INDENT * depth + stripped)
            depth += 1
        else:
            lines.append(INDENT * depth + stripped)
            if _opens_block(stripped):
                depth += 1
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"
