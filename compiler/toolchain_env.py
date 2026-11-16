"""Capture and cache the Visual Studio environment cl.exe needs.

`VsDevCmd.bat -arch=x64` costs 1.3-1.7 s and produces the same environment for
every build with the same toolset. Capturing it once and handing the result to
cl.exe directly turns a ~1.6 s build into a ~0.4 s one; the cache key includes
the batch file's path, size and modification time, so a Visual Studio update
produces a fresh capture instead of a stale environment.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import tempfile

CACHE_ENV_VAR = "ANVIL_VSENV_CACHE"
QUOTE = '"'
NL = chr(10)


def cache_directory() -> pathlib.Path:
    override = os.environ.get(CACHE_ENV_VAR)
    if override:
        return pathlib.Path(override)
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return pathlib.Path(base) / "anvil" / "toolchain"


def cache_path(devcmd: pathlib.Path, arch: str = "x64") -> pathlib.Path:
    info = devcmd.stat()
    key = hashlib.sha256(
        f"{devcmd}|{info.st_size}|{info.st_mtime_ns}|{arch}".encode("utf-8")
    ).hexdigest()[:16]
    return cache_directory() / f"vsenv-{key}.json"


def parse_environment(text: str) -> dict[str, str]:
    """`set` output to a mapping, skipping banners and drive-scoped entries."""
    environment: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line or line.startswith("="):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        environment[key.upper()] = value
    return environment


def capture(devcmd: pathlib.Path, arch: str = "x64", timeout: int = 120) -> dict[str, str] | None:
    """Run VsDevCmd once and read back the environment it sets."""
    handle, name = tempfile.mkstemp(suffix=".cmd", prefix="anvil-env-")
    os.close(handle)
    helper = pathlib.Path(name)
    try:
        helper.write_text(
            NL.join(
                (
                    "@echo off",
                    "call " + QUOTE + str(devcmd) + QUOTE + " -arch=" + arch + " >nul",
                    "if errorlevel 1 exit /b %errorlevel%",
                    "set",
                )
            )
            + NL,
            encoding="utf-8",
        )
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", str(helper)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        helper.unlink(missing_ok=True)
    if result.returncode != 0:
        return None
    environment = parse_environment(result.stdout)
    # Without INCLUDE the capture silently produced nothing useful.
    return environment if "INCLUDE" in environment else None


def load(devcmd: pathlib.Path, arch: str = "x64") -> dict[str, str] | None:
    try:
        path = cache_path(devcmd, arch)
    except OSError:
        return None
    try:
        environment = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return environment if isinstance(environment, dict) and "INCLUDE" in environment else None


def store(environment: dict[str, str], devcmd: pathlib.Path, arch: str = "x64") -> None:
    try:
        path = cache_path(devcmd, arch)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(environment, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def ensure(devcmd: pathlib.Path, arch: str = "x64") -> dict[str, str] | None:
    """The toolset environment, from cache when possible."""
    environment = load(devcmd, arch)
    if environment is not None:
        return environment
    environment = capture(devcmd, arch)
    if environment is not None:
        store(environment, devcmd, arch)
    return environment
