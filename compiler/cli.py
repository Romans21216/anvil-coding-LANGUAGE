"""Command-line entry point for compiling Anvil source and project manifests."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import hashlib
import shutil
import subprocess
import sys
import tomllib

from compiler.build import build_c, find_compiler
from compiler.codegen import emit_c
from compiler.common import CompileError
from compiler.diagnostics import render, render_editor
from compiler.timing import Timings
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


CACHE_DIR_NAME = ".anvil-cache"
SOURCE_LIMIT_BYTES = 4 * 1024 * 1024


CACHE_KEY_VERSION = b"anvil-cache-v3"


def _file_digest(path: pathlib.Path) -> bytes:
    """SHA-256 of a file's bytes, read in blocks so large tools stay cheap."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.digest()


def _compiler_identity(compiler: str) -> bytes:
    """Compiler path plus the hash of its bytes.

    A compiler replaced in place with different code of the same length and a
    restored modification time must not reuse an executable the old one
    produced, so identity comes from contents rather than stat metadata.
    """
    path = pathlib.Path(compiler)
    parts = [str(path).encode("utf-8", "replace")]
    try:
        parts.append(_file_digest(path))
    except OSError:
        parts.append(b"unreadable")
    return b"\0".join(parts)


def _sdk_fingerprint(root: pathlib.Path) -> bytes:
    """Content fingerprint of the Windows SDK version a build selects.

    Every file under the newest version's Include and Lib trees contributes its
    path, size and modification time, so a library or header changed in place
    inside an unchanged version directory still invalidates the build cache.
    Directory-enumeration metadata makes the ~6,000 files cost about 8 ms
    rather than the ~530 ms that a separate stat call per file takes.
    """
    try:
        versions = sorted(
            entry.name for entry in (root / "Include").iterdir() if entry.is_dir()
        )
    except OSError:
        return b"missing"
    if not versions:
        return b"missing"
    version = versions[-1]
    digest = hashlib.sha256()
    digest.update(version.encode("utf-8", "replace"))
    for tree in ("Include", "Lib"):
        entries: list[tuple[str, int, int]] = []
        stack = [root / tree / version]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as scan:
                    for entry in scan:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(pathlib.Path(entry.path))
                        else:
                            try:
                                info = entry.stat(follow_symlinks=False)
                            except OSError:
                                continue
                            entries.append((entry.path, info.st_size, info.st_mtime_ns))
            except OSError:
                continue
        for path, size, mtime in sorted(entries):
            digest.update(f"{path}|{size}|{mtime}".encode("utf-8", "replace"))
    return digest.digest()


def _toolchain_identity(compiler: str) -> bytes:
    """The linker and Windows SDK the C build actually selects.

    build_c runs cl.exe, which invokes link.exe from its own toolset and links
    against the SDK that VsDevCmd puts on the search path. Both decide the
    executable's bytes, so a linker or SDK change must invalidate the cache
    even when the generated C and cl.exe are unchanged.
    """
    folder = pathlib.Path(compiler).parent
    linker = folder / "link.exe"
    if linker.is_file():
        linker_part = b"link:" + _file_digest(linker)
    else:
        linker_part = b"link:missing"
    program_files = pathlib.Path(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    )
    sdk = program_files / "Windows Kits" / "10"
    return b"\0".join(
        (
            linker_part,
            b"sdk:" + _sdk_fingerprint(sdk),
            b"sdk-env:"
            + os.environ.get("WindowsSDKVersion", "").encode("utf-8", "replace"),
        )
    )


def _cache_key(
    generated: str,
    compiler: str,
    release: bool,
    runtime: pathlib.Path | None = None,
) -> str:
    """Hash everything that decides the executable's bytes."""
    digest = hashlib.sha256()
    digest.update(CACHE_KEY_VERSION)
    digest.update(generated.encode("utf-8"))
    tag = (
        release.encode("utf-8")
        if isinstance(release, str)
        else (b"release" if release else b"debug")
    )
    digest.update(chr(0).encode("utf-8") + tag)
    digest.update(_compiler_identity(compiler))
    digest.update(_toolchain_identity(compiler))
    if runtime is None:
        runtime = pathlib.Path(__file__).resolve().parents[1] / "runtime"
    # Every top-level runtime source and header belongs to the C build's
    # transitive input. anvil_runtime.c includes anvil_projection.h, whose
    # inline projection and clipping change output without changing the
    # generated C, so hashing only the .c/.h pair can return a stale artifact.
    for file in sorted(runtime.glob("*")):
        if file.is_file() and file.suffix in (".c", ".h"):
            digest.update(file.name.encode("utf-8"))
            digest.update(file.read_bytes())
    for source_file in sorted((pathlib.Path(__file__).resolve().parent).glob("*.py")):
        digest.update(source_file.read_bytes())
    return digest.hexdigest()


def _cache_path(out: pathlib.Path, key: str) -> pathlib.Path:
    return out.parent / CACHE_DIR_NAME / f"{key}.exe"


def _deps_sidecar(out: pathlib.Path, base_key: str) -> pathlib.Path:
    """Where the previous build's consumed-header list lives for a base key."""
    return out.parent / CACHE_DIR_NAME / f"{base_key}.deps.json"


def _dependency_paths(deps_file: pathlib.Path) -> list[str]:
    """Every include path listed anywhere in a `/sourceDependencies` document.

    MSVC emits one `Data` record for a single source and a list of records when
    the command line names several, so walk the document instead of assuming a
    shape. An unreadable or unrecognised file yields no paths.
    """
    try:
        data = json.loads(deps_file.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return []
    found: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "Includes" and isinstance(value, list):
                    found.extend(item for item in value if isinstance(item, str))
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return found


def _dependency_digest(deps_file: pathlib.Path) -> bytes:
    """Hash the bytes of every header the previous build actually consumed.

    `cl.exe /sourceDependencies` lists the headers a build read. Hashing those
    files' contents closes the same-size/same-mtime SDK collision (C8-11) for
    the header half of the input set at the cost of a few megabytes read,
    instead of the 1.2 GB a whole-SDK content walk would cost. A missing or
    unreadable sidecar yields b"" so the build falls back to the metadata key.
    """
    includes = _dependency_paths(deps_file)
    if not includes:
        return b""
    digest = hashlib.sha256()
    seen: set[str] = set()
    for entry in includes:
        path = pathlib.Path(entry)
        name = str(path).lower()
        if name in seen:
            continue
        seen.add(name)
        digest.update(name.encode("utf-8", "replace"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"missing")
    return digest.digest()


def _libs_sidecar(out: pathlib.Path, base_key: str) -> pathlib.Path:
    """Where the previous build's resolved static-library list lives."""
    return out.parent / CACHE_DIR_NAME / f"{base_key}.libs.json"


def _library_digest(libs_file: pathlib.Path) -> bytes:
    """Hash the bytes of every `.lib` the linker resolved for the last build.

    These files are chosen by `#pragma comment(lib, …)` inside SDK headers, so
    they never appear on the command line or in the header list; without this
    a same-size, same-mtime library replacement would reuse a stale executable
    (C8-11, library half). A real build resolves nine libraries, 62 MB, which
    costs about 36 ms to digest. A missing or unreadable list yields b"".
    """
    try:
        libraries = json.loads(libs_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return b""
    if not isinstance(libraries, list):
        return b""
    digest = hashlib.sha256()
    seen: set[str] = set()
    for entry in libraries:
        if not isinstance(entry, str):
            continue
        path = pathlib.Path(entry)
        name = str(path).lower()
        if name in seen:
            continue
        seen.add(name)
        digest.update(name.encode("utf-8", "replace"))
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"missing")
    return digest.digest()


def _key_with_dependencies(
    base_key: str,
    deps_file: pathlib.Path,
    libs_file: pathlib.Path | None = None,
) -> str:
    """Fold the consumed-header and resolved-library bytes into the base key."""
    extra = _dependency_digest(deps_file)
    library_extra = _library_digest(libs_file) if libs_file is not None else b""
    if not extra and not library_extra:
        return base_key
    digest = hashlib.sha256()
    digest.update(base_key.encode("utf-8"))
    digest.update(b"\0deps\0")
    digest.update(extra)
    digest.update(b"\0libs\0")
    digest.update(library_extra)
    return digest.hexdigest()


def cached_build(generated: str, compiler: str, out: pathlib.Path, release: bool) -> bool:
    """Copy a cached executable into place; True when the cache answered."""
    base_key = _cache_key(generated, compiler, release)
    key = _key_with_dependencies(
        base_key, _deps_sidecar(out, base_key), _libs_sidecar(out, base_key)
    )
    entry = _cache_path(out, key)
    if not entry.exists():
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(entry, out)
    return True


def store_build(
    generated: str,
    compiler: str,
    out: pathlib.Path,
    release: bool,
    deps_source: pathlib.Path | None = None,
    libs_source: pathlib.Path | None = None,
) -> None:
    if not out.exists():
        return
    base_key = _cache_key(generated, compiler, release)
    deps_sidecar = _deps_sidecar(out, base_key)
    libs_sidecar = _libs_sidecar(out, base_key)
    for source, sidecar in ((deps_source, deps_sidecar), (libs_source, libs_sidecar)):
        if source is None:
            continue
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(source, sidecar)
        except OSError:
            pass
    key = _key_with_dependencies(base_key, deps_sidecar, libs_sidecar)
    entry = _cache_path(out, key)
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


def _run_program(command: list[str], source_path: pathlib.Path,
                 manifest_path: pathlib.Path | None) -> int:
    """Run relative assets from the project root or standalone source folder."""
    root = (manifest_path.parent if manifest_path else source_path.parent).resolve()
    return subprocess.run(command, cwd=root).returncode


def _package_after_build(
    args,
    source_path: pathlib.Path,
    out: pathlib.Path,
    funcs,
    top,
    project_name: str,
    backend: str,
    declared_assets: list[str],
    manifest_path: pathlib.Path | None,
    compiler,
) -> int:
    """Collect assets, validate them and write (or print) the package manifest."""
    from compiler import package as package_mod
    from compiler.builtin_usage import used_builtins
    from compiler.common import LANGUAGE_VERSION

    root = (manifest_path.parent if manifest_path else source_path.parent).resolve()
    sources = {source_path.resolve()}
    for node in top:
        origin = getattr(node, "source", None)
        if origin:
            sources.add(pathlib.Path(origin).resolve())
    for function in funcs.values():
        origin = getattr(function, "source", None)
        if origin:
            sources.add(pathlib.Path(origin).resolve())
    if backend == "native":
        identity = {"name": "anvil-native", "language_version": LANGUAGE_VERSION}
    else:
        identity = {
            "name": compiler[0],
            "sha256": package_mod.sha256_file(pathlib.Path(compiler[1])),
        }
    return package_mod.package(
        project_root=root,
        name=project_name,
        backend=backend,
        entry=source_path,
        program=out,
        declared_assets=declared_assets,
        sources=sorted(sources),
        features=used_builtins(funcs, top),
        compiler=identity,
        target_dir=args.package or pathlib.Path("dist"),
        dry_run=args.package_dry_run,
    )


def main() -> int:
    if sys.argv[1:2] == ["verify"]:
        verify_parser = argparse.ArgumentParser(
            description="Validate Anvil source, project settings and reachable assets without linking."
        )
        verify_parser.add_argument("_command", choices=("verify",))
        verify_parser.add_argument("source", type=pathlib.Path)
        verify_parser.add_argument("--format", choices=("text", "json"), default="text")
        verify_args = verify_parser.parse_args()
        from compiler.verify import main as verify_main

        return verify_main(verify_args.source, verify_args.format)
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
    ap.add_argument(
        "--explain",
        metavar="CODE",
        help="print the cause and fix for a diagnostic code (for example ANV102)",
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
    ap.add_argument(
        "--release",
        action="store_true",
        help="optimize the C build (now the default; kept for existing scripts)",
    )
    ap.add_argument(
        "--debug",
        action="store_true",
        help="build the C output unoptimized (/Od) instead of the default release build",
    )
    ap.add_argument(
        "--dynamic-runtime",
        action="store_true",
        help=(
            "link the C build against the system VC++ runtime (/MD): about 15x "
            "smaller, but the target machine must have that runtime installed"
        ),
    )
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
        "--diagnostics",
        choices=("caret", "editor"),
        default="caret",
        help="diagnostic format: caret blocks or one-line path:line:column",
    )
    ap.add_argument(
        "--timings",
        action="store_true",
        help="print read/parse/generate/build timings to stderr (C backend)",
    )
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="ignore the build cache and do not store a new entry",
    )
    ap.add_argument(
        "--package",
        type=pathlib.Path,
        metavar="DIR",
        help="copy the program and its assets into DIR with anvil-package.json",
    )
    ap.add_argument(
        "--package-dry-run",
        action="store_true",
        help="validate assets and print the package manifest without writing",
    )
    ap.add_argument(
        "--run",
        action="store_true",
        help="run the built program and return its exit code",
    )
    ap.add_argument(
        "--clean",
        action="store_true",
        help="remove generated build artifacts next to the source",
    )
    ap.add_argument(
        "--doctor",
        action="store_true",
        help="report the toolchain state and exit",
    )
    ap.add_argument(
        "--new",
        type=pathlib.Path,
        metavar="DIR",
        help="create a starter project in DIR",
    )
    ap.add_argument(
        "--format",
        action="store_true",
        help="normalise whitespace and indentation in the source file",
    )
    ap.add_argument(
        "--format-check",
        action="store_true",
        help="exit 1 when --format would change the source file",
    )
    ap.add_argument(
        "--test",
        action="store_true",
        help="compile and run every tests/*.ANVL file in the project",
    )
    ap.add_argument(
        "--print-imports",
        action="store_true",
        help="print the builtins this program actually uses and stop",
    )
    ap.add_argument(
        "--backend",
        choices=("c", "native", "wasm"),
        default="c",
        help="select the C toolchain, the x64 PE backend, or the WebAssembly console target",
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
    if args.debug and args.release:
        print("--debug and --release contradict each other", file=sys.stderr)
        return 2
    args.release = not args.debug
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
    from compiler import commands as lifecycle

    toolchain_root = pathlib.Path(__file__).resolve().parents[1]
    if args.explain:
        from compiler.error_codes import code_list, explain

        text = explain(args.explain)
        if text is None:
            print(
                f"unknown diagnostic code {args.explain!r}; known codes: {code_list()}",
                file=sys.stderr,
            )
            return 2
        print(text)
        return 0
    if args.doctor:
        return lifecycle.doctor(toolchain_root)
    if args.new is not None:
        return lifecycle.new_project(args.new)
    if args.clean:
        root = args.source.parent if args.source else pathlib.Path(".")
        return lifecycle.clean(root)
    if args.test:
        root = args.source.parent if args.source else pathlib.Path(".")
        return lifecycle.run_project_tests(root, args.backend)
    if args.run and (args.check or args.emit_c or args.package or args.package_dry_run):
        ap.error("--run builds and runs; drop --check, --emit-c or --package")
    if args.source is None:
        ap.error("a source file is required unless --repl is used")
    if args.format or args.format_check:
        return lifecycle.format_file(args.source, args.format_check)
    try:
        source_path = args.source
        include_root = None
        fixed_hz = 60
        declared_assets: list[str] = []
        project_name = "Anvil Game"
        manifest_path = None
        manifest_entry = None
        if args.source.suffix.lower() == ".anvlproj":
            if args.backend == "native":
                raise CompileError(
                    "--backend native does not support .ANVLproj manifests yet; compile the entry .ANVL file directly"
                )
            manifest_text = args.source.read_text(encoding="utf-8")
            manifest = tomllib.loads(manifest_text)
            unknown_keys = set(manifest) - {"name", "entry", "engine", "assets"}
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
            assets_table = manifest.get("assets", {})
            if not isinstance(assets_table, dict):
                raise CompileError(f"{args.source}: 'assets' must be a TOML table")
            unknown_asset_keys = set(assets_table) - {"files"}
            if unknown_asset_keys:
                raise CompileError(
                    f"{args.source}: unsupported asset setting(s): "
                    f"{', '.join(sorted(unknown_asset_keys))}"
                )
            asset_files = assets_table.get("files", [])
            if not isinstance(asset_files, list) or not all(
                isinstance(item, str) and item for item in asset_files
            ):
                raise CompileError(
                    f"{args.source}: assets.files must be a list of non-empty strings"
                )
            declared_assets = list(asset_files)
            manifest_path = args.source
            manifest_entry = entry
            project_root = args.source.resolve().parent
            include_root = project_root
            source_path = (project_root / entry).resolve()
            try:
                source_path.relative_to(project_root)
            except ValueError as exc:
                raise CompileError(
                    f"{args.source}: entry must resolve inside the project folder"
                ) from exc
        timings = Timings(args.timings)
        try:
            size = source_path.stat().st_size
            if size > SOURCE_LIMIT_BYTES:
                raise CompileError(
                    f"{source_path}: source file is {size} bytes, over the "
                    f"{SOURCE_LIMIT_BYTES // (1024 * 1024)} MiB budget"
                )
            source = source_path.read_text(encoding="utf-8")
        except OSError as error:
            if manifest_path is not None:
                raise CompileError(
                    f"{manifest_path}: entry {manifest_entry!r} cannot be read: "
                    f"{error.strerror or error}"
                ) from error
            raise CompileError(f"cannot read {source_path}: {error.strerror or error}") from error
        except UnicodeDecodeError as error:
            raise CompileError(
                f"cannot read {source_path}: the file is not valid UTF-8 ({error.reason} at byte {error.start})"
            ) from error
        timings.mark("read")
        funcs, top, variables, arrays = parse(source_path, source, include_root=include_root)
        timings.mark("parse")
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

        from compiler import lints

        warnings = []
        for node in builtin_usage.unused_imports(funcs, top):
            warnings.append(
                (node, f"import '{node.value}' is never used")
            )
        for message, node in lints.report(funcs, top, source_path):
            warnings.append((node, message))
        for node, message in warnings:
            text = f"{node.source or source_path}:{node.line}: warning: {message}"
            print(
                render_editor(text) if args.diagnostics == "editor" else render(text),
                file=sys.stderr,
            )
        if warnings and args.deny_warnings:
            print(
                f"{source_path}: {len(warnings)} warning(s) treated as errors",
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
            elif args.backend == "wasm":
                from compiler import wasm as wasm_backend

                wasm_backend.validate(source_path, funcs, top)
            else:
                emit_c(
                    source_path, funcs, top, variables, arrays, fixed_hz, project_name
                )
            timings.mark("generate")
            timings.report()
            print(f"{source_path}: ok")
            return 0
        if args.backend == "wasm":
            from compiler import wasm as wasm_backend

            if args.package or args.package_dry_run:
                raise CompileError("--package does not apply to the wasm backend")
            out = args.output or source_path.with_suffix(".wasm")
            emit_path = args.emit_c or args.generated_c
            wasm_backend.build(
                source_path,
                funcs,
                top,
                variables,
                arrays,
                out,
                fixed_hz,
                project_name,
                emit_c_path=pathlib.Path(emit_path) if emit_path else None,
            )
            timings.mark("build")
            timings.report()
            if emit_path:
                print(f"Wrote {emit_path}")
                return 0
            print(f"Built {out} as WebAssembly; host page {out.with_suffix('.html')}")
            if args.run:
                host = pathlib.Path(__file__).resolve().parents[1] / "tools" / "wasm_host.mjs"
                return _run_program(
                    ["node", str(host.resolve()), str(out.resolve())],
                    source_path, manifest_path,
                )
            return 0
        if args.backend == "native":
            if args.emit_c or args.generated_c or args.cc or args.debug or args.dynamic_runtime:
                raise CompileError(
                    "--emit-c, --generated-c, --cc, --debug and --dynamic-runtime apply only "
                    "to --backend c"
                )
            executable = NativeCodegen(
                source_path, funcs, top, variables, arrays
            ).generate()
            out = args.output or source_path.with_suffix(".exe")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(executable)
            _place_extension_dlls(out)
            print(f"Built {out} as native AMD64 PE (no C/Rust compiler)")
            if args.run:
                return _run_program([str(out.resolve())], source_path, manifest_path)
            if args.package or args.package_dry_run:
                return _package_after_build(
                    args, source_path, out, funcs, top, project_name, "native",
                    declared_assets, manifest_path, None,
                )
            return 0
        generated = emit_c(
            source_path, funcs, top, variables, arrays, fixed_hz, project_name
        )
        timings.mark("generate")
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
            build_c(
                compiler[1],
                c_path,
                out,
                args.release,
                libraries,
                args.dynamic_runtime,
            )
            timings.mark("build")
            timings.report()
            print(f"Built {out} using {compiler[0]}")
        else:
            cached = False if args.no_cache else cached_build(
                generated,
                compiler[1],
                out,
                f"r{int(args.release)}d{int(args.dynamic_runtime)}",
            )
            if cached:
                timings.mark("build")
                timings.report()
                print(f"Built {out} using {compiler[0]} (reused build cache)")
            else:
                deps_tmp = out.parent / CACHE_DIR_NAME / (
                    f".pending-{os.getpid()}.deps.json"
                )
                libs_tmp = out.parent / CACHE_DIR_NAME / (
                    f".pending-{os.getpid()}.libs.json"
                )
                deps_tmp.parent.mkdir(parents=True, exist_ok=True)
                try:
                    build_c(
                        compiler[1],
                        c_path,
                        out,
                        args.release,
                        (),
                        args.dynamic_runtime,
                        None if args.no_cache else deps_tmp,
                        None if args.no_cache else libs_tmp,
                    )
                    if not args.no_cache:
                        store_build(
                            generated,
                            compiler[1],
                            out,
                            f"r{int(args.release)}d{int(args.dynamic_runtime)}",
                            deps_tmp if deps_tmp.exists() else None,
                            libs_tmp if libs_tmp.exists() else None,
                        )
                finally:
                    deps_tmp.unlink(missing_ok=True)
                    libs_tmp.unlink(missing_ok=True)
                timings.mark("build")
                timings.report()
                print(f"Built {out} using {compiler[0]}")
        _place_extension_dlls(out)
        if args.run:
            return _run_program([str(out.resolve())], source_path, manifest_path)
        if args.package or args.package_dry_run:
            return _package_after_build(
                args, source_path, out, funcs, top, project_name, "c",
                declared_assets, manifest_path, compiler,
            )
        return 0
    except tomllib.TOMLDecodeError as e:
        print(f"{args.source}: {e}", file=sys.stderr)
        return 1
    except (CompileError, OSError, UnicodeError, subprocess.CalledProcessError) as e:
        printer = render_editor if args.diagnostics == "editor" else render
        print(printer(str(e)), file=sys.stderr)
        return 1
