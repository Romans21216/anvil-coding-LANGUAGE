# Compiler and Build

The primary pipeline is:

```text
.ANVL source -> Anvil parser and semantic checks -> ordinary C source -> MSVC -> Windows .exe
```

One normal build command runs the full pipeline: Anvil validates and translates `.ANVL` to temporary C, invokes the C compiler/linker to produce machine code and an executable, then removes the C and object intermediates. Use `--generated-c PATH` to preserve C for inspection or `--emit-c PATH` to emit it without building. The optional `native` backend directly emits x64/PE for a limited subset; it is experimental and not a prerequisite for the primary workflow. See [the experimental native backend](../NATIVE_X64_COMPILER_MIGRATION.md).

## Direct native executable

```powershell
python compiler/anvil.py examples/functions.ANVL --backend native --output build/functions-native.exe
```

The native subset includes numeric functions with up to sixteen parameters, checked global numeric arrays, arithmetic except remainder, comparisons, short-circuit `and`/`or`, branches, `while`/inclusive `for` loops, scalar locals/globals, and six-fractional-digit console output. Explicit `call fn(main, ...)` entry arguments use the ordinary call ABI; implicit `main` takes no arguments. Native 2D supports buffered opaque rectangles, fixed updates, keyboard input and client-pixel mouse queries. Math includes abs/sqrt/floor/ceil/min/max, deterministic seeded integer random numbers, 3D gradient noise and fBm, with an Anvil-written procedural library compiled directly into the EXE. See the migration guide for numeric ranges, stack-frame/temporary limits and exact behavior.

The C runtime is Windows-focused and remains short of the broader engine, Forge, media, and operating-system requirements. The optional direct backend lacks much of the existing C language/runtime coverage and is not the primary compiler target.

## Direct source build

```powershell
python compiler/anvil.py examples/first_world.ANVL --release --output build/first_world.exe
python compiler/anvil.py examples/first_world.ANVL --release --generated-c build/first_world.c --output build/first_world.exe
```

## Project build

```powershell
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
```

The `.ANVLproj` file is a TOML manifest with a `name`, project-relative `entry`, and optional `[engine].fixed_hz`. The compiler rejects unknown settings and entries outside the project folder.

## C output only

```powershell
python compiler/anvil.py examples/functions.ANVL --emit-c build/functions.c
```

`--emit-c` applies to the default C backend only. Compiler phases are split across lexer, parser, semantic validation, C code generation, direct x64 generation, PE writing, and CLI modules.


Local multi-file source composition uses top-level `include "relative/library.ANVL"`. Both backends resolve the local include graph; the native backend compiles reachable functions and their runtime dependencies. See [include semantics and limits](../INCLUDES.md). Namespaces, package registries and separate object linking remain unfinished.

Native project builds accept `.ANVLproj` with `--backend native`. The existing `name` supplies the Unicode window title, `entry` resolves inside the project directory, and `[engine].fixed_hz` accepts integer rates1–240 (default60). Includes may span the project tree. Native graphical updates, `time()` and `delta()` use that rate. Direct source titles and console behavior retain their defaults. Unsupported native features fail explicitly without invoking C/Rust.


Build artifacts: normal Anvil builds keep generated C, MSVC object files, and the Visual Studio environment helper in temporary build-owned directories and remove them after the build. Use `--generated-c PATH` to preserve generated C while building, or `--emit-c PATH` to write C only.

The C backend emits functions reachable from top-level calls, `main`, or graphical callbacks and drops unused global scalar/array declarations. It follows callback dispatch helpers so `fnref(...)` targets remain available, while still validating every function body. Release builds use function/data sections and linker garbage collection. A small runtime-module registry selects the separate networking translation unit when reachable Anvil code uses network statements or `receive()`; other C runtime systems remain in the core translation unit. User-facing package imports and external dependency resolution are still unfinished.
