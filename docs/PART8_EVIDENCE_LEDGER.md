# Part 8 evidence ledger

This ledger maps each Part 8 section to what is actually verified in this
checkout today, the exact commits and commands that prove it, and the gap that
remains. A row is only marked verified when a command below was run on this
tree. It complements `docs/CAPABILITY_MATRIX.md` (measured backend behaviour)
and preserves `docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md` as the chronological batch history.

Run the whole suite with `python -m pytest tests -q`; see `docs/TESTING.md`
for the headless/interactive split and the recorded environment.

| Section | Status | Evidence | Remaining gap |
| --- | --- | --- | --- |
| 8.8 Language contract | Verified for numbers, text, enums and control flow | `fdb6344`, `e6513b4`: whole-text `number(text)`, `chr(0)` contract, native mantissa/exponent parity; `c8f7c76` closest-name suggestions on unknown functions and variables; `f6b2b1e`/`7a05bd9` stable codes for ten common errors with `--explain`; cross-backend tests in `tests/test_number.py`, `tests/test_mid.py`, `tests/test_chrorrd.py`; `tools/capability_matrix.py` runs enums, lists, arrays, loops, recursion on both backends | Records/structures, general text variables beyond the current model |
| 8.9 Ownership and budgets | Verified for the existing resources | Local arrays capped at 8,192 elements and 16 MiB active (`tests/test_compiler.py`); calls capped at a 512 KiB stack budget on both backends (`tests/test_recursion_budget.py`, `6f0f3e8`, `506664d`); image caps (8,192 px/side, 16.7 Mpx, 128 MiB) enforced with a named `image_error()` reason per limit (`tests/test_image_limits.py`, `e4de27d`), plus missing-file diagnostics (`tests/test_image_error.py`) | No general allocator auditing or leak instrumentation |
| 8.10 Compiler and build loop | Verified | `dd40769` staging output; `40bf89d` cache key covers every runtime header plus compiler identity; `d1e56b9` keys on compiler contents, the linker and the SDK (C8-9/C8-10); `ca70a03` folds the **bytes** of every header reported by `cl /sourceDependencies` into the key, and `ccddb20` does the same for the static libraries reported by linker `/VERBOSE` (C8-11), on top of the retained SDK metadata prefilter; the environment cache is keyed by `VsDevCmd.bat`/`vcvarsall.bat` contents (C8-12, `a4eafbc`); `0b0130d` `--no-cache`; `a24a071` 4 MiB entry budget; `--check` runs backend lowering; `--print-imports`; `--doctor`; `2fe1008` idempotent native guard; `a896281` warns when an unused function calls an unknown one; `test_opt_parity` compares release, debug and native results | The C backend has no source-level debugger; WASM DWARF line maps are opt-in via `--debug-info` (8.12); diagnostics carry a line and caret by default and a 1-based column under `--diagnostics editor` (`50bb070`) |
| 8.11 Window loop and flicker | Partial | Buffered presentation with visible-pixel checks, rapid resize, GDI-count checks, minimize/restore repaint, close, injected backbuffer-allocation failure, and `window_on_top`/`window_fullscreen` verified against live Win32 styles and rectangle (`tests/test_native_window.py`); keyboard/mouse edge state (`test_native_keyboard`, `test_native_mouse`); seven 960×600 visual captures passed `python tools/visual_smoke.py --check` and were reviewed on 2026-11-17 | Occlusion and DPI changes are not covered; controls and ten-second live flicker observations still need a person |
| 8.12 Browser target | Partial | `--backend wasm` compiles a console subset and 2D scenes with clang/wasm-ld into `program.wasm` plus a generated canvas host page; the freestanding runtime imports only `env` functions (write, canvas primitives, input setters, save storage, and optional WebGL sphere-impostor capability/submission). Canvas 2D (`clear`/`rect`/`circle`/`line`/`text`/`present`) and the `anvil_frame` loop are verified by recorded draw streams and by opening the page in Chromium; keyboard, mouse, wheel and `time()`/`delta()` are verified with DOM events in Chromium (`d9d308a`); `sin`/`cos`/`rnd` match the C backend byte for byte, including `sin(1e6)` (`34bc2b2`); `tan` is available on both and agrees byte for byte over straight and large angles (`tests/test_tan.py`); typed saves persist across separate Node runs (`f236793`) and now use IndexedDB with a `localStorage` fallback and one-time migration, with Chromium round-trip evidence (Batch 103); the text helpers, `ord`/`chr`, `noise` and `fbm` match the C backend byte for byte (`3e17017`, Batch 56); runtime errors report their active Anvil statement line and function, with a function-level map fallback for raw traps and unmapped wasm frames (`tests/test_wasm.py`); `--debug-info` adds DWARF `.debug_line` tables with `#line` mappings, verified by `llvm-objdump --source --line-numbers --disassemble` resolving a WASM instruction to the original `.ANVL` file and line (`tests/test_wasm.py`); baked music plays through Web Audio with length/position/volume and loop wrapping (Batch 67); `scene 3d` renders cube/plane/sphere and compile-time-baked glTF models with the C runtime's camera basis and projection, overhead shadows (a separate draw layer so the floor cannot cover them), and bounding-sphere culling for models, rendered by WebGL with a real depth buffer and a painter fallback for Node and `?painter=1` (Batches 64-67); browser `ray_sphere` uses an analytic WebGL sphere impostor with per-fragment depth and sphere-to-sphere shadows when `EXT_frag_depth` is available, while Node, painter mode and unsupported browsers retain adaptive tessellation; two-sphere C/Chrome fixtures pass silhouette and color tolerances under default and oblique cameras; both C and WASM depth orderings produce equivalent images; an isolated sphere occluder darkens the receiver in both renderers; on Chrome 157 / NVIDIA RTX 5070 Ti, the active impostor path measured 1/8/32 p95 CPU-side call times 0.2/0.3/0.3 ms, JS heap peaks 1.47/1.64/1.96 MiB and max call times 0.7/1.3/0.9 ms, passing configured budgets; GPU execution time is not measured (Batch 108, `tests/test_wasm_browser_parity.py`, `tools/bench_wasm_ray_spheres.mjs`); the fresh 960×600 Chrome 157 / SwiftShader screenshot [`ray_sphere_wasm.png`](screenshots/ray_sphere_wasm.png) predates the shader and documents the tessellation facets; broad camera-angle, lighting and shadow parity remain open; repeat the passing 32-sphere SwiftShader performance result on hardware WebGL; sprites are baked from literal `image_load()` paths at build time (8/24/32-bit BMP) and drawn through the canvas with tint/flip/rotation and atlas regions; literal `sound_load()` WAVs are baked as int16 samples and played through Web Audio with looping, volume, pan, pitch, duration and three mixer groups; recorded draw streams and Chromium checks cover these (Batches 59-60); a path computed at run time loads normally on the C backend, and in the browser build `image_load`/`sound_load`/`music_load` return 0 with a named "only literal ..." reason (`tests/test_asset_paths.py`).| interactive Chrome DevTools DWARF source lookup and breakpoints still need a manual check; true streaming music (the browser track is baked); physics beyond the ported 2D solver; 1 MiB bump allocator; no `include` in the wasm pipeline; host page is fixed at 960x600; broader browser sphere-impostor parity remains open; repeat performance checks on hardware WebGL; the prior screenshot and measurements describe the tessellation fallback |
| 8.13 3D content pipeline | Partial | `scene 3d`, perspective camera, plane/cube/sphere and `ray_sphere` with CPU BVH and a 40-sphere desktop C batch (32 in the wasm approximation); wasm static and animated unskinned `model_draw` and `ray_mesh` bake glTF data into the module, sample first-clip node TRS (LINEAR/STEP; rotation slerp), compose morph deltas/defaults before node transforms, and submit through the depth-tested triangle path; animated or morphed rest-pose culling is skipped and all wasm model submissions enforce a shared 16,384-triangle frame budget, including skinned draws (`tests/test_wasm.py::WasmModelTests`, exact-limit, overflow, mixed-path, skin and reset cases); Windows C-vs-Chrome pixel-mask and RGBA comparisons exceed 0.92 silhouette IoU; visible-pixel mean RGB error is below 10/255 for static and below 25/255 for animated+morphed, with >90% of visible pixels within 16/32 channel levels (`tests/test_wasm_browser_parity.py`); skinned wasm `model_draw` and `ray_mesh` both support one skin with up to 64 joints; Node draw-stream tests prove animated skinned `ray_mesh` matches the `model_draw` triangle path, and C/Chrome parity for a 50/50 animated joint blend from an oblique camera under custom lighting is covered; an animated skinned/rotated-mesh crossing renders parity in both submission orders; broader camera, lighting and depth matrices remain open. `examples/first_world.ANVL` builds and is run interactively (not automated); compile-time glTF import (`model_draw`) bakes node transforms, material/vertex colours, a bounding sphere and up to 200k triangles from `.gltf` or `.glb` into the executable, and a model with an animation clip is baked node-local with its hierarchy and keyframes so `model_animate` + `model_draw` pose it per draw (translation/rotation/scale, LINEAR and STEP, slerp rotations, clip looping; verified by measured ink bounds in `tests/test_gltf_animation.py`), a static model with up to eight morph targets bakes per-vertex POSITION deltas blended by `model_morph` (`tests/test_gltf_morph.py`), and `ray_mesh` composes static morph weights plus animated node transforms in C, with rendered per-instance pose snapshots (`tests/test_gltf_ray_mesh.py`, `examples/ray_mesh_animated_morph.ANVL`); a skinned model bakes `JOINTS_0`/`WEIGHTS_0` with one skin's inverse bind matrices and blends `nodeWorld * inverseBind` per joint at draw time, with the joint motion driven by the same clip (a fully weighted joint moves the mesh as far as the joint, a 50/50 blend lands half way, a clip-less rig draws at the bind pose: `tests/test_gltf_skins.py`), with per-frame bounding-sphere culling (20 off-screen 2,048-triangle models: 3.83 ms -> 0.20 ms per frame, 18.9x) and overhead flattened shadows for cubes and models (`tests/test_shadows.py`) with loader unit tests, a located missing-file error and pixel tests for shading, depth ordering and GLB rendering (`tests/test_gltf_model.py`, `docs/MODELS.md`) | Static, animated and skinned base-color PNG `model_draw` plus static and animated unskinned textured `ray_mesh` are implemented on C/WASM (Batches 141, 143, 144, 145, 146); repeated texture batches, painter/no-WebGL fallback, and cutout/partial-alpha parity are covered by the focused Batch 147 regressions; fixed textured staging is bounded at 16,384 triangles, but initial/peak WASM memory-page measurement remains open; Desktop C has no GPU path or 3D batching, skinned textured `ray_mesh` and C skinned `ray_mesh` remain unsupported, and shadows are overhead-only |
| 8.14 2D, audio, physics, network, packaging | Partial, commands complete | BMP sprite builtins with documented limits and source-located errors (`tests/test_image_error.py`, `tests/test_compiler.py`); sprite tint, flip, centred rotation and atlas-region drawing verified against live window pixels (`tests/test_sprite_draw.py`); bounded 4,096-particle system with gravity, fade and a post-draw pass (`tests/test_particles.py`); a controllable directional light (`light`/`light_ambient`/`light_intensity`) verified against cube-face pixels (`tests/test_lighting.py`); per-monitor DPI awareness with a `dpi_scale()` query and `window_scale(factor)` resizing verified against the OS DPI and a live client rect (`tests/test_window_scale.py`); UTF-8 text drawn through GDI's wide API with fallback fonts and character-level wrapping (`tests/test_utf8_text.py`, `examples/text_wrap_demo.ANVL`); 2D camera pan/zoom with mouse inverse mapping, zoom-scaled glyphs and `parallax(factor)` layers, verified against pixels (`tests/test_camera2d.py`, `tests/test_text_zoom.py`, `tests/test_parallax.py`, `examples/parallax_demo.ANVL`); a screen fade (`screen_fade`, `screen_fade_to`, `screen_fade_alpha`) composited after every draw and before the present, verified against live window pixels at 0/128/255 plus a timed ramp, and emitted as a host overlay on the wasm canvas (`tests/test_screen_fade.py`); a scene manager (`scene_change/name/target/changing/changed/progress`) that fades out, swaps the current scene inside the black hold and fades back in, verified by the reported timeline and by a real window reading black at the midpoint and the drawn frame afterwards on both backends (`tests/test_scene_manager.py`); scene transitions (`scene_change/name/target/changing/changed/progress`) own a timed fade and swap an identifier at the midpoint; the application remains responsible for loading and drawing scene contents (test cases are in `tests/test_scene_manager.py`, not run in this review); a UI focus registry for custom-drawn controls (`ui_focus_add/clear/count/next/prev/set/at/activate/label`, `ui_accessible`) with a click on the topmost region and Enter/Space activation verified in a real window, the focused label read back from the MSAA child window, and the wasm build recording one `announce` op per focus change that the generated page writes into an aria-live region (`tests/test_ui_focus.py`); tilemaps: a 16-slot grid of up to 512x512 cells that names tiles in a tileset image, with `tilemap_new/free/columns/rows/tiles/set/get/fill/area/draw/error`, camera-aware culled drawing, per-tile solid flags, `tilemap_cell`/`tilemap_collide` AABB queries and row-wrapping tile animation (`tilemap_animate`/`tilemap_frame`), viewport-scaled drawing (a 512x512 map costs 0.12 ms p50 work in the `tilemap_large` runtime scene, down from 0.38 ms walking every cell) and a wasm refusal (`tests/test_tilemap.py`, `examples/tilemap_demo.ANVL`, `tools/bench_runtime.py`); bounded WAV audio (PCM and 4-bit IMA ADPCM, with `sound_duration`/`sound_rms` queries) with 16 slots, 8 voices, 48 MiB decoded budget, volume/pan/pitch, looping, device-loss fallback and `sound_error()` diagnostics (`tests/test_audio.py`), plus three mixer groups and a master gain with per-group stop (`tests/test_audio_groups.py`) and streaming music (PCM or ADPCM) decoded from disk with looping, position/length and named errors (`tests/test_music.py`, `tests/test_wav_adpcm.py`); typed key/value saves with atomic writes, magic/type bytes, slot-name validation, `%LOCALAPPDATA%\Anvil\<project>` storage and `save_error()` diagnostics, plus a per-project format version (`save_version`/`save_set_version`) for migrating an old layout and a named "needs a newer Anvil version" error for a future format (`tests/test_saves.py`); 2D physics with restitution and friction (`tests/test_compiler.py`); UDP double transport with malformed-packet fuzzing (`tests/test_net_fuzz.py`, `031bfb0`); `--package` with dry run, asset validation and hashed manifest (`79d8af3`); `new`/`run`/`build`/`test`/`format`/`clean`/`doctor`/`package` all exist (`75a4805`, `5967fdb`, `44dcd1b`) | Multi-value blobs (one number or one text value per slot); audio is complete for this milestone; 2D sprite batching exists (`sprite_batch`), 3D batching does not; transport is one-peer unauthenticated UDP |
| 8.15 Testing, security, efficiency | Partial | `docs/TESTING.md` labels each of the 145 test modules; packet fuzzing; capability matrix under test; per-line output flush (`tests/test_output_flush.py`); recursion bound; package asset validation; compile-time, image-size and runtime frame-time budgets (idle, overdraw, text, particles, 3D) published in `tools/bench_budgets.json` and enforced by `tests/test_perf_thresholds.py`, `tests/test_runtime_budget.py`, `python tools/bench_anvil.py --check` and `python tools/bench_runtime.py --check`; `frame_tick()`/`frame_render()`/`frame_present()` report the last frame's phases, and `bench_runtime` budgets scene work and present separately because a GDI blit occasionally blocks ~4 ms on the compositor; `tools/bench_memory.py` samples the compile process tree (132.6-138.4 MB across the latest full matrix; generated C 1.6-178.8 KB and executable 152.6-418.8 KB) and each scene runtime working set (5.2-24.2 MB), and an `assets` scene that loads eight 64x64 BMPs and two 0.25 s WAVs and reports `memory_images`/`memory_audio`/`memory_video` (131,072 / 576,000 / 9,216,000 bytes; the video figure now counts both backbuffers and the depth buffer, and `memory_gpu` reports the 4,608,000 bytes a compositor can see) plus their values after destroy and enforces `tools/mem_budgets.json` (`tests/test_memory_budget.py`); `tools/bench_input.py` posts key messages to a real window and measures key-to-`pressed(A)` latency (p50 25.5-29.4 ms, p95 43.3-51.6 ms over 20 presses) with `tools/input_budgets.json` and `tests/test_input_latency.py`; `memory_gpu()` reports the only compositor-visible surfaces - the two DIB backbuffers, 4,608,000 bytes - because rendering is CPU-side (`tests/test_memory_builtins.py`); `tools/bench_memory.py` also measures an `audio` scene (four 1.5 s sounds loaded, three played: 1,152,000 decoded bytes) and a `network` scene fed 200 datagrams by the harness, both with enforced `run_peak_mb` budgets, and an `audio_bytes` budget for the decoded mix; the latest complete 21-scene `python tools/bench_memory.py --check` passed, including audio at 13.0 MB, network at 5.6 MB, and the three GLB-backed ray-mesh scenes, all under their explicit 60 MB run limits. The decoded audio byte count is exactly 1,152,000.| Measured with `--timings`: parse+generate ~3 ms, cold C build ~400 ms after the toolset environment is cached, cache hit ~170 ms. Runtime p50 on the recorded machine: idle 0.38 ms, 2D overdraw (1,200 rects + 120 circles) 3.62 ms, 40 text lines 1.12 ms, about 2,400 live particles 0.88 ms, 20 cubes + plane 2.88 ms; budgets are 2.5x the measured medians. `memory_images`/`memory_audio`/`memory_video`/`memory_total` expose per-class byte counts and the fixed 2,304,000-byte backbuffer (`tests/test_memory_builtins.py`), and `memory_report()` names each live image/sound with the Anvil `file:line` that allocated it and the Anvil call chain that reached it - every generated function pushes its name on entry, so a load three calls deep prints `from fn(main) > fn(setup) > fn(load_world)`, a setup-block load prints `from top level`, and a chain past eight names is truncated with ` > ...` (`tests/test_memory_report.py`). Visual check: `python tools/visual_smoke.py --check` passed on 2026-11-17 for all seven examples at 960×600; reviewed each capture for scene composition and rendering artefacts. Interactive controls and ten-second live flicker observation still need a human operator. There is no GPU VRAM beyond the backbuffers to cover (drawing is CPU-side, so `memory_gpu()` is the complete figure until a GPU path exists), and the network scene measures the process side only, because a UDP socket's buffers live in the kernel. Windows x64 only |
| 8.16 Delivery order and evidence | This ledger plus generated matrix | `docs/CAPABILITY_MATRIX.md` now measures C, native and wasm: 12 of 14 cases run on all three backends, and all 14 run on C and wasm, `docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md` batches 14–22, commit list below | Browser and 3D rows remain open before the delivery order can complete |
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
- `ca70a03` cache key hashes the bytes of headers reported by `/sourceDependencies` (C8-11 header half)
- `ccddb20` cache key hashes the bytes of libraries reported by linker `/VERBOSE` (C8-11 library half)

## How to re-check

### Browser ray-sphere performance and depth

`node tools/bench_wasm_ray_spheres.mjs` compiles and opens 1-, 8- and 32-sphere
scenes in headless Chrome/WebGL, warms each scene for 45 frames, then records
180 direct `anvil_frame` durations in each of three fresh-page trials. It also
checks JS heap use, verifies overlapping near/far spheres yield the same front
pixel in both submission orders, and enforces the checked-in p95, max-frame and
heap budgets. It also requests opt-in `EXT_disjoint_timer_query` samples around
the sphere impostor draw and reports GPU execution separately from CPU call
duration. On the recorded Ryzen 7 9800X3D / Chrome 157 / SwiftShader run,
the worst trial p95s were 4.6 / 4.9 / 6.0 ms and heap peaks were 4.7 / 17.0 /
72.6 MiB for 1 / 8 / 32 spheres. These numbers describe the tessellation fallback on this headless software
renderer and machine.

On hardware-required Chrome 157 / ANGLE / NVIDIA GeForce RTX 5070 Ti, three
trials produced non-disjoint timer-query GPU draw p50 / worst-trial p95 values
of 0.0031 / 0.0071 ms, 0.0039 / 0.0080 ms, and 0.0077 / 0.0125 ms for 1, 8,
and 32 spheres. Valid samples totaled 678 / 677 / 680; one trial group was
unavailable for 1 and 32 spheres. Rare query maxima were about 0.18 ms for 8
and 32 spheres. These values measure only the sphere draw command, not full
frame presentation latency. Raw results are emitted outside Git in the path
selected by `WASM_RAY_BENCH_OUTPUT`.

### Morph-aware wasm model culling

`node tools/bench_wasm_morph_culling.mjs` builds paired 1,000-instance scenes
with 16 triangles per morphing model, placing every instance outside the camera
frustum. It warms 60 frames and measures 240 `anvil_frame` calls in each of
three fresh-page trials with culling enabled and disabled. On the recorded
Ryzen 7 9800X3D / Chrome 157 / SwiftShader run, maximum trial p95 was 0.2 ms
with culling and 8.3 ms without (97.6% lower); max sampled frame was 0.3 ms
and 13.5 ms, respectively. This measures a headless software-WebGL run on this
machine; it is not a GPU performance claim. The paired run data is emitted to
`%TEMP%/anvil_wasm_morph_culling_chromium.json` and intentionally stays out of
Git.

The browser parity test compares exact RGBA frames for all nine pairs from
the `{0, 0.5, 1}` weight grid on two morph targets. A Node draw-stream test
checks that an offscreen group contributes no submitted triangles while a
visible sibling still draws.

```bash
python -m pytest tests -q
python tools/capability_matrix.py --check
python compiler/anvil.py --doctor
python compiler/anvil.py game.ANVLproj --test
python compiler/anvil.py examples/first_world.ANVL --check
```

The full-suite count changes as tests land; the latest recorded run is in
`docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md`.

## Batch 120 — validate the current full test tree

Ran the entire current suite after the GLB WASM render regression, the memory
benchmark fixture repair, and the in-progress browser/3D changes. The full
result was 1,060 passed, 1 skipped, and 1 xfailed in 867.77 seconds. The test
tree contains 151 `test_*.py` modules. Scoped `git diff --check` passed for the
current changed source, test, tool and evidence files.

The run validates the current worktree, including the recent GLB and memory
changes; it does not close the documented product gaps in Part 8. No commit or
push was made.

## Batch 121 — reconcile WASM music and GPU timing evidence

Corrected stale WASM capability text that still said browser music was baked
and streaming was unavailable, although `music_load` now streams a same-origin
PCM WAV sidecar. The Part 8 ledger now records the Chromium HTTP range and
advancing media-clock verification. It also replaces the stale claim that GPU
time was unmeasured with the hardware `EXT_disjoint_timer_query` measurements
from Batch 112 and states their limit: they time the sphere draw command, not
full-frame presentation. Updated the browser limits regression to prevent the
streaming-music claim from regressing.

Validation: `python -m pytest tests/test_wasm_docs.py
tests/test_wasm.py::WasmMusicTests -q` — 5 passed; scoped `git diff --check`
passed. No code behavior changed; no commit or push was made.
## Batch 122 — close glTF importer audit blockers

Hardened the compiler-side glTF/GLB importer. Model paths and external buffer
URIs resolve inside the configured project root after symlink resolution;
relative buffer URIs remain relative to their model file. The importer enforces
container, buffer, decoded-accessor, geometry, and triangle limits before the
corresponding large allocations. Primitive index accessors must be unsigned
integer scalars and cannot be normalized. Scene-less node graphs now start only
at parentless roots. Import-scoped caches avoid reopening valid model
containers and external buffers, and malformed URI types become located model
errors. Documented the path policy and limits in `docs/MODELS.md`.

Regression coverage includes parent and absolute escapes, a Windows directory
junction escape, allowed in-root subfolders, scene-less transformed hierarchies, invalid index
formats, malformed URI diagnostics, exact and over-limit triangle boundaries
with a located CLI error, and a one-read I/O check. Validation: `python -m pytest tests/test_gltf_import_bounds.py
tests/test_gltf_model.py tests/test_gltf_skins.py tests/test_gltf_animation.py
tests/test_gltf_morph.py -q` — 58 passed. No full-suite run, commit, or push.
A 40-import median on the same small quad fixture measured 0.740 ms for
external-buffer glTF and 0.464 ms for embedded GLB. This is a repeatable
smoke measurement, not a representative large-model benchmark.

## Batch 123 — verify GLB render paths and reconcile audit status

Re-ran the C pixel-render comparison for `.glb` versus `.gltf` and the WASM
renderer submission test for an embedded-BIN GLB; both passed. Expanded the
Windows path-escape regression to use a real outside-project directory
junction because unprivileged file symlink creation is unavailable here;
`mklink /J` succeeded and `Path.resolve()` confirmed the outside target before
the importer rejected it. Added exact-limit acceptance and over-limit
source-located rejection for the 200,000-triangle budget. The focused glTF
suites passed 58 tests; the full suite remains unrun for this batch.

The old P8-204 audit summary now identifies its path and allocation blockers as
historical findings addressed in 8.207. Textured GLB rendering and the broader
Part 8 3D gate remain open; this batch does not add texture decoding or claim
full glTF feature coverage.

## Batch 124 — validate limits before opening buffers

Moved accessor count, element, range, alignment and normalization checks ahead
of reading its source buffer. Added a regression that patches `read_bytes()`
to fail if called, then verifies oversized model containers, external buffers
and accessor counts are rejected before any file read. Focused glTF importer
suites passed 59 tests. The C GLB pixel comparison and WASM embedded-GLB render
test passed again (2 passed). `git diff --check` passed.

## Batch 125 — add a GLB `model_draw` example

Added `examples/glb_model.ANVL`, which renders the bundled `ray_mesh.glb`
through the ordinary raster `model_draw` path. Updated `docs/MODELS.md` to
clarify that embedded base-color textures are not decoded and textured
materials currently fall back to their base-color factor. `python
compiler/anvil.py examples/glb_model.ANVL --check` passed.

## Batch 129 — re-verify WASM GLB rendering

After the project-root and URI-resolution hardening, reran the embedded-BIN
GLB model draw regression through the WASM compiler and runtime. It passed
(`1 passed, 67 deselected`), and the new `model_draw` example still passes
`--check`.

## Batch 126 — normalize path resolution failures

Wrapped model, buffer, container and project-root resolution so filesystem
errors and symlink loops become `ModelError` diagnostics instead of uncaught
Python exceptions. Added a symlink-loop simulation regression. Focused path and
GLB render tests passed (4 passed); `git diff --check` passed.

## Batch 127 — handle encoded glTF buffer URIs

External buffer URI paths are percent-decoded before resolution and
project-root containment checks. An encoded `%2e%2e` traversal regression
confirms the decoded path cannot escape. The `data:` scheme and `;base64`
marker are recognized case-insensitively. Validation: the encoded-path
containment test and GLB container-loading test passed.

## Batch 128 — re-run importer suites after URI hardening

Ran `python -m pytest tests/test_gltf_import_bounds.py tests/test_gltf_model.py
-q` after path-resolution and percent-encoded URI changes: 33 passed. This
covers the focused importer, path, malformed-input and C GLB render behavior
for the current change set.

## Batch 130 — cover GLB assets in nested project manifests

Added a regression with a nested `src/main.ANVL`, a `.glb` under the project
`models/` directory and an embedded BIN chunk. The `.ANVLproj` WASM `--check`
path resolves the model against the manifest root and succeeds; this exercises
the project-root configuration through `wasm.validate`, not just standalone
source imports.

## Batch 131 — prove embedded GLB visibility in Chromium

Added `test_embedded_glb_model_draw_is_visible_in_chromium` to the browser
parity suite. It compiles one embedded-BIN GLB for C and WASM, captures the
WASM output from headless Chrome, then compares silhouette and visible color
against the native C renderer. Validation in this Windows/Chrome environment:
`python -m pytest tests/test_wasm_browser_parity.py -k
embedded_glb_model_draw_is_visible_in_chromium -q` — 1 passed, 16 deselected.

## Batch 132 — reconcile model texture documentation

Reconciled `docs/MODELS.md`: embedded base-color texture decoding is unsupported
and textured materials render with their `baseColorFactor` fallback, while the
other listed unsupported features are explicitly refused with a located
compile error. This corrects the prior contradictory claim that textures both
fell back and failed compilation.

## Batch 133 — test manifest GLB preflight in `anvil verify`

Added a nested-project test for the separate `anvil verify` code path. A
`src/main.ANVL` entry references an embedded-BIN `models/quad.glb`; JSON
preflight resolves it from the manifest root and reports no diagnostics. The
entire verifier suite passed: 9 passed.

## Batch 134 — cover case-insensitive data buffer URIs

Added a regression for `DATA:application/octet-stream;BASE64,...` buffer URIs.
It confirms the importer accepts the URI scheme and base64 marker without
case sensitivity and decodes the binary payload correctly. Focused test:
`python -m pytest tests/test_gltf_import_bounds.py::GltfImportBoundsTests::test_data_buffer_uri_scheme_and_base64_marker_are_case_insensitive -q`
— 1 passed.

## Batch 135 — reconcile importer capability documentation

Updated the `compiler.gltf` module description to include GLB 2 containers,
external/data/BIN buffers, and supported morph targets. The old description
claimed only JSON glTF was supported and that morph targets were unsupported,
contradicting the current importer and model guide. No runtime behavior changed.

## Batch 136 — clarify model texture support in the WASM guide

Corrected the WASM guide's statement that textured geometry is C-only. The
glTF importer does not decode base-color textures for either renderer; both
use the material `baseColorFactor` fallback. Texture rendering remains open.

## Batch 137 — add bounded PNG texture import primitives

Added a standard-library PNG decoder for bounded, non-interlaced 8-bit RGB and
RGBA images, plus safe loading of URI-backed and bufferView-backed glTF image
bytes. The helpers validate PNG chunk checksums and ranges, decompression size,
pixel count, row filters, and project-root containment. These are importer
building blocks only: model UV/material wiring and C/WASM texture rasterization
remain unimplemented, so the documented fallback behavior is still accurate.

## Batch 138 — connect static C model textures to rasterization

Connected the PNG image decoder to material texture references and `TEXCOORD_0`
baking for static, unskinned models. The C `model_draw` renderer now receives
UVs, texture pixels, material tint/alpha and texture indices, then samples them
with perspective-correct interpolation in the depth-tested software rasterizer.
The renderer clips textured triangles against the near plane and keeps
`baseColorFactor` behavior for untextured primitives in a mixed mesh.

WASM builds keep their existing base-color-factor fallback and omit texture
arrays from the generated module. Animated, skinned or morphed C models with
base-color textures are rejected with a located compile error. `ray_mesh` also
continues to use factor colors. Only `git diff --check` was run; runtime texture
rendering has not yet been exercised.

Batch 139 supersedes the WASM fallback note above: static unskinned WebAssembly
model_draw now includes and samples embedded PNG textures.

## Batch 139 — render static GLB textures in WebAssembly

Extended model_draw texture baking to WebAssembly and added a textured
triangle host import. The browser WebGL renderer converts the embedded packed
RGBA pixels to WebGL textures, samples UVs with depth-correct interpolation,
and depth-tests textured triangles with the rest of the 3D scene. The Node
host records textured submissions and the no-WebGL painter falls back to the
material tint. ray_mesh and textured animated, skinned or morphed models
retain the material-factor fallback/refusal behavior. Only git diff --check
was run; browser and runtime rendering remain unverified.

## Batch 17 — render static GLB base-color PNG textures

Extended compile-time glTF import to decode bounded, non-interlaced 8-bit
RGB/RGBA PNG images from embedded bufferViews, base64 data URIs, or
project-contained external URIs. Static unskinned meshes bake TEXCOORD_0,
material/vertex tint, alpha and texture indices alongside packed pixels in the
executable. The C software rasterizer clips textured triangles at the near
plane, samples repeat-wrapped UVs with perspective-correct interpolation,
shades with the scene light and depth-tests the result. MASK alpha mode,
texture transforms, non-repeat samplers and textured animated/skinned/morphed
models are rejected. Documentation and item #201's partial-status notes were
updated. No test suite or runtime fixture was run in this batch; texture
rendering is not yet independently verified.


## Batch 140 — clip textured WebAssembly GLB triangles at the near plane

The WASM textured model renderer now transforms each vertex into camera space,
clips its triangle against the C renderer's 0.08 near-depth plane, interpolates
UVs at generated vertices, and fan-triangulates the visible polygon. The new
Chrome parity regression includes fully-front, one-behind, two-behind and
fully-behind triangles, a UV gradient, and a farther overlapping triangle to
cover depth ordering.

Validation: `python -m pytest
tests/test_wasm_browser_parity.py::WasmBrowserParityTests::test_embedded_glb_texture_clips_at_near_plane_with_uv_and_depth_parity
-q` — 1 passed in 4.31 s. The test builds both C and WASM renderers and compares
Chrome pixels against the C framebuffer. `git diff --check` passed. No commit or
push.

## Batch 141 — batch WebAssembly textured GLB submission

Static textured model draws now stage projected vertices in a bounded WASM
buffer and call the browser host once per contiguous texture run. The host packs
those runs into a single typed vertex buffer and issues one WebGL draw, retaining
run order for alpha/painter behavior. Textured static draws use a dedicated
200,000 source-triangle frame budget; all other model paths retain their
16,384-triangle limit. The capture tool reports opt-in per-frame draw/buffer/
upload counters and frame timings, and
`tools/bench_wasm_textured_submission.mjs` reproduces 1k/10k/100k benchmarks.

Chrome/SwiftShader run (30 warmups, 120 frames):

| Triangles | p50 | p95 | max | JS heap peak | persistent buffers / draws per frame | Upload |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 2.4 ms | 4.1 ms | 5.3 ms | 1.3 MiB | 1 / 1 | 108,000 B |
| 10,000 | 3.3 ms | 5.1 ms | 5.8 ms | 4.0 MiB | 1 / 1 | 1,080,000 B |
| 100,000 | 13.1 ms | 15.5 ms | 15.9 ms | 12.1 MiB | 1 / 1 | 10,800,000 B |

The 100k measurement fits the 200k admission cap and the configured 20 ms p95,
25 ms maximum-frame and 25 MiB heap budgets on this host. `performance.memory`
varies by browser and hardware. The benchmark uses one texture run; material-run
count bounds draws and persistent vertex buffers.

Validation: the GLB near-plane C/Chrome parity test passes after the host ABI
change; `node --check` passes for both benchmark/capture scripts. No commit or
push.

### Streamed music WAV validation follow-up

Baked PCM and browser-streamed WAV metadata now share `_wav_pcm_info()`. Both
accept ordinary PCM and PCM WAVE_FORMAT_EXTENSIBLE with the standard full PCM
subformat GUID and matching valid-bit depth, and reject unsupported codecs,
invalid byte rate/block alignment, partial sample frames, and empty data with
matching validation errors. A compiler regression proves an extensible
non-PCM subtype fails at the `music_load` location before WASM output is
created. Validation: three shared-reader unit tests and two browser-music build
regressions pass.


### Oblique-camera textured GLB parity

The bundled GLB example now sets a non-axis-aligned `camera_angle(20, -12)`.
`test_bundled_textured_glb_example_matches_c_in_chromium` builds the same source
and embedded texture for C and WASM, captures the Chromium output and compares
silhouette and visible-pixel color metrics. The focused regression passed.

### Textured GLB camera-angle parity

The bundled GLB C/Chrome regression now checks three camera angles—straight-on,
positive oblique and negative oblique—and asserts silhouette IoU, visible-pixel
MAE and within-16-channel coverage for each pair. The three-angle test passed in
17.70 seconds on Windows/Chrome.

### Animated textured GLB model_draw

The glTF importer now preserves per-triangle texture coordinates, tint, alpha,
and texture slot data for animated models. C and WebAssembly apply the sampled
node transforms and morph deltas before submitting posed textured triangles
through their existing texture renderers. `examples/glb_animated_textured_model.ANVL`
uses an embedded-PNG animated GLB. The example passed compiler `--check` and a
WASM build; a temporary generated animated asset also compiled to C and WASM
and rendered in headless Chromium with four visible texture colors (95,172
visible pixels). No test suite was run. Textured skinned models and textured
`ray_mesh` remain unsupported.

### Textured skinned GLB model_draw

`load_skinned` now emits UV/material records beside joint-weighted triangles.
Both C and WebAssembly apply the joint blend and submit skinned textured
`model_draw` geometry through the existing texture renderer. Added
`examples/glb_skinned_textured.glb` and `examples/glb_skinned_textured_model.ANVL`.
The checked-in example passed `--check`, fresh C/WASM builds and a Chromium
capture (7,021 visible pixels, three sampled texture colors). A textured
skinned `ray_mesh` WASM compile still uses the existing flat-material call.
No test suite was run; textured `ray_mesh` remains open.

### Static textured GLB ray_mesh

Static unskinned textured `ray_mesh` now samples base-color PNG textures on
both backends. C retains BVH ray tracing and samples UVs at each hit; WebAssembly
uses the existing textured raster renderer with near-plane clipping. The new
`examples/glb_textured_ray_mesh.ANVL` passed `--check`, fresh C/WASM builds and
a Chromium capture (94,864 visible pixels, four texture colors). Animated or
skinned textured `ray_mesh` remains flat-colored, and C skinned `ray_mesh` is
still unsupported. No test suite was run.


### Textured WebAssembly batch integrity and fallbacks

The browser host uses independent pooled arrays for each queued texture chunk and
concatenates batch vertex data when compatible runs are combined. The Node host
records `textured_triangle_batch` operations with finite screen bounds, triangle
count, texture dimensions/layer and average tint. Painter and simulated no-WebGL
Chromium captures render both of two repeated embedded-texture GLB instances. A
three-camera C/Chrome parity regression verifies the same repeated-instance
scene. An RGBA fixture with a transparent texel and a half-alpha texel passes C
and Chrome silhouette/color tolerances.

Validation: four focused tests passed in 17.31 s. No full suite was run. The
WASM staging buffer decreased from 60,800,000 bytes to 2,490,368 bytes; the
separate animated texture pose buffer remains 2,621,440 bytes. Initial and peak
linear-memory pages still need a dedicated recorded budget.

### Textured WebAssembly run pooling follow-up

Textured static model draws cap pooled renderer vertex staging at 48 MiB and
material runs at 256 per frame, with atomic overflow rejection. Five focused
Node/Chromium regressions pass. Chrome 157 / SwiftShader 100k-triangle fixture:
15.3 ms p95, 15.8 ms max, 42.2 MiB process JS heap (including the compiled
WASM module); A/B/A: 4.4 ms p95, 4.7 ms max, three ordered draws. This is a
software-renderer measurement.

The benchmark records exported WebAssembly memory pages at module start, peak
through warmup and 120 measured frames, and end. Chrome 157 / SwiftShader
1k/10k/100k fixtures were 47/69/288 pages at all three points (no runtime
growth); A/B/A used 44 pages. The harness enforces a 320-page measured-fixture
budget. The final budget-enforced run measured p95 4.5/5.5/15.6 ms and maximum
frames 5.1/5.7/16.4 ms for the 1k/10k/100k cases. This closes page accounting
for these fixtures, not arbitrary larger compiled models.

The benchmark also covers the maximum 200,000 source-triangle static textured
model. Chrome 157 / SwiftShader measured 533 WASM pages at start/peak/end,
84.6 MiB process JS heap, 26.8 ms p95 and 28.1 ms maximum frame. It stayed
within the dedicated 600-page, 100 MiB, 40 ms p95 and 50 ms max-frame gates.
Near-plane worst-case clipping and hardware GPU timing are not included.
