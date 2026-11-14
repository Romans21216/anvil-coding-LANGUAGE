"""Command-line entry point for compiling Anvil source and project manifests."""

from __future__ import annotations

import argparse
import json
import pathlib
import hashlib
import shutil
import subprocess
import sys
import tomllib

from compiler.build import build_c, find_compiler
from compiler.codegen import emit_c
from compiler.common import CompileError
from compiler.diagnostics import render
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


CACHE_DIR_NAME = ".anvil-cache"


def _cache_key(generated: str, compiler: str, release: bool) -> str:
    """Hash everything that decides the executable's bytes."""
    digest = hashlib.sha256()
    digest.update(generated.encode("utf-8"))
    digest.update(b"\0release" if release else b"\0debug")
    digest.update(str(pathlib.Path(compiler)).encode("utf-8", "replace"))
    runtime = pathlib.Path(__file__).resolve().parents[1] / "runtime"
    for name in ("anvil_runtime.c", "anvil_runtime.h"):
        file = runtime / name
        if file.exists():
            digest.update(file.read_bytes())
    for source_file in sorted((pathlib.Path(__file__).resolve().parent).glob("*.py")):
        digest.update(source_file.read_bytes())
    return digest.hexdigest()


def _cache_path(out: pathlib.Path, key: str) -> pathlib.Path:
    return out.parent / CACHE_DIR_NAME / f"{key}.exe"


def cached_build(generated: str, compiler: str, out: pathlib.Path, release: bool) -> bool:
    """Copy a cached executable into place; True when the cache answered."""
    entry = _cache_path(out, _cache_key(generated, compiler, release))
    if not entry.exists():
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(entry, out)
    return True


def store_build(generated: str, compiler: str, out: pathlib.Path, release: bool) -> None:
    if not out.exists():
        return
    entry = _cache_path(out, _cache_key(generated, compiler, release))
    entry.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out, entry)


def _place_extension_dlls(output: pathlib.Path) -> None:
    """Copy each registered DLL beside the executable the loader will start."""
    import shutil

    from compiler import extensions as extension_api

    for dll in extension_api.dlls():
        target = output.parent / dll.name
        if dll.resolve() != target.resolve():
            shutil.copyfile(dll, target)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compile Anvil source or a project to a native executable with the selected backend."
        )
    )
    ap.add_argument(
        "source",
        nargs="?",
        type=pathlib.Path,
        help="input .ANVL source or .ANVLproj project manifest (omit with --repl)",
    )
    ap.add_argument("--emit-c", type=pathlib.Path, help="emit C source only and stop")
    ap.add_argument("--generated-c", type=pathlib.Path, help="choose generated C path")
    ap.add_argument("--output", "-o", type=pathlib.Path, help="output executable")
    ap.add_argument(
        "--cc",
        help=(
            "explicit C compiler compatible with the Windows runtime "
            "(MSVC is verified)"
        ),
    )
    ap.add_argument("--release", action="store_true", help="enable native optimization")
    ap.add_argument(
        "--check",
        action="store_true",
        help="parse and validate only; report problems without building an output",
    )
    ap.add_argument(
        "--deny-warnings",
        action="store_true",
        help="treat compiler warnings (such as an unused import) as errors",
    )
    ap.add_argument(
        "--print-imports",
        action="store_true",
        help="print the builtins this program actually uses and stop",
    )
    ap.add_argument(
        "--backend",
        choices=("c", "native"),
        default="c",
        help="select the C toolchain or experimental Anvil-owned x64 PE backend",
    )
    ap.add_argument(
        "--extension",
        action="append",
        metavar="MANIFEST",
        help=(
            "register an extension function manifest (repeatable); functions "
            "become callable like builtins on both backends"
        ),
    )
    ap.add_argument(
        "--repl",
        action="store_true",
        help="start the interactive Anvil shell instead of compiling a file",
    )
    ap.add_argument(
        "--hello",
        action="store_true",
        help="build and run a greeting program, so the first command always works",
    )
    ap.add_argument(
        "--repl-backend",
        choices=("native", "c"),
        default="native",
        help="backend the interactive shell uses (default: native)",
    )
    args = ap.parse_args()
    from compiler import extensions as extension_api

    extension_api.reset()
    if args.extension:
        try:
            extension_api.load(args.extension)
        except extension_api.ExtensionError as error:
            print(str(error), file=sys.stderr)
            return 2
    if args.hello:
        from compiler.repl import hello_main

        return hello_main(backend=args.repl_backend)
    if args.repl:
        from compiler.repl import repl_main

        return repl_main(backend=args.repl_backend)
    if args.source is None:
        ap.error("a source file is required unless --repl is used")
    try:
        source_path = args.source
        include_root = None
        fixed_hz = 60
        project_name = "Anvil Game"
        if args.source.suffix.lower() == ".anvlproj":
            if args.backend == "native":
                raise CompileError(
                    "--backend native does not support .ANVLproj manifests yet; compile the entry .ANVL file directly"
                )
            manifest_text = args.source.read_text(encoding="utf-8")
            manifest = tomllib.loads(manifest_text)
            unknown_keys = set(manifest) - {"name", "entry", "engine"}
            if unknown_keys:
                raise CompileError(
                    f"{args.source}: unsupported project setting(s): "
                    f"{', '.join(sorted(unknown_keys))}"
                )
            name = manifest.get("name", project_name)
            if (
                not isinstance(name, str)
                or not name.strip()
                or "\0" in name
                or any(ord(ch) < 32 for ch in name)
            ):
                raise CompileError(
                    f"{args.source}: project name must be a non-empty "
                    "string without control characters"
                )
            project_name = name.strip()
            engine = manifest.get("engine", {})
            if not isinstance(engine, dict):
                raise CompileError(f"{args.source}: 'engine' must be a TOML table")
            unknown_engine_keys = set(engine) - {"fixed_hz"}
            if unknown_engine_keys:
                raise CompileError(
                    f"{args.source}: unsupported engine setting(s): "
                    f"{', '.join(sorted(unknown_engine_keys))}"
                )
            fixed_hz = engine.get("fixed_hz", 60)
            if (
                isinstance(fixed_hz, bool)
                or not isinstance(fixed_hz, int)
                or not 1 <= fixed_hz <= 240
            ):
                raise CompileError(
                    f"{args.source}: engine.fixed_hz must be an integer from 1 to 240"
                )
            entry = manifest.get("entry")
            if not isinstance(entry, str) or not entry:
                raise CompileError(
                    f"{args.source}: manifest needs a non-empty string 'entry'"
                )
            project_root = args.source.resolve().parent
            include_root = project_root
            source_path = (project_root / entry).resolve()
            try:
                source_path.relative_to(project_root)
            except ValueError as exc:
                raise CompileError(
                    f"{args.source}: entry must resolve inside the project folder"
                ) from exc
        try:
            source = source_path.read_text(encoding="utf-8")
        except OSError as error:
            raise CompileError(f"cannot read {source_path}: {error.strerror or error}") from error
        except UnicodeDecodeError as error:
            raise CompileError(
                f"cannot read {source_path}: the file is not valid UTF-8 ({error.reason} at byte {error.start})"
            ) from error
        funcs, top, variables, arrays = parse(source_path, source, include_root=include_root)
        for provided in extension_api.anvil_sources():
            provided_source = provided.read_text(encoding="utf-8")
            provided_functions, provided_top, _, _ = parse(provided, provided_source)
            for name, function in provided_functions.items():
                if name in funcs:
                    raise CompileError(
                        f"{provided}: extension function {name!r} already exists "
                        f"in {source_path.name}"
                    )
                funcs[name] = function
            top = top + provided_top
        from compiler import builtin_usage

        unused = builtin_usage.unused_imports(funcs, top)
        for node in unused:
            print(
                render(
                    f"{node.source or source_path}:{node.line}: warning: "
                    f"import '{node.value}' is never used"
                ),
                file=sys.stderr,
            )
        if unused and args.deny_warnings:
            print(
                f"{source_path}: {len(unused)} warning(s) treated as errors",
                file=sys.stderr,
            )
            return 1
        if args.print_imports:
            from compiler.builtin_usage import used_builtins

            resolved = used_builtins(funcs, top)
            print("builtins: " + (", ".join(resolved) or "none"))
            return 0
        if args.check:
            # Lowering (type) errors only surface in code generation, so a
            # parse-only check reported "ok" for programs that cannot build.
            # --check must never write files, whichever backend is selected.
            if args.backend == "native":
                NativeCodegen(source_path, funcs, top, variables, arrays).generate()
            else:
                emit_c(
                    source_path, funcs, top, variables, arrays, fixed_hz, project_name
                )
            print(f"{source_path}: ok")
            return 0
        if args.backend == "native":
            if args.emit_c or args.generated_c or args.cc or args.release:
                raise CompileError(
                    "--emit-c, --generated-c, --cc, and --release apply only to --backend c"
                )
            executable = NativeCodegen(
                source_path, funcs, top, variables, arrays
            ).generate()
            out = args.output or source_path.with_suffix(".exe")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(executable)
            _place_extension_dlls(out)
            print(f"Built {out} as native AMD64 PE (no C/Rust compiler)")
            return 0
        generated = emit_c(
            source_path, funcs, top, variables, arrays, fixed_hz, project_name
        )
        c_path = (
            args.emit_c or args.generated_c or source_path.with_suffix(".generated.c")
        )
        c_path.parent.mkdir(parents=True, exist_ok=True)
        c_path.write_text(generated, encoding="utf-8", newline="\n")
        if args.emit_c:
            print(f"Wrote {c_path}")
            return 0
        compiler = find_compiler(args.cc)
        if not compiler:
            print(
                "No C compiler found. Install Visual Studio 2022 Build Tools "
                "with the C++ workload. Generated source: "
                f"{c_path}",
                file=sys.stderr,
            )
            return 2
        out = args.output or source_path.with_suffix(".exe")
        try:
            extension_api.ensure_import_libraries(pathlib.Path(compiler[1]))
        except extension_api.ExtensionError as error:
            print(str(error), file=sys.stderr)
            return 2
        libraries = extension_api.libraries()
        if libraries:
            # The generated C only names the extension symbols, so the cache key
            # would miss a rebuilt DLL; always link when extensions are present.
            build_c(compiler[1], c_path, out, args.release, libraries)
            print(f"Built {out} using {compiler[0]}")
        else:
            cached = cached_build(generated, compiler[1], out, args.release)
            if cached:
                print(f"Built {out} using {compiler[0]} (reused build cache)")
            else:
                build_c(compiler[1], c_path, out, args.release)
                store_build(generated, compiler[1], out, args.release)
                print(f"Built {out} using {compiler[0]}")
        _place_extension_dlls(out)
        return 0
    except tomllib.TOMLDecodeError as e:
        print(f"{args.source}: {e}", file=sys.stderr)
        return 1
    except (CompileError, OSError, UnicodeError, subprocess.CalledProcessError) as e:
        print(render(str(e)), file=sys.stderr)
        return 1
