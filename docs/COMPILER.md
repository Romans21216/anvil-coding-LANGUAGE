# Anvil Compiler

## What the compiler does

```text
.ANVL source → parser and source-located validation → backend → Windows .exe
```

`compiler/anvil.py` is the command-line compiler. The default backend remains the existing C implementation for full current engine coverage. An experimental `--backend native` path writes x64 machine code and a PE32+ executable directly, without generating C/Rust or invoking another compiler. Its language coverage is currently limited; see [the native compiler migration status](NATIVE_X64_COMPILER_MIGRATION.md). The target direction is a complete Anvil-owned native backend and runtime, with no C or Rust dependency.

## Compiler architecture

The command-line path remains `compiler/anvil.py`; it is now a small compatibility facade that re-exports the existing compiler API. Implementation responsibilities are separated into these modules:

| Module | Responsibility |
|---|---|
| `compiler/lexer.py` | Comment stripping, delimiter-aware keyword splitting, and lexical helpers. |
| `compiler/parser.py` | Parse source statements and produce an unresolved `ParsedProgram`; its `parse()` entry point preserves the former four-value result. |
| `compiler/semantics.py` | Resolve variable/local references, reject invalid declarations, and validate C symbol collisions before code generation. |
| `compiler/expressions.py` | Parse expressions, check expression types/arity, and lower expressions to C. |
| `compiler/codegen.py` | Emit C statements, runtime calls, and complete translation units from validated nodes. |
| `compiler/build.py` | Discover MSVC and invoke the native compiler/linker. |
| `compiler/cli.py` | Parse CLI/project settings and orchestrate source loading, semantic validation, C generation, and build output. |
| `compiler/native_codegen.py` | Experimental direct x64 code generation for a limited numeric Anvil subset. |
| `compiler/native_x64.py` | Anvil-owned x64 code fixups and PE32+ executable image writing. |
| `compiler/common.py` | Shared AST/data types, language limits, runtime names, and repository paths. |

The C CLI order is source reading → syntax parsing → semantic validation → C generation → optional MSVC build. The native order is source reading → syntax parsing and validation → x64 code generation → PE writing. The parser and semantic checker expose phase-level entry points for focused tests, while existing `compiler/anvil.py` commands and importable functions remain compatible. The phase boundary regression tests live in `tests/test_compiler_modules.py`.

Python compiler files use Black's default 88-column formatting. Contributors can check formatting with `python -m black --check compiler tests/test_compiler_modules.py` when Black is installed. The project does not require Black to run or build Anvil.

```powershell
python compiler/anvil.py examples/first_world.ANVL --emit-c build/first_world.c
python compiler/anvil.py examples/first_world.ANVL --release --generated-c build/first_world.c --output build/first_world.exe
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
python compiler/anvil.py examples/functions.ANVL --backend native --output build/functions-native.exe
```

The existing C backend requires Python 3.11+ and Visual Studio 2022 Build Tools with the **Desktop development with C++** workload. MSVC `cl` is the verified native compiler and is the only automatic compiler choice. `--emit-c` stops after C generation. The experimental `--backend native` path requires only Python and Windows; it supports a limited numeric subset and writes an EXE directly.

## Current language slice

The compiler supports numeric global `var` bindings, fixed-size numeric arrays declared as `array name(size)` globally or inside a function, indexed with `array(name,index)`, function-local `local` bindings, `fn(name, parameters...)` functions, recursive calls, numeric `output` return values, `set/add/sub`, arithmetic and comparisons, `if/else/end`, `while condition ... end`, inclusive `for local(index) = start to end [step amount] ... end`, and `call fn(name, arguments...)` as both a statement and a numeric expression. Function-local arrays have zero-initialized per-call heap storage that is freed on every return, with an 8,192-element per-function limit and a 16 MiB total active-call budget. Array indexes are checked at runtime, with source-location diagnostics; see [the language guide](LANGUAGE.md#fixed-size-numeric-arrays). It also supports 2D/3D display primitives, keyboard and resize-aware mouse input, configurable camera movement and field of view, delta/time, random/noise helpers, and the UDP numeric API. `display ray_sphere(x,y,z,radius)` is a built-in ray-traced primitive. Its C runtime builds a per-frame BVH for up to 32 traced spheres and uses the tree for closest-hit and hard-shadow queries. The `ray_backend(name)` and `ray_backend_available(name)` built-ins select a ray-tracing backend at runtime and query support. The current build only implements CPU BVH; DXR and Embree return unavailable. Unsupported statements receive a file and line diagnostic.

The current parser checks expression structure and operator precedence, built-in and user-function call arity, number/string expression types, declared global/local/array references, source function calls, C-name collisions, project settings, and project path containment before C generation. An optional `language version 1` declaration selects the current syntax; unversioned files retain version 1 behavior for compatibility. Malformed, duplicate, late, and unsupported version declarations receive path-and-line diagnostics. Generated numeric division calls a runtime guard that reports the source path and line and exits with code 2 when the divisor is zero. Numeric expressions also reject NaN and infinite results, including overflow and invalid math outputs, with source-located exit code 2 diagnostics. Numeric `while`/inclusive `for` loops, `break`/`continue`, fixed-size global and function-local numeric arrays, growable numeric and text lists (capped at 256 entries), text values with `len`/`char`/`mid` and text function parameters and returns, optional `number`/`text`/`bool` annotations, enums, whole-file includes and selective function imports, fixed-step 2D circle/axis-aligned-box physics, and BMP image/sprite loading are supported. Records/structures, general image formats, saves, audio, 3D physics, and Unicode code-point indexing are not. `.ANVLproj` is a UTF-8 TOML project manifest. It uses `name`, `entry`, and optional `engine.fixed_hz` (1–240); unsupported keys are rejected, and entry paths cannot escape the project folder. An optional `[assets]` table with `files = [...]` lists packaged assets; `--package` also picks up literal `image_load("...")` and `sound_load("...")` paths from the sources, rejects assets outside the project folder, and refuses to package when any asset is missing. The generated `anvil-package.json` records the format, name, target, backend, compiler identity (path plus SHA-256 for cl, language version for native), used builtins, the program size and hash, each asset path/size/hash and a checksums map. It contains no timestamps, so identical inputs produce identical manifest bytes.

## Native performance

Ahead-of-time compilation removes VM dispatch from generated function calls. MSVC
release builds use `/O2`. The conventional software rasterizer and CPU BVH ray
tracing are both CPU-bound; there is no GPU/DXR backend. A 116-case differential
probe compares both backends' output on every build.

Measured on the rarity-roll program (one function calling a 500-line mixer), best
of three runs:

| backend | compile time | executable |
|---|---|---|
| native | 0.12 s | 130,048 B |
| C, `--release` | 1.9 s cold, 0.13 s cached | 182,784 B |

The native build has no external toolchain to start and no cache, so it is steady;
the C build's first run pays for loading the MSVC environment and later runs reuse
the build cache.

## Native backend limits

The direct backend handles console programs (numeric functions with up to sixteen
parameters, arithmetic including remainder, comparisons, short-circuit Boolean
operators, `if`/`while`/`for`, numeric and text locals and globals, arrays and text
lists, and output rounded to six fractional digits) and a `scene 2d` window whose
drawing is limited to `display rect`.

Not ported yet: `scene 3d`, physics, image calls, ray tracing, network receive, and
`net_host`/`net_join` inside a native scene. Each refusal names the missing feature
and points at the other backend, for example
`body_force() is not available in the native x64 backend yet; build with --backend c`
or `native 2D graphics currently supports display rect only`.

Output values outside its signed 64-bit formatting range (about 9.2e18) stop with a
controlled error instead of printing; the C backend prints the full decimal
expansion. The backend is not the default until the remaining features are ported
and verified.

## Output size

The C backend builds optimized by default: `anvil program.ANVL` links a release
image, and `--debug` opts back into `/Od`. A hello-world measures:

| build | bytes |
|---|---|
| default (release, static CRT) | 143,360 |
| `--debug` | 263,680 |
| `--dynamic-runtime` (`/MD`) | 9,728 |
| `--backend native` | 2,560 |

`--dynamic-runtime` links the system VC++ runtime instead of baking the static
CRT into the image — about 15x smaller, but the machine that runs the executable
must have that runtime, so it stays opt-in. Release builds also pass `/Gy` with
`/OPT:REF /OPT:ICF`, and the gcc path gets `-ffunction-sections
-fdata-sections -Wl,--gc-sections`, so unused code never reaches the image.

## Command line

| flag | effect |
|---|---|
| `--backend c\|native` | pick the C toolchain (default) or the Anvil-owned x64 PE backend |
| `--output`, `-o` | name the executable |
| `--debug` | build the C output unoptimized (`/Od`); release is the default |
| `--dynamic-runtime` | link the system VC++ runtime (`/MD`) instead of the static CRT |
| `--cc <path>` | use a specific C compiler instead of the one discovery finds |
| `--emit-c <path>` | write the generated C and stop, without building |
| `--generated-c <path>` | choose where the generated C is written |
| `--check` | parse and validate only, with no output written |
| `--deny-warnings` | treat warnings as build failures |
| `--no-cache` | ignore the build cache and do not store a new entry |
| `--package <dir>` | copy the program and its assets into `dir` with `anvil-package.json` |
| `--package-dry-run` | validate assets and print the package manifest without writing |
| `--run` | build the program and run it, returning its exit code |
| `--clean` | remove generated build artifacts beside the source |
| `--doctor` | report the Python, C compiler, native backend and runtime state |
| `--new <dir>` | create a starter project with a manifest, program and README |
| `--print-imports` | print the builtins the program actually uses and stop |
| `--extension <manifest>` | register an extension (repeatable), see `docs/EXTENSIONS.md` |
| `--repl-backend c\|native` | backend used by the interactive shell |
| `--repl` | start the interactive shell instead of compiling a file |
| `--hello` | build and run a greeting program, so the first command always works |
