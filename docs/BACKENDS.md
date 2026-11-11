# Backend capability matrix

Two backends compile `.ANVL`:

- **C** (default): emits C, links `runtime/anvil_runtime.c` with MSVC.
- **native**: emits an AMD64 PE directly (`--backend native`), no C toolchain.

Every row marked "both" is covered by tests that compile and run the same
program on both backends and compare stdout (see `tests/` and
`scripts/differential_probe.py`). A row marked "C only" is a documented,
source-located limitation on the native backend — the compiler rejects it with a
message rather than mis-compiling.

| Feature | C | native | Evidence |
|---|---|---|---|
| Functions, numeric parameters (up to 16), returns | yes | yes | `test_native_x64.py`, `test_compiler.py` |
| Recursion | yes | yes | `test_break_continue.py`, `test_native_x64.py` |
| Text values, `&` joining, escapes | yes | yes | `test_strings.py`, `test_native_x64.py` |
| Text builtins (`len`, `upper`, `lower`, `trim`, `left`, `right`, `char`, `mid`, `chr`, `ord`, `number`, `contains`, `starts_with`, `ends_with`) | yes | yes | `test_len.py`, `test_mid.py`, `test_trim.py`, `test_number.py`, `test_char.py`, `test_chrorrd.py`, `test_contains.py`, `test_edges.py` |
| Text-returning functions | yes | yes | `test_text_functions.py` |
| Text arguments to functions | yes | yes | `tests/test_text_params.py` |
| Numeric globals, `set`/`add`/`sub`, top-level init | yes | yes | `test_native_x64.py` |
| Fixed-size arrays (global and function-local) | yes | yes | `test_native_x64.py`, `test_lists.py` |
| Growable lists (`list`/`add`/`count`/`array`) | yes | yes | `test_lists.py` |
| `say` / `write` / `ask` / `press enter` / `wait` / `stop` | yes | yes | `test_say.py`, `test_ask.py`, `test_press_enter.py`, `test_wait.py`, `test_stop.py` |
| `break` / `continue` in `for`/`while`/`repeat` | yes | yes | `test_break_continue.py` |
| `seed` / `rnd` / `noise` / `fbm` | yes | yes | `test_native_procedural.py` |
| Math builtins and `%` | yes | yes | `test_round.py`, `test_mod.py`, `test_native_trig.py` |
| Source `include` (with reachability) | yes | yes | `test_includes.py`, `test_deadcode.py` |
| Unreachable-function elimination | yes | yes | `test_deadcode.py` |
| Located compile and runtime diagnostics, exit 1/2 contract | yes | yes | `test_diagnostics.py`, `test_native_x64.py` |
| REPL (`--repl`) and `--hello` | yes | yes | `test_repl.py` |
| 2D engine: `scene 2d`, `fn(draw)`, `fn(update)`, `display rect`, keyboard, mouse, `time`/`delta`/`compute` | yes | yes (rectangles only) | `test_native_window.py`, `test_native_keyboard.py`, `test_native_mouse.py` |
| Engine: images, physics, ray backend, 3D shapes, `.ANVLproj` manifests | yes | **no** | native rejects with "not available in the native x64 backend yet" |
| Networking (`net host`/`net join`/`send`/`receive`) | yes | **no** | native rejects at top level |
| Console number printing | to ~1e63 | to 9.2e18 (then a range error) | `test_number_format.py` |

## Native-only limits (all source-located compile errors)

| Limit | Value | Message |
|---|---|---|
| Parameters per function | 16 | `native backend supports at most sixteen parameters` |
| Function frame | 4096 bytes | `native function frame exceeds 4096 bytes` |
| Local arrays per function | 4096 bytes of stack | `native local arrays are limited to 4096 bytes per function` |
| Expression nesting | 64 | `expression nesting exceeds 64 levels` |
| Aggregate global data | 16 MiB | `native aggregate data exceeds the 16 MiB limit` |

## Regenerating the evidence

```powershell
python scripts/differential_probe.py     # same program on both backends, diffs stdout
python -m pytest tests -q                # full suite
python tools/grade_anvil.py              # beginner scorecard
```
