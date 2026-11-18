// Node host for an Anvil wasm module: wires the canvas imports to either a
// recorded command list (--record, used by tests) or no-ops, and writes text
// output to stdout. With an exported anvil_frame it runs a few frames so a
// scene program produces draws.
import fs from "node:fs";

const args = process.argv.slice(2);
const record = args.includes("--record");
const inputIndex = args.indexOf("--input");
const script = inputIndex >= 0 ? JSON.parse(args[inputIndex + 1]) : null;
const file = args.find(
  (argument, index) =>
    !argument.startsWith("--") && !(inputIndex >= 0 && index === inputIndex + 1),
);
if (!file) {
  console.error("usage: node tools/wasm_host.mjs [--record] [--input JSON] program.wasm");
  process.exit(2);
}

const saveFile = process.env.ANVIL_SAVE_FILE;
const saves = new Map();
if (saveFile && fs.existsSync(saveFile)) {
  for (const [key, value] of Object.entries(JSON.parse(fs.readFileSync(saveFile, "utf8")))) {
    saves.set(key, value);
  }
}
const persistSaves = () => {
  if (saveFile) fs.writeFileSync(saveFile, JSON.stringify(Object.fromEntries(saves)));
};

const mapFile = file.replace(/\.wasm$/, ".map.json");
let sourceMap = {};
if (fs.existsSync(mapFile)) {
  try { sourceMap = JSON.parse(fs.readFileSync(mapFile, "utf8")); } catch (error) { sourceMap = {}; }
}
const describeError = (error) => {
  const message = String((error && error.message) || error);
  if (message.startsWith("Anvil runtime error in fn(")) return message;
  const stack = String((error && error.stack) || error);
  for (const line of stack.split("\n")) {
    for (const name of Object.keys(sourceMap)) {
      if (line.indexOf("." + name) >= 0) {
        const entry = sourceMap[name];
        return "Anvil runtime error in fn(" + entry.name + ") at line " + entry.line + ": " + stack.split("\n")[0];
      }
    }
  }
  return stack;
};

const bytes = fs.readFileSync(file);
const utf8 = new TextDecoder();
let memory = null;
const ops = [];
const voices = new Map();
const triangles = [];
const texturedTriangles = [];
let nextVoice = 0;
let musicPlaying = false;
const readCString = (pointer) => {
  const view = new Uint8Array(memory.buffer);
  let end = pointer;
  while (end < view.length && view[end] !== 0) end++;
  return utf8.decode(view.subarray(pointer, end));
};

const imports = {
  env: {
    write(fd, pointer, length) {
      const view = new Uint8Array(memory.buffer, pointer, length);
      const chunk = Buffer.from(view);
      if (fd === 2) process.stderr.write(chunk);
      else process.stdout.write(chunk);
    },
    runtime_error(messagePointer, functionPointer, line) {
      throw new Error(
        "Anvil runtime error in fn(" + readCString(functionPointer) +
        ") at line " + line + ": " + readCString(messagePointer)
      );
    },
    clear(r, g, b, a) {
      ops.push(["clear", r, g, b, a]);
    },
    rect(x, y, w, h, r, g, b, a) {
      ops.push(["rect", x, y, w, h, r, g, b, a]);
    },
    circle(x, y, radius, r, g, b, a) {
      ops.push(["circle", x, y, radius, r, g, b, a]);
    },
    line(x1, y1, x2, y2, thickness, r, g, b, a) {
      ops.push(["line", x1, y1, x2, y2, thickness, r, g, b, a]);
    },
    text(x, y, pointer, length, r, g, b, a) {
      const view = new Uint8Array(memory.buffer, pointer, length);
      ops.push(["text", x, y, utf8.decode(view), r, g, b, a]);
    },
    image_draw(pointer, width, height, dx, dy, dw, dh, angle, tintR, tintG, tintB, flipX, flipY) {
      const source = new Uint32Array(memory.buffer, pointer, width * height);
      let hash = 2166136261 >>> 0;
      for (let index = 0; index < source.length; index++) {
        hash ^= source[index];
        hash = Math.imul(hash, 16777619) >>> 0;
      }
      ops.push(["image", width, height, dx, dy, dw, dh, angle, tintR, tintG, tintB, flipX, flipY, hash]);
    },
    image_region(pointer, width, height, sx, sy, sw, sh, dx, dy, dw, dh, tintR, tintG, tintB, flipX, flipY) {
      const source = new Uint32Array(memory.buffer, pointer, width * height);
      let hash = 2166136261 >>> 0;
      for (let index = 0; index < source.length; index++) {
        hash ^= source[index];
        hash = Math.imul(hash, 16777619) >>> 0;
      }
      ops.push(["image_region", width, height, sx, sy, sw, sh, dx, dy, dw, dh, tintR, tintG, tintB, flipX, flipY, hash]);
    },
    music_play(pointer, frames, channels, rate, volume, loop) {
      musicPlaying = true;
      ops.push(["music_play", frames, channels, rate, volume, loop ? 1 : 0]);
      return 1;
    },
    music_stream(urlPointer, duration, volume, loop) {
      musicPlaying = true;
      ops.push(["music_stream", readCString(urlPointer), duration, volume, loop ? 1 : 0]);
      return 1;
    },
    music_stop() {
      musicPlaying = false;
      ops.push(["music_stop"]);
    },
    music_playing() {
      return musicPlaying ? 1 : 0;
    },
    music_volume(volume) {
      ops.push(["music_volume", volume]);
    },
    music_position() {
      return 0;
    },
    sound_play(pointer, frames, channels, rate, volume, loop, group) {
      const samples = new Int16Array(memory.buffer, pointer, frames * channels);
      let peak = 0;
      for (let index = 0; index < samples.length; index++) {
        const value = Math.abs(samples[index]);
        if (value > peak) peak = value;
      }
      nextVoice += 1;
      voices.set(nextVoice, group || 1);
      ops.push(["sound_play", frames, channels, rate, volume, peak, nextVoice, loop ? 1 : 0, group || 1]);
      return nextVoice;
    },
    sound_stop(voice) {
      const existed = voices.delete(voice);
      ops.push(["sound_stop", voice, existed ? 1 : 0]);
    },
    sound_stop_all() {
      const stopped = voices.size;
      voices.clear();
      ops.push(["sound_stop_all", stopped]);
    },
    sound_group_volume(group, volume) {
      ops.push(["sound_group_volume", group, volume]);
    },
    sound_group_mute(group, muted) {
      ops.push(["sound_group_mute", group, muted]);
    },
    sound_group_stop(group) {
      let stopped = 0;
      for (const [voice, owner] of voices) {
        if (group === 0 || owner === group) {
          voices.delete(voice);
          stopped += 1;
        }
      }
      ops.push(["sound_group_stop", group, stopped]);
      return stopped;
    },
    sound_volume(voice, volume) {
      ops.push(["sound_volume", voice, volume]);
    },
    sound_pan(voice, pan) {
      ops.push(["sound_pan", voice, pan]);
    },
    sound_pitch(voice, rate) {
      ops.push(["sound_pitch", voice, rate]);
    },
    sound_active() {
      return voices.size;
    },
    triangle(x1, y1, z1, x2, y2, z2, x3, y3, z3, r, g, b, a, layer) {
      triangles.push([x1, y1, z1, x2, y2, z2, x3, y3, z3, r, g, b, a, layer]);
    },
    textured_triangle(pointer, count, pixels, width, height, layer) {
      const source = new Float64Array(memory.buffer, pointer, count * 19);
      let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
      let red = 0, green = 0, blue = 0;
      for (let triangle = 0; triangle < count; triangle++) {
        const base = triangle * 19;
        for (const corner of [0, 5, 10]) {
          const x = source[base + corner], y = source[base + corner + 1];
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
        red += source[base + 15];
        green += source[base + 16];
        blue += source[base + 17];
      }
      const color = count > 0
        ? [Math.round(red / count), Math.round(green / count), Math.round(blue / count)]
        : [0, 0, 0];
      const batch = { count, minX, maxX, minY, maxY, width, height, layer, color };
      texturedTriangles.push(batch);
      ops.push(["textured_triangle_batch", count, minX, maxX, minY, maxY,
        width, height, layer, ...color]);
    },
    sphere_impostor_available() {
      return 0;
    },
    sphere_impostor(x, y, z, radius, r, g, b, a, lightX, lightY, lightZ, focal) {
      ops.push(["sphere_impostor", x, y, z, radius, r, g, b, a, lightX, lightY, lightZ, focal]);
    },
    scene_mode(enabled) {
      ops.push(["scene_mode", enabled ? 1 : 0]);
    },
    fade(alpha) {
      ops.push(["fade", Math.round(alpha)]);
    },
    announce(pointer, length) {
      const view = new Uint8Array(memory.buffer, pointer, length);
      ops.push(["announce", utf8.decode(view)]);
    },
    present() {
      if (triangles.length || texturedTriangles.length) {
        if (process.env.ANVIL_WASM_DUMP_TRIANGLES) {
          fs.writeFileSync(
            process.env.ANVIL_WASM_DUMP_TRIANGLES,
            JSON.stringify(triangles),
          );
        }
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        for (const t of triangles) {
          for (const [x, y] of [[t[0], t[1]], [t[3], t[4]], [t[6], t[7]]]) {
            if (x < minX) minX = x;
            if (x > maxX) maxX = x;
            if (y < minY) minY = y;
            if (y > maxY) maxY = y;
          }
        }
        for (const t of texturedTriangles) {
          if (t.minX < minX) minX = t.minX;
          if (t.maxX > maxX) maxX = t.maxX;
          if (t.minY < minY) minY = t.minY;
          if (t.maxY > maxY) maxY = t.maxY;
        }
        // Colour variety alongside the bounds: a shaded sphere must not come
        // out as one flat tone, and a cast shadow shows up as a much darker
        // triangle, so both are worth recording without dumping every op.
        const tones = new Set();
        let darkest = Infinity;
        let brightest = -Infinity;
        for (const t of triangles) {
          const luminance = t[9] + t[10] + t[11];
          tones.add(t[9] + "," + t[10] + "," + t[11]);
          if (luminance < darkest) darkest = luminance;
          if (luminance > brightest) brightest = luminance;
        }
        for (const t of texturedTriangles) {
          const luminance = t.color[0] + t.color[1] + t.color[2];
          tones.add(t.color.join(","));
          if (luminance < darkest) darkest = luminance;
          if (luminance > brightest) brightest = luminance;
        }
        ops.push([
          "triangles",
          triangles.length + texturedTriangles.reduce((total, item) => total + item.count, 0),
          Math.round(minX),
          Math.round(maxX),
          Math.round(minY),
          Math.round(maxY),
          tones.size,
          Math.round(darkest),
          Math.round(brightest),
        ]);
        triangles.length = 0;
        texturedTriangles.length = 0;
      }
      ops.push(["present"]);
    },
    save_read(pointer, out, capacity) {
      const value = saves.get(readCString(pointer));
      if (value === undefined) return -1;
      const encoded = Buffer.from(value, "utf8");
      const view = new Uint8Array(memory.buffer, out, Math.min(encoded.length, capacity));
      view.set(encoded.subarray(0, view.length));
      return view.length;
    },
    save_write(pointer, valuePointer) {
      saves.set(readCString(pointer), readCString(valuePointer));
      persistSaves();
    },
    save_delete(pointer) {
      const existed = saves.delete(readCString(pointer));
      persistSaves();
      return existed ? 1 : 0;
    },
  },
};

const module = await WebAssembly.compile(bytes);
const instance = await WebAssembly.instantiate(module, imports);
memory = instance.exports.memory;
try {
  if (instance.exports.main) instance.exports.main();
  if (script) {
    for (const step of script) {
      if (step[0] === "frame") instance.exports.anvil_frame(step[1] ?? 1000 / 60);
      else if (step[0] === "key") instance.exports.anvil_key(step[1], step[2]);
      else if (step[0] === "mouse") instance.exports.anvil_mouse(step[1], step[2]);
      else if (step[0] === "button") instance.exports.anvil_mouse_button(step[1], step[2]);
      else if (step[0] === "wheel") instance.exports.anvil_wheel(step[1]);
    }
  } else if (instance.exports.anvil_frame) {
    const frames = Number(process.env.ANVIL_WASM_FRAMES ?? "3");
    for (let index = 0; index < frames; index++) {
      instance.exports.anvil_frame(1000 / 60);
    }
  }
} catch (error) {
  console.error(describeError(error));
  process.exit(1);
}
if (record) console.log(JSON.stringify(ops));
