# Getting Started

For direct source-to-EXE builds using Python alone, see [the direct compiler workflow](Compiler-and-Build.md). The broader engine workflow below uses the transitional C/MSVC backend.

## Requirements

- Windows
- Python 3.11 or newer
- Visual Studio 2022 Build Tools with the **Desktop development with C++** workload

MSVC `cl.exe` is the verified native compiler. See the project README for the current setup notes.

## Build a native game

From the project root:

```powershell
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
```

To compile a small command-line program:

```powershell
python compiler/anvil.py examples/numeric_demo.ANVL --release --output build/numeric_demo.exe
```

To try function parameters and local variables:

```powershell
python compiler/anvil.py examples/functions.ANVL --release --output build/functions_demo.exe
./build/functions_demo.exe
```

The sample prints `13`. Use `--emit-c build/program.c` to inspect the generated C without building an executable.

## Editor support

The VS Code extension is in `vscode-extension/`. The current package is `anvil-language-support-0.1.13.vsix`; install it through **Extensions: Install from VSIX...** if you want the newer syntax coloring. Installed Anvil extension 0.1.4 is preserved in the existing development setup. The extension provides syntax coloring and editor pairing/indentation rules; it does not provide autocomplete, diagnostics, or debugging.

