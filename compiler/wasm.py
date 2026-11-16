"""WebAssembly console backend (Part 8, 8.12 first slice).

The Windows runtime needs GDI, Win32 and sockets, so a browser target cannot
reuse it. This backend emits the same generated C but against
`runtime/anvil_wasm.c`, a small freestanding runtime whose only host dependency
is an imported `env.write(fd, ptr, len)`. Programs are limited to a console
subset; anything outside it is refused with a source-located error rather than
failing at link time.

Build:  python compiler/anvil.py hello.ANVL --backend wasm -o hello.wasm
Run:    node tools/wasm_host.mjs hello.wasm
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

from compiler.builtin_usage import used_builtins
from compiler.codegen import emit_c
from compiler.common import CompileError

ROOT = pathlib.Path(__file__).resolve().parents[1]

ALLOWED_BUILTINS = {
    "abs",
    "ceil",
    "clamp",
    "floor",
    "len",
    "max",
    "mid",
    "min",
    "number",
    "round",
    "sqrt",
    "upper",
    "time",
    "delta",
    "pressed",
    "held",
    "mouse_x",
    "mouse_y",
    "mouse_pressed",
    "mouse_held",
    "mouse_wheel",
}

ENGINE_STATEMENT = re.compile(r"^\s*engine\b", re.MULTILINE)
SCENE_STATEMENT = re.compile(r"^\s*scene\s+(\w+)", re.MULTILINE)
DISPLAY_STATEMENT = re.compile(r"^\s*display\s+([a-z_]+)\s*\(", re.MULTILINE)
CAMERA_STATEMENT = re.compile(r"^\s*camera\b", re.MULTILINE)
ALLOWED_SHAPES = {"rect", "circle", "line", "text"}

HOST_PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
 body { margin:0; background:#0d1117; }
 canvas { display:block; margin:12px; background:#000; box-shadow:0 0 0 1px #30363d; }
 #out { position:fixed; left:12px; bottom:12px; color:#ff7b72; font:13px ui-monospace,monospace; white-space:pre-wrap; }
</style>
<canvas id="screen" width="960" height="600"></canvas>
<div id="out"></div>
<script>
const canvas = document.getElementById("screen");
const context = canvas.getContext("2d");
const errors = document.getElementById("out");
const utf8 = new TextDecoder();
function rgba(r, g, b, a) {
  return "rgba(" + r + "," + g + "," + b + "," + ((a === undefined ? 255 : a) / 255) + ")";
}
async function start() {
  try {
    if (location.protocol === "file:") {
      throw new Error("Serve this folder over HTTP (python -m http.server); browsers block wasm fetches from file:// URLs.");
    }
    const bytes = await (await fetch("__WASM__")).arrayBuffer();
    const module = await WebAssembly.compile(bytes);
    let memory = null;
    let app = null;
    const imports = { env: {
      write(fd, pointer, length) {
        const view = new Uint8Array(memory.buffer, pointer, length);
        console.log(utf8.decode(view));
      },
      clear(r, g, b, a) {
        context.fillStyle = rgba(r, g, b, a);
        context.fillRect(0, 0, canvas.width, canvas.height);
      },
      rect(x, y, w, h, r, g, b, a) {
        context.fillStyle = rgba(r, g, b, a);
        context.fillRect(x, y, w, h);
      },
      circle(x, y, radius, r, g, b, a) {
        context.fillStyle = rgba(r, g, b, a);
        context.beginPath();
        context.arc(x, y, Math.abs(radius), 0, Math.PI * 2);
        context.fill();
      },
      line(x1, y1, x2, y2, thickness, r, g, b, a) {
        context.strokeStyle = rgba(r, g, b, a);
        context.lineWidth = Math.max(1, thickness);
        context.beginPath();
        context.moveTo(x1, y1);
        context.lineTo(x2, y2);
        context.stroke();
      },
      text(x, y, pointer, length, r, g, b, a) {
        const view = new Uint8Array(memory.buffer, pointer, length);
        context.fillStyle = rgba(r, g, b, a);
        context.font = "20px 'Segoe UI', system-ui, sans-serif";
        context.textBaseline = "top";
        context.fillText(utf8.decode(view), x, y);
      },
      present() {},
    }};
    const instance = await WebAssembly.instantiate(module, imports);
    memory = instance.exports.memory;
    app = instance;
    // Exposed so a test page or console can step frames deterministically.
    window.anvil = instance;
    const keyCodes = { Space: 32, Enter: 13, Escape: 27, ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40 };
    const keyCode = (event) => {
      if (event.code && event.code.indexOf("Key") === 0) return event.code.charCodeAt(3);
      if (keyCodes[event.code] !== undefined) return keyCodes[event.code];
      return event.keyCode || 0;
    };
    window.addEventListener("keydown", (event) => {
      if (!app) return;
      app.exports.anvil_key(keyCode(event), 1);
      if ([32, 37, 38, 39, 40].indexOf(keyCode(event)) >= 0) event.preventDefault();
    });
    window.addEventListener("keyup", (event) => {
      if (app) app.exports.anvil_key(keyCode(event), 0);
    });
    canvas.addEventListener("mousemove", (event) => {
      if (!app) return;
      const rect = canvas.getBoundingClientRect();
      app.exports.anvil_mouse(
        (event.clientX - rect.left) * canvas.width / rect.width,
        (event.clientY - rect.top) * canvas.height / rect.height
      );
    });
    canvas.addEventListener("mousedown", (event) => {
      if (app) app.exports.anvil_mouse_button([0, 2, 1][event.button] || 0, 1);
    });
    canvas.addEventListener("mouseup", (event) => {
      if (app) app.exports.anvil_mouse_button([0, 2, 1][event.button] || 0, 0);
    });
    canvas.addEventListener("wheel", (event) => {
      if (app) app.exports.anvil_wheel(event.deltaY);
    }, { passive: true });
    if (instance.exports.main) instance.exports.main();
    if (instance.exports.anvil_frame) {
      let last = performance.now();
      const tick = (now) => {
        const delta = now - last;
        last = now;
        try {
          instance.exports.anvil_frame(delta);
        } catch (error) {
          errors.textContent = String(error);
          return;
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  } catch (error) {
    errors.textContent = String(error);
  }
}
start();
</script>
</html>
"""


def _find_tool(name: str) -> str | None:
    return shutil.which(name)


def validate(
    source_path: pathlib.Path, functions, top, source_text: str | None = None
) -> list[str]:
    text = source_text
    if text is None:
        text = pathlib.Path(source_path).read_text(encoding="utf-8")
    match = SCENE_STATEMENT.search(text)
    if match and match.group(1).lower() != "2d":
        line = text.count("\n", 0, match.start()) + 1
        raise CompileError(
            f"{source_path}:{line}: the wasm backend draws 'scene 2d' only; "
            f"'scene {match.group(1)}' needs the C backend"
        )
    for match in DISPLAY_STATEMENT.finditer(text):
        if match.group(1) in ALLOWED_SHAPES:
            continue
        line = text.count("\n", 0, match.start()) + 1
        raise CompileError(
            f"{source_path}:{line}: display {match.group(1)}(...) is not available "
            "in the wasm backend yet"
        )
    for pattern, label in ((CAMERA_STATEMENT, "camera"), (ENGINE_STATEMENT, "engine")):
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            raise CompileError(
                f"{source_path}:{line}: '{label}' statements are not available in "
                "the wasm backend yet"
            )
    used = used_builtins(functions, top)
    for name in used:
        if name in ALLOWED_BUILTINS:
            continue
        for index, line_text in enumerate(text.splitlines(), 1):
            if re.search(rf"\b{re.escape(name)}\s*\(", line_text):
                raise CompileError(
                    f"{source_path}:{index}: '{name}' is not available in the wasm "
                    "backend yet"
                )
        raise CompileError(
            f"{source_path}: '{name}' is not available in the wasm backend yet"
        )
    return used


def build(
    source_path: pathlib.Path,
    functions,
    top,
    variables,
    arrays,
    out: pathlib.Path,
    fixed_hz: int,
    project_name: str,
    emit_c_path: pathlib.Path | None = None,
) -> None:
    validate(source_path, functions, top)
    generated = emit_c(
        source_path,
        functions,
        top,
        variables,
        arrays,
        fixed_hz,
        project_name,
        runtime_header="anvil_wasm.h",
        minimal_includes=True,
    )
    if emit_c_path is not None:
        emit_c_path.parent.mkdir(parents=True, exist_ok=True)
        emit_c_path.write_text(generated, encoding="utf-8")
        return
    clang = _find_tool("clang")
    if clang is None:
        raise CompileError(
            "the wasm backend needs clang and wasm-ld on PATH; install LLVM or "
            "select --backend c"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = out.parent / ".anvil-cache"
    cache.mkdir(exist_ok=True)
    c_path = cache / (out.stem + ".wasm.c")
    c_path.write_text(generated, encoding="utf-8")
    command = [
        clang,
        "--target=wasm32-unknown-unknown",
        "-nostdlib",
        "-O2",
        f"-I{ROOT / 'runtime'}",
        f"-Wl,--no-entry",
        "-Wl,--export=main",
        "-Wl,--export-memory",
        "-o",
        str(out),
        str(c_path),
        str(ROOT / "runtime" / "anvil_wasm.c"),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise CompileError(
            "wasm build failed:\n" + (result.stderr or result.stdout).strip()
        )
    page = out.with_suffix(".html")
    page.write_text(
        HOST_PAGE.replace("__TITLE__", out.stem).replace("__WASM__", out.name),
        encoding="utf-8",
    )
