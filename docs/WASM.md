# WebAssembly target

`--backend wasm` compiles a subset of Anvil to a WebAssembly module and writes a
host page beside it. Console programs run under Node and browser pages render 2D
and selected 3D scenes to a `<canvas>`. The browser host also provides input,
audio, IndexedDB-backed saves and WebGL for the documented feature subset.

```sh
python compiler/anvil.py hello.ANVL --backend wasm -o hello.wasm
node tools/wasm_host.mjs hello.wasm
# or: python compiler/anvil.py hello.ANVL --backend wasm --run
```

The build writes `hello.wasm` and `hello.html`. Browsers refuse `fetch()` from
`file://` URLs, so serve the folder over HTTP:

```sh
python -m http.server 8000
# then open http://localhost:8000/hello.html
```

## What runs

The generated C is the same code the C backend emits; only the runtime differs.
`runtime/anvil_wasm.c` is a freestanding runtime (no libc, no libm, no OS) whose
host dependencies are imports in `env`:

```c
void write(int fd, const void *bytes, int length);
void clear(int r, int g, int b, int a);
void rect(double x, double y, double w, double h, int r, int g, int b, int a);
void circle(double x, double y, double radius, int r, int g, int b, int a);
void line(double x1, double y1, double x2, double y2, double thickness,
          int r, int g, int b, int a);
void text(double x, double y, const char *text, int length,
          int r, int g, int b, int a);
void present(void);
```

`anvil_run` stores the callbacks and returns; the host drives frames by calling
the exported `anvil_frame(delta_ms)`, which runs one update, clears with the
scene colour, draws and calls `present`.

The freestanding runtime provides `printf`/`putchar`, number formatting, string
helpers, arrays and a 1 MiB bump allocator. Browser resources are baked at build
time; arbitrary runtime file and network access are not exposed.

Supported today:

- numbers, arithmetic, comparisons, `and`/`or`/`not`
- globals, fixed arrays, functions with parameters and return values
- `if` / `else`, `while`, `for`
- `say`, `write`, `output`
- text values, `&` joining, and the builtins `len`, `mid`, `upper`, `lower`,
  `trim`, `left`, `right`, `char`, `contains`, `starts_with`, `ends_with`,
  `number`, `ord`, `chr`
- `noise` and `fbm` (same hash and gradient tables as the C runtime)
- `floor`, `ceil`, `sqrt`, `abs`, `min`, `max`, `clamp`, `round`
- `sin`, `cos` (range-reduced Taylor series, no libm), `tan` (nearest-pi/2
  double-double reduction for ordinary angles, reciprocal evaluation near
  poles; extremely large finite inputs retain the angle reducer's 1e20 limit),
  and `rnd` (xorshift64,
  inclusive integer range like the C runtime)
- `scene 2d` with `fn(draw)`, `clear`, and `display rect/circle/line/text`
- `scene 3d` with `camera perspective`, `camera fov`, `camera_angle`,
  `display cube/plane/sphere`, `model_draw` and lighting controls (glTF baked
  at build time)
- input and time: `time()`, `delta()`, `pressed(key)`, `held(key)`,
  `mouse_x()`, `mouse_y()`, `mouse_pressed(button)`, `mouse_held(button)`,
  `mouse_wheel()`
- images: `image_load`, `image_width`, `image_height`, `image_draw`,
  `image_draw_scaled`, `image_draw_rotated`, `image_tint`, `image_flip`,
  `image_destroy`, `image_error` (literal paths baked at build time)
- audio: `sound_load`, `sound_play`, `sound_play_loop`, `sound_stop`,
  `sound_stop_all`, `sound_volume`, `sound_pan`, `sound_pitch`,
  `sound_duration`, `sound_group`, `sound_group_volume`, `sound_group_mute`,
  `sound_group_gain`, `sound_group_stop`, `sound_active`, `sound_destroy`,
  `sound_error` (literal paths baked at build time; streaming music is not there
  yet)
- music: `music_load`, `music_play`, `music_play_loop`, `music_stop`,
  `music_playing`, `music_volume`, `music_position`, `music_length`,
  `music_error` (one literal track, baked at build time)
- physics: `body_create`, `body_create_box`, `body_destroy`, `body_active`,
  `body_x/y/vx/vy`, `body_set_velocity`, `body_force`, `body_restitution`,
  `body_friction`, `body_collision`, `physics_capacity`, `physics_gravity`,
  `physics_step`
- particles: `particle_emit`, `particle_count`, `particle_clear`,
  `particle_gravity` — the same 4,096-particle pool, fading squares drawn after
  the program's own pass
- accounting: `memory_images`, `memory_audio`, `memory_video`, `memory_total`
- saves: `save_number`, `load_number`, `save_text`, `load_text`,
  `save_exists`, `save_delete`, `save_error`

Refused with a source-located error:

- `engine` statements
- `display` shapes other than `rect`, `circle`, `line`, `text`, `cube`, `plane`,
  `sphere` and `ray_sphere` (sprites use the image API)
- any other builtin; the current refusals are `memory_report`,
  `frame_capture`, `text_width` and the `tilemap_*` family (the console, canvas, baked-asset,
  audio, save, physics, particle and accounting builtins listed above
  are supported)

For example:

```text
hello.ANVL:2: 'time' is not available in the wasm backend yet
```

## Input

The host page listens on the window and canvas and calls exported setters:

| Browser event | Export | Notes |
| --- | --- | --- |
| `keydown` / `keyup` | `anvil_key(code, down)` | `KeyA`–`KeyZ` map to `A`–`Z` (65–90); Space 32, Enter 13, Escape 27, arrows 37–40 |
| `mousemove` | `anvil_mouse(x, y)` | scaled from the canvas CSS size to its 960×600 buffer |
| `mousedown` / `mouseup` | `anvil_mouse_button(index, down)` | index 0 left, 1 right, 2 middle |
| `wheel` | `anvil_wheel(delta)` | `deltaY` |

`anvil_frame(delta_ms)` advances `time()` by the delta (clamped to 0–250 ms) and
sets `delta()` in seconds; pressed edges and wheel deltas last one frame, like
the C runtime's first-update clearing. `mouse_x()`/`mouse_y()` are `-1` until the
pointer first moves.

The page calls `anvil_input_release()` on `blur` and when the tab becomes
hidden. Without it a keyup delivered to another window is never seen, so the
module would keep the key held forever and the next press would not register as
a fresh press. The export clears held and pressed keys, mouse buttons and the
wheel delta; a test drives a real generated page through
`tools/wasm_page.mjs` and proves the release and re-press.

The page exposes `window.anvil` (the instance) so a console or test can step
frames and inject input deterministically:

```js
window.anvil.exports.anvil_key(65, 1);
window.anvil.exports.anvil_frame(16);
```

## 3D

`scene 3d` works with the same camera conventions as the C runtime: `camera
perspective x y z` sets the eye, `camera fov(degrees)` clamps to 20-120 and sets
the focal length from the 960-pixel width, `camera_angle(yaw,pitch)` turns the
view, and `display cube/plane/sphere` submit world-space triangles. Each
triangle is rotated, translated, put in camera space with the C runtime's basis,
projected, flat-shaded with the scene light and handed to the host. The
`light(x,y,z)` vector points toward the light; zero and non-finite vectors are
rejected, and valid vectors are normalized when shading. `light_ambient(level)`
sets the 0–1 floor (default 0.28), and `light_intensity(level)` sets the 0–2
scale for the lit part (default 1). Both setters return their previous value
and ignore non-finite input. Shading is `ambient + (1 - ambient) * intensity *
max(0, dot(normal, light))`, clamped to 0–1. Primitive triangles are one-sided;
imported model triangles are two-sided. The C sphere's per-pixel shading and the
wasm sphere's tessellated facets use the same scene-light settings.

Shadows are the same overhead projection as the desktop runtime: `shadow(on)`,
`shadow_height(y)` and `shadow_alpha(a)` flatten a cube's bottom face and every
model triangle onto the ground plane in black with that alpha. Shadow triangles
carry a separate draw layer so they paint after ordinary geometry; without it
the floor's own triangles sorted over them. The shadow quad uses the cube's
bottom face — the first attempt used a side face, which projected to a line.

Bounding-sphere culling is implemented for `model_draw`: a model is skipped when
its whole sphere is behind the near plane or outside the screen, and
`mesh_culled()` reports it.

`model_draw` and `ray_mesh` bake static or animated unskinned glTF triangles into
the module and submit them through the depth-tested raster path. `model_draw` also
supports one skin with up to 64 joints and four vertex influences; it samples the
first animation clip or uses the bind pose when no clip exists. Skinned draws skip
bounds culling and overhead shadows. In WebAssembly, `ray_mesh` is triangle
submission, not the C runtime's software ray-tracing/BVH implementation, and
skinned `ray_mesh` receives a located diagnostic. All wasm model submissions, including skinned `model_draw`, share a 16,384-triangle frame budget. Each call
is checked as a whole and returns 0 without submitting geometry when the call
would exceed the remaining budget. `mesh_drawn()` counts triangles from the most
recent model submission; `mesh_culled()` reports whole-model frustum culling,
and `mesh_culling(on)` controls that culling.

The page renders triangles with WebGL into an offscreen 960x600 canvas and blits
it onto the visible canvas at `present()`. The shader maps camera depth onto the
clip-space z axis and a real depth buffer resolves every pixel, so submission
order no longer matters and intersecting geometry is correct. Shadows (layer 1)
are drawn after geometry with the depth test disabled, which keeps them on top
of the floor without letting them cover the object.

Two fallbacks still use the painter's algorithm: the Node host (no WebGL) and a
page opened with `?painter=1`. `?nosort=1` additionally skips the far-to-near
sort, which is how the depth test is demonstrated — an unsorted painter shows
the farther cube, WebGL shows the nearer one. 3D is still painted after any 2D
drawing in the frame, and 2D primitives in a 3D scene are covered by the blit.
Skinned `ray_mesh` is unsupported; textured geometry remains C-backend only. Unskinned animated
`model_draw` and `ray_mesh` models support the first glTF clip with translation,
rotation and scale tracks using LINEAR or STEP interpolation. `model_animate`
sets a per-model clock; `model_animation_length` is baked as a compile-time
constant. Static and animated unskinned models also support morph targets as
described below.

`display ray_sphere(...)` is supported in `scene 3d` as a tessellated,
per-vertex shaded approximation, with sphere-to-sphere shadow checks. Tessellation
adapts to projected sphere size and shares a 16,384 candidate-triangle frame
budget across the 32-sphere queue. On Chrome 157 / SwiftShader, the checked-in
benchmark measured maximum p95 work of 4.6 ms for 1 sphere, 4.9 ms for 8, and
6.0 ms for 32; the maximum sampled JS heap peaks were 4.7, 17.0 and 72.6 MiB.
The C backend still provides exact per-pixel sphere tracing; the browser path
has polygonal silhouettes and facet lighting.

`model_draw(...)` and `ray_mesh(...)` are supported in `scene 3d` for static
and animated unskinned models, including morph targets. Per-group glTF defaults
are preserved and `model_morph(path,index,weight)` overrides that target for every
group. Morph deltas are applied before the animated node transform and the
placement transform; culling is skipped for animated or morphed models because
the baked rest-pose bounds do not contain all poses. Both calls use the same WebGL depth-tested triangle path, which resolves
overlapping mesh depth per pixel in the browser. `model_draw` and `ray_mesh`
share a 16,384-triangle frame budget across
static and animated submissions; each call is accepted whole or rejected before
triangle submission. The Node and `?painter=1` fallbacks sort
triangles and can show intersections. The browser path has no mesh BVH or
ray-traced shadows; skinned `ray_mesh` remains a located unsupported case.

`tests/test_wasm_browser_parity.py` renders a static morphing GLTF and an
animated-morph ray mesh through the C/Win32 and wasm/Chrome paths, then compares
visible-pixel masks and RGBA output. Each fixture requires silhouette IoU above
0.92; static visible-pixel mean RGB error is below 10/255, and animated+morphed
error is below 25/255, with over 90% of visible pixels within 16 or 32 levels
per channel, respectively. The additional model-lighting fixture uses a custom
light, ambient and intensity setting with an oblique camera and verifies that a
zero direction is rejected; its C/Chrome RGBA comparison also passes. A second
primitive fixture checks one-sided cube shading and sphere lighting against C.
An intersecting, rotated-cube fixture compares C and Chrome in both submission
orders; each renderer's pixels remain order-independent and the C/Chrome color
comparison passes. A second crossing-depth fixture draws two tilted GLTF quads
through `model_draw` in both orders and also passes the C/Chrome RGBA thresholds.
The animated+morphed ray-mesh comparison uses an offset, oblique camera. These
fixtures do not establish parity across every camera, lighting setting,
primitive combination, or crossing-depth scene.

## Audio

Audio follows the image strategy: `sound_load("...")` with a literal path is
decoded at build time (PCM WAV, mono or stereo, 8- or 16-bit, 8,000-192,000 Hz,
8 MiB of baked samples) and emitted as int16 samples at their original rate.
The page builds an `AudioBuffer` at that rate and lets the browser resample, so
nothing is converted twice. `sound_play` and `sound_play_loop` return a host voice id, and
`sound_stop`, `sound_stop_all`, `sound_volume`, `sound_pan`, `sound_pitch` and
`sound_active` map onto `AudioBufferSourceNode`, a gain node and a stereo
panner. Pan clamps to -1..1 and pitch to 0.25-4, like the C runtime, and
`sound_duration` reports the baked length in seconds.

Mixer groups work the same way as on the desktop: every voice routes through one
of three group gain nodes into a master, groups default to gain 1 and group 1,
`sound_group` moves a loaded sound, `sound_group_volume`/`sound_group_mute` act
on the nodes, `sound_group_gain` reports the effective gain (0 while muted) and
`sound_group_stop` stops the voices in a group (group 0 stops all) and returns
how many it stopped. `window.anvilAudio().groups` shows the four live gains.

Browsers refuse to start audio before a user gesture. The page listens for
`keydown` and `pointerdown` and resumes the context then, so a game that plays a
sound on the title screen will stay silent until the player clicks or presses a
key — the usual browser rule, not a bug. `window.anvilAudio()` exposes
`{active, voices, state, sampleRate}` for debugging and tests.

A computed path cannot be baked and reports that through `sound_error()`; a
missing file or a compressed WAV is a located build error. The Node host records
each play with frame count, channels, rate, volume and peak sample so the tests
can assert the bake without an audio device.

## Diagnostics

A wasm trap reports the active Anvil function and statement line. The generated
C emits a source-line marker before each Anvil statement; runtime helpers keep
that marker with the active function and pass it to the host when a runtime
error occurs. Both the page and Node host report, for example:

```
Anvil runtime error in fn(update) at line 6: Anvil chr out of range
```

`program.map.json` retains the function-to-declaration map for raw traps and
unmapped wasm frames. Statement-level locations cover Anvil runtime errors;
they are not a DWARF debugger or a mapping for arbitrary machine instructions.

## Images

A browser cannot read files synchronously, so the wasm backend bakes images at
build time instead of loading them at run time. Every `image_load("...")` with a
literal string is decoded while compiling (8-, 24- and 32-bit BMP, 8,192 pixels
per side, 4 MiB of baked pixels in total) and emitted as a C array; a computed path
cannot be baked and reports that through `image_error()` at run time, and a
missing file is a located build error.

Drawing forwards the baked pixels to the host, which owns the canvas: the page
converts ARGB pixels once per image into an offscreen canvas (with the tint
applied) and draws it scaled, flipped or rotated with smoothing disabled, so
sprite art stays crisp. The Node host records the draw with a checksum of the
pixels, which is what the tests assert.

`image_draw_region` copies an atlas cell: the source rectangle must lie fully
inside the image, otherwise the call returns 0 and draws nothing, exactly like
the C runtime.

Not implemented yet: 4-bit BMPs and any image loaded through a non-literal
path.

## Physics

The 2D physics solver is ported from the C runtime rather than reimplemented:
the same circle/box contact tests, four solver iterations, default gravity of
-9.81, restitution and friction bounds and the same handle encoding, so a scene
that settles on the desktop settles identically in the browser. The only shim
additions it needed were `isfinite` and `hypot`. The capability matrix's
`physics-body` case now runs on C and wasm, which is how that parity is checked.

## Music

One looping track per build, like the desktop streaming player, with one
difference worth stating plainly: the browser build cannot stream from disk
without an async fetch contract, and the music API is synchronous, so the track
is decoded at build time and baked into the module (16 MiB of samples, PCM WAV
mono/stereo, 8/16-bit, 8,000-192,000 Hz). `music_length()` is the decoded
duration, `music_position()` comes from the host's audio clock and wraps on a
looping track, and `music_stop` stops and resets the source. A computed path
cannot be baked and reports that through `music_error()`; a missing file is a
located build error.

## Saves

Saves work in the browser without files. The host page backs them with
**IndexedDB** (database `anvil-saves`, store `saves`) under
`anvil:<project>/<slot>`; the project name comes from the compiled program
(default `Anvil_Game`). Because Anvil's save API is synchronous, the page reads
the whole namespace into memory before the module starts: reads answer from
that map, and writes land in the map immediately and reach IndexedDB in the
background. Where IndexedDB is unavailable - the Node page harness, private
mode, a locked-down context - the same interface is backed by `localStorage`,
and saves left there by an older build are migrated into IndexedDB once on the
next load. Values use the same type rules as the C
runtime: numbers are stored as 16 hex digits of their IEEE-754 bits (so a
round trip is exact), text as UTF-8 with a 255-byte limit, and reading the wrong
type returns `0` with the same messages the C runtime uses ("the save holds
text, not a number" / "the save holds a number, not text"). Slot names are 1-64
letters, digits, `.`, `_` or `-`.

The Node host keeps saves in memory unless `ANVIL_SAVE_FILE` names a JSON file,
in which case it loads and rewrites that file so saves persist across runs.

`localStorage` was the original backend and is capped at roughly 5 MB per
origin; IndexedDB removes that ceiling. `window.anvilSaveBackend` reports which
store the page actually used (`indexedDB` or `localStorage`), which is what the
browser checks assert.

## Hosts

- `tools/wasm_host.mjs` — Node host used by tests and `--run`; writes module
  output to stdout and drives input with `--input '[["key",65,1],["frame"]]'`.
- `tools/wasm_page.mjs` — runs a generated host page against small DOM stubs so
  the page's own event wiring (keys, mouse, focus loss) is tested, not just the
  module.
- `hello.html` — generated page that fetches the module, wires `env.write` to a
  `<pre>`, and calls `main()`.

Both instantiate the module with the same import object, so behaviour is
identical.

## Limits

- A 1 MiB bump allocator backs `calloc`; there is no freeing. Programs that
  allocate more than that fail at runtime.
- Numbers are IEEE doubles. `sin`/`cos` are a range-reduced Taylor series, not
  libm: the reduction keeps 2π as a hi/lo pair and subtracts in double-double,
  so the phase is exact through 1e15 radians and within 1e-11 of libm through
  1e20. Past 1e20 the phase needs a 2/π table the freestanding runtime does not
  carry, so the reduction returns 0 instead of a wrong angle.
- `tan` follows the same finite-input convention as C: binary64 inputs near an
  odd multiple of π/2 produce a large finite result; the nearest representable
  value is not an exact mathematical pole.
- Audio uses Web Audio; browser saves use IndexedDB when available and fall
  back to `localStorage` when it is not. `tan` is available. IndexedDB, audio,
  and trigonometry support do not imply full platform parity: instruction-level
  source maps and true streaming music remain open browser-target work.
- Only literal `image_load()` paths are baked; computed asset paths cannot be
  resolved by the browser build. 4-bit BMPs are supported.
- 3D uses WebGL with a depth buffer when available; Node and `?painter=1` use
  painter sorting and can show intersection artifacts. The browser supports
  static and animated unskinned `model_draw` and `ray_mesh`, including morph
  targets through the depth-tested triangle path, plus overhead shadows and tessellated
  `ray_sphere`; both model APIs share the 16,384-triangle frame budget.
  Skinned `ray_mesh` and textured geometry remain unsupported in wasm; skinned
  `model_draw` supports one skin with up to 64 joints.
- `chr` writes `Anvil chr out of range` to stderr and traps out of range, the
  same exit the C runtime gives; the Node host exits 1 and the page throws.
- Text helpers truncate counts toward zero and clamp to the string length, the
  same as the C runtime; `char` returns empty text for out-of-range indexes.
- `anvil_frame(delta_ms)` advances `time()` and `delta()`; unskinned model clips
  are sampled when `model_draw` or `ray_mesh` is submitted.
