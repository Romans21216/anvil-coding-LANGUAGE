"""Text expressions: one lowering path for `display text` and `print`.

A text context accepts a quoted string, a `+` chain that mixes text and numeric
expressions, and any text builtin (`upper`, `mid`, `replace`, ...).  A bare
numeric expression is formatted with the single number format.  Everything
lowers to a C `const char *`, so `display text(...)` and `print` share one
implementation and one set of rules.
"""

from __future__ import annotations

from compiler.expressions import ExpressionParser


def text_expression(
    path,
    line: int,
    source: str,
    functions,
    scope=None,
    arrays=None,
    temporary_owner=None,
    temporary_counter=None,
) -> str:
    """Lower one text expression to a C `const char *` expression."""
    source = (source or "").strip()
    if not source:
        return '""'
    parser = ExpressionParser(
        path, line, source, functions, scope, arrays,
        temporary_owner, temporary_counter,
    )
    code, kind = parser.parse_full()
    if kind == "string":
        return code
    return f"anvil_str_num({parser.checked_number(code)})"
