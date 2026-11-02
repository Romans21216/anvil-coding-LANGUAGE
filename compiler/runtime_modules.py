"""Explicit optional C runtime module registry."""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

from compiler.common import CompileError, ROOT


@dataclass(frozen=True)
class RuntimeModule:
    source: pathlib.Path
    gcc_libraries: tuple[str, ...] = ()


MODULES = {
    "networking": RuntimeModule(
        ROOT / "runtime" / "anvil_network.c", ("-lws2_32",)
    ),
}

_MODULE_MARKER = re.compile(
    r"^/\* ANVIL_RUNTIME_MODULE: ([a-z][a-z0-9_]*) \*/$", re.MULTILINE
)


def select_runtime_modules(generated_c: str) -> tuple[RuntimeModule, ...]:
    """Resolve explicit feature markers emitted by the Anvil C generator."""
    names = set(_MODULE_MARKER.findall(generated_c))
    unknown = sorted(names - MODULES.keys())
    if unknown:
        raise CompileError(
            "generated C requests unknown runtime module(s): " + ", ".join(unknown)
        )
    return tuple(MODULES[name] for name in sorted(names))
