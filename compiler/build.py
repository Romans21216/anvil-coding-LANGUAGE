"""Native C toolchain discovery and executable linking."""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

from compiler.common import INCLUDE, RUNTIME
from compiler import toolchain_env

_LIBRARY_LINE = re.compile(r"Searching (.+?\.lib):", re.IGNORECASE)


def record_link_libraries(output: str, destination: pathlib.Path) -> None:
    """Save the library files the linker resolved, for cache-key hashing.

    `link /VERBOSE` prints the full path of every `.lib` it opens. The paths are
    the linker's own resolution of `#pragma comment(lib, …)` directives, which
    never appear on the command line, so they are the only reliable way to know
    which static libraries a build consumed (C8-11, library half).
    """
    libraries: list[str] = []
    for raw in _LIBRARY_LINE.findall(output):
        path = pathlib.Path(re.sub(r"\\+", r"\\", raw))
        if path.is_file() and str(path) not in libraries:
            libraries.append(str(path))
    try:
        destination.write_text(json.dumps(libraries, indent=1), encoding="utf-8")
    except OSError:
        pass


def find_compiler(requested: str | None):
    # MSVC is the supported default for the Windows-only native runtime.
    for name in ([requested] if requested else ["cl"]):
        if name and shutil.which(name):
            return name, shutil.which(name)
    if requested in (None, "cl", "cl.exe"):
        for root in (
            pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            pathlib.Path(r"C:\Program Files (x86)"),
        ):
            for p in root.glob(
                "Microsoft Visual Studio/*/*/VC/Tools/MSVC/*/bin/Hostx64/x64/cl.exe"
            ):
                return "cl.exe", str(p)
    return None


def build_c(
    compiler: str,
    generated: pathlib.Path,
    output: pathlib.Path,
    release: bool,
    libraries=(),
    dynamic_runtime: bool = False,
    deps_path: pathlib.Path | None = None,
    libs_path: pathlib.Path | None = None,
):
    """Build beside the final path and move into place only on success.

    A failed compile or link must never destroy the last good executable, so the
    toolchain writes a sibling staging file and the finished PE is renamed over
    the target atomically.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(f"{output.stem}.partial{output.suffix}")
    try:
        _build_c_into(compiler, generated, staging, release)
        if staging.exists():
            os.replace(staging, output)
    finally:
        staging.unlink(missing_ok=True)


def _build_c_into(
    compiler: str, generated: pathlib.Path, output: pathlib.Path, release: bool
):
    output.parent.mkdir(parents=True, exist_ok=True)
    # Link into a sibling file and only replace the previous output once the
    # toolchain succeeds, so a failed build can never leave a truncated or
    # half-linked executable behind (Part 8 section 8.10).
    staging = output.with_name(output.stem + ".partial" + output.suffix)
    staging.unlink(missing_ok=True)
    if pathlib.Path(compiler).name.lower() == "cl.exe":
        obj_dir = output.parent / (output.stem + "_obj")
        obj_dir.mkdir(exist_ok=True)
        args = [
            compiler,
            "/nologo",
            "/TC",
            "/I" + str(INCLUDE),
            str(generated),
            str(RUNTIME),
            "/Fe:" + str(staging),
            "/Fo:" + str(obj_dir) + "\\",
            "/O2" if release else "/Od",
        ]
        # /MD links against the system VC++ runtime instead of baking the static
        # CRT into the image: ~15x smaller, but the target machine must have the
        # runtime installed, so it stays opt-in.
        if dynamic_runtime:
            args.append("/MD")
        # Thin release binaries: function-level linking plus link-time removal of
        # everything the program never reaches (and folding of identical bodies).
        if release:
            args.append("/Gy")
        if deps_path is not None:
            # Record every header this build read so the cache key can hash
            # their bytes instead of the whole SDK tree (C8-11).
            args.append(f"/sourceDependencies{deps_path}")
        if libs_path is not None and not (release or libraries):
            args.append("/link")
        if release or libraries:
            args.append("/link")
            if release:
                args.extend(["/OPT:REF", "/OPT:ICF"])
            args.extend(str(library) for library in libraries)
        if libs_path is not None:
            args.append("/VERBOSE")
        install_root = pathlib.Path(compiler).parents[7]
        devcmd = install_root / "Common7" / "Tools" / "VsDevCmd.bat"
        if os.name == "nt" and devcmd.exists():
            # VsDevCmd costs 1.3-1.7 s per build; a cached environment makes
            # the same cl.exe invocation cost ~0.4 s. Fall back to the .cmd
            # wrapper whenever the capture is unavailable.
            environment = toolchain_env.ensure(devcmd)
            if environment is not None:
                # The capture can be hours old: keep the caller's current
                # environment (TEMP, TMP, session PATH) and let the toolchain
                # values win where they overlap.
                child_env = dict(os.environ)
                child_env.update(environment)
                if libs_path is None:
                    subprocess.run(args, check=True, env=child_env)
                else:
                    # /VERBOSE output is the only record of the libraries the
                    # linker resolved, so capture it and keep the console quiet
                    # unless the build fails.
                    completed = subprocess.run(
                        args,
                        env=child_env,
                        capture_output=True,
                        text=True,
                        errors="replace",
                    )
                    if completed.returncode != 0:
                        sys.stderr.write(completed.stdout)
                        sys.stderr.write(completed.stderr)
                        completed.check_returncode()
                    record_link_libraries(completed.stdout, libs_path)
            else:
                helper = output.parent / (output.stem + ".build.cmd")
                helper.write_text(
                    '@echo off\ncall "'
                    + str(devcmd)
                    + '" -arch=x64 >nul\nif errorlevel 1 exit /b %errorlevel%\n'
                    + subprocess.list2cmdline(args)
                    + "\nexit /b %errorlevel%\n",
                    encoding="utf-8",
                )
                try:
                    subprocess.run(
                        ["cmd.exe", "/d", "/c", str(helper)], check=True
                    )
                finally:
                    helper.unlink(missing_ok=True)
        else:
            subprocess.run(args, check=True)
    else:
        args = [
            compiler,
            str(generated),
            str(RUNTIME),
            "-I",
            str(INCLUDE),
            "-o",
            str(staging),
            "-lm",
            "-lgdi32",
            "-luser32",
            "-lws2_32",
            "-ldwmapi",
        ]
        if release:
            args += ["-O3", "-DNDEBUG", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections"]
        else:
            args += ["-O0", "-g"]
        subprocess.run(args, check=True)
    os.replace(staging, output)
