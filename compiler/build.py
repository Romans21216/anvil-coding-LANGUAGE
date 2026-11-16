"""Native C toolchain discovery and executable linking."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

from compiler.common import INCLUDE, RUNTIME


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
        if release or libraries:
            args.append("/link")
            if release:
                args.extend(["/OPT:REF", "/OPT:ICF"])
            args.extend(str(library) for library in libraries)
        install_root = pathlib.Path(compiler).parents[7]
        devcmd = install_root / "Common7" / "Tools" / "VsDevCmd.bat"
        if os.name == "nt" and devcmd.exists():
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
                subprocess.run(["cmd.exe", "/d", "/c", str(helper)], check=True)
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
        ]
        if release:
            args += ["-O3", "-DNDEBUG", "-ffunction-sections", "-fdata-sections", "-Wl,--gc-sections"]
        else:
            args += ["-O0", "-g"]
        subprocess.run(args, check=True)
    os.replace(staging, output)
