# Anvil Native x64 Compiler Migration

## Required end state

The Anvil compiler parses and validates `.ANVL` itself, generates x86-64 machine code, and writes a Windows PE executable directly. It does not emit C or Rust source, invoke a C or Rust compiler, or route the engine runtime through a C/Rust shim.

The `.ANVL` source syntax and engine APIs remain Anvil-owned. Generated EXEs contain native code for the validated program and the Anvil runtime components it uses.

## Current state

An experimental direct backend is available with `python -m compiler.anvil <file.ANVL> --backend native --output <file.exe>`. It emits AMD64 instructions and PE32+ sections itself and imports only the Windows APIs it uses. Its supported subset includes simple functions with up to four numeric parameters, numeric local/global slots, fixed-size global numeric arrays with dynamic checked reads and writes, addition/subtraction/multiplication/division, comparisons, short-circuit `and`/`or`, `if`, `while`, inclusive ascending/descending `for` loops, and console output rounded to six fractional digits (trailing zeroes are removed). Array indices are evaluated once; negative, fractional, and out-of-range indices produce a line-numbered runtime diagnostic and exit code 2. Aggregate direct-native global data is capped at 16 MiB before PE payload allocation; declarations that exceed the limit fail with a source-located compiler diagnostic. Native integration tests exercise successful array reads/writes, index failures, and pre-allocation aggregate-limit rejection. The native backend has been executed on Windows without invoking a C or Rust compiler.

The direct backend now has an initial Windows 2D runtime: `scene 2d`, literal opaque `clear rgba`, top-level numeric initialization, `fn(draw)`, `display rect(...) -rgb(...)`, and optional `fn(update)` with `time()`, `delta()`, and `compute()`. Runtime instructions and the PE are emitted by Anvil; USER32/GDI32 functions are imported directly from Windows. No C/Rust source, compiler, linker, or runtime shim is used.

The regular build still defaults to the C backend. The native backend does **not** yet support function-local arrays, the full language, project manifests, other shapes, text, alpha blending, 3D, assets, audio, input, physics, noise, or networking. Full no-C engine parity remains unfinished.

## Native 2D scene

```powershell
python -m compiler.anvil examples/native_2d.ANVL --backend native --output build/native_2d.exe
./build/native_2d.exe
```

The window has a 960×640 outer size initially and a resizable client area. Coordinates are client pixels; rectangles clip to that area, with floor/ceil edges matching the existing rectangle contract. The background and `fn(draw)` repaint on exposure, resize, and simulation updates. Each rectangle uses a Windows brush that is deleted after drawing. Closing the window ends the message loop and releases the background brush. There is no interpolation or double buffering in this first backend.

If `fn(update)` exists, it takes no parameters and advances at fixed 1/60-second simulation steps. A 10 ms Windows timer wakes the event loop; elapsed time is accumulated to determine the number of updates. At most 250 ms of elapsed time is accepted per wake after a stall. `delta()` is 1/60 and `time()` is elapsed simulation time. `time()` in a draw-only scene also enables the clock; a static scene without update/time waits for Windows messages without a polling loop. `compute(expression)` is supported in both console and graphical native programs. Built-ins for input and all other runtime systems remain unsupported.

The clear colour currently requires four literal 0–255 channels and alpha 255. Rectangles accept numeric coordinate/colour expressions, `-rgb(r,g,b)`, or `-rgba(r,g,b,255)`; other opacity values and modifiers produce compiler diagnostics. Unsupported native graphics fail explicitly instead of falling back to the C backend.

`tests/test_native_window.py` executes an emitted EXE, inspects actual client pixels for colour, clipped and fractional edges, verifies timer-driven movement and erasure, resizes the window, and closes it with exit code 0. It also checks rejected constructs. These tests require an interactive Windows desktop. Windows painting follows the [BeginPaint/EndPaint lifecycle](https://learn.microsoft.com/en-us/windows/win32/gdi/drawing-in-the-client-area), and scheduling uses [window timers](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-settimer).

## Troubleshooting the direct backend

| Symptom | Action |
|---|---|
| C compiler is requested | Select `--backend native`; the current default is still C. |
| Unsupported native shape, opacity, or built-in | Use the documented native subset and check the source-line compiler diagnostic. Unsupported features do not silently use another backend. |
| `native scene 2d requires fn(draw)` | Define `fn(draw)` with no parameters. An optional `fn(update)` also takes no parameters. |
| Native data exceeds 16 MiB | Reduce global array/storage requirements; runtime metadata also uses native program data. |
| Output EXE cannot be overwritten | Close the running generated window, then rebuild. |
| GUI test cannot read window pixels | Run it in an interactive Windows x64 desktop; it samples a visible test window and closes that process afterward. |

## Architecture

1. Preserve the custom Anvil lexer, parser, semantic checks, and source-located diagnostics.
2. Lower the validated syntax tree to a small typed Anvil intermediate representation.
3. Generate x86-64 machine code with an Anvil-owned instruction encoder, label/fixup system, stack-frame layout, and calling convention.
4. Write a PE32+ executable with an Anvil-owned PE image writer. Use only explicit Windows API imports needed by each program.
5. Port engine runtime components to native x64 code emitted by the Anvil backend. No generated EXE may depend on a C/Rust runtime shim.
6. Migrate language and engine features in tested batches. The old C path is removed only after equivalent native behavior and tests exist.

## Rollout sequence

1. Machine-code and PE writer primitives; emit a minimal console EXE and verify it runs. **Implemented.**
2. Arithmetic, checked numeric operations, functions, branches, and loops. **Partially implemented:** arithmetic, simple function calls, `if`, and `while` work; complete numeric diagnostics and language parity remain outstanding.
3. Global slots and fixed-size global arrays, including checked indexing. **Partially implemented:** global slots and global arrays now compile directly; function-local heap arrays and their allocation/lifetime rules remain.
4. Native input, window lifecycle, 2D drawing, and image resources. **Partially implemented:** window lifecycle, fixed updates, time/delta, background clearing, and opaque rectangles work; remaining shapes, input and image resources are outstanding.
5. Camera, 3D primitives, BVH ray tracing, physics, procedural noise, and networking.
6. Switch the default build to the direct x64/PE backend, port regression coverage, then remove C generation and MSVC-specific compiler invocation.

## Acceptance checks

- The experimental `--backend native` path generates a PE32+ `.exe` directly from Anvil-owned machine-code and PE-writing modules.
- It does not generate C/Rust source and does not invoke a C/Rust compiler or linker.
- Windows runs the produced executable; its imports are limited to documented system APIs and its own generated runtime.
- Function calls, numeric semantics, arrays, diagnostics, and supported engine APIs match the language specification.
- Native regression tests cover code generation, PE metadata/fixups, execution, resource lifetime, and engine behavior.
- Documentation and evaluation reports distinguish implemented native features from migration work still in progress.

The latest completed independent review evaluated `2b0a7b113cd7eb9d4b6a4e82bb4faae7aa59b505` at 64/100, below 98. The new window-runtime candidate awaits a fresh review; its implementation evidence does not change that score. Full engine migration and the Forge format/target work remain unfinished. See `docs/ANVIL_EVALUATION.txt`.
