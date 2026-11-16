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
- `scene 2d` with `fn(draw)`, `clear`, and `display rect/circle/line/text`

Refused with a source-located error:

- `scene 3d`, `camera` and `engine` statements
- `display` shapes other than `rect`, `circle`, `line` and `text` (cubes,
  spheres, planes, sprites, ray-sphere)
- any other builtin (`time`, `rnd`, `image_load`, `sound_*`, `save_*`, ...)

For example:

```text
hello.ANVL:2: 'time' is not available in the wasm backend yet
```

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
- No keyboard/mouse, Web Audio, IndexedDB or source maps yet; those are the
  remaining 8.12 items. 3D and images also need the C backend.
- `anvil_frame` ignores its delta argument; animations advance per host frame.
