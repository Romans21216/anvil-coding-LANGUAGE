"""Close-name suggestions for unknown identifiers.

Diagnostics point at the identifier and, when the guess is unambiguous and
close enough to be useful, name the candidate the author probably meant.
Short names are never corrected: `x` and `y` are one edit apart and a
suggestion there would be noise rather than help.
"""

from __future__ import annotations

from collections.abc import Iterable

MIN_LENGTH = 3
MAX_DISTANCE = 2


def _distance(left: str, right: str, limit: int) -> int:
    """Damerau-Levenshtein distance, or limit + 1 when it exceeds the limit."""
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    before_previous: list[int] = []
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        row_minimum = i
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            value = min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + cost,  # substitution
            )
            if (
                i > 1
                and j > 1
                and left_char == right[j - 2]
                and left[i - 2] == right_char
            ):
                value = min(value, before_previous[j - 2] + 1)
            current.append(value)
            if value < row_minimum:
                row_minimum = value
        if row_minimum > limit:
            return limit + 1
        before_previous, previous = previous, current
    return previous[-1]


def closest_name(name: str, candidates: Iterable[str]) -> str | None:
    """Return the single close candidate for a name, or None when unsure."""
    if len(name) < MIN_LENGTH:
        return None
    budget = min(MAX_DISTANCE, max(1, len(name) // 3))
    lowered = name.lower()
    best: str | None = None
    best_distance = budget + 1
    tied = False
    for candidate in sorted(set(candidates)):
        if not candidate or candidate == name:
            continue
        distance = _distance(lowered, candidate.lower(), budget)
        if distance > budget:
            continue
        if distance < best_distance:
            best, best_distance, tied = candidate, distance, False
        elif distance == best_distance:
            tied = True
    return None if best is None or tied else best


def suggestion_suffix(name: str, candidates: Iterable[str]) -> str:
    """A `; did you mean 'x'?` suffix, or an empty string when unsure."""
    match = closest_name(name, candidates)
    return f"; did you mean {match!r}?" if match is not None else ""
