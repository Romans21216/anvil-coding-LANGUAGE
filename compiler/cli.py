"""Command-line entry point for compiling Anvil source and project manifests."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import tomllib

from compiler.build import build_c, find_compiler
from compiler.codegen import emit_c
from compiler.common import CompileError
from compiler.common import (
    MAX_ACTIVE_LOCAL_ARRAY_BYTES,
    MAX_ACTIVE_LOCAL_ARRAY_MIB,
    MAX_ARRAY_SIZE,
    MAX_LOCAL_ARRAY_ELEMENTS,
)
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compile Anvil source or a project to a native executable with the selected backend."
        )
    )
    ap.add_argument(
        "source",
        type=pathlib.Path,
        help="input .ANVL source or .ANVLproj project manifest",
    )
    ap.add_argument("--emit-c", type=pathlib.Path, help="emit C source only and stop")
    ap.add_argument('--inspect-metadata',action='store_true',help='read embedded Anvil name/author/version from an executable')
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
        "--backend",
        choices=("c", "native"),
        default="c",
        help="select the C toolchain or experimental Anvil-owned x64 PE backend",
    )
    args = ap.parse_args()
    try:
        if args.inspect_metadata:
            from compiler.program_metadata import unpack
            sys.stdout.buffer.write((json.dumps(unpack(args.source.read_bytes()),ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
            return 0
        source_path = args.source
        include_root = None
        fixed_hz = 60
        local_array_elements = MAX_LOCAL_ARRAY_ELEMENTS
        active_local_array_bytes = MAX_ACTIVE_LOCAL_ARRAY_BYTES
        project_name = "Anvil Game"
        if args.source.suffix.lower() == ".anvlproj":
            manifest_text = args.source.read_text(encoding="utf-8")
            manifest = tomllib.loads(manifest_text)
            unknown_keys = set(manifest) - {"name", "entry", "engine", "memory"}
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
            memory = manifest.get("memory", {})
            if not isinstance(memory, dict):
                raise CompileError(f"{args.source}: 'memory' must be a TOML table")
            unknown_memory_keys = set(memory) - {
                "local_array_elements", "active_call_memory_mib"
            }
            if unknown_memory_keys:
                raise CompileError(
                    f"{args.source}: unsupported memory setting(s): "
                    f"{', '.join(sorted(unknown_memory_keys))}"
                )
            local_array_elements = memory.get(
                "local_array_elements", MAX_LOCAL_ARRAY_ELEMENTS
            )
            if (
                isinstance(local_array_elements, bool)
                or not isinstance(local_array_elements, int)
                or not 1 <= local_array_elements <= MAX_ARRAY_SIZE
            ):
                raise CompileError(
                    f"{args.source}: memory.local_array_elements must be an "
                    f"integer from 1 to {MAX_ARRAY_SIZE}"
                )
            active_call_memory_mib = memory.get(
                "active_call_memory_mib",
                MAX_ACTIVE_LOCAL_ARRAY_BYTES // (1024 * 1024),
            )
            if (
                isinstance(active_call_memory_mib, bool)
                or not isinstance(active_call_memory_mib, int)
                or not 1 <= active_call_memory_mib <= MAX_ACTIVE_LOCAL_ARRAY_MIB
            ):
                raise CompileError(
                    f"{args.source}: memory.active_call_memory_mib must be an "
                    f"integer from 1 to {MAX_ACTIVE_LOCAL_ARRAY_MIB}"
                )
            active_local_array_bytes = active_call_memory_mib * 1024 * 1024
            entry = manifest.get("entry")
            if not isinstance(entry, str) or not entry:
                raise CompileError(
                    f"{args.source}: manifest needs a non-empty string 'entry'"
                )
            if any(ord(char) < 32 for char in entry):
                raise CompileError(f"{args.source}: entry must not contain control characters")
            project_root = args.source.resolve().parent
            include_root = project_root
            source_path = (project_root / entry).resolve()
            try:
                source_path.relative_to(project_root)
            except ValueError as exc:
                raise CompileError(
                    f"{args.source}: entry must resolve inside the project folder"
                ) from exc
        source = source_path.read_text(encoding="utf-8")
        funcs, top, variables, arrays = parse(
            source_path,
            source,
            include_root=include_root,
            local_array_elements=local_array_elements,
            active_local_array_bytes=active_local_array_bytes,
        )
        if args.backend == "native":
            if args.emit_c or args.generated_c or args.cc or args.release:
                raise CompileError(
                    "--emit-c, --generated-c, --cc, and --release apply only to --backend c"
                )
            executable = NativeCodegen(
                source_path, funcs, top, variables, arrays, fixed_hz=fixed_hz,
                active_local_array_bytes=active_local_array_bytes,
                title=project_name if include_root is not None else "Anvil Native 2D"
            ).generate()
            out = args.output or source_path.with_suffix(".exe")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(executable)
            print(f"Built {out} as native AMD64 PE (no C/Rust compiler)")
            return 0
        generated = emit_c(
            source_path, funcs, top, variables, arrays, fixed_hz, project_name,
            active_local_array_bytes,
        )
        if args.emit_c:
            c_path = args.emit_c
            c_path.parent.mkdir(parents=True, exist_ok=True)
            c_path.write_text(generated, encoding="utf-8", newline="\n")
            print(f"Wrote {c_path}")
            return 0
        compiler = find_compiler(args.cc)
        if not compiler:
            if args.generated_c:
                args.generated_c.parent.mkdir(parents=True, exist_ok=True)
                args.generated_c.write_text(generated, encoding="utf-8", newline="\n")
                generated_note = f" Generated source: {args.generated_c}."
            else:
                generated_note = " Use --generated-c PATH or --emit-c PATH to preserve it."
            print(
                "No C compiler found. Install Visual Studio 2022 Build Tools "
                "with the C++ workload." + generated_note,
                file=sys.stderr,
            )
            return 2
        out = args.output or source_path.with_suffix(".exe")
        if args.generated_c:
            c_path = args.generated_c
            c_path.parent.mkdir(parents=True, exist_ok=True)
            c_path.write_text(generated, encoding="utf-8", newline="\n")
            build_c(compiler[1], c_path, out, args.release)
        else:
            with tempfile.TemporaryDirectory(prefix="anvil-build-") as build_dir:
                c_path = pathlib.Path(build_dir) / "program.c"
                c_path.write_text(generated, encoding="utf-8", newline="\n")
                build_c(compiler[1], c_path, out, args.release)
        print(f"Built {out} using {compiler[0]}")
        return 0
    except tomllib.TOMLDecodeError as e:
        print(f"{args.source}: {e}", file=sys.stderr)
        return 1
    except (CompileError, OSError, UnicodeError, subprocess.CalledProcessError) as e:
        print(str(e), file=sys.stderr)
        return 1
