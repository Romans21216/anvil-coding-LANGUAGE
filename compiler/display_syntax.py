"""Shared display suffix parsing; independent of either code-generation backend."""

import re

from compiler.common import CompileError
from compiler.lexer import mask_strings


def take_display_modifiers(raw, names, path, line):
    """Extract only top-level suffixes; retain original literal/expression spans."""
    masked = mask_strings(raw)
    found, spans = [], []
    depth = index = 0
    while index < len(masked):
        char = masked[index]
        if depth == 0 and char == "-" and index > 0 and masked[index - 1].isspace():
            match = re.match(r"-(rgb|rgba|rotate|l)\(", masked[index:])
            if match and match.group(1) in names:
                argument_start = index + match.end()
                end, nested = argument_start, 1
                while end < len(masked) and nested:
                    nested += (masked[end] == "(") - (masked[end] == ")")
                    end += 1
                if nested:
                    raise CompileError(f"{path}:{line}: unclosed -{match.group(1)} display modifier")
                found.append((match.group(1), raw[argument_start:end - 1]))
                spans.append((index, end))
                index = end
                continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        index += 1
    remaining, previous = [], 0
    for start, end in spans:
        remaining.append(raw[previous:start])
        previous = end
    remaining.append(raw[previous:])
    return found, "".join(remaining)

