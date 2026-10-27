"""Command-line entry point for compiling Anvil source and project manifests."""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tomllib

from compiler.build import build_c, find_compiler
from compiler.codegen import emit_c
from compiler.common import CompileError
from compiler.native_codegen import NativeCodegen
from compiler.parser import parse


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Compile Anvil source or project to C, then link a native executable."
        )
    )
    ap.add_argument(
        "source",
        type=pathlib.Path,
        help="input .ANVL source or .ANVLproj project manifest",
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
        "--backend",
        choices=("c", "native"),
        default="c",
        help="select the C toolchain or experimental Anvil-owned x64 PE backend",
    )
    args = ap.parse_args()
    try:
        source_path = args.source
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
            source_path = (project_root / entry).resolve()
            try:
                source_path.relative_to(project_root)
            except ValueError as exc:
                raise CompileError(
                    f"{args.source}: entry must resolve inside the project folder"
                ) from exc
        source = source_path.read_text(encoding="utf-8")
        funcs, top, variables, arrays = parse(source_path, source)
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
        build_c(compiler[1], c_path, out, args.release)
        print(f"Built {out} using {compiler[0]}")
        return 0
    except tomllib.TOMLDecodeError as e:
        print(f"{args.source}: {e}", file=sys.stderr)
        return 1
    except (CompileError, OSError, UnicodeError, subprocess.CalledProcessError) as e:
        print(str(e), file=sys.stderr)
        return 1
