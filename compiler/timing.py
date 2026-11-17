"""Phase timing for the `--timings` flag.

Kept out of the CLI body so the compile pipeline stays timing-free: the CLI
only marks boundaries, and this object decides whether anything is printed.
Phases are reported in the order they were marked, with a total that equals
the sum of the phases, so nothing is hidden in an unmarked gap.
"""

from __future__ import annotations

import json
import pathlib
import platform
import sys
import tracemalloc
import time


class _DisabledTimings:
    """Shared zero-allocation sink used when no timing output was requested."""

    __slots__ = ()

    def mark(self, phase: str) -> None:
        return None

    def set_metadata(self, **values) -> None:
        return None

    def report(self, stream=None) -> None:
        return None


DISABLED_TIMINGS = _DisabledTimings()


class Timings:
    def __init__(self, enabled: bool, json_path: pathlib.Path | None = None) -> None:
        self.enabled = enabled
        self.json_path = json_path
        self.capture_enabled = enabled or json_path is not None
        self._owns_trace = json_path is not None and not tracemalloc.is_tracing()
        if self._owns_trace:
            tracemalloc.start()
        self._trace_start_bytes: int | None = None
        if json_path is not None and tracemalloc.is_tracing():
            # Profiles describe this invocation, even when embedded in a host
            # that started tracemalloc earlier. Keep tracing active, but reset
            # its high-water mark to the current allocation baseline.
            self._trace_start_bytes = tracemalloc.get_traced_memory()[0]
            tracemalloc.reset_peak()
        self._started = time.perf_counter() if self.capture_enabled else 0.0
        self._marks: list[tuple[str, float]] | None = [] if self.capture_enabled else None
        self.metadata: dict | None = {} if self.capture_enabled else None
        self._peak_bytes: int | None = None
        self._peak_working_set_bytes: int | None = None

    @staticmethod
    def _process_peak_working_set() -> int | None:
        from compiler.process_memory import current_process_peak_working_set_bytes

        return current_process_peak_working_set_bytes()

    def mark(self, phase: str) -> None:
        """Close the current phase and start the next one."""
        if not self.capture_enabled:
            return
        now = time.perf_counter()
        assert self._marks is not None
        self._marks.append((phase, now - self._started))
        self._started = now

    def set_metadata(self, **values) -> None:
        if self.metadata is not None:
            self.metadata.update(values)

    def _profile(self) -> dict:
        durations = [
            {"name": phase, "value": round(seconds * 1000.0, 3), "unit": "ms"}
            for phase, seconds in self._marks
        ]
        try:
            from compiler import gltf

            asset_seconds = gltf.import_time_seconds()
        except ImportError:
            asset_seconds = 0.0
        try:
            from compiler import wasm

            asset_seconds += wasm.asset_import_time_seconds()
            child_working_set = wasm.toolchain_peak_working_set_bytes()
            process_tree_working_set = wasm.toolchain_process_tree_peak_working_set_bytes()
        except ImportError:
            child_working_set = None
            process_tree_working_set = None
        asset_import_ms = round(asset_seconds * 1000.0, 3)
        return {
            "schema": "anvil.build-profile",
            "version": 1,
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "processor": platform.processor() or None,
            },
            "phases": durations,
            "asset_import": {
                "value": asset_import_ms,
                "unit": "ms",
                "sources": ["glTF model importer", "WASM BMP/WAV bakers"],
            },
            "total": {
                "value": round(sum(seconds for _, seconds in (self._marks or ())) * 1000.0, 3),
                "unit": "ms",
            },
            "artifacts": dict(self.metadata or {}),
            "memory": {
                "peak_bytes": self._peak_bytes,
                "measurement": "Python allocations traced by tracemalloc",
                "peak_working_set_bytes": self._peak_working_set_bytes,
                "process_measurement": "Windows process high-water working set; excludes child processes",
                "child_peak_working_set_bytes": child_working_set,
                "toolchain_process_tree_peak_working_set_bytes": process_tree_working_set,
                "child_process_measurement": "WASM clang direct child high-water working set; process-tree field is sampled combined current working set; Windows only",
            },
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
            if tracemalloc.is_tracing():
                peak = tracemalloc.get_traced_memory()[1]
                baseline = self._trace_start_bytes or 0
                self._peak_bytes = max(0, peak - baseline)
            self._peak_working_set_bytes = self._process_peak_working_set()
            if self._owns_trace:
                tracemalloc.stop()
            self.json_path.parent.mkdir(parents=True, exist_ok=True)
            self.json_path.write_text(
                json.dumps(self._profile(), indent=2) + "\n", encoding="utf-8"
            )
