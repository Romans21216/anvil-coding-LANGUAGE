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
    "sin",
    "cos",
    "rnd",
    "save_number",
    "load_number",
    "save_text",
    "load_text",
    "save_exists",
    "save_delete",
    "save_error",
    "lower",
    "trim",
    "left",
    "right",
    "char",
    "contains",
    "starts_with",
    "ends_with",
    "ord",
    "chr",
    "noise",
    "fbm",
    "image_load",
    "image_width",
    "image_height",
    "image_draw",
    "image_draw_scaled",
    "image_draw_rotated",
    "image_tint",
    "image_flip",
    "image_destroy",
    "image_error",
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
context.imageSmoothingEnabled = false;
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
    const imageCache = new Map();
    const readCString = (pointer) => {
      const bytes = new Uint8Array(memory.buffer);
      let end = pointer;
      while (end < bytes.length && bytes[end] !== 0) end++;
      return utf8.decode(bytes.subarray(pointer, end));
    };
    const imports = { env: {
      write(fd, pointer, length) {
        const view = new Uint8Array(memory.buffer, pointer, length);
        const text = utf8.decode(view);
        if (fd === 2) console.error(text);
        else console.log(text);
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
      image_draw(pointer, width, height, dx, dy, dw, dh, angle, tintR, tintG, tintB, flipX, flipY) {
        const source = new Uint32Array(memory.buffer, pointer, width * height);
        const key = pointer;
        let offscreen = imageCache.get(key);
        if (!offscreen) {
          offscreen = document.createElement("canvas");
          offscreen.width = width;
          offscreen.height = height;
          const surface = offscreen.getContext("2d");
          const image = surface.createImageData(width, height);
          const out = new Uint32Array(image.data.buffer);
          for (let index = 0; index < width * height; index++) {
            const pixel = source[index];
            const a = (pixel >>> 24) & 255;
            const r = Math.round((((pixel >>> 16) & 255) * tintR) / 255);
            const g = Math.round((((pixel >>> 8) & 255) * tintG) / 255);
            const b = Math.round(((pixel & 255) * tintB) / 255);
            out[index] = ((a << 24) | (b << 16) | (g << 8) | r) >>> 0;
          }
          surface.putImageData(image, 0, 0);
          imageCache.set(key, offscreen);
        }
        context.save();
        context.translate(dx + dw / 2, dy + dh / 2);
        if (angle) context.rotate((angle * Math.PI) / 180);
        context.scale(flipX ? -1 : 1, flipY ? -1 : 1);
        context.drawImage(offscreen, -dw / 2, -dh / 2, dw, dh);
        context.restore();
      },
      present() {},
      save_read(pointer, out, capacity) {
        const value = localStorage.getItem("anvil:" + readCString(pointer));
        if (value === null) return -1;
        const bytes = new TextEncoder().encode(value);
        const view = new Uint8Array(memory.buffer, out, Math.min(bytes.length, capacity));
        view.set(bytes.subarray(0, view.length));
        return view.length;
      },
      save_write(pointer, valuePointer) {
        localStorage.setItem("anvil:" + readCString(pointer), readCString(valuePointer));
      },
      save_delete(pointer) {
        const key = "anvil:" + readCString(pointer);
        const existed = localStorage.getItem(key) !== null;
        localStorage.removeItem(key);
        return existed ? 1 : 0;
      },
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



IMAGE_LOAD = re.compile(r'image_load\(\s*"((?:\\.|[^"\\])*)"')
MAX_BAKED_IMAGE_BYTES = 4 * 1024 * 1024


def _bmp_pixels(path: pathlib.Path) -> tuple[int, int, list[int]]:
    """Decode an uncompressed 24/32-bit BMP into 0xAARRGGBB pixels."""
    data = path.read_bytes()
    if len(data) < 54 or data[:2] != b"BM":
        raise ValueError("not a BMP file")
    offset = int.from_bytes(data[10:14], "little")
    width = int.from_bytes(data[18:22], "little", signed=True)
    height = int.from_bytes(data[22:26], "little", signed=True)
    bits = int.from_bytes(data[28:30], "little")
    if bits not in (24, 32):
        raise ValueError(f"{bits}-bit BMPs are not supported (24 or 32 only)")
    if width <= 0 or height == 0 or width > 8192 or abs(height) > 8192:
        raise ValueError("the image is outside the 8,192-pixel limit")
    top_down = height < 0
    rows = abs(height)
    stride = (width * (bits // 8) + 3) & ~3
    if offset + stride * rows > len(data):
        raise ValueError("the file is too short for its declared size")
    pixels: list[int] = []
    for row in range(rows):
        source_row = row if top_down else rows - row - 1
        base = offset + source_row * stride
        for column in range(width):
            at = base + column * (bits // 8)
            blue, green, red = data[at], data[at + 1], data[at + 2]
            alpha = data[at + 3] if bits == 32 else 255
            pixels.append((alpha << 24) | (red << 16) | (green << 8) | blue)
    return width, rows, pixels


def bake_images(source_path: pathlib.Path, text: str) -> str:
    """Bake literal image_load() BMPs into C arrays the runtime can serve."""
    images: dict[str, tuple[int, int, list[int]]] = {}
    total_bytes = 0
    for match in IMAGE_LOAD.finditer(text):
        literal = match.group(1).replace("\\\\", "\\")
        if literal in images:
            continue
        target = (source_path.parent / literal).resolve()
        line = text.count("\n", 0, match.start()) + 1
        try:
            width, height, pixels = _bmp_pixels(target)
        except FileNotFoundError:
            raise CompileError(
                f"{source_path}:{line}: image_load cannot read \"{literal}\""
            ) from None
        except ValueError as error:
            raise CompileError(
                f"{source_path}:{line}: image_load \"{literal}\": {error}"
            ) from None
        total_bytes += len(pixels) * 4
        if total_bytes > MAX_BAKED_IMAGE_BYTES:
            raise CompileError(
                f"{source_path}:{line}: baked images exceed the 4 MiB budget"
            )
        images[literal] = (width, height, pixels)
    if not images:
        return "\nvoid anvil_wasm_register_images(void) {}\n"
    chunks = ["\n/* Baked images: the browser cannot read files synchronously. */"]
    for index, (_literal, (width, height, pixels)) in enumerate(images.items()):
        chunks.append(f"static const unsigned int anvil_baked_pixels_{index}[] = {{")
        row: list[str] = []
        for pixel in pixels:
            row.append(f"0x{pixel:08x}u")
            if len(row) == 12:
                chunks.append("  " + ", ".join(row) + ",")
                row = []
        if row:
            chunks.append("  " + ", ".join(row) + ",")
        chunks.append("};")
    chunks.append("static const AnvilWasmImage anvil_baked_images[] = {")
    for index, (literal, (width, height, _pixels)) in enumerate(images.items()):
        escaped = literal.replace("\\", "\\\\")
        chunks.append(f'  {{"{escaped}", {width}, {height}, anvil_baked_pixels_{index}}},')
    chunks.append("};")
    chunks.append(
        "void anvil_wasm_register_images(void) {\n"
        f"  anvil_wasm_set_images(anvil_baked_images, {len(images)});\n"
        "}\n"
    )
    return "\n".join(chunks)

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
    generated += bake_images(source_path, source_path.read_text(encoding="utf-8"))
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
