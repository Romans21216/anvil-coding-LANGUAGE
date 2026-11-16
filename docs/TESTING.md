# Testing Anvil

This page labels what the automated tests actually cover, what they need to run,
and which tolerances they assume. It exists so no claim rests on an unlabelled
test run (Part 8 section 8.15).

## Recorded environment

| Item | Value |
| --- | --- |
| OS | Windows 11 (10.0.26200) |
| Python | 3.13.15 (64-bit) |
| C compiler | MSVC `cl.exe` 14.51.36231 (Visual Studio 18 Community, x64) |
| Shell used for the commands below | Git Bash, run from the repository root |
| Window tests | An unlocked interactive desktop session |

The C backend needs MSVC; the native backend needs only Python. When `cl.exe`
is absent, tests that build C programs raise `SkipTest` instead of failing.

## Commands

| Purpose | Command |
| --- | --- |
| Full suite (headless and interactive) | `python -m pytest tests -q` |
| Headless only | `python -m pytest tests -q --ignore=tests/test_native_keyboard.py --ignore=tests/test_native_mouse.py --ignore=tests/test_native_window.py --ignore=tests/test_native_procedural.py` |
| One area | `python -m pytest tests/test_number.py tests/test_mid.py -q` |
| Backend capability drift | `python tools/capability_matrix.py --check` |
| Compile-time and size budgets | `python tools/bench_anvil.py --check` (re-baseline with `--write-budgets`) |
| Runtime frame-time budgets | `python tools/bench_runtime.py --check` (re-baseline with `--write-budgets`) |
| Compile and runtime memory budgets | `python tools/bench_memory.py --check` (re-baseline with `--write-budgets`) |
| Input latency budget (interactive) | `python tools/bench_input.py --check` (re-baseline with `--write-budgets`) |
| Sprite atlas packing | `python tools/pack_atlas.py sheet.bmp --atlas sheet.json sprites/*.bmp` |
| WebAssembly console build | `python compiler/anvil.py hello.ANVL --backend wasm -o hello.wasm` then `node tools/wasm_host.mjs hello.wasm` |
| A project's own cases | `python compiler/anvil.py game.ANVLproj --test [--backend native]` |
| Formatting | `python compiler/anvil.py file.ANVL --format-check` |
| VS Code grammar and sample validation | `npm test --prefix vscode-extension` |

`--test` compiles and runs every `tests/**/*.ANVL` file in a project. A case
passes when the built program exits 0; failures print the captured build and
run output.

## Headless coverage

These suites never create a window. They compile and run console programs,
inspect generated C or PE bytes, or test compiler behaviour directly:

- Compiler and language: `test_compiler`, `test_compiler_limits`,
  `test_compiler_modules`, `test_refusals`, `test_diagnostics`, `test_lints`,
  `test_includes`, `test_selective_imports`, `test_import_statement`,
  `test_unused_imports`, `test_deadcode`, `test_dead_branches`, `test_enums`,
  `test_declared_types`, `test_bool_values`, `test_break_continue`, `test_elif`,
  `test_repeat`, `test_for_each`, `test_not`, `test_literal_dedupe`,
  `test_generated_agreement`, `test_backend_agreement`.
- Text, numbers and collections: `test_number`, `test_number_format`,
  `test_ask_number`, `test_mid`, `test_chrorrd`, `test_char`, `test_len`,
  `test_trim`, `test_contains`, `test_edges`, `test_left_right`, `test_strings`,
  `test_text_compare`, `test_text_functions`, `test_text_lists`,
  `test_text_list_link`, `test_text_order`, `test_text_params`,
  `test_text_recursion`, `test_textcase`, `test_lists`, `test_list_remove`,
  `test_round`, `test_mod`.
- Runtime behaviour without a window: `test_runtime`,
  `test_runtime_prototypes`, `test_noise_bounds`, `test_recursion_budget`,
  `test_random_builtin`, `test_random_pipeline`, `test_net_status`,
  `test_clock`, `test_wait`, `test_say`, `test_say_expressions`, `test_write`,
  `test_ask`, `test_press_enter`, `test_stop`, `test_grade`, `test_qa_report`,
  `test_tutorial`, `test_repl`.
- Tooling and delivery: `test_build_cache`, `test_build_atomic`,
  `test_thin_build`, `test_commands`, `test_format`, `test_package`,
  `test_source_limits`, `test_capability_matrix`, `test_native_x64` (byte-level
  PE inspection), `test_extensions`, `test_libraries`, `test_more_libraries`,
  `test_all_libraries_import`, `test_library_edges`, `test_essentials`,
  `test_geometry`, `test_vector`, `test_units_validate`, `test_image_error`,
  `test_audio`,
  `test_saves`,
  `test_suggestions`, `test_opt_parity`, `test_timing`, `test_timings_cli`,
  `test_first_hour`,
  `test_image_limits`, `test_output_flush`, `test_net_fuzz`,
  `test_native_trig`, `test_bench`, `test_perf_thresholds`.

## Interactive coverage

These suites launch a generated Windows PE and drive it through real window
messages. They require an unlocked desktop; a locked session or a disconnected
remote desktop can prevent window creation:

- `test_native_keyboard` — key down/up, held/pressed edges, repeat
  suppression, focus loss.
- `test_native_mouse` — client-pixel mapping, letterbox rejection, all three
  buttons, wheel accumulation.
- `test_native_window` — visible pixels during and after drawing, resize,
  minimize/restore, close, and injected backbuffer-allocation failure.
- `test_native_procedural` — gradient noise, FBM and procedural helpers in a
  running image.
- `test_sprite_draw` — C-backend sprite tint, horizontal flip, 90° rotation and
  atlas-region draws checked by reading the pixels the program presented.
- `test_camera2d` — C-backend `camera2d` pan, zoom, rejection of a zero zoom
  and reset, sampled from the presented window.
- `test_input_latency` — posts key messages to a real window and measures the
  delay until `pressed(A)` fires; interactive, kept to a few presses.
- `test_memory_builtins` — loads images and a WAV and asserts the exact byte
  counts from `memory_images`/`memory_audio`/`memory_video`/`memory_total`.
- `test_memory_budget` — samples the compiler's process tree and each scene's
  working set, checks generated C and executable sizes, and enforces
  `tools/mem_budgets.json`.
- `test_runtime_budget` — builds and runs the idle, 2D-overdraw, text and 3D
  benchmark scenes and enforces the frame-time budgets in
  `tools/bench_budgets.json`.
- `test_atlas_pack` — packs solid BMPs, reads the sheet back to check the
  manifest rectangles, and requires byte-identical output across runs.
- `test_audio_groups` — mixer-group assignment, gain clamping, master gain,
  mute and per-group stop; playback cases skip without an audio device.
- `test_music` — streaming music loading, length, volume clamps, bad-file
  messages, position/stop and loop-versus-finish behavior.
- `test_wav_adpcm` — IMA ADPCM decoding for one-shot sounds and streaming music,
  decoded amplitude against a PCM reference, and bit-depth rejections.
- `test_wasm` — builds the console subset and 2D canvas scenes with
  clang/wasm-ld, runs them under Node (including the recorded draw-command
  stream, scripted keyboard/mouse input, trig/rnd results matching the C
  backend, typed saves across separate Node runs, text helpers, `ord`/`chr`, `noise`/`fbm`, the `chr` failure path
  compared against the C backend, and baked sprites and atlas regions through
  recorded draw streams), checks the generated host
  page, and asserts located refusals.
- `test_particles` — argument validation, the 4,096-particle bound, clear
  counts, and window pixels for a fresh and fading particle.
- `test_shadows` — a tilted camera samples the flattened shadow of a model and
  of a cube, and checks the shadow moves with `shadow_height`.
- `test_gltf_model` — glTF/GLB loaders, node transforms, a located missing-model
  error, window pixels for flat shading and depth ordering, and culling counters
  for behind-camera versus visible models.
- `test_text_zoom` — text glyphs grow with the camera zoom and return to their
  original size on reset, measured from the presented pixels.
- `test_includes` — the subset that runs an included graphical sample.

The harness (`tests/native_app.py`) builds the PE, starts it, finds the window
belonging to that process id, and sends only bounded messages to it. It never
posts to unrelated windows. Global state is read with `ReadProcessMemory`, so
assertions cover the program's own memory rather than screenshots.

## Tolerances and assumptions

- The runtime uses a fixed 960×600 virtual framebuffer; window resizing
  letterboxes and never scales the pixel grid. Pixel assertions sample the
  framebuffer after a frame has been presented.
- Fixed updates run at `engine.fixed_hz` (1–240, default 60). Tests wait on
  process state with explicit timeouts (15–60 s); no correctness check depends
  on wall-clock sleeps.
- Native PE tests compare exact bytes for generated code and exact values for
  runtime results. C tests build with MSVC release settings.
- The capability matrix is a behaviour record, not a performance benchmark; no
  speed claim is made from these tests.

## Known gaps

- Only Windows x64 is exercised. Linux, macOS, browser and mobile targets have
  no automated runs.
- The VS Code extension is validated by grammar and sample checks
  (`npm test`), not by inspecting a live editor window.
- Automated window tests verify pixels and state; they are not a substitute for
  a manual look at a game running on real hardware.
- `test_runtime.py::test_mouse_events_map_to_virtual_frame_and_preserve_update_edges`
  drives a real window and cursor, and has failed once under full-suite load
  while passing alone in 1.7 s. Treat a lone failure there as a flake only
  after re-running it in isolation.
- `test_native_window.py` covers pixels during a slow draw, rapid resize,
  GDI counts, minimize/restore and allocation failure; occlusion and DPI
  changes still have no automated case.
- The full suite took 180 s with a warm toolset-environment cache (719 passed); the
  first run after a Visual Studio update pays one ~1.2 s environment capture.
- The full-suite count changes as tests are added; the latest recorded run is
  in `docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md`.
