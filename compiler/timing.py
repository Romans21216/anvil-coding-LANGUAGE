"""Phase timing for the `--timings` flag.

Kept out of the CLI body so the compile pipeline stays timing-free: the CLI
only marks boundaries, and this object decides whether anything is printed.
Phases are reported in the order they were marked, with a total that equals
the sum of the phases, so nothing is hidden in an unmarked gap.
"""

from __future__ import annotations

import sys
import time


class Timings:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self._started = time.perf_counter()
        self._marks: list[tuple[str, float]] = []

    def mark(self, phase: str) -> None:
        """Close the current phase and start the next one."""
        if not self.enabled:
            return
        now = time.perf_counter()
        self._marks.append((phase, now - self._started))
        self._started = now

    @staticmethod
    def _milliseconds(seconds: float) -> int:
        return max(0, int(round(seconds * 1000)))

    def report(self, stream=None) -> None:
        if not self.enabled or not self._marks:
            return
        target = stream if stream is not None else sys.stderr
        parts = [
            f"{phase} {self._milliseconds(seconds)} ms"
            for phase, seconds in self._marks
        ]
        total = sum(seconds for _, seconds in self._marks)
        parts.append(f"total {self._milliseconds(total)} ms")
        print("timings: " + ", ".join(parts), file=target)
