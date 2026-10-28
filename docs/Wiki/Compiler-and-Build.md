# Compiler and Build

The default, broader prototype pipeline is:

```text
.ANVL source -> parser and semantic checks -> ordinary C source -> MSVC -> Windows .exe
```

The experimental `native` backend emits x64 instructions and writes the PE32+ executable itself. It does not output C/Rust or invoke a system compiler, and includes a growing numeric and 2D runtime subset. The no-C native backend is the project target; full engine and runtime parity is not complete. See [Native x64 migration](../NATIVE_X64_COMPILER_MIGRATION.md).

## Direct native executable

```powershell
python compiler/anvil.py examples/functions.ANVL --backend native --output build/functions-native.exe
```

The native subset includes numeric functions with up to sixteen parameters, checked global numeric arrays, arithmetic except remainder, comparisons, short-circuit `and`/`or`, branches, `while`/inclusive `for` loops, scalar locals/globals, and six-fractional-digit console output. Explicit `call fn(main, ...)` entry arguments use the ordinary call ABI; implicit `main` takes no arguments. Native 2D supports buffered opaque rectangles, fixed updates, keyboard input and client-pixel mouse queries. Math includes abs/sqrt/floor/ceil/min/max, deterministic seeded integer random numbers, 3D gradient noise and fBm, with an Anvil-written procedural library compiled directly into the EXE. See the migration guide for numeric ranges, stack-frame/temporary limits and exact behavior.

Native 3D/camera, broader graphics/assets, audio, physics, networking, trigonometry, project manifests, package registries/binary plugins and Forge targets remain unsupported. These broader workflows are still incomplete in the requested final no-C/no-Rust architecture; the C backend remains the default prototype.

## Direct source build

```powershell
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
