# Anvil Compiler

## What the compiler does

```text
.ANVL source → parser and source-located validation → ordinary C source → C compiler/linker → Windows .exe
```

`compiler/anvil.py` is the current command-line compiler. It translates Anvil statements to direct C function calls and links `runtime/anvil_runtime.c`. The generated file is ordinary inspectable C; the game program itself is not Rust and is not an extension to Rust. A Rust backend is not implemented yet.

```powershell
python compiler/anvil.py examples/first_world.ANVL --emit-c build/first_world.c
python compiler/anvil.py examples/first_world.ANVL --release --generated-c build/first_world.c --output build/first_world.exe
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
```

The compiler requires Python 3.11+ and Visual Studio 2022 Build Tools with the **Desktop development with C++** workload. MSVC `cl` is the verified native compiler and is the only automatic compiler choice. Numeric-only programs use the same compiler and native C backend. `--emit-c` stops after generation so the intermediate code can be inspected or built separately.

## Current language slice

The compiler supports numeric global `var` bindings, fixed-size numeric arrays declared as `array name(size)` globally or inside a function, indexed with `array(name,index)`, function-local `local` bindings, `fn(name, parameters...)` functions, recursive calls, numeric `output` return values, `set/add/sub`, arithmetic and comparisons, `if/else/end`, `while condition ... end`, inclusive `for local(index) = start to end [step amount] ... end`, and `call fn(name, arguments...)` as both a statement and a numeric expression. Function-local arrays have zero-initialized per-call heap storage that is freed on every return, with an 8,192-element per-function limit and a 16 MiB total active-call budget. Array indexes are checked at runtime, with source-location diagnostics; see [the language guide](LANGUAGE.md#fixed-size-numeric-arrays). It also supports 2D/3D display primitives, keyboard state, configurable camera movement and field of view, delta/time, random/noise helpers, and the UDP numeric API. `display ray_sphere(x,y,z,radius)` is a built-in ray-traced primitive. Its C runtime builds a per-frame BVH for up to 32 traced spheres and uses the tree for closest-hit and hard-shadow queries. The `ray_backend(name)` and `ray_backend_available(name)` built-ins select a ray-tracing backend at runtime and query support. The current build only implements CPU BVH; DXR and Embree return unavailable. Unsupported statements receive a file and line diagnostic.

The current parser checks expression structure and operator precedence, built-in and user-function call arity, number/string expression types, declared global/local/array references, source function calls, C-name collisions, project settings, and project path containment before C generation. An optional `language version 1` declaration selects the current syntax; unversioned files retain version 1 behavior for compatibility. Malformed, duplicate, late, and unsupported version declarations receive path-and-line diagnostics. Generated numeric division calls a runtime guard that reports the source path and line and exits with code 2 when the divisor is zero. Numeric expressions also reject NaN and infinite results, including overflow and invalid math outputs, with source-located exit code 2 diagnostics. Numeric `while`/inclusive `for` loops, fixed-size global and function-local numeric arrays, and built-in fixed-step 2D circle/axis-aligned-box physics are supported; dynamic arrays, structures, imports, assets, saves, audio, 3D physics, static types, and general strings are not. `.ANVLproj` is a UTF-8 TOML project manifest. It uses `name`, `entry`, and optional `engine.fixed_hz` (1–240); unsupported keys are rejected, and entry paths cannot escape the project folder.

## Native performance

Ahead-of-time compilation removes VM dispatch from generated function calls. MSVC release builds use `/O2`. No benchmark suite or cross-language comparison exists yet, so the compiler makes no speed claim. The conventional software rasterizer and CPU BVH ray tracing are both CPU-bound; there is no GPU/DXR backend.

## Rust output

A future Rust backend can emit a normal `.rs` program and use `rustc` as the system compiler. The C backend is the only working backend in this project today. Output formats are backends, not syntax extensions: each takes Anvil source, emits standard target-language source, and invokes that language's compiler/linker.

