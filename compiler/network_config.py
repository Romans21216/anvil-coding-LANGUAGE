"""IPv4 literal validation shared by the C and optional native backends."""

from __future__ import annotations

import ipaddress
import json

from compiler.common import CompileError


def ipv4(raw: str, path, line: int) -> str:
    """Parse a quoted IPv4 string and return its canonical dotted-decimal form."""
    try:
        address = json.loads(raw)
        if not isinstance(address, str):
            raise ValueError("expected a string")
        return str(ipaddress.IPv4Address(address))
    except (ValueError, TypeError) as error:
        raise CompileError(f"{path}:{line}: expected a quoted IPv4 address") from error
