# Compiler and Build

The default, full-featured pipeline is:

```text
.ANVL source -> parser and semantic checks -> ordinary C source -> MSVC -> Windows .exe
```

The experimental `native` backend emits x64 instructions and writes the PE32+ executable itself. It does not output C/Rust or invoke a system compiler, but currently supports only a small numeric language subset. The no-C native backend is the project target; full engine and runtime parity is not complete. See [Native x64 migration](../NATIVE_X64_COMPILER_MIGRATION.md).

## Direct native executable

```powershell
python compiler/anvil.py examples/functions.ANVL --backend native --output build/functions-native.exe
```

The supported native subset includes simple numeric functions with up to four parameters, arithmetic except remainder, comparisons, short-circuit `and`/`or`, `if`, `while`, inclusive ascending/descending `for`, numeric variables, and integer console output. Graphics, input, arrays, project manifests, and other engine APIs are not supported by this backend yet.

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

