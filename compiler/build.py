"""Native C toolchain discovery and executable linking."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

from compiler.common import INCLUDE, RUNTIME
from compiler.runtime_modules import RuntimeModule, select_runtime_modules


def _msvc_arguments(
    compiler: str,
    generated: pathlib.Path,
    output: pathlib.Path,
    object_dir: pathlib.Path,
    release: bool,
    runtime_modules: tuple[RuntimeModule, ...] = (),
) -> list[str]:
    args = [
        compiler,
        "/nologo",
        "/TC",
        "/utf-8",
        "/I" + str(INCLUDE),
        str(generated),
        str(RUNTIME),
        *(str(module.source) for module in runtime_modules),
        "/Fe:" + str(output),
        "/Fo:" + str(object_dir) + "\\",
    ]
    if release:
        # COMDAT sections let LINK discard runtime features the Anvil program
        # does not reference. Keep debug builds easy to inspect instead.
        args.extend(["/O2", "/Gy", "/Gw", "/link", "/OPT:REF"])
    else:
        args.append("/Od")
    return args


def _gcc_arguments(
    compiler: str,
    generated: pathlib.Path,
    output: pathlib.Path,
    release: bool,
    runtime_modules: tuple[RuntimeModule, ...] = (),
) -> list[str]:
    args = [
        compiler,
        str(generated),
        str(RUNTIME),
        *(str(module.source) for module in runtime_modules),
        "-I",
        str(INCLUDE),
        "-o",
        str(output),
        "-lm",
        "-lgdi32",
        "-luser32",
    ]
    libraries = sorted({library for module in runtime_modules for library in module.gcc_libraries})
    args.extend(libraries)
    if release:
        args.extend(
            [
                "-O3",
                "-DNDEBUG",
                "-ffunction-sections",
                "-fdata-sections",
                "-Wl,--gc-sections",
            ]
        )
    else:
        args.extend(["-O0", "-g"])
    return args


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
    compiler: str, generated: pathlib.Path, output: pathlib.Path, release: bool
):
    output.parent.mkdir(parents=True, exist_ok=True)
    runtime_modules = select_runtime_modules(generated.read_text(encoding="utf-8"))
    if pathlib.Path(compiler).name.lower() == "cl.exe":
        with tempfile.TemporaryDirectory(prefix="anvil-obj-") as object_dir:
            obj_dir = pathlib.Path(object_dir)
            args = _msvc_arguments(
                compiler, generated, output, obj_dir, release, runtime_modules
            )
            install_root = pathlib.Path(compiler).parents[7]
            devcmd = install_root / "Common7" / "Tools" / "VsDevCmd.bat"
            if os.name == "nt" and devcmd.exists():
                helper = obj_dir / (output.stem + ".build.cmd")
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
        args = _gcc_arguments(compiler, generated, output, release, runtime_modules)
        subprocess.run(args, check=True)
