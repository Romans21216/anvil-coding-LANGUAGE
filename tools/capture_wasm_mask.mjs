import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const root = path.resolve(process.argv[2] || ".");
const page = process.argv[3] || "program.html";
const captureFrames = Number.parseInt(process.env.ANVIL_WASM_CAPTURE_FRAMES || "1", 10);
if (!Number.isInteger(captureFrames) || captureFrames < 1 || captureFrames > 60)
  throw new Error("ANVIL_WASM_CAPTURE_FRAMES must be between 1 and 60");
const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
if (!fs.existsSync(path.join(root, page))) throw new Error(`page not found: ${page}`);

const contentTypes = {
  ".html": "text/html",
  ".wasm": "application/wasm",
  ".gltf": "model/gltf+json",
  ".glb": "model/gltf-binary",
  ".bin": "application/octet-stream",
};
const server = http.createServer((req, res) => {
  let target;
  try {
    target = path.resolve(root, `.${decodeURIComponent(new URL(req.url, "http://localhost").pathname)}`);
  } catch {
    res.writeHead(400).end();
    return;
  }
  if (target !== root && !target.startsWith(`${root}${path.sep}`)) {
    res.writeHead(403).end();
    return;
  }
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
    res.writeHead(404).end();
    return;
  }
  res.writeHead(200, { "content-type": contentTypes[path.extname(target)] || "application/octet-stream" });
  fs.createReadStream(target).pipe(res);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));

const temp = fs.mkdtempSync(path.join(os.tmpdir(), "anvil-wasm-mask-"));
const chrome = spawn(chromePath, [
  "--headless=new", "--no-sandbox", "--enable-unsafe-swiftshader",
  "--use-gl=angle", "--use-angle=swiftshader-webgl", "--enable-webgl",
  "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
  "--remote-debugging-port=0", `--user-data-dir=${path.join(temp, "profile")}`,
  "about:blank",
], { stdio: "ignore", windowsHide: true });

async function pollJson(url, predicate = (value) => value) {
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        const value = await response.json();
        const match = predicate(value);
        if (match) return match;
      }
    } catch {}
    await delay(100);
  }
  throw new Error(`timed out waiting for ${url}`);
}

let nextId = 0;
async function connect(target) {
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  const pending = new Map();
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  return { ws, send };
}

try {
  const portFile = path.join(temp, "profile", "DevToolsActivePort");
  let devtoolsPort = 0;
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      devtoolsPort = Number(fs.readFileSync(portFile, "utf8").split(/\r?\n/, 1)[0]);
      if (Number.isInteger(devtoolsPort) && devtoolsPort > 0) break;
    } catch {}
    await delay(100);
  }
  if (!devtoolsPort) throw new Error("Chrome did not create a readable DevTools port file");
  await pollJson(`http://127.0.0.1:${devtoolsPort}/json/version`);
  const url = `http://127.0.0.1:${server.address().port}/${encodeURIComponent(page)}`;
  const response = await fetch(`http://127.0.0.1:${devtoolsPort}/json/new?${url}`, { method: "PUT" });
  if (!response.ok) throw new Error(`Chrome page creation failed: ${response.status}`);
  const cdp = await connect(await response.json());
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", { width: 960, height: 600, deviceScaleFactor: 1, mobile: false });
  for (let attempt = 0; attempt < 100; attempt++) {
    const ready = await cdp.send("Runtime.evaluate", {
      expression: "!!(window.anvil && window.anvil.exports.anvil_frame && document.getElementById('screen'))",
      returnByValue: true,
    });
    if (ready.result.value) break;
    if (attempt === 99) throw new Error("wasm page did not initialize");
    await delay(50);
  }
  const evaluated = await cdp.send("Runtime.evaluate", {
    expression: `(() => {
      const canvas = document.getElementById('screen');
      const context = canvas.getContext('2d');
      const gl = document.createElement('canvas').getContext('webgl');
      if (!gl) throw new Error('WebGL unavailable');
      const frames = [];
      for (let frame = 0; frame < ${captureFrames}; frame++) {
        window.anvil.exports.anvil_frame(16.6667);
        const pixels = context.getImageData(0, 0, 960, 600).data;
        let rgbaBinary = '';
        for (let start = 0; start < pixels.length; start += 8192)
          rgbaBinary += String.fromCharCode(...pixels.subarray(start, start + 8192));
        frames.push(btoa(rgbaBinary));
      }
      const last = Uint8Array.from(atob(frames[frames.length - 1]), (char) => char.charCodeAt(0));
      const packed = new Uint8Array(Math.ceil(960 * 600 / 8));
      for (let pixel = 0; pixel < 960 * 600; pixel++) {
        const offset = pixel * 4;
        if (last[offset] > 2 || last[offset + 1] > 2 || last[offset + 2] > 2)
          packed[pixel >> 3] |= 1 << (pixel & 7);
      }
      let binary = '';
      for (let start = 0; start < packed.length; start += 8192)
        binary += String.fromCharCode(...packed.subarray(start, start + 8192));
      return { width: 960, height: 600, mask: btoa(binary), rgba: frames[frames.length - 1], frames };
    })()` ,
    returnByValue: true,
  });
  if (evaluated.exceptionDetails) throw new Error(JSON.stringify(evaluated.exceptionDetails));
  process.stdout.write(JSON.stringify(evaluated.result.value) + "\n");
  cdp.ws.close();
} finally {
  if (process.platform === "win32") spawnSync("taskkill", ["/PID", String(chrome.pid), "/T", "/F"], { stdio: "ignore" });
  else chrome.kill();
  server.close();
  try { fs.rmSync(temp, { recursive: true, force: true }); } catch {}
}
