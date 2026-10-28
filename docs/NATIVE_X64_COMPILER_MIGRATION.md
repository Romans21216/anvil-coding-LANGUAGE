# Anvil Native x64 Compiler Migration

## Required end state

The Anvil compiler parses and validates `.ANVL` itself, generates x86-64 machine code, and writes a Windows PE executable directly. It does not emit C or Rust source, invoke a C or Rust compiler, or route the engine runtime through a C/Rust shim.

The `.ANVL` source syntax and engine APIs remain Anvil-owned. Generated EXEs contain native code for the validated program and the Anvil runtime components it uses.

## Current state

An experimental direct backend is available with `python -m compiler.anvil <file.ANVL> --backend native --output <file.exe>`. It emits AMD64 instructions and PE32+ sections itself and imports only the Windows APIs it uses. Its supported subset includes simple functions with up to sixteen numeric parameters, numeric local/global slots, fixed-size global numeric arrays with dynamic checked reads and writes, addition/subtraction/multiplication/division, comparisons, short-circuit `and`/`or`, `if`, `while`, inclusive ascending/descending `for` loops, and console output rounded to six fractional digits (trailing zeroes are removed). Array indices are evaluated once; negative, fractional, and out-of-range indices produce a line-numbered runtime diagnostic and exit code 2. Aggregate direct-native global data is capped at 16 MiB before PE payload allocation; declarations that exceed the limit fail with a source-located compiler diagnostic. Native integration tests exercise successful array reads/writes, index failures, and pre-allocation aggregate-limit rejection. The native backend has been executed on Windows without invoking a C or Rust compiler.

The direct backend now has an initial Windows 2D runtime: `scene 2d`, literal opaque `clear rgba`, top-level numeric initialization, `fn(draw)`, `display rect(...) -rgb(...)`, and optional `fn(update)` with `time()`, `delta()`, `compute()`, `held(key)`, `pressed(key)` and the mouse queries below. Runtime instructions and the PE are emitted by Anvil; USER32/GDI32 functions are imported directly from Windows. No C/Rust source, compiler, linker, or runtime shim is used.

The regular build still defaults to the C backend. The native backend does **not** yet support the full language, other shapes, text, alpha blending, 3D, assets, audio, physics, trigonometry, or networking. Full no-C engine parity remains unfinished.

## Native 2D scene

```powershell
python -m compiler.anvil examples/native_2d.ANVL --backend native --output build/native_2d.exe
./build/native_2d.exe
```

The window has a 960×640 outer size initially and a resizable client area. Coordinates are client pixels; rectangles clip to that area, with floor/ceil edges matching the existing rectangle contract. The background and `fn(draw)` compose into a persistent compatible bitmap/DC on exposure, resize, and simulation updates; one BitBlt copies the completed frame to the visible paint DC. The bitmap is replaced only when the client dimensions change. Empty/minimized clients skip allocation/presentation. Background erasure is handled by the composed frame. Each rectangle brush is deleted after drawing, and shutdown restores the stock bitmap before deleting the owned bitmap/DC. Backbuffer allocation/presentation errors pair EndPaint and release resources before reporting a controlled error. Interpolation remains absent.

If `fn(update)` exists, it takes no parameters and advances at configured simulation steps (60 Hz by default). A 10 ms Windows timer wakes the event loop; elapsed time is accumulated to determine the number of updates. At most 250 ms of elapsed time is accepted per wake after a stall. `delta()` is 1/fixed_hz and `time()` is elapsed simulation time. `time()` or keyboard/mouse queries in a draw-only scene also enable the clock; a static scene without update/time/input waits for Windows messages without a polling loop. `compute(expression)` is supported in both console and graphical native programs. Other runtime systems remain unsupported.

The clear colour currently requires four literal 0–255 channels and alpha 255. Rectangles accept numeric coordinate/colour expressions, `-rgb(r,g,b)`, or `-rgba(r,g,b,255)`; other opacity values and modifiers produce compiler diagnostics. Unsupported native graphics fail explicitly instead of falling back to the C backend.

`tests/test_native_window.py` executes an emitted EXE, inspects actual client pixels for colour, clipped and fractional edges, verifies timer-driven movement and erasure, resizes the window, and closes it with exit code 0. It also checks rejected constructs. These tests require an interactive Windows desktop. Windows painting follows the [BeginPaint/EndPaint lifecycle](https://learn.microsoft.com/en-us/windows/win32/gdi/drawing-in-the-client-area), and scheduling uses [window timers](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-settimer).

## Native keyboard input

`held(key)` returns 1 until release or focus loss. `pressed(key)` is an edge retained through the next fixed update, then cleared after that callback. Multiple reads in the same update see the same edge. Auto-repeat does not generate another edge while held, and a down/up tap between updates is retained. A draw-only scene observes the edge in its next draw, then clears it. Focus loss clears held and pending edge state. System-key messages also update state and continue to DefWindowProc so standard Windows shortcuts retain their default behavior.

Keys use shared named constants `A`–`Z`, `SPACE`, `LEFT`, `RIGHT`, `UP`, `DOWN`, `ENTER`, and `ESCAPE`, or numeric virtual-key codes. Numeric query arguments are evaluated once and truncated toward zero; out-of-range codes return false. The constants are also numeric values in native console programs. Keyboard queries require a native 2D scene and one numeric argument.

The compiler emits the keyboard state/helpers only when a query is used; state uses two 256-byte tables. It receives window-local messages and does not poll global keyboard state or add a separate DLL dependency. This is internal native-runtime feature selection, not the planned general include/plugin packaging system. `tests/test_native_keyboard.py` sends bounded messages directly to the generated test window and checks real compiled globals for edges, held/release, repeats, focus loss, short taps, draw-only behavior, invalid codes, and one-time expression evaluation; it never sends global keyboard input. Win32 handling follows [Microsoft's keyboard message contract](https://learn.microsoft.com/en-us/windows/win32/inputdev/about-keyboard-input).

## Native mouse input

`mouse_x()` and `mouse_y()` return client-pixel coordinates, matching native rectangles. Both return `-1` before any position message, outside the client bounds, after a mouse-leave message, or on focus loss/cancellation. Bounds are checked against the current client rectangle, including after resize. This differs from the broader C renderer's fixed 960×600 virtual viewport.

`mouse_held("left")`, `mouse_held("right")`, and `mouse_held("middle")` report button-down state. `mouse_pressed(...)` exposes a pending down transition throughout the next fixed update, then clears it. Repeated down messages do not create new edges; a short down/up tap survives until the next update. In draw-only scenes, the next draw consumes edges. Buttons require a literal string (case-insensitive); unsupported names and nonliteral arguments produce source-line diagnostics. General native string values remain unsupported.

`mouse_wheel()` accumulates signed vertical wheel detents, including fractional detents, for the same update/draw interval. Repeated queries in that interval see the same value. Horizontal wheel input is not implemented. Focus loss and cancellation clear buttons, pending edges, wheel and position. Capture transfer clears held buttons while retaining pending taps. Mouse-down captures input to the owning window for outside-client drag/release; the last button release relinquishes capture if still owned by that window.

Mouse state, handlers and the additional system imports are emitted only when a mouse query is used. `tests/test_native_mouse.py` runs real emitted PE windows and tests signed/outside coordinates, resized client bounds, all three buttons, repeats, taps, actual OS capture ownership, simultaneous buttons, focus/capture/cancel clearing, fractional wheel accumulation, draw-only consumption and invalid source diagnostics. Tests send messages only to their own generated window and never inject global pointer input. The coordinate test uses an explicit test-only PE wrapper to dispatch its message and sample coordinate queries synchronously, avoiding races with unrelated posted mouse messages (#62). It executes the original production handler/query code; ordinary generated applications contain no test hook. Win32 behavior follows [Microsoft's mouse input contract](https://learn.microsoft.com/en-us/windows/win32/inputdev/using-mouse-input).

The native2D example supports left drag, wheel movement, right-click pause, middle-click reset, a pointer marker and the existing keyboard controls. Mouse execution evidence and its remaining coordinate-dispatch coverage limit are recorded in [QA_REPORT.md](QA_REPORT.md).

## Native math and procedural runtime

The direct backend implements `abs(x)`, `sqrt(x)`, `floor(x)`, `ceil(x)`, `min(a,b)`, `max(a,b)`, `rnd(a,b)`, `noise(x,y,z)` and `fbm(x,y,z,octaves,lacunarity,gain)`. Arguments evaluate once in source order. `sqrt` of a negative value and non-finite arithmetic report a numeric error and exit with code 2. Floor/ceil support all finite binary64 values, including magnitudes too large for signed integer conversion. Native `sin`/`cos` remain unsupported.

`seed(value)` works at top level and in functions. It truncates a nonnegative finite value below 2^64 to an unsigned seed. Zero selects the fixed default seed. `rnd(a,b)` swaps reversed bounds, rounds the lower bound upward and upper bound downward, and returns an inclusive integer using xorshift64* with the same generator/mapping as the existing runtime. If the rounded upper bound is at or below the lower bound, it returns the lower bound without advancing the generator. Bounds must be within ±(2^53−1), the exact binary64 integer range; invalid ranges terminate with a diagnostic rather than invoking an undefined integer conversion. This generator is deterministic and not cryptographic; modulo mapping has a small statistical bias for spans that do not divide 2^64.

`noise` uses deterministic three-dimensional gradient noise with quintic interpolation and a fixed 32-bit hash, matching the existing C runtime on valid coordinates. It is independent of `seed`. Coordinates must be at least −2147483648 and below 2147483647, so the two lattice corners fit signed 32-bit integers. Invalid coordinates exit with a diagnostic. `fbm` combines up to sixteen noise octaves, truncating/clamping the octave count to 0..16, starting amplitude at 0.5 and normalizing by accumulated amplitude. Zero octaves or zero normalization returns zero. Every sampled octave obeys noise bounds; intermediate non-finite arithmetic fails in a controlled way. Diagnostics inside the Anvil procedural library refer to its runtime operations rather than implying an unsupported input succeeded.

Gradient selection, fade, interpolation, noise and fBm are written in [Anvil runtime source](../runtime/native/procedural.ANVL). Only requested routines and their dependencies are compiled into the PE. Numeric primitives, integer hash and RNG state transitions use Anvil-owned machine-code emission. This is a built-in runtime library. Local source `include` composition is described in [INCLUDES.md](INCLUDES.md); package registries and binary plugins remain unfinished. A program using only `sqrt` does not bundle the noise library. The native function prefix `_anvil_native_` is reserved and the private hash intrinsic cannot be called by user code.

Calls pass the first four numeric arguments in XMM0–3 and later arguments in aligned Win64 stack slots. Up to sixteen arguments are supported within the existing sixteen-temporary expression budget. Scalar locals and compiler temporaries now support disp32 offsets. Each function frame is limited to 4096 bytes with a compiler diagnostic above that limit; unbounded recursion remains unsupported. The frame limit avoids silently permitting large unprobed Win64 allocations while broader stack-budget work is pending.

Build `examples/native_procedural.ANVL` with `--backend native` for generated terrain. Space or left click regenerates it from a new seed. Generated-PE tests cover reference noise/fBm values, RNG sequence/reseeding, math domains, nested argument side effects, sixteen-argument calls, large local offsets, library selection, and graphical use. Independent review of3270998 passed111tests and scored72/100; explicit-main/Wiki/test-race corrections are verified, while untouched coordinate OS-dispatch coverage remains partial (#63).

## Troubleshooting the direct backend

| Symptom | Action |
|---|---|
| C compiler is requested | Select `--backend native`; the current default is still C. |
| Unsupported native shape, opacity, or built-in | Use the documented native subset and check the source-line compiler diagnostic. Unsupported features do not silently use another backend. |
| `native scene 2d requires fn(draw)` | Define `fn(draw)` with no parameters. An optional `fn(update)` also takes no parameters. |
| Native data exceeds 16 MiB | Reduce global array/storage requirements; runtime metadata also uses native program data. |
| Output EXE cannot be overwritten | Close the running generated window, then rebuild. |
| GUI test cannot read window pixels | Run it in an interactive Windows x64 desktop; it samples a visible test window and closes that process afterward. |
| Native seed/random/noise range error | Use the numeric ranges above; reduce fBm coordinates/lacunarity if later octaves exceed the lattice range. |
| Native function frame exceeds 4096 bytes | Split large scalar-local functions into smaller functions; local array elements use heap storage; general stack budgets are still pending. |
| Older native sample flickers | Rebuild with the buffered-presentation fix for issue #57. The regression checks visible pixels during slow drawing and verifies that the old unbuffered implementation fails that check. |

## Architecture

1. Preserve the custom Anvil lexer, parser, semantic checks, and source-located diagnostics.
2. Lower the validated syntax tree to a small typed Anvil intermediate representation.
3. Generate x86-64 machine code with an Anvil-owned instruction encoder, label/fixup system, stack-frame layout, and calling convention.
4. Write a PE32+ executable with an Anvil-owned PE image writer. Use only explicit Windows API imports needed by each program.
5. Port engine runtime components to native x64 code emitted by the Anvil backend. No generated EXE may depend on a C/Rust runtime shim.
6. Migrate language and engine features in tested batches. The old C path is removed only after equivalent native behavior and tests exist.

## Rollout sequence

1. Machine-code and PE writer primitives; emit a minimal console EXE and verify it runs. **Implemented.**
2. Arithmetic, checked numeric operations, functions, branches, and loops. **Partially implemented:** checked numeric operations, functions with sixteen arguments, branches and numeric loops work; full language parity remains outstanding.
3. Global slots and fixed-size global/local arrays with checked indexing. **Implemented within documented bounds:** per-call zeroed heap storage, cleanup and active allocation budget are verified.
4. Native input, window lifecycle, 2D drawing, and image resources. **Partially implemented:** window lifecycle, fixed updates, time/delta, keyboard held/edge input, background clearing, and buffered opaque rectangles work; mouse input is independently verified; remaining shapes and image resources are outstanding.
5. Camera, 3D primitives, BVH ray tracing, physics, procedural noise, and networking.
6. Switch the default build to the direct x64/PE backend, port regression coverage, then remove C generation and MSVC-specific compiler invocation.

## Acceptance checks

- The experimental `--backend native` path generates a PE32+ `.exe` directly from Anvil-owned machine-code and PE-writing modules.
- It does not generate C/Rust source and does not invoke a C/Rust compiler or linker.
- Windows runs the produced executable; its imports are limited to documented system APIs and its own generated runtime.
- Function calls, numeric semantics, arrays, diagnostics, and supported engine APIs match the language specification.
- Native regression tests cover code generation, PE metadata/fixups, execution, resource lifetime, and engine behavior.
- Documentation and evaluation reports distinguish implemented native features from migration work still in progress.

Local source includes preserve physical source locations and select reachable native functions. Runtime numeric/index diagnostics use pooled UTF-8 source paths. See [include semantics and limits](INCLUDES.md). Expression processing has a 64-level budget and statement nesting a 128-block limit; [troubleshooting](INCLUDES.md#compiler-depth-limits-and-troubleshooting) explains how to split larger expressions/functions.

Current exact review identifiers, scores, findings and verified fixes are maintained in [QA_REPORT.md](QA_REPORT.md) and [structured state](CODEX_AUTONOMOUS_STATE.json). The full engine/Forge/OS migration remains active. Coordinate integration uses test instrumentation and retains the untouched-dispatch gap #63. Current findings, verified corrections and exact review snapshots are linked from the QA report; this guide records feature contracts rather than live scores.

Native project builds accept `.ANVLproj` with `--backend native`. The existing `name` supplies the Unicode window title, `entry` resolves inside the project directory, and `[engine].fixed_hz` accepts integer rates1–240 (default60). Includes may span the project tree. Native graphical updates, `time()` and `delta()` use that rate. Direct source titles and console behavior retain their defaults. Unsupported native features fail explicitly without invoking C/Rust.

## Native local arrays

Function-local `array name(size)` declarations now use one zeroed process-heap block per invocation. They shadow global arrays of the same name. Every explicit return and implicit zero return releases the block, preserving the numeric result. Up to8,192 elements per function and16MiB of active element storage across calls are permitted; allocator overhead and scalar stacks are outside that element budget. Budget/allocation/release errors report the function source path/entry line and exit2. Index errors retain the access location. This uses direct Windows HeapAlloc/HeapFree calls, with no C/Rust shim. Unused array functions do not add heap imports. Arrays cannot escape a function or be passed as pointers.

`python -m compiler.anvil examples/local_arrays.ANVL --backend native --output build/local_arrays_native.exe` builds the existing example; it prints27. A new native_arrays module owns allocation/lifetime emission, and a frame-relative integer/pointer encoder helper supports it. This implementation has local regression tests; exact independent evaluation status is recorded in the QA report. The latest full review remains identified in QA_REPORT.md.
