"""Native C toolchain discovery and executable linking."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

from compiler.common import CompileError, INCLUDE, ROOT, RUNTIME
from compiler.runtime_modules import RuntimeModule, select_runtime_modules


def _msvc_arguments(
    compiler: str,
    generated: pathlib.Path,
    output: pathlib.Path,
    object_dir: pathlib.Path,
    release: bool,
    runtime_modules: tuple[RuntimeModule, ...] = (),
    resource_file: pathlib.Path | None = None,
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
    if resource_file is not None:
        if "/link" not in args:
            args.append("/link")
        args.append(str(resource_file))
    return args


def _gcc_arguments(
    compiler: str,
    generated: pathlib.Path,
    output: pathlib.Path,
    release: bool,
    runtime_modules: tuple[RuntimeModule, ...] = (),
    resource_object: pathlib.Path | None = None,
) -> list[str]:
    args = [
        compiler,
        str(generated),
        str(RUNTIME),
        *(str(module.source) for module in runtime_modules),
        *([str(resource_object)] if resource_object is not None else []),
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
    icon = ROOT / "assets" / "icons" / "anvil-executable.ico"
    if not icon.is_file():
        raise CompileError(f"Anvil executable icon asset is missing: {icon}")
    if pathlib.Path(compiler).name.lower() == "cl.exe":
        with tempfile.TemporaryDirectory(prefix="anvil-obj-") as object_dir:
            obj_dir = pathlib.Path(object_dir)
            resource_source = obj_dir / "anvil_icon.rc"
            resource_file = obj_dir / "anvil_icon.res"
            resource_source.write_text(
                '#define IDI_ANVIL 1\nIDI_ANVIL ICON "'
                + icon.resolve().as_posix()
                + '"\n',
                encoding="utf-8",
                newline="\n",
            )
            args = _msvc_arguments(
                compiler, generated, output, obj_dir, release, runtime_modules,
                resource_file,
            )
            install_root = pathlib.Path(compiler).parents[7]
            devcmd = install_root / "Common7" / "Tools" / "VsDevCmd.bat"
            if os.name == "nt" and devcmd.exists():
                helper = obj_dir / (output.stem + ".build.cmd")
                helper.write_text(
                    '@echo off\ncall "'
                    + str(devcmd)
                    + '" -arch=x64 >nul\nif errorlevel 1 exit /b %errorlevel%\n'
                    + subprocess.list2cmdline([
                        "rc.exe", "/nologo", "/fo" + str(resource_file),
                        str(resource_source),
                    ])
                    + "\nif errorlevel 1 exit /b %errorlevel%\n"
                    + subprocess.list2cmdline(args)
                    + "\nexit /b %errorlevel%\n",
                    encoding="utf-8",
                )
                try:
                    subprocess.run(["cmd.exe", "/d", "/c", str(helper)], check=True)
                finally:
                    helper.unlink(missing_ok=True)
            else:
                subprocess.run(
                    ["rc.exe", "/nologo", "/fo" + str(resource_file),
                     str(resource_source)],
                    check=True,
                )
                subprocess.run(args, check=True)
    else:
        windres = shutil.which("windres")
        if not windres:
            raise CompileError(
                "Embedding the Anvil executable icon with GCC requires windres; "
                "install MinGW binutils or use MSVC."
            )
        with tempfile.TemporaryDirectory(prefix="anvil-obj-") as object_dir:
            obj_dir = pathlib.Path(object_dir)
            resource_source = obj_dir / "anvil_icon.rc"
            resource_object = obj_dir / "anvil_icon.o"
            resource_source.write_text(
                '#define IDI_ANVIL 1\nIDI_ANVIL ICON "'
                + icon.resolve().as_posix()
                + '"\n',
                encoding="utf-8",
                newline="\n",
            )
            subprocess.run(
                [windres, "--input-format=rc", "--output-format=coff", "-i",
                 str(resource_source), "-o", str(resource_object)],
                check=True,
            )
            args = _gcc_arguments(
                compiler, generated, output, release, runtime_modules,
                resource_object,
            )
            subprocess.run(args, check=True)
