"""Lexical helpers shared by the Anvil parser."""

from __future__ import annotations

import pathlib

from compiler.common import CompileError


def strip_comment(line: str) -> str:
    quoted = False
    escaped = False
    for i, ch in enumerate(line):
        if escaped:
            escaped = False
        elif ch == "\\" and quoted:
            escaped = True
        elif ch == '"':
            quoted = not quoted
        elif ch == "#" and not quoted:
            return line[:i]
    return line


def mask_strings(text: str) -> str:
    """Blank quoted contents and delimiters while preserving source positions."""
    result = list(text)
    quoted = escaped = False
    for index, char in enumerate(text):
        if quoted:
            result[index] = " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            result[index] = " "
            quoted = True
    return "".join(result)


def validate_port(path: pathlib.Path, line: int, text: str) -> None:
    try:
        port = int(text)
    except ValueError as exc:
        raise CompileError(f"{path}:{line}: invalid UDP port") from exc
    if not 1 <= port <= 65535:
        raise CompileError(f"{path}:{line}: UDP port must be between 1 and 65535")


def split_keyword(text: str, keyword: str) -> tuple[str, str] | None:
    """Split at a standalone keyword outside strings and parentheses."""
    depth, quoted, escaped = 0, False, False
    index = 0
    while index < len(text):
        ch = text[index]
        if escaped:
            escaped = False
        elif ch == "\\" and quoted:
            escaped = True
        elif ch == '"':
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
        elif not quoted and depth == 0 and text.startswith(keyword, index):
            before_ok = index > 0 and text[index - 1].isspace()
            after = index + len(keyword)
            after_ok = after < len(text) and text[after].isspace()
            if before_ok and after_ok:
                return text[:index].strip(), text[after:].strip()
        index += 1
    return None
