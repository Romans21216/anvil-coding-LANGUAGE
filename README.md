# Anvil

**Anvil** is a small BASIC/Lua-inspired game language with its own `.ANVL` source format. The compiler validates Anvil programs, emits ordinary C, and invokes MSVC to produce a native Windows `.exe`. Anvil is not Rust syntax and does not extend Rust.

## What works now

- Numeric global variables, function parameters, numeric return values, recursion, and function-local state.
- A Windows C backend, branches, input, time, seeded random numbers, gradient noise, and fractal noise.
- A native software renderer for 2D rectangles, circles, lines and text, plus basic 3D cubes, spheres, and planes.
- Keyboard camera movement/look, adjustable field of view, and the built-in BVH-accelerated CPU ray-traced sphere function `display ray_sphere(...)`.
- A small opt-in UDP multiplayer primitive for one numeric value and one LAN peer.
- A VS Code syntax extension and a browser-based preview workbench.

This is an early prototype, not a production engine. Rendering uses a fixed-size software buffer. CPU BVH ray tracing is implemented; RTX/DXR and Embree are not. The network sample is not secure or reliable Internet multiplayer. Rust output, GPU rendering, assets, audio, physics, portability, and performance benchmarks remain future work. “Hyper-efficient” is a design goal, not a measured result.

## Build a Windows executable

Install Python 3.11+ and Visual Studio 2022 Build Tools with the **Desktop development with C++** workload. Then run:

```powershell
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
```

The compiler emits inspectable C and uses MSVC to build the executable.

## Documentation and development

- [Language guide](docs/LANGUAGE.md)
- [Engine runtime](docs/ENGINE.md)
- [Compiler and build](docs/COMPILER.md)
- [Multiplayer prototype](docs/MULTIPLAYER.md)
- [Complete improvement backlog](docs/IMPROVEMENT_BACKLOG.md)
- [Wiki-ready reference pages](docs/Wiki/Home.md)
- [Bug reporting and contribution rules](CONTRIBUTING.md)

Run compiler/runtime tests with `python -m unittest discover -s tests -v`; validate VS Code syntax support with `npm test --prefix vscode-extension`.

Source files use `.ANVL`; project manifests use `.ANVLproj`. The language/engine are a prototype and do not claim the `.ANVL` suffix is globally unique.