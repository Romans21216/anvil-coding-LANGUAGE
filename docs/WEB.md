# Browser target

Part 8 asks for a browser story that "must use standard web technologies and
must not require a user to install a plugin". This page records exactly what
`--package --web` delivers today, so nobody plans around a capability that is
not there.

## What the command produces

```
python compiler/anvil.py game.ANVLproj --package --web
```

writes:

```
game/dist/<name>/
  package.json          target "browser", per-file sizes and SHA-256 checksums
  web/index.html        the lab page, titled with the project name
  web/engine.js         the lab engine with the project source embedded
  web/style.css         styling, with remote font imports stripped
  web/assets/...        the project's assets, same relative paths
```

The page is static: open `web/index.html` from disk, no server, no build step
and no plugin. Opening it makes no network requests — the packaged stylesheet
drops the Google Fonts `@import` that the repository copy uses — so the bundle
works offline and does not contact a third party.

## What the page actually runs

The lab is a **preview**, not a compiled runtime. It parses the source for
`scene`, `clear` and `display` declarations and renders them on a 2D canvas,
animating `-rotate` and re-reading declarations as you edit. That covers the
"author a scene and see it in a browser" half of the authoring loop.

It does **not** execute `fn(update)`, `fn(draw)`, variables, control flow,
physics, audio, networking or image loading. The generated folder says so in
`package.json` (the backend is recorded as `html+canvas`) and the CLI prints the
same note after packaging.

## Why it is a preview and not a port

The runtime is C against Win32 (GDI, WinMM, Winsock). Running Anvil programs in
a browser faithfully would need either a WebAssembly build of that runtime with
its platform calls replaced, or a second interpreter in JavaScript. Neither
exists yet; shipping a half-faithful JavaScript interpreter would quietly
diverge from the compiler's semantics, which is worse than an honest preview.

## Testing

`tests/test_commands.py::WebPackageTests` pins the parts that can go wrong
silently:

- the bundle contains `index.html`, `engine.js` and `style.css`, and the
  project's source really is embedded in `engine.js`;
- no bundled file contains `http://` or `https://`, so the page cannot phone
  home or fail offline;
- a source containing a backtick and `${` is escaped so the template literal
  stays valid, and `node --check` parses the result when Node is installed;
- `package.json` reports `target: "browser"`, `backend: "html+canvas"` and
  checksums for the bundled files;
- `--web` without `--package` is rejected with a located message.

## Path to real browser delivery

1. Compile the runtime's platform layer behind a thin interface (window, input,
   audio, sockets) so a WebAssembly target can supply canvas, DOM events,
   WebAudio and WebSocket implementations.
2. Emit WebAssembly from the C backend (MSVC cannot target wasm; this needs a
   second toolchain such as clang with a wasi or emscripten sysroot).
3. Keep the preview as the zero-install authoring surface and make the compiled
   target the "publish" path, with the same `package.json` shape.
