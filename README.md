# Anvil

**Anvil** is a small BASIC/Lua-inspired game language with its own `.ANVL` source format. The current default compiler emits C and invokes MSVC for broader engine coverage. An experimental direct x64 backend (`--backend native`) writes a Windows `.exe` without emitting C/Rust or invoking another compiler; it supports numeric programs and an initial 2D window runtime. The project target is a complete Anvil-owned compiler and runtime with no C or Rust dependency.

## What works now

- A Windows C backend for numeric globals, checked fixed-size global and function-local arrays, function-local variables, parameterized and recursive functions with numeric return values, calls, branches, inclusive `for`/`while` loops, input, time, seeded random numbers, gradient noise, and fractal noise.
- An experimental direct x64/PE32+ backend for numeric functions, checked fixed-size global arrays (up to 16 MiB total program data), arithmetic, comparisons, branches, loops, and console output rounded to six fractional digits. Its initial Win32 2D runtime supports a resizable window, buffered opaque rectangles, `fn(draw)`, configurable 1–240 Hz `fn(update)` (default60), `time()`/`delta()`/`compute()`, and `held(key)`/`pressed(key)`. It emits the EXE directly from `.ANVL` and imports Windows APIs without a C/Rust runtime shim. Full native engine parity remains incomplete.
- A small native software renderer for 2D rectangles, circles, lines and text, plus shaded 3D cubes, spheres, and grid planes with a perspective camera and depth buffer.
- Keyboard camera movement/look, adjustable field of view, and a built-in BVH-accelerated CPU ray-traced sphere with shadows and specular lighting.
- Keyboard edge/held state, configurable fixed-step updates, deterministic RNG and noise helpers.
- Resize-aware mouse position, per-update button edges, held buttons, and signed wheel input in virtual framebuffer coordinates.
- 2D sprite resources loaded from bounded uncompressed 24-bit/32-bit BMP files, with alpha blending, nearest-neighbor scaling, clipping, and explicit release.
- A first LAN multiplayer primitive: opt-in UDP host/join and exchanging one numeric value.
- A configurable fixed-step 2D circle and axis-aligned box-body system (up to 128 slots) with forces, gravity, restitution, mixed-shape collision response, and Coulomb friction.
- A VS Code language extension and a browser-based preview workbench.

This is an early prototype. Conventional primitives use a fixed-size software rasterizer, and ray-traced spheres use CPU BVH traversal; hardware DXR is not implemented. Image loading supports uncompressed BMP only; 3D mesh textures, image compression, and sprite animation are not implemented. Physics supports up to 128 fixed-step 2D circles and axis-aligned boxes, including mixed-shape contacts and per-body Coulomb friction, but has no rotation, continuous collision detection, or broad phase. The networking sample is a bare LAN prototype, not a secure or reliable Internet multiplayer stack. Audio, 3D physics, a full editor, portability, and performance benchmarks are future work. “Hyper-efficient” is a design goal, not a measured result.

## Build an EXE

On Windows, install Python 3.11 or newer and Visual Studio 2022 Build Tools with the **Desktop development with C++** workload. MSVC is the verified compiler. Then run:

```powershell
python compiler/anvil.py examples/first_world.ANVL --release --generated-c build/first_world.c --output build/first_world.exe
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
python compiler/anvil.py examples/loops.ANVL --release --output build/loops.exe
python compiler/anvil.py examples/arrays.ANVL --release --output build/arrays.exe
python compiler/anvil.py examples/physics.ANVL --release --output build/physics.exe
python compiler/anvil.py examples/physics_boxes.ANVL --release --output build/physics_boxes.exe
python compiler/anvil.py examples/physics_friction.ANVL --release --output build/physics_friction.exe
python compiler/anvil.py examples/image_sprite.ANVL --release --output build/image_sprite.exe
```

This writes inspectable C and compiles it with MSVC. To only translate Anvil to C, add `--emit-c build/first_world.c`. The generated C is ordinary C, while the runtime currently targets Windows.

To try the experimental direct backend, only Python 3.11 or newer is required on Windows x64:

```powershell
python compiler/anvil.py examples/functions.ANVL --backend native --output build/functions-native.exe
python compiler/anvil.py examples/native_2d.ANVL --backend native --output build/native_2d.exe
./build/native_2d.exe
```

This backend writes x64 machine code and a PE32+ executable directly. In the native 2D sample, Left/Right move the panel, Space pauses the animated marker, and R resets its position. Left drag positions the panel, the wheel moves it horizontally, right click pauses, and middle click resets. Closing the window ends the program. Native rendering supports opaque rectangles in client pixels, with keyboard input and client-pixel mouse queries for pointer position, three buttons, and vertical wheel input. Other shapes, text, 3D, assets, physics, networking, remain unavailable on this path. See [the native compiler migration plan](docs/NATIVE_X64_COMPILER_MIGRATION.md) for its exact limits and status.

The direct backend also supports basic math, deterministic seeded integer random numbers, gradient noise and fBm. Build `examples/native_procedural.ANVL` with `--backend native` for terrain generated by an Anvil-written procedural runtime. Space or left click regenerates it. See the migration guide for numeric domains and remaining native limitations; package registries/binary plugins and Forge targets remain unfinished.

## Run checks

```powershell
python -m unittest discover -s tests -v
python scripts/validate_qa_report.py
npm ci --prefix vscode-extension
npm test --prefix vscode-extension
```

The numeric sample builds and prints `17`. The starter world builds into a native Windows executable. Run it to open the game window.

## Files

- [Language guide](docs/LANGUAGE.md)
- [Formal language specification](docs/LANGUAGE_SPEC.md)
- [Engine runtime](docs/ENGINE.md)
- [Completion matrix](docs/COMPLETION_MATRIX.md)
- [Audited implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Autonomous development progress](docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md)
- [Multiplayer prototype](docs/MULTIPLAYER.md)
- [Compiler and build](docs/COMPILER.md)
- [Starter world](examples/first_world.ANVL)
- [LAN counter sample](examples/network_counter.ANVL)
- [LAN client sample](examples/network_client.ANVL)
- [Numeric compiler sample](examples/numeric_demo.ANVL)
- [Function parameters and local variables sample](examples/functions.ANVL)
- [While and numeric for loop sample](examples/loops.ANVL)
- [Fixed-size arrays sample](examples/arrays.ANVL)
- [2D circle physics sample](examples/physics.ANVL)
- [2D boxes and mixed-shape physics sample](examples/physics_boxes.ANVL)
- [Mouse input sample](examples/mouse_input.ANVL)
- [BMP image sprite sample](examples/image_sprite.ANVL)
- [VS Code extension](vscode-extension/README.md)
- [Full improvement backlog](docs/IMPROVEMENT_BACKLOG.md)
- [Wiki pages](docs/Wiki/Home.md)
- [Contribution and bug reporting rules](CONTRIBUTING.md)

`.ANVL` is the source extension and `.ANVLproj` is the TOML project manifest. The compiler resolves the manifest's entry path within the project folder and applies its project name and fixed update rate. Anvil is a working project name; it has not had trademark clearance.

## Troubleshooting

- **No C compiler found:** install the Visual Studio Build Tools C++ workload, then rerun the command from a new PowerShell session.
- **Manifest entry is rejected:** use a path relative to `game.ANVLproj`; entries must stay inside that project folder.
- **VS Code validation cannot find a package:** run `npm ci --prefix vscode-extension` once, then rerun the validation command.

The `.ANVL` suffix is used here for Anvil source; the name also appears in an unrelated metadata serialization format, so the suffix is not globally unique.


Local multi-file source composition uses top-level `include "relative/library.ANVL"`. Both backends resolve the local include graph; the native backend compiles reachable functions and their runtime dependencies. See [include semantics and limits](docs/INCLUDES.md). Namespaces, package registries and separate object linking remain unfinished.

Native project builds accept `.ANVLproj` with `--backend native`. The existing `name` supplies the Unicode window title, `entry` resolves inside the project directory, and `[engine].fixed_hz` accepts integer rates1–240 (default60). Includes may span the project tree. Native graphical updates, `time()` and `delta()` use that rate. Direct source titles and console behavior retain their defaults. Unsupported native features fail explicitly without invoking C/Rust.
