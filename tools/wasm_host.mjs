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

const bytes = fs.readFileSync(file);
const utf8 = new TextDecoder();
let memory = null;
const ops = [];
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
    present() {
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
if (record) console.log(JSON.stringify(ops));
