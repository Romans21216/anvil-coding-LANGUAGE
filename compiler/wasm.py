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
    "image_draw_region",
    "image_tint",
    "image_flip",
    "image_destroy",
    "image_error",
    "sound_load",
    "sound_play",
    "sound_stop",
    "sound_stop_all",
    "sound_volume",
    "sound_active",
    "sound_destroy",
    "sound_error",
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
    const audioState = { ctx: null, voices: new Map(), nextVoice: 0, active: 0 };
    const audioContext = () => {
      if (!audioState.ctx) {
        const Ctor = window.AudioContext || window.webkitAudioContext;
        if (!Ctor) return null;
        audioState.ctx = new Ctor();
      }
      if (audioState.ctx.state === "suspended") audioState.ctx.resume();
      return audioState.ctx;
    };
    const resumeAudio = () => {
      if (audioState.ctx && audioState.ctx.state === "suspended") {
        audioState.ctx.resume();
      }
    };
    window.addEventListener("keydown", resumeAudio);
    window.addEventListener("pointerdown", resumeAudio);
    window.anvilAudio = () => ({
      active: audioState.active,
      voices: audioState.voices.size,
      state: audioState.ctx ? audioState.ctx.state : "none",
      sampleRate: audioState.ctx ? audioState.ctx.sampleRate : 0,
    });
    const tintedSurface = (pointer, width, height, tintR, tintG, tintB) => {
      const key = pointer + ":" + tintR + ":" + tintG + ":" + tintB;
      let offscreen = imageCache.get(key);
      if (offscreen) return offscreen;
      const source = new Uint32Array(memory.buffer, pointer, width * height);
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
      return offscreen;
    };
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
        const offscreen = tintedSurface(pointer, width, height, tintR, tintG, tintB);
        context.save();
        context.translate(dx + dw / 2, dy + dh / 2);
        if (angle) context.rotate((angle * Math.PI) / 180);
        context.scale(flipX ? -1 : 1, flipY ? -1 : 1);
        context.drawImage(offscreen, -dw / 2, -dh / 2, dw, dh);
        context.restore();
      },
      image_region(pointer, width, height, sx, sy, sw, sh, dx, dy, dw, dh, tintR, tintG, tintB, flipX, flipY) {
        const offscreen = tintedSurface(pointer, width, height, tintR, tintG, tintB);
        context.save();
        context.translate(dx + dw / 2, dy + dh / 2);
        context.scale(flipX ? -1 : 1, flipY ? -1 : 1);
        context.drawImage(offscreen, sx, sy, sw, sh, -dw / 2, -dh / 2, dw, dh);
        context.restore();
      },
      sound_play(pointer, frames, channels, rate, volume) {
        const ctx = audioContext();
        if (!ctx || frames <= 0) return 0;
        const samples = new Int16Array(memory.buffer, pointer, frames * channels);
        const buffer = ctx.createBuffer(channels, frames, rate);
        for (let channel = 0; channel < channels; channel++) {
          const data = buffer.getChannelData(channel);
          for (let frame = 0; frame < frames; frame++) {
            data[frame] = samples[frame * channels + channel] / 32768;
          }
        }
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        const gain = ctx.createGain();
        gain.gain.value = volume;
        source.connect(gain).connect(ctx.destination);
        audioState.nextVoice += 1;
        const voice = audioState.nextVoice;
        audioState.voices.set(voice, { source, gain });
        audioState.active += 1;
        source.onended = () => {
          if (audioState.voices.delete(voice)) {
            audioState.active = Math.max(0, audioState.active - 1);
          }
        };
        source.start();
        return voice;
      },
      sound_stop(voice) {
        const entry = audioState.voices.get(voice);
        if (!entry) return;
        try { entry.source.stop(); } catch (error) { /* already ended */ }
      },
      sound_stop_all() {
        for (const entry of audioState.voices.values()) {
          try { entry.source.stop(); } catch (error) { /* already ended */ }
        }
        audioState.voices.clear();
        audioState.active = 0;
      },
      sound_volume(voice, volume) {
        const entry = audioState.voices.get(voice);
        if (entry) entry.gain.gain.value = volume;
      },
      sound_active() {
        return audioState.active;
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
    if bits not in (8, 24, 32):
        raise ValueError(f"{bits}-bit BMPs are not supported (8, 24 or 32 only)")
    if width <= 0 or height == 0 or width > 8192 or abs(height) > 8192:
        raise ValueError("the image is outside the 8,192-pixel limit")
    header_size = int.from_bytes(data[14:18], "little")
    palette: list[tuple[int, int, int]] = []
    if bits == 8:
        count = int.from_bytes(data[46:50], "little") or 256
        base = 14 + header_size
        for index in range(count):
            at = base + index * 4
            if at + 3 >= len(data):
                raise ValueError("the palette is truncated")
            palette.append((data[at + 2], data[at + 1], data[at]))
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
            if bits == 8:
                index = data[at]
                if index >= len(palette):
                    raise ValueError("a pixel index is outside the palette")
                red, green, blue = palette[index]
                alpha = 255
            else:
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

SOUND_LOAD = re.compile(r'sound_load\(\s*"((?:\\.|[^"\\])*)"')
MAX_BAKED_SOUND_BYTES = 8 * 1024 * 1024


def _wav_pcm(path: pathlib.Path) -> tuple[int, int, int, list[int]]:
    """Decode a PCM WAV into (channels, rate, frames, interleaved int16)."""
    data = path.read_bytes()
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF WAVE file")
    position = 12
    fmt = None
    payload = None
    while position + 8 <= len(data):
        chunk = data[position : position + 4]
        size = int.from_bytes(data[position + 4 : position + 8], "little")
        body = data[position + 8 : position + 8 + size]
        position += 8 + size + (size & 1)
        if chunk == b"fmt ":
            fmt = body
        elif chunk == b"data":
            payload = body
        if fmt is not None and payload is not None:
            break
    if fmt is None or payload is None or len(fmt) < 16:
        raise ValueError("the file has no fmt or data chunk")
    tag = int.from_bytes(fmt[0:2], "little")
    channels = int.from_bytes(fmt[2:4], "little")
    rate = int.from_bytes(fmt[4:8], "little")
    bits = int.from_bytes(fmt[14:16], "little")
    if tag not in (1, 0xFFFE):
        raise ValueError("compressed WAVs are not supported (PCM only)")
    if channels not in (1, 2):
        raise ValueError("only mono or stereo WAVs are supported")
    if bits not in (8, 16):
        raise ValueError("only 8- or 16-bit PCM is supported")
    if not 8000 <= rate <= 192000:
        raise ValueError("the sample rate is outside 8,000-192,000")
    frame_bytes = channels * (bits // 8)
    frames = len(payload) // frame_bytes
    if frames == 0:
        raise ValueError("the WAV holds no samples")
    samples: list[int] = []
    for index in range(frames * channels):
        if bits == 8:
            samples.append((payload[index] - 128) << 8)
        else:
            at = index * 2
            samples.append(int.from_bytes(payload[at : at + 2], "little", signed=True))
    return channels, rate, frames, samples


def bake_sounds(source_path: pathlib.Path, text: str) -> str:
    """Bake literal sound_load() WAVs into C arrays the runtime can serve."""
    sounds: dict[str, tuple[int, int, int, list[int]]] = {}
    total = 0
    for match in SOUND_LOAD.finditer(text):
        literal = match.group(1).replace("\\\\", "\\")
        if literal in sounds:
            continue
        target = (source_path.parent / literal).resolve()
        line = text.count("\n", 0, match.start()) + 1
        try:
            channels, rate, frames, samples = _wav_pcm(target)
        except FileNotFoundError:
            raise CompileError(
                f'{source_path}:{line}: sound_load cannot read "{literal}"'
            ) from None
        except ValueError as error:
            raise CompileError(
                f'{source_path}:{line}: sound_load "{literal}": {error}'
            ) from None
        total += len(samples) * 2
        if total > MAX_BAKED_SOUND_BYTES:
            raise CompileError(
                f"{source_path}:{line}: baked sounds exceed the 8 MiB budget"
            )
        sounds[literal] = (channels, rate, frames, samples)
    chunks: list[str] = ["\n/* Baked sounds: the browser cannot stream from disk. */"]
    for index, (_literal, (_channels, _rate, _frames, samples)) in enumerate(
        sounds.items()
    ):
        chunks.append(f"static const short anvil_baked_sound_{index}[] = {{")
        row: list[str] = []
        for sample in samples:
            row.append(str(sample))
            if len(row) == 16:
                chunks.append("  " + ", ".join(row) + ",")
                row = []
        if row:
            chunks.append("  " + ", ".join(row) + ",")
        chunks.append("};")
    if sounds:
        chunks.append("static const AnvilWasmSound anvil_baked_sounds[] = {")
        for index, (literal, (channels, rate, frames, _samples)) in enumerate(
            sounds.items()
        ):
            escaped = literal.replace("\\", "\\\\")
            chunks.append(
                f'  {{"{escaped}", {channels}, {rate}, {frames}, anvil_baked_sound_{index}}},'
            )
        chunks.append("};")
    chunks.append(
        "void anvil_wasm_register_sounds(void) {\n"
        f"  anvil_wasm_set_sounds(anvil_baked_sounds, {len(sounds)});\n"
        "}\n"
        if sounds
        else "void anvil_wasm_register_sounds(void) {}\n"
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
    source_text = source_path.read_text(encoding="utf-8")
    generated += bake_images(source_path, source_text)
    generated += bake_sounds(source_path, source_text)
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
