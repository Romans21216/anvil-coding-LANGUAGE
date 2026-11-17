# Anvil Compiler

## What the compiler does

```text
.ANVL source → Anvil parser and source-located validation → generated C → C compiler/linker → machine-code executable
```

`compiler/anvil.py` is the command-line compiler. A normal build performs both stages automatically: Anvil validates and translates the source to ordinary C in a temporary build directory, invokes the selected C compiler and linker, then removes the C and object intermediates. `--generated-c PATH` preserves the translated C alongside the executable for inspection; `--emit-c PATH` stops after translation. The C toolchain is responsible for machine-code generation and linking. The `--backend native` switch is an optional direct-x64 experiment, not the required architecture; its limited feature coverage is documented in [the experimental backend status](NATIVE_X64_COMPILER_MIGRATION.md).

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
| `compiler/native_codegen.py` | Direct x64 code generation for numeric programs and an initial 2D runtime. |
| `compiler/native_x64.py` | Anvil-owned x64 code fixups and PE32+ executable image writing. |
| `compiler/common.py` | Shared AST/data types, language limits, runtime names, and repository paths. |

The production CLI order is source reading → syntax parsing → semantic validation → C generation → C compiler/linker. The optional native experiment uses source reading → syntax parsing and validation → x64 code generation → PE writing. The parser and semantic checker expose phase-level entry points for focused tests, while existing `compiler/anvil.py` commands and importable functions remain compatible. The phase boundary regression tests live in `tests/test_compiler_modules.py`.

The compiler formatting convention is Black's default 88-column style; some native emitters still require formatting and instruction abstractions. Contributors can check formatting with `python -m black --check compiler tests/test_compiler_modules.py` when Black is installed. The project does not require Black to run or build Anvil.

## Reachability and dead-code elimination

The C backend emits only Anvil functions reachable from the program entry calls or engine callbacks. It follows ordinary calls and the generated dispatch calls for function-reference variables, so callback targets remain present. Graphical startup runs top-level `call fn(...)` initializers after project setup and before `anvil_run`. Semantic checks still validate every declared function before emission; an unused function with an invalid reference remains a compile error. After validation, the C pass removes unreachable function definitions and global scalar/array declarations unused by top-level initialization and emitted functions. It preserves reachable writes and expression evaluation. A runtime-module registry emits image, networking, and physics markers only when reachable code uses their built-ins; the build compiles `runtime/anvil_image.c`, `runtime/anvil_network.c`, and `runtime/anvil_physics.c` separately and links Winsock only for networking. Image storage registers a cleanup hook with the core runtime, which executes registered module cleanup before releasing its framebuffer. Core renderer and other runtime APIs remain in `runtime/anvil_runtime.c`. The registry is internal; user-facing package imports and external dependency resolution remain unfinished. Release MSVC builds package functions/data with `/Gy` and `/Gw` and pass `/OPT:REF` to the linker; GCC-compatible release invocations use function/data sections and `--gc-sections`. User-facing package imports, external dependency resolution and separate object caches remain unfinished.

```powershell
python compiler/anvil.py examples/first_world.ANVL --emit-c build/first_world.c
python compiler/anvil.py examples/first_world.ANVL --release --output build/first_world.exe
python compiler/anvil.py examples/first_world.ANVL --release --generated-c build/first_world.c --output build/first_world.exe
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
python compiler/anvil.py examples/functions.ANVL --backend native --output build/functions-native.exe
```

The existing C backend requires Python 3.11+ and Visual Studio 2022 Build Tools with the **Desktop development with C++** workload. MSVC `cl` is the verified native compiler and is the only automatic compiler choice. Normal C builds keep their C and object intermediates in temporary directories; `--generated-c` preserves C and `--emit-c` stops after generation. The experimental `--backend native` path requires only Python and Windows; it supports numeric programs and an initial 2D runtime and writes an EXE directly.

## Current language slice

The compiler supports numeric global `var` bindings, fixed-size numeric arrays declared as `array name(size)` globally or inside a function, indexed with `array(name,index)`, function-local `local` bindings, `fn(name, parameters...)` functions, recursive calls, numeric `output` return values, `set/add/sub`, arithmetic and comparisons, `if/else/end`, `while condition ... end`, inclusive `for local(index) = start to end [step amount] ... end`, and `call fn(name, arguments...)` as both a statement and a numeric expression. Function-local arrays have zero-initialized per-call heap storage that is freed on every return, with an 8,192-element per-function limit and a 16 MiB total active-call budget. Array indexes are checked at runtime, with source-location diagnostics; see [the language guide](LANGUAGE.md#fixed-size-numeric-arrays). It also supports 2D/3D display primitives, keyboard and resize-aware mouse input, configurable camera movement and field of view, delta/time, random/noise helpers, and the UDP numeric API. `display ray_sphere(x,y,z,radius)` is a built-in ray-traced primitive. `display ray_triangle(x1,y1,z1,x2,y2,z2,x3,y3,z3)` submits a world-space triangle to the C ray tracer; up to 40 triangles are accepted per batch and checked linearly while spheres use the BVH. In C, static and animated `.gltf`/`.glb` meshes use `ray_mesh(path,x,y,z,scale,rx,ry,rz)` and a cached per-asset triangle BVH (up to 200,000 triangles per mesh, 40 instances per frame, 32 cached assets and a shared 128 MiB budget for cached BVHs and per-frame posed copies); animated instances snapshot posed triangles and refit bounds per frame; `model_morph` weights apply to static meshes and are blended before node transforms on animated meshes, including assets that use both controls. Wasm `model_draw` and `ray_mesh` accept static and animated unskinned models, including morph targets and per-group defaults, through the WebGL depth-tested triangle path; both calls share a 16,384 submitted-triangle frame cap and `model_morph` overrides apply across groups. This is not ray tracing. Wasm supports unskinned animated models through the same triangle path; skinned `model_draw` supports one skin with up to 64 joints; skinned `ray_mesh` receives a located diagnostic. C `model_draw` supports skinned meshes, while C `ray_mesh` does not. The desktop C runtime builds a per-frame BVH for up to 40 traced spheres and uses the tree for closest-hit and hard-shadow queries; the WebAssembly approximation accepts 32. The `ray_backend(name)` and `ray_backend_available(name)` built-ins select a ray-tracing backend at runtime and query support. The current desktop build only implements CPU BVH; DXR and Embree return unavailable. Unsupported statements receive a file and line diagnostic, and unknown function or variable names name the closest declared match when one is unambiguous.

The current parser checks expression structure and operator precedence, built-in and user-function call arity, number/string expression types, declared global/local/array references, source function calls, C-name collisions, project settings, and project path containment before C generation. An optional `language version 1` declaration selects the current syntax; unversioned files retain version 1 behavior for compatibility. Malformed, duplicate, late, and unsupported version declarations receive path-and-line diagnostics. Generated numeric division calls a runtime guard that reports the source path and line and exits with code 2 when the divisor is zero. Numeric expressions also reject NaN and infinite results, including overflow and invalid math outputs, with source-located exit code 2 diagnostics. Numeric `while`/inclusive `for` loops, `break`/`continue`, fixed-size global and function-local numeric arrays, growable numeric and text lists (capped at 256 entries), text values with `len`/`char`/`mid` and text function parameters and returns, optional `number`/`text`/`bool` annotations, enums, whole-file includes and selective function imports, fixed-step 2D circle/axis-aligned-box physics, and BMP image/sprite loading are supported. Records/structures, general image formats, saves, audio, 3D physics, and Unicode code-point indexing are not. `.ANVLproj` is a UTF-8 TOML project manifest. It uses `name`, `entry`, and optional `engine.fixed_hz` (1–240); unsupported keys are rejected, and entry paths cannot escape the project folder. An optional `[assets]` table with `files = [...]` lists packaged assets; `--package` also picks up literal `image_load("...")` and `sound_load("...")` paths from the sources, rejects assets outside the project folder, and refuses to package when any asset is missing. The generated `anvil-package.json` records the format, name, target, backend, compiler identity (path plus SHA-256 for cl, language version for native), used builtins, the program size and hash, each asset path/size/hash and a checksums map. It contains no timestamps, so identical inputs produce identical manifest bytes. The measured backend capability table lives in `docs/CAPABILITY_MATRIX.md` and is generated by `tools/capability_matrix.py`; `--check` fails when it drifts. A project test case is any `.ANVL` file under `tests/`; it passes when the built program exits 0, failures print the captured build/run output, and `--test` exits 1 if any case fails or no tests exist. The formatter only rewrites whitespace and leading indentation (Anvil ignores indentation); it never changes tokens, collapses runs of blank lines, ends the file with one newline, is idempotent, and every example still compiles after formatting.

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
| C, `--release` | 0.42 s cold, 0.05 s cached | 182,784 B |

The native build has no external toolchain to start and no cache, so it is steady;
the C build's first run pays for loading the MSVC environment and later runs reuse
the build cache.

`--timings` reports each phase separately so a slow step is identifiable: a cold C build on this machine measured about 0.4-0.6 s depending on load (parse and generate are ~3 ms each; the rest is `cl.exe`), while a cache hit replaces the build with a ~0.11-0.18 s copy plus the dependency-sidecar digests. The build phase was 1,597 ms before the Visual Studio environment was cached: `VsDevCmd.bat -arch=x64` costs 1.3-1.7 s and is now run once per toolset, with the captured environment reused for later builds. Published ceilings for compile time and executable size live in `tools/bench_budgets.json` and are enforced by `python tools/bench_anvil.py --check`.

`--profile-json <path>` writes a versioned `anvil.build-profile` JSON record with phase durations, platform metadata, and source/generated/output byte counts. Its `artifacts.build_state` distinguishes check-only, C-only emission, native output, cold compile, and warm cache hit. Peak Python allocation memory is measured with `tracemalloc` and recorded in bytes; native allocations from external compiler processes are not included.

The cache key covers the generated C, every runtime source and header, the compiler
Python sources, the **contents** of `cl.exe`, the contents of the `link.exe` beside it,
and a content fingerprint of the selected Windows SDK (every file under the newest
version's Include and Lib trees, by path, size and modification time; about 10-40 ms
thanks to directory-enumeration metadata, so an SDK library or header changed in place
inside an unchanged version directory still invalidates the cache). A compiler replaced
in place with the same size and a restored timestamp, or a different linker in the same
toolset, therefore misses the cache instead of reusing a stale executable. The captured
Visual Studio environment is named from a digest of `VsDevCmd.bat` and `vcvarsall.bat`
contents, so a same-size script replacement cannot revive a stale environment. Libraries passed to `build_c`
through `libraries=` are not part of the key yet.

On top of the metadata fingerprint, a successful C build records the headers it actually
read with `cl /sourceDependencies` into `<cache>/<base-key>.deps.json`, and the cache key
then folds in the **bytes** of those headers. A real program (`examples/first_world.ANVL`)
consumes 120 distinct headers, 5.45 MB, and digesting them costs about 10 ms per cache
lookup; the flag adds no measurable compile time (315 ms with and without it). This closes
the same-size, same-mtime header collision that a metadata-only fingerprint cannot see,
without paying the ~5.9 s that hashing the whole 1.2 GB SDK tree would cost. The sidecar is
absent after the first build with an older cache entry, in which case the build falls back
to the metadata key and rewrites it on the next real build.

Static libraries get the same treatment from the other end of the toolchain. A cached
build runs the linker with `/VERBOSE` and records every `.lib` it resolved (the
`#pragma comment(lib, …)` defaults inside SDK headers never appear on the command line)
into `<cache>/<base-key>.libs.json`; those files' bytes are folded into the key too. A real
build resolves nine libraries totalling 62 MB, which costs about 36 ms to digest, taking a
`first_world` cache hit from ~145 ms to ~170 ms against a 315 ms cold build. Header and
library sidecars are independent: either may be missing, and the key falls back for that
half alone.

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

`anvil verify <source.ANVL|project.ANVLproj>` validates the source and project
manifest, checks supported literal assets reachable from the program entry
points, and runs C lowering validation without linking or writing an executable.
It reports independent asset failures together. Add `--format json` for a
versioned JSON object (`version: 1`) with `ok` and a `diagnostics` array.
Reachable asset calls whose path is computed dynamically receive an explicit
preflight diagnostic because the compiler cannot determine which file to check.

`python tools/bench_runtime.py --json profile.json` writes a versioned
`anvil.runtime-profile` record with per-scene work and present percentiles,
sample/run counts, warmup frames, bucket resolution, applicable budgets and
machine environment. This captures steady-state frame work separately from
present cost; compiler phase timings and process memory remain in their existing
tools and reports.

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
| `--diagnostics caret\|editor` | caret blocks (default) or one-line `path:line:column` messages for editors |
| `--explain CODE` | print the cause and fix for a stable diagnostic code (see [diagnostic codes](ERRORS.md)) |
| `--timings` | print `read/parse/generate/build` milliseconds to stderr |
| `--profile-json <path>` | write versioned phase timings and artifact metadata as JSON |
| `--package <dir>` | copy the program and its assets into `dir` with `anvil-package.json` |
| `--package-dry-run` | validate assets and print the package manifest without writing |
| `--run` | build and run from the project directory (manifest directory, or source directory for standalone files), returning its exit code |
| `--clean` | remove generated build artifacts beside the source |
| `--doctor` | report the Python, C compiler, native backend and runtime state |
| `--new <dir>` | create a starter project with a manifest, program and README |
| `--format` | normalise line endings, trailing whitespace, blank runs and block indentation |
| `--format-check` | exit 1 when `--format` would change the source file |
| `--test` | compile and run every `tests/**/*.ANVL` case with the selected backend |
| `--print-imports` | print the builtins the program actually uses and stop |
| `--extension <manifest>` | register an extension (repeatable), see `docs/EXTENSIONS.md` |
| `--repl-backend c\|native` | backend used by the interactive shell |
| `--repl` | start the interactive shell instead of compiling a file |
| `--hello` | build and run a greeting program, so the first command always works |
