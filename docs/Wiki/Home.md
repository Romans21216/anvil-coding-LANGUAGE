# Anvil Wiki

Anvil is a small BASIC/Lua-inspired game language using `.ANVL` source files. Its current Windows compiler validates Anvil source, emits ordinary C, and invokes MSVC to create a native `.exe`.

## Start here

- [Getting Started](Getting-Started.md): install the current Windows toolchain and build a sample.
- [Language Reference](Language-Reference.md): functions, expressions, scope, drawing, and built-ins.
- [Engine Runtime](Engine-Runtime.md): rendering, camera controls, timing, and ray tracing.
- [Compiler and Build](Compiler-and-Build.md): project files, C generation, and native builds.
- [Multiplayer](Multiplayer.md): the experimental UDP host/client API and its limits.
- [Roadmap](Roadmap.md): what works and the full improvement backlog.
- [Bug Reporting](Bug-Reporting.md): reproduction details and issue naming/labels.

## Current implementation

Working features include numeric global variables, fixed-size checked numeric arrays, parameterized functions, numeric return values, function-local numeric state, branches, `while` and inclusive numeric `for` loops, recursion, 2D and basic 3D drawing, keyboard input, camera movement, time, deterministic random/noise helpers, CPU BVH ray-traced spheres, and a one-peer UDP numeric prototype.

The implementation is a prototype, not a complete engine. It currently targets Windows/MSVC, uses a fixed-size software rasterizer, supports up to 32 ray-traced spheres per batch, and has no GPU/DXR or Embree backend. The network API is not suitable for public Internet games.

