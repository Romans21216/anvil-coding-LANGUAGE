# Part 8 evidence ledger

This ledger maps each Part 8 section to what is actually verified in this
checkout today, the exact commits and commands that prove it, and the gap that
remains. A row is only marked verified when a command below was run on this
tree. It complements `docs/CAPABILITY_MATRIX.md` (measured backend behaviour)
and `docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md` (batch history).

Run the whole suite with `python -m pytest tests -q`; see `docs/TESTING.md`
for the headless/interactive split and the recorded environment.

| Section | Status | Evidence | Remaining gap |
| --- | --- | --- | --- |
| 8.8 Language contract | Verified for numbers, text, enums and control flow | `fdb6344`, `e6513b4`: whole-text `number(text)`, `chr(0)` contract, native mantissa/exponent parity; `c8f7c76` closest-name suggestions on unknown functions and variables; `f6b2b1e`/`7a05bd9` stable codes for ten common errors with `--explain`; cross-backend tests in `tests/test_number.py`, `tests/test_mid.py`, `tests/test_chrorrd.py`; `tools/capability_matrix.py` runs enums, lists, arrays, loops, recursion on both backends | Records/structures, general text variables beyond the current model |
| 8.9 Ownership and budgets | Verified for the existing resources | Local arrays capped at 8,192 elements and 16 MiB active (`tests/test_compiler.py`); calls capped at a 512 KiB stack budget on both backends (`tests/test_recursion_budget.py`, `6f0f3e8`, `506664d`); image caps (8,192 px/side, 16.7 Mpx, 128 MiB) enforced with a named `image_error()` reason per limit (`tests/test_image_limits.py`, `e4de27d`), plus missing-file diagnostics (`tests/test_image_error.py`) | No general allocator auditing or leak instrumentation |
| 8.10 Compiler and build loop | Verified | `dd40769` staging output; `40bf89d` cache key covers every runtime header plus compiler identity; `d1e56b9` keys on compiler contents, the linker and the SDK (C8-9/C8-10); `_sdk_fingerprint` hashes every SDK file and the environment cache is keyed by script contents (C8-11/C8-12); `0b0130d` `--no-cache`; `a24a071` 4 MiB entry budget; `--check` runs backend lowering; `--print-imports`; `--doctor`; `2fe1008` idempotent native guard; `a896281` warns when an unused function calls an unknown one; `test_opt_parity` compares release, debug and native results | No source-level debugger or source maps; diagnostics carry a line and caret by default and a 1-based column under `--diagnostics editor` (`50bb070`) |
| 8.11 Window loop and flicker | Partial | Buffered presentation with visible-pixel checks, rapid resize, GDI-count checks, minimize/restore repaint, close, injected backbuffer-allocation failure, and `window_on_top`/`window_fullscreen` verified against live Win32 styles and rectangle (`tests/test_native_window.py`); keyboard/mouse edge state (`test_native_keyboard`, `test_native_mouse`) | Occlusion and DPI changes are not covered; no manual visual run this session |
| 8.12 Browser target | Not implemented | Repository search finds no WASM/Emscripten target; README describes the desktop editor as a preview workbench | Whole target: WASM ABI, canvas/WebGL, input, audio, storage |
| 8.13 3D content pipeline | Partial | `scene 3d`, perspective camera, plane/cube/sphere and `ray_sphere` with CPU BVH and a 32-sphere batch; `examples/first_world.ANVL` builds and is run interactively (not automated) | No glTF import, animation, shadows, culling/batching or GPU path |
| 8.14 2D, audio, physics, network, packaging | Partial, commands complete | BMP sprite builtins with documented limits and source-located errors (`tests/test_image_error.py`, `tests/test_compiler.py`); no boundary tests for the size caps; 2D physics with restitution and friction (`tests/test_compiler.py`); UDP double transport with malformed-packet fuzzing (`tests/test_net_fuzz.py`, `031bfb0`); `--package` with dry run, asset validation and hashed manifest (`79d8af3`); `new`/`run`/`build`/`test`/`format`/`clean`/`doctor`/`package` all exist (`75a4805`, `5967fdb`, `44dcd1b`) | Audio and saves are absent; no atlas, rotation or camera systems; transport is one-peer unauthenticated UDP |
| 8.15 Testing, security, efficiency | Partial | `docs/TESTING.md` labels 91 headless/interactive modules; packet fuzzing; capability matrix under test; per-line output flush (`tests/test_output_flush.py`); recursion bound; package asset validation | Measured with `--timings`: parse+generate ~3 ms, cold C build 413 ms after the toolset environment is cached (`1148433`), cache hit 41 ms; thresholds still not enforced in CI; Windows x64 only |
| 8.16 Delivery order and evidence | This ledger plus generated matrix | `docs/CAPABILITY_MATRIX.md` (12 of 14 cases identical across backends), `docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md` batches 14–22, commit list below | Browser and 3D rows remain open before the delivery order can complete |
| 8.17 New-user trial | Partially automated | `tests/test_first_hour.py` runs the documented path end to end: `--new`, `--check`, build with `--timings`, run, `--format`, `--package-dry-run`, `--package`, `--doctor`, `--explain` | Watching a real new programmer and recording pauses and repairs is still outstanding |

## Commit index for this evidence

- `fdb6344` cross-backend number and text-slice parity (C8-1/C8-3/C8-5)
- `214e200` bounded noise coordinates (C8-7)
- `40bf89d` cache key covers runtime headers and compiler identity (C8-6)
- `e6513b4` native number parser matches the C grammar (C8-2/C8-4/C8-8)
- `dd40769` staging build output
- `0b0130d` `--no-cache`
- `a24a071` oversized entry source rejected before reading
- `6f0f3e8`, `506664d` bounded call depth on both backends
- `79d8af3` packaging with dry run and manifest
- `75a4805` `--run`, `--clean`, `--doctor`, `--new`
- `5967fdb` `--format` and `--format-check`
- `44dcd1b` `--test` project runner
- `8997af2` testing and coverage labels
- `1afefc5` measured capability matrix
- `2fe1008` single-emission native frame guard
- `031bfb0`, `fafc438` non-finite network payloads ignored; per-line `say` flush
- `e4de27d` image load failures name the exact limit
- `d1e56b9` cache identity hashes cl.exe, link.exe and the SDK (C8-9/C8-10)
- `c8f7c76`, `fbf87ee` did-you-mean suggestions on both backends
- `a896281` unused-function typo warning
- `50bb070` `--diagnostics editor` prints file:line:column
- `1148433` cached toolset environment makes cold builds ~4x faster
- `f6b2b1e` stable diagnostic codes + generated `docs/ERRORS.md`
- `7a05bd9` `--explain CODE`
- `25ac3ab` `window_on_top` / `window_fullscreen` with live-state tests

## How to re-check

```bash
python -m pytest tests -q
python tools/capability_matrix.py --check
python compiler/anvil.py --doctor
python compiler/anvil.py game.ANVLproj --test
python compiler/anvil.py examples/first_world.ANVL --check
```

The full-suite count changes as tests land; the latest recorded run is in
`docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md`.
