# WebAssembly target

`--backend wasm` compiles a console subset of Anvil to a WebAssembly module and
writes a host page beside it. It is the first slice of the browser target: the
module runs today under Node and in a browser, but it has no canvas, input,
audio or storage yet.

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
single host dependency is:

```c
void env.write(int fd, const void *bytes, int length);
```

It provides `printf`/`putchar`, number formatting, string helpers, arrays and a
1 MiB bump allocator. Everything else — graphics, audio, files, network, input —
is outside the subset.

Supported today:

- numbers, arithmetic, comparisons, `and`/`or`/`not`
- globals, fixed arrays, functions with parameters and return values
- `if` / `else`, `while`, `for`
- `say`, `write`, `output`
- text values, `&` joining, and the builtins `len`, `mid`, `upper`, `number`
- `floor`, `ceil`, `sqrt`, `abs`, `min`, `max`, `clamp`, `round`

Refused with a source-located error:

- `scene`, `display`, `engine` statements — graphics need the C backend
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
- No canvas, keyboard/mouse, Web Audio, IndexedDB or source maps yet; those are
  the remaining 8.12 items.
