// Node host for an Anvil wasm module: wires the canvas imports to either a
// recorded command list (--record, used by tests) or no-ops, and writes text
// output to stdout. With an exported anvil_frame it runs a few frames so a
// scene program produces draws.
import fs from "node:fs";

const args = process.argv.slice(2);
const record = args.includes("--record");
const file = args.find((argument) => !argument.startsWith("--"));
if (!file) {
  console.error("usage: node tools/wasm_host.mjs [--record] program.wasm");
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
if (instance.exports.anvil_frame) {
  const frames = Number(process.env.ANVIL_WASM_FRAMES ?? "3");
  for (let index = 0; index < frames; index++) {
    instance.exports.anvil_frame(1000 / 60);
  }
}
if (record) console.log(JSON.stringify(ops));
