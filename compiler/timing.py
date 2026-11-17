"""Phase timing for the `--timings` flag.

Kept out of the CLI body so the compile pipeline stays timing-free: the CLI
only marks boundaries, and this object decides whether anything is printed.
Phases are reported in the order they were marked, with a total that equals
the sum of the phases, so nothing is hidden in an unmarked gap.
"""

from __future__ import annotations

import sys
import json
import pathlib
import platform
import time


class Timings:
    def __init__(self, enabled: bool, json_path: pathlib.Path | None = None) -> None:
        self.enabled = enabled
        self.json_path = json_path
        self.capture_enabled = enabled or json_path is not None
        self._started = time.perf_counter() if self.capture_enabled else 0.0
        self._marks: list[tuple[str, float]] = []
        self.metadata: dict = {}

    def mark(self, phase: str) -> None:
        """Close the current phase and start the next one."""
        if not self.capture_enabled:
            return
        now = time.perf_counter()
        self._marks.append((phase, now - self._started))
        self._started = now

    def set_metadata(self, **values) -> None:
        self.metadata.update(values)

    def _profile(self) -> dict:
        durations = [
            {"name": phase, "value": round(seconds * 1000.0, 3), "unit": "ms"}
            for phase, seconds in self._marks
        ]
        return {
            "schema": "anvil.build-profile",
            "version": 1,
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "processor": platform.processor() or None,
            },
            "phases": durations,
            "total": {
                "value": round(sum(seconds for _, seconds in self._marks) * 1000.0, 3),
                "unit": "ms",
            },
            "artifacts": dict(self.metadata),
            "memory": {"peak_bytes": None, "measurement": "not available in compiler process"},
        }

    @staticmethod
    def _milliseconds(seconds: float) -> int:
        return max(0, int(round(seconds * 1000)))

    def report(self, stream=None) -> None:
        if not self._marks:
            return
        if self.enabled:
            target = stream if stream is not None else sys.stderr
            parts = [
                f"{phase} {self._milliseconds(seconds)} ms"
                for phase, seconds in self._marks
            ]
            total = sum(seconds for _, seconds in self._marks)
            parts.append(f"total {self._milliseconds(total)} ms")
            print("timings: " + ", ".join(parts), file=target)
        if self.json_path is not None:
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            self.json_path.write_text(
                json.dumps(self._profile(), indent=2) + "\n", encoding="utf-8"
            )
