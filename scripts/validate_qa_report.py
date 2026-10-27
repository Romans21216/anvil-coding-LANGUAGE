#!/usr/bin/env python3
"""Check the current QA rubric's criterion, category, and total arithmetic."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "QA_REPORT.md"


def fail(message: str) -> int:
    print(f"QA report validation failed: {message}", file=sys.stderr)
    return 1


def main() -> int:
    report = REPORT.read_text(encoding="utf-8")
    table_start = report.find("| # | Criterion | Score | Evidence, deduction, and status |")
    table_end = report.find("### Deduction details and follow-up", table_start)
    if table_start < 0 or table_end < 0:
        return fail("could not locate the current 50-criterion rubric")

    table = report[table_start:table_end]
    criterion_rows = [
        (int(number), int(score))
        for number, score in re.findall(r"^\| (\d+) \| [^\n]*? \| ([12]) \|", table, re.MULTILINE)
    ]
    criteria = dict(criterion_rows)
    if len(criterion_rows) != 50 or set(criteria) != set(range(1, 51)):
        return fail(f"expected criteria 1–50 exactly once, found {len(criterion_rows)} rows")

    categories = {
        "Requirement fulfillment": (1, 10),
        "Functionality and reliability": (11, 20),
        "Code quality and architecture": (21, 30),
        "Testing and verification": (31, 40),
        "Developer experience and delivery": (41, 50),
    }
    declared: dict[str, int] = {}
    for name in categories:
        match = re.search(
            rf"^\| \| \*\*{re.escape(name)}\*\* \| \*\*(\d+)/20\*\* \|.*$",
            table,
            re.MULTILINE,
        )
        if not match:
            return fail(f"missing subtotal for {name}")
        declared[name] = int(match.group(1))

    for name, (first, last) in categories.items():
        actual = sum(criteria[index] for index in range(first, last + 1))
        if declared[name] != actual:
            return fail(f"{name} declares {declared[name]}/20, criterion rows sum to {actual}/20")

    total_match = re.search(r"^\| \| \*\*Total\*\* \| \*\*(\d+)/100\*\* \|", table, re.MULTILINE)
    latest_match = re.search(r"\*\*Latest independent evaluation:\*\* \*\*(\d+)/100", report)
    if not total_match or not latest_match:
        return fail("missing declared total or latest evaluation score")
    total = sum(criteria.values())
    declared_total = int(total_match.group(1))
    latest_total = int(latest_match.group(1))
    if declared_total != total or latest_total != total:
        return fail(
            f"criterion rows sum to {total}/100; table declares {declared_total}/100 and header declares {latest_total}/100"
        )

    print(f"QA rubric arithmetic passes: 50 criteria = {total}/100; category subtotals agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
