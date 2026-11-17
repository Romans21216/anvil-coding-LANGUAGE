import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const root = process.cwd();
const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const instanceCount = 1000;
const triangleCount = 16;
const warmupFrames = Number(process.env.ANVIL_BENCH_WARMUP || 60);
const sampleFrames = Number(process.env.ANVIL_BENCH_SAMPLES || 240);
const trials = Number(process.env.ANVIL_BENCH_TRIALS || 3);
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "anvil-morph-cull-bench-"));
const children = [];
const files = new Map();
let server;
let debugPort;

function writeModel(file) {
  const positions = [];
  const indices = [];
  const deltas = [];
  for (let i = 0; i < triangleCount; i++) {
    positions.push(-0.3, -0.3, 0, 0.3, -0.3, 0, 0, 0.3, 0);
    const first = i * 3;
    indices.push(first, first + 1, first + 2);
    deltas.push(0.01, 0, 0, 0.01, 0, 0, 0.01, 0, 0);
  }
  const chunks = [Buffer.from(new Float32Array(positions).buffer)];
  const indexBytes = Buffer.from(new Uint16Array(indices).buffer);
  const deltaBytes = Buffer.from(new Float32Array(deltas).buffer);
  const positionBytes = chunks[0];
  chunks.push(indexBytes, deltaBytes);
  const binary = Buffer.concat(chunks);
  const doc = {
    asset: { version: "2.0" }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
    meshes: [{ weights: [0], primitives: [{ attributes: { POSITION: 0 }, indices: 1, material: 0, targets: [{ POSITION: 2 }] }] }],
    materials: [{ pbrMetallicRoughness: { baseColorFactor: [0.8, 0.3, 0.1, 1] } }],
    buffers: [{ uri: `data:application/octet-stream;base64,${binary.toString("base64")}`, byteLength: binary.length }],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: positionBytes.length },
      { buffer: 0, byteOffset: positionBytes.length, byteLength: indexBytes.length },
      { buffer: 0, byteOffset: positionBytes.length + indexBytes.length, byteLength: deltaBytes.length },
    ],
    accessors: [
      { bufferView: 0, componentType: 5126, count: triangleCount * 3, type: "VEC3" },
      { bufferView: 1, componentType: 5123, count: triangleCount * 3, type: "SCALAR" },
      { bufferView: 2, componentType: 5126, count: triangleCount * 3, type: "VEC3" },
    ],
  };
  fs.writeFileSync(file, JSON.stringify(doc));
}

function writeProgram(directory, culling) {
  const source = path.join(directory, "bench.ANVL");
  const output = path.join(directory, "bench.wasm");
  fs.writeFileSync(source, [
    "scene 3d", "camera perspective 0 0 12", "camera fov(70)",
    "fn(draw)", `  set var(culling) = mesh_culling(${culling ? 1 : 0})`,
    `  for local(i) = 0 to ${instanceCount - 1}`,
    '    set var(ok) = model_draw("mesh.gltf", 200, 0, 0, 1, 0, 0, 0)',
    "  end", "end", "",
  ].join("\n"));
  const built = spawnSync("python", [path.join(root, "compiler/anvil.py"), source, "--backend", "wasm", "-o", output], { encoding: "utf8", timeout: 300000 });
  if (built.status !== 0) throw new Error(`compile culling=${culling} failed: ${built.stdout}\n${built.stderr}`);
  const pageName = culling ? "culled" : "unculled";
  const html = fs.readFileSync(output.replace(/\.wasm$/, ".html"), "utf8").replaceAll("bench.wasm", `${pageName}.wasm`);
  files.set(`/${pageName}.html`, Buffer.from(html));
  files.set(`/${pageName}.wasm`, fs.readFileSync(output));
}

function connect(target) {
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  return new Promise((resolve, reject) => {
    ws.onopen = () => {
      const pending = new Map();
      let next = 0;
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (!message.id || !pending.has(message.id)) return;
        const entry = pending.get(message.id); pending.delete(message.id);
        if (message.error) entry.reject(new Error(message.error.message)); else entry.resolve(message.result);
      };
      resolve({ ws, send(method, params = {}) { return new Promise((res, rej) => { const id = ++next; pending.set(id, { resolve: res, reject: rej }); ws.send(JSON.stringify({ id, method, params })); }); } });
    };
    ws.onerror = reject;
  });
}

async function waitFor(predicate, label) {
  for (let i = 0; i < 100; i++) {
    try { const response = await fetch(`http://127.0.0.1:${debugPort}/json/list`); const tabs = await response.json(); const target = tabs.find(predicate); if (target) return target; } catch {}
    await delay(100);
  }
  throw new Error(`timed out waiting for ${label}`);
}

try {
  writeModel(path.join(temp, "mesh.gltf"));
  for (const culling of [true, false]) {
    const directory = path.join(temp, culling ? "culled" : "unculled");
    fs.mkdirSync(directory);
    fs.copyFileSync(path.join(temp, "mesh.gltf"), path.join(directory, "mesh.gltf"));
    writeProgram(directory, culling);
  }
  server = http.createServer((req, res) => {
    const body = files.get(new URL(req.url, "http://localhost").pathname);
    if (!body) { res.writeHead(404).end(); return; }
    res.writeHead(200, { "content-type": req.url.endsWith(".wasm") ? "application/wasm" : "text/html" });
    res.end(body);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  const profile = path.join(temp, "profile");
  const chrome = spawn(chromePath, ["--headless=new", "--no-sandbox", "--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader-webgl", "--enable-webgl", "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore", windowsHide: true });
  children.push(chrome);
  const portFile = path.join(profile, "DevToolsActivePort");
  for (let i = 0; i < 100 && !fs.existsSync(portFile); i++) await delay(100);
  if (!fs.existsSync(portFile)) throw new Error("Chrome did not create its DevTools port file");
  debugPort = Number(fs.readFileSync(portFile, "utf8").split(/\r?\n/, 1)[0]);
  const version = await (await fetch(`http://127.0.0.1:${debugPort}/json/version`)).json();
  const results = [];
  const modes = Array.from({ length: trials }, (_, trial) => trial % 2 ? [false, true] : [true, false]).flat();
  for (const culling of modes) {
    const name = culling ? "culled" : "unculled";
    const response = await fetch(`http://127.0.0.1:${debugPort}/json/new?http://127.0.0.1:${port}/${name}.html?trial=${results.length}`, { method: "PUT" });
    if (!response.ok) throw new Error(`Chrome page creation failed: ${response.status}`);
    const target = await response.json();
    const cdp = await connect(target);
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 960, height: 600, deviceScaleFactor: 1, mobile: false });
    const readyTarget = await waitFor((tab) => tab.id === target.id, `${name} tab`);
    for (let attempt = 0; attempt < 100; attempt++) {
      const ready = await cdp.send("Runtime.evaluate", { expression: "!!(window.anvil && window.anvil.exports.anvil_frame)", returnByValue: true });
      if (ready.result.value) break;
      if (attempt === 99) throw new Error(`${name} wasm did not initialize: ${readyTarget.url}`);
      await delay(50);
    }
    const measured = await cdp.send("Runtime.evaluate", {
      expression: `(() => { const f=window.anvil.exports.anvil_frame; for(let i=0;i<${warmupFrames};i++) f(16.6667); const gl=document.createElement('canvas').getContext('webgl'); if(!gl) throw new Error('WebGL unavailable'); const samples=[]; for(let i=0;i<${sampleFrames};i++){const start=performance.now();f(16.6667);samples.push(performance.now()-start);} samples.sort((a,b)=>a-b); return {p50_ms:samples[Math.floor(samples.length*.50)],p95_ms:samples[Math.ceil(samples.length*.95)-1],max_ms:samples[samples.length-1]}; })()`,
      returnByValue: true,
    });
    if (measured.exceptionDetails) throw new Error(JSON.stringify(measured.exceptionDetails));
    results.push({ culling, trial: Math.floor(results.length / 2), ...measured.result.value });
    cdp.ws.close();
  }
  const summarize = (enabled) => {
    const rows = results.filter((row) => row.culling === enabled);
    return { p50_ms: rows.map((row) => row.p50_ms).sort((a,b)=>a-b)[Math.floor(rows.length/2)], p95_ms: Math.max(...rows.map((row) => row.p95_ms)), max_ms: Math.max(...rows.map((row) => row.max_ms)) };
  };
  const culled = summarize(true), unculled = summarize(false);
  const report = { chrome: version.Browser, platform: { os: os.platform(), release: os.release(), cpu: os.cpus()[0]?.model }, instances: instanceCount, triangles_per_instance: triangleCount, warmup_frames: warmupFrames, measured_frames_per_trial: sampleFrames, trials, culled, unculled, p95_improvement_percent: (1 - culled.p95_ms / unculled.p95_ms) * 100, results };
  const output = process.env.ANVIL_BENCH_OUTPUT || path.join(os.tmpdir(), "anvil_wasm_morph_culling_chromium.json");
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(report, null, 2));
  process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  if (!(culled.p95_ms < unculled.p95_ms)) process.exitCode = 1;
} finally {
  for (const child of children) if (process.platform === "win32") spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" }); else child.kill();
  server?.close();
  try { fs.rmSync(temp, { recursive: true, force: true }); } catch {}
}
