# WebAssembly target

`--backend wasm` compiles a subset of Anvil to a WebAssembly module and writes a
host page beside it. Console programs run under Node and in a browser; 2D scenes
draw on a `<canvas>`. Input, audio, storage and 3D are not there yet.

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

It provides `printf`/`putchar`, number formatting, string helpers, arrays and a
1 MiB bump allocator. Audio, files, network and input are outside the subset.

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
- `sin`, `cos` (range-reduced Taylor series, no libm) and `rnd` (xorshift64,
  inclusive integer range like the C runtime)
- `scene 2d` with `fn(draw)`, `clear`, and `display rect/circle/line/text`
- `scene 3d` with `camera perspective`, `camera fov`, `camera_angle`,
  `display cube/plane/sphere` and `model_draw` (glTF baked at build time)
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
- saves: `save_number`, `load_number`, `save_text`, `load_text`,
  `save_exists`, `save_delete`, `save_error`

Refused with a source-located error:

- `scene 3d`, `camera` and `engine` statements
- `display` shapes other than `rect`, `circle`, `line` and `text` (cubes,
  spheres, planes, sprites, ray-sphere)
- any other builtin (`time`, `rnd`, `image_load`, `sound_*`, `save_*`, ...)

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
projected, flat-shaded by a fixed directional light and handed to the host.

Shadows are the same overhead projection as the desktop runtime: `shadow(on)`,
`shadow_height(y)` and `shadow_alpha(a)` flatten a cube's bottom face and every
model triangle onto the ground plane in black with that alpha. Shadow triangles
carry a separate draw layer so they paint after ordinary geometry; without it
the floor's own triangles sorted over them. The shadow quad uses the cube's
bottom face — the first attempt used a side face, which projected to a line.

Bounding-sphere culling is implemented for `model_draw`: a model is skipped when
its whole sphere is behind the near plane or outside the screen, and
`mesh_culled()` reports it.

`model_draw` works because the compiler bakes glTF triangles into the module
exactly as it does for the C backend: the runtime receives 12 doubles per
triangle (three positions plus RGB), scales, rotates and translates them, then
submits them through the same path as the primitives. `mesh_drawn()` counts the
triangles submitted in the frame; `mesh_culled()` is always 0 because there is
no bounding-sphere test yet, and `mesh_culling(on)` only echoes its argument.

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
drawing in the frame, and 2D primitives in a 3D scene are covered by the blit. Skins, morph targets,
textures and `ray_sphere` remain C-backend only.

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

A wasm trap shows up in JavaScript as `RuntimeError: unreachable` with a stack of
minified frame numbers. The compiler writes a source map next to the module
(`program.map.json`) and embeds the same table in the host page, mapping each
generated function (`anvil_update`) to its Anvil name and the line where the
function is declared. Both hosts walk the stack until they find a mapped frame
and report, for example:

```
Anvil runtime error in fn(update) at line 4: RuntimeError: unreachable
```

This is a function-level map, not instruction-level: it tells you which Anvil
function trapped and where it starts, not the exact statement. Unmapped frames
(runtime helpers such as `anvil_text_chr`) fall through to the raw stack.

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
`localStorage` under `anvil:<project>/<slot>`; the project name comes from the
compiled program (default `Anvil_Game`). Values use the same type rules as the C
runtime: numbers are stored as 16 hex digits of their IEEE-754 bits (so a
round trip is exact), text as UTF-8 with a 255-byte limit, and reading the wrong
type returns `0` with the same messages the C runtime uses ("the save holds
text, not a number" / "the save holds a number, not text"). Slot names are 1-64
letters, digits, `.`, `_` or `-`.

The Node host keeps saves in memory unless `ANVIL_SAVE_FILE` names a JSON file,
in which case it loads and rewrites that file so saves persist across runs.

`localStorage` is synchronous and small (about 5 MB per origin). A game that
needs larger or structured storage will get IndexedDB later; the API will not
change.

## Hosts

- `tools/wasm_host.mjs` — Node host used by tests and `--run`; writes module
  output to stdout.
- `hello.html` — generated page that fetches the module, wires `env.write` to a
  `<pre>`, and calls `main()`.

Both instantiate the module with the same import object, so behaviour is
identical.

## Limits

- A 1 MiB bump allocator backs `calloc`; there is no freeing. Programs that
  allocate more than that fail at runtime.
- Numbers are IEEE doubles, as on the native backends, but `sin`/`cos` and other
  libm functions are not linked yet.
- No Web Audio, IndexedDB or source maps yet; saves use `localStorage` for now.
  Those are the remaining 8.12 items. 3D and images also need the C backend.
- `sin`/`cos` lose accuracy for arguments far outside the reduced range (the
  test pins 1e6 radians, which still matches libm to six decimals); `tan` is not
  available yet.
- Only literal `image_load()` paths are baked; 4-bit BMPs are not supported.
- 3D uses a painter's algorithm rather than a depth buffer; expect sorting
  artifacts where geometry intersects, and no model/shadow/ray support.
- `chr` writes `Anvil chr out of range` to stderr and traps out of range, the
  same exit the C runtime gives; the Node host exits 1 and the page throws.
- Text helpers truncate counts toward zero and clamp to the string length, the
  same as the C runtime; `char` returns empty text for out-of-range indexes.
- `anvil_frame` ignores its delta argument; animations advance per host frame.
