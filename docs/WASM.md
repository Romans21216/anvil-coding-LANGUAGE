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
- text values, `&` joining, and the builtins `len`, `mid`, `upper`, `number`
- `floor`, `ceil`, `sqrt`, `abs`, `min`, `max`, `clamp`, `round`
- `sin`, `cos` (range-reduced Taylor series, no libm) and `rnd` (xorshift64,
  inclusive integer range like the C runtime)
- `scene 2d` with `fn(draw)`, `clear`, and `display rect/circle/line/text`
- input and time: `time()`, `delta()`, `pressed(key)`, `held(key)`,
  `mouse_x()`, `mouse_y()`, `mouse_pressed(button)`, `mouse_held(button)`,
  `mouse_wheel()`
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
  test pins 1e6 radians, which still matches libm to six decimals); `tan`,
  `noise` and `fbm` are not available yet.
- `anvil_frame` ignores its delta argument; animations advance per host frame.
