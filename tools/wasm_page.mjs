// Drive a generated Anvil wasm host page without a browser.
//
// The page is a thin shell around the module: it fetches the .wasm, wires
// keyboard/mouse/focus events and calls anvil_frame from requestAnimationFrame.
// This harness runs that same script against small DOM stubs so input plumbing
// can be tested where it actually lives, instead of only in the module.
//
//   node tools/wasm_page.mjs page.html '[["frame"],["keydown","KeyA"],["blur"],["frame"]]'
//
// Actions: frame [ms], keydown <code>, keyup <code>, blur, visibility <bool>,
// mousedown <button>, mouseup <button>, wheel <delta>.
// The page's console output goes to stdout; page errors go to stderr.

import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";

const [, , pageArg, scriptArg] = process.argv;
if (!pageArg) {
  console.error("usage: node tools/wasm_page.mjs <page.html> [action-json]");
  process.exit(2);
}
const pagePath = path.resolve(pageArg);
const html = fs.readFileSync(pagePath, "utf8");
const script = html.slice(html.lastIndexOf("<script>") + 8, html.lastIndexOf("</script>"));
const actions = scriptArg ? JSON.parse(scriptArg) : [];

const output = [];
const errors = [];
const listeners = new Map();
const canvasListeners = new Map();
let frameCallback = null;
let frameTime = 0;

const addListener = (map) => (type, fn) => {
  if (!map.has(type)) map.set(type, []);
  map.get(type).push(fn);
};

function makeContext2d() {
  return new Proxy(
    { canvas: null },
    {
      get(target, property) {
        if (property in target) return target[property];
        if (property === "measureText")
          return (text) => ({ width: String(text).length * 8 });
        if (property === "createImageData" || property === "getImageData")
          return (w, h) => ({
            width: w,
            height: h,
            data: new Uint8ClampedArray(Math.max(1, w * h * 4)),
          });
        return () => {};
      },
      set(target, property, value) {
        target[property] = value;
        return true;
      },
    },
  );
}

const context2d = makeContext2d();
const screen = {
  width: 960,
  height: 600,
  addEventListener: addListener(canvasListeners),
  getContext: (kind) => (kind === "2d" ? context2d : null),
  getBoundingClientRect: () => ({ left: 0, top: 0, width: 960, height: 600 }),
};
const out = { textContent: "" };
const document = {
  hidden: false,
  getElementById: (id) => (id === "screen" ? screen : out),
  createElement: () => ({
    width: 0,
    height: 0,
    getContext: (kind) => (kind === "2d" ? makeContext2d() : null),
  }),
  addEventListener: addListener(listeners),
};
const sandbox = {
  console: {
    log: (...parts) => output.push(parts.join(" ")),
    error: (...parts) => errors.push(parts.join(" ")),
  },
  document,
  location: { protocol: "http:", search: "" },
  performance: { now: () => frameTime },
  requestAnimationFrame: (fn) => {
    frameCallback = fn;
    return 1;
  },
  cancelAnimationFrame: () => {},
  fetch: async (url) => ({
    arrayBuffer: async () => {
      const bytes = fs.readFileSync(path.join(path.dirname(pagePath), String(url)));
      return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    },
  }),
  localStorage: {
    store: new Map(),
    getItem(key) {
      return this.store.has(key) ? this.store.get(key) : null;
    },
    setItem(key, value) {
      this.store.set(key, String(value));
    },
    removeItem(key) {
      this.store.delete(key);
    },
  },
  TextDecoder,
  TextEncoder,
  URLSearchParams,
  WebAssembly,
  Uint8Array,
  Uint32Array,
  Float32Array,
  Int16Array,
  Uint8ClampedArray,
  Math,
  Date,
  setTimeout,
  clearTimeout,
  queueMicrotask,
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.window.addEventListener = addListener(listeners);
sandbox.AudioContext = undefined; // no audio in the harness

vm.createContext(sandbox);
vm.runInContext(script, sandbox, { filename: "host-page.js" });

const tick = async () => new Promise((resolve) => setTimeout(resolve, 0));
for (let attempt = 0; attempt < 500 && !sandbox.window.anvil; attempt++) {
  await tick();
  if (sandbox.window.anvil) break;
}
if (!sandbox.window.anvil) {
  console.error("the page did not finish loading its module");
  process.exit(1);
}

const fire = (map, type, event) => {
  for (const fn of map.get(type) || []) fn(event);
};
const keyEvent = (code) => ({
  code,
  keyCode: code.startsWith("Key") ? code.charCodeAt(3) : 0,
  preventDefault() {},
});

for (const [action, value] of actions) {
  if (action === "frame") {
    frameTime += Number(value ?? 1000 / 60);
    if (frameCallback) {
      const callback = frameCallback;
      frameCallback = null;
      callback(frameTime);
    }
  } else if (action === "keydown") {
    fire(listeners, "keydown", keyEvent(value));
  } else if (action === "keyup") {
    fire(listeners, "keyup", keyEvent(value));
  } else if (action === "blur") {
    fire(listeners, "blur", {});
  } else if (action === "visibility") {
    document.hidden = Boolean(value);
    fire(listeners, "visibilitychange", {});
  } else if (action === "mousedown" || action === "mouseup") {
    fire(canvasListeners, action, { button: Number(value ?? 0) });
  } else if (action === "wheel") {
    fire(canvasListeners, "wheel", { deltaY: Number(value ?? 0) });
  } else {
    console.error("unknown action: " + action);
    process.exit(2);
  }
  await tick();
}

await tick();
process.stdout.write(output.join(""));
if (out.textContent) process.stderr.write(out.textContent + "\n");
for (const line of errors) process.stderr.write(line + "\n");
process.exit(errors.length ? 1 : 0);
