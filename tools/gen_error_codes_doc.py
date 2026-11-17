"""Regenerate docs/ERRORS.md from compiler/error_codes.py.

Run after adding or editing a diagnostic code:

    python tools/gen_error_codes_doc.py

tests/test_error_codes.py checks that the page lists every code, so a forgotten
regeneration fails the suite instead of drifting silently.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compiler.error_codes import CATEGORIES  # noqa: E402

NL = chr(10)


def render() -> str:
    lines = [
        "# Diagnostic codes",
        "",
        "Every compiler message that has a stable code is listed here. The codes come",
        "from `compiler/error_codes.py`, which also powers `anvil.py --explain CODE`;",
        "this page is generated from that table by `tools/gen_error_codes_doc.py`, so",
        "the two cannot drift.",
        "",
        "| Code | Error | Cause | Fix |",
        "| --- | --- | --- | --- |",
    ]
    for category in CATEGORIES:
        lines.append(
            f"| `{category.code}` | {category.name} | {category.cause} | {category.fix} |"
        )
    lines += [
        "",
        "Ask the compiler about one code:",
        "",
        "```",
        "python compiler/anvil.py --explain ANV102",
        "```",
        "",
        "Messages without a code are either internal checks or one-off diagnostics;",
        "they still carry `path:line` and a caret, and `--diagnostics editor` adds a",
        "column for editor integration.",
        "",
    ]
    return NL.join(lines)


def main() -> None:
    path = ROOT / "docs" / "ERRORS.md"
    path.write_text(render(), encoding="utf-8")
    print("wrote", path, "with", len(CATEGORIES), "codes")


if __name__ == "__main__":
    main()
