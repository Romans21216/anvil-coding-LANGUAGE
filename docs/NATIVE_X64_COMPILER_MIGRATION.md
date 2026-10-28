# Anvil Native x64 Compiler Migration

## Required end state

The Anvil compiler parses and validates `.ANVL` itself, generates x86-64 machine code, and writes a Windows PE executable directly. It does not emit C or Rust source, invoke a C or Rust compiler, or route the engine runtime through a C/Rust shim.

The `.ANVL` source syntax and engine APIs remain Anvil-owned. Generated EXEs contain native code for the validated program and the Anvil runtime components it uses.

## Current state

An experimental direct backend is available with `python -m compiler.anvil <file.ANVL> --backend native --output <file.exe>`. It emits AMD64 instructions and PE32+ sections itself and imports only the Windows APIs it uses. It currently compiles a narrow numeric subset: simple functions with up to four numeric parameters, numeric local/global slots, addition/subtraction/multiplication/division, comparisons, short-circuit `and`/`or`, `if`, `while`, inclusive ascending/descending `for` loops, and console output rounded to six fractional digits (trailing zeroes are removed). Independent review of commit `f330d4b` verified the six-place output formatting and closed issue #49; issue #52 tracks the remaining large-value range defect. The native backend has been executed on Windows with language samples, without invoking a C or Rust compiler.

The regular build still defaults to the existing C backend. The native backend does **not** yet support the full language, project manifests, arrays, engine APIs, or graphics/audio/input/networking runtime. In particular, its executable is not yet a game-engine runtime. The current C path remains until native behavior reaches parity; no claim should say the full no-C requirement is complete.

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
3. Globals, fixed arrays, function-local heap arrays, and their bounds/allocation rules.
4. Native input, window lifecycle, 2D drawing, and image resources.
5. Camera, 3D primitives, BVH ray tracing, physics, procedural noise, and networking.
6. Switch the default build to the direct x64/PE backend, port regression coverage, then remove C generation and MSVC-specific compiler invocation.

## Acceptance checks

- The experimental `--backend native` path generates a PE32+ `.exe` directly from Anvil-owned machine-code and PE-writing modules.
- It does not generate C/Rust source and does not invoke a C/Rust compiler or linker.
- Windows runs the produced executable; its imports are limited to documented system APIs and its own generated runtime.
- Function calls, numeric semantics, arrays, diagnostics, and supported engine APIs match the language specification.
- Native regression tests cover code generation, PE metadata/fixups, execution, resource lifetime, and engine behavior.
- Documentation and evaluation reports distinguish implemented native features from migration work still in progress.

The direct-native candidate `ade1ff6b434b6c66d67a155320dc538ff2eb6ac3` was independently scored 56/100, below the required 98/100. All 88 tests passed. Issue #49 is fixed and #52 has a controlled range guard. The review filed #53 for rejecting the signed minimum and #54 for non-finite arithmetic that exits without a diagnostic. The current unreviewed candidate formats the minimum and emits a line-numbered error for non-finite math; the full suite passes 89 tests locally. The native engine runtime is incomplete, and the C backend remains the default pending feature parity; Rust output is not a target. See `docs/ANVIL_EVALUATION.txt`.
