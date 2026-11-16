"""Stable diagnostic codes for the common compile errors.

Raise sites report `path:line: message`; retrofitting a code onto every one of
them would be noisy and easy to get wrong, so a code is derived from the
message text at the point it is rendered. Each pattern is a stable contract:
`--explain ANV102` prints the cause and the fix, and editor-format diagnostics
carry `error[ANV102]` so a tool can link to it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["CATEGORIES", "Category", "classify", "explain"]


@dataclass(frozen=True)
class Category:
    code: str
    name: str
    pattern: re.Pattern[str]
    cause: str
    fix: str


CATEGORIES: tuple[Category, ...] = (
    Category(
        "ANV101",
        "unknown name",
        re.compile(r"unknown name '[^']+'"),
        "A bare name is not a value. The compiler treats an unquoted word as a "
        "value that must already exist, and nothing with that name is in scope.",
        "Read a variable with var(name), or call a function with call fn(name, ...). "
        "If the name is a typo, the message usually suggests the closest match.",
    ),
    Category(
        "ANV102",
        "unknown variable",
        re.compile(r"unknown variable '[^']+'"),
        "The variable is read before it has ever been assigned, so no storage "
        "exists for it.",
        "Assign it first with set var(name) = value. Function parameters are "
        "already variables; locals declared with set local(name) need local(name) "
        "to read them.",
    ),
    Category(
        "ANV103",
        "unknown local variable",
        re.compile(r"unknown local variable '[^']+'"),
        "local(name) refers to a function-local binding that this function never "
        "declares.",
        "Declare it with set local(name) = value before reading it. Locals are "
        "per call and do not survive a return.",
    ),
    Category(
        "ANV104",
        "unknown function",
        re.compile(r"unknown function '[^']+'"),
        "A call names a function that is not declared anywhere in the program or "
        "its includes.",
        "Check the spelling, or declare the function with fn(name) before calling "
        "it. Includes must be listed at the top of the file.",
    ),
    Category(
        "ANV105",
        "wrong argument count",
        re.compile(r"function '[^']+' expects \d+ argument\(s\), got \d+"),
        "The function was declared with a different number of parameters than "
        "this call passes.",
        "Pass exactly the declared number of arguments, or change the declaration. "
        "The message states both counts.",
    ),
    Category(
        "ANV106",
        "unclosed block",
        re.compile(r"unclosed function|expected 'end'"),
        "A block was opened (fn, if, while, for) and never closed, so the parser "
        "ran out of file while still inside it.",
        "Add the missing end for the block named in the message. Indentation does "
        "not close blocks in Anvil.",
    ),
    Category(
        "ANV107",
        "unterminated text",
        re.compile(r"unterminated string"),
        "A text literal was opened with a quote and the line ended before the "
        "closing quote.",
        'Close the string. Supported escapes are ' + chr(92) + 'n, ' + chr(92) + 't, '
        + chr(92) + '" and ' + chr(92) + chr(92) + '; a raw newline cannot appear inside '
        "one line.",
    ),
    Category(
        "ANV108",
        "non-finite number",
        re.compile(r"numeric literal must be finite|non-finite"),
        "A numeric literal or computed value is NaN or infinite, which Anvil "
        "rejects so comparisons stay meaningful.",
        "Use a finite literal, or guard the division/modulo that produced it. "
        "Anvil numbers are IEEE-754 doubles.",
    ),
    Category(
        "ANV109",
        "statement outside a function",
        re.compile(r"only configuration, initial values, and calls are allowed at top level"),
        "A statement that needs a function body was written at top level.",
        "Move the statement into fn(main) or another function. Top level accepts "
        "configuration, arrays, enums, includes, initial values and calls.",
    ),
    Category(
        "ANV110",
        "no entry function",
        re.compile(r"define at least one fn\(name\) function"),
        "The program has no functions at all, so there is nothing to run.",
        "Add fn(main) with the program's statements and end with call fn(main).",
    ),
)


def message_body(message: str) -> str:
    """Drop a leading `path:line:` (and optional column) from a diagnostic."""
    return re.sub(r"^[^\r\n]*?:\d+(?::\d+)?:\s*", "", message.strip(), count=1)


def classify(message: str) -> Category | None:
    body = message_body(message)
    for category in CATEGORIES:
        if category.pattern.search(body):
            return category
    return None


def by_code(code: str) -> Category | None:
    wanted = code.strip().upper()
    for category in CATEGORIES:
        if category.code == wanted:
            return category
    return None


def explain(code: str) -> str | None:
    category = by_code(code)
    if category is None:
        return None
    return (
        f"error[{category.code}]: {category.name}" + chr(10) + chr(10)
        + "Cause: " + category.cause + chr(10) + chr(10)
        + "Fix: " + category.fix
    )


def code_list() -> str:
    return ", ".join(f"{category.code} ({category.name})" for category in CATEGORIES)
