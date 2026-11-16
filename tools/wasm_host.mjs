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

const bytes = fs.readFileSync(file);
const utf8 = new TextDecoder();
let memory = null;
const ops = [];
const imports = {
  env: {
    write(fd, pointer, length) {
      const view = new Uint8Array(memory.buffer, pointer, length);
      process.stdout.write(Buffer.from(view));
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
    present() {
      ops.push(["present"]);
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
