# Compiler and Build

The compilation pipeline is:

```text
.ANVL source -> parser and semantic checks -> ordinary C source -> MSVC -> Windows .exe
```

Anvil syntax is not Rust syntax and does not extend Rust. The compiler emits inspectable C. Rust generation is not implemented.

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

The current compiler is a single Python source file that handles parsing, validation, C generation, and build orchestration. Separating those responsibilities is part of the improvement backlog.

