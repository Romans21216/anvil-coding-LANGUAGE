// Minimal Node host for an Anvil wasm program: wires env.write to stdout and
// calls the exported main(). Used by tests and `anvil.py --backend wasm --run`.
import fs from "node:fs";

const file = process.argv[2];
if (!file) {
  console.error("usage: node tools/wasm_host.mjs program.wasm");
  process.exit(2);
}

const bytes = fs.readFileSync(file);
let memory = null;
const imports = {
  env: {
    write(fd, pointer, length) {
      const view = new Uint8Array(memory.buffer, pointer, length);
      process.stdout.write(Buffer.from(view));
    },
  },
};

const module = await WebAssembly.compile(bytes);
const instance = await WebAssembly.instantiate(module, imports);
memory = instance.exports.memory;
if (typeof instance.exports.main === "function") {
  instance.exports.main();
} else {
  console.error("the module does not export main()");
  process.exit(1);
}
