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
| `compiler/native_codegen.py` | Direct x64 code generation for numeric programs and an initial 2D runtime. |
| `compiler/native_x64.py` | Anvil-owned x64 code fixups and PE32+ executable image writing. |
| `compiler/common.py` | Shared AST/data types, language limits, runtime names, and repository paths. |

The C CLI order is source reading → syntax parsing → semantic validation → C generation → optional MSVC build. The native order is source reading → syntax parsing and validation → x64 code generation → PE writing. The parser and semantic checker expose phase-level entry points for focused tests, while existing `compiler/anvil.py` commands and importable functions remain compatible. The phase boundary regression tests live in `tests/test_compiler_modules.py`.

The compiler formatting convention is Black's default 88-column style; some native emitters still require formatting and instruction abstractions. Contributors can check formatting with `python -m black --check compiler tests/test_compiler_modules.py` when Black is installed. The project does not require Black to run or build Anvil.

```powershell
python compiler/anvil.py examples/first_world.ANVL --emit-c build/first_world.c
python compiler/anvil.py examples/first_world.ANVL --release --generated-c build/first_world.c --output build/first_world.exe
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
python compiler/anvil.py examples/functions.ANVL --backend native --output build/functions-native.exe
```

The existing C backend requires Python 3.11+ and Visual Studio 2022 Build Tools with the **Desktop development with C++** workload. MSVC `cl` is the verified native compiler and is the only automatic compiler choice. `--emit-c` stops after C generation. The experimental `--backend native` path requires only Python and Windows; it supports numeric programs and an initial 2D runtime and writes an EXE directly.

## Current language slice

The compiler supports numeric global `var` bindings, fixed-size numeric arrays declared as `array name(size)` globally or inside a function, indexed with `array(name,index)`, function-local `local` bindings, `fn(name, parameters...)` functions, recursive calls, numeric `output` return values, `set/add/sub`, arithmetic and comparisons, `if/else/end`, `while condition ... end`, inclusive `for local(index) = start to end [step amount] ... end`, and `call fn(name, arguments...)` as both a statement and a numeric expression. Function-local arrays have zero-initialized per-call heap storage that is freed on every return, with an 8,192-element per-function limit and a 16 MiB total active-call budget. Array indexes are checked at runtime, with source-location diagnostics; see [the language guide](LANGUAGE.md#fixed-size-numeric-arrays). It also supports 2D/3D display primitives, keyboard and resize-aware mouse input, configurable camera movement and field of view, delta/time, random/noise helpers, and the UDP numeric API. `display ray_sphere(x,y,z,radius)` is a built-in ray-traced primitive. Its C runtime builds a per-frame BVH for up to 32 traced spheres and uses the tree for closest-hit and hard-shadow queries. The `ray_backend(name)` and `ray_backend_available(name)` built-ins select a ray-tracing backend at runtime and query support. The current build only implements CPU BVH; DXR and Embree return unavailable. Unsupported statements receive a file and line diagnostic.

The current parser checks expression structure and operator precedence, built-in and user-function call arity, number/string expression types, declared global/local/array references, source function calls, C-name collisions, project settings, and project path containment before C generation. An optional `language version 1` declaration selects the current syntax; unversioned files retain version 1 behavior for compatibility. Malformed, duplicate, late, and unsupported version declarations receive path-and-line diagnostics. Generated numeric division calls a runtime guard that reports the source path and line and exits with code 2 when the divisor is zero. Numeric expressions also reject NaN and infinite results, including overflow and invalid math outputs, with source-located exit code 2 diagnostics. Numeric `while`/inclusive `for` loops, fixed-size global and function-local numeric arrays, fixed-step 2D circle/axis-aligned-box physics, and BMP image/sprite loading are supported; dynamic arrays, structures, imports, general image formats, saves, audio, 3D physics, static types, and general strings are not. `.ANVLproj` is a UTF-8 TOML project manifest. It uses `name`, `entry`, and optional `engine.fixed_hz` (1–240); unsupported keys are rejected, and entry paths cannot escape the project folder.

## Native performance

Ahead-of-time compilation removes VM dispatch from generated function calls. MSVC release builds use `/O2`. No benchmark suite or cross-language comparison exists yet, so the compiler makes no speed claim. The conventional software rasterizer and CPU BVH ray tracing are both CPU-bound; there is no GPU/DXR backend.

## Native backend limits

The direct backend supports up to sixteen numeric parameters, scalar globals/locals, checked fixed-size global arrays, arithmetic except remainder, comparisons, short-circuit Boolean operators, branches and numeric loops. It emits console output rounded to six fractional digits and rejects values outside the signed 64-bit formatting range with a controlled diagnostic. Its initial buffered Win32 2D runtime supports opaque rectangles, fixed updates, keyboard/mouse input and time/delta queries. Basic math, seeded RNG, gradient noise/fBm and local source includes with reachable-function selection are also available.

Function-local arrays, native project manifests, other graphics primitives, text/alpha blending, 3D/camera, assets/audio, physics/networking and trigonometry remain unsupported on the direct path. The broader C/MSVC backend remains the default until native parity is verified. See [native semantics and limits](NATIVE_X64_COMPILER_MIGRATION.md), [include troubleshooting](INCLUDES.md#compiler-depth-limits-and-troubleshooting) and [current evaluation evidence](QA_REPORT.md).
