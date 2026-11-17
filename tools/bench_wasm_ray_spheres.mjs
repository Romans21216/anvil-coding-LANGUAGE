import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const root = process.cwd();
const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
let port;
const sampleCount = 180;
const warmupCount = 45;
const trials = 3;
const budgets = {
  p95_ms: { 1: 6.0, 8: 7.0, 32: 8.0 },
  max_frame_ms: 16.7,
  heap_peak_mb: { 1: 10.0, 8: 35.0, 32: 100.0 },
};
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "anvil-wasm-ray-"));
const children = [];
const files = {};

function source(count) {
  const cols = count === 1 ? 1 : count === 8 ? 4 : 8;
  const rows = count / cols;
  const xo = (cols - 1) * 0.65;
  const yo = (rows - 1) * 0.65;
  return [
    "scene 3d", "camera perspective 0 0 12", "camera fov(70)",
    "clear rgba(11, 16, 27, 255)", "", "fn(draw)",
    `  for local(x) = 0 to ${cols - 1}`,
    `    for local(y) = 0 to ${rows - 1}`,
    `      display ray_sphere(local(x) * 1.3 - ${xo}, local(y) * 1.3 - ${yo}, -1, 0.45) -rgb(172, 106, 255)`,
    "    end", "  end", "end", "",
  ].join("\n");
}

for (const count of [1, 8, 32]) {
  const src = path.join(temp, `spheres_${count}.ANVL`);
  const out = path.join(temp, `spheres_${count}.wasm`);
  fs.writeFileSync(src, source(count));
  const built = spawnSync("python", [path.join(root, "compiler/anvil.py"), src, "--backend", "wasm", "-o", out], { encoding: "utf8", timeout: 300000 });
  if (built.status !== 0) throw new Error(`compile ${count} failed: ${built.stderr}`);
  files[`/spheres_${count}.html`] = fs.readFileSync(out.replace(/\.wasm$/, ".html"));
  files[`/spheres_${count}.wasm`] = fs.readFileSync(out);
}

for (const order of ["far_near", "near_far"]) {
  const pair = {
    far: "display ray_sphere(0, 0, 0, 1.5) -rgb(30, 70, 240)",
    near: "display ray_sphere(0, 0, 1, 1.5) -rgb(240, 50, 30)",
  };
  const draws = order === "far_near" ? [pair.far, pair.near] : [pair.near, pair.far];
  const src = path.join(temp, `depth_${order}.ANVL`);
  const out = path.join(temp, `depth_${order}.wasm`);
  fs.writeFileSync(src, ["scene 3d", "camera perspective 0 0 8", "", "fn(draw)", ...draws.map((line) => `  ${line}`), "end", ""].join("\n"));
  const built = spawnSync("python", [path.join(root, "compiler/anvil.py"), src, "--backend", "wasm", "-o", out], { encoding: "utf8", timeout: 300000 });
  if (built.status !== 0) throw new Error(`compile depth ${order} failed: ${built.stderr}`);
  files[`/depth_${order}.html`] = fs.readFileSync(out.replace(/\.wasm$/, ".html"));
  files[`/depth_${order}.wasm`] = fs.readFileSync(out);
}

const server = http.createServer((req, res) => {
  const body = files[new URL(req.url, "http://localhost").pathname];
  if (!body) { res.writeHead(404).end(); return; }
  res.writeHead(200, { "content-type": req.url.endsWith(".wasm") ? "application/wasm" : "text/html" });
  res.end(body);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const httpPort = server.address().port;
const userData = path.join(temp, "profile");
const chrome = spawn(chromePath, [
  "--headless=new", "--no-sandbox", "--enable-unsafe-swiftshader",
  "--use-gl=angle", "--use-angle=swiftshader-webgl", "--enable-webgl",
  "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
  "--js-flags=--expose-gc", "--remote-debugging-port=0",
  `--user-data-dir=${userData}`, "about:blank",
], { stdio: "ignore", windowsHide: true });
children.push(chrome);

async function pollJson(url, predicate = (x) => x) {
  for (let i = 0; i < 100; i++) {
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
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    }
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  return { ws, send };
}

try {
  const portFile = path.join(userData, "DevToolsActivePort");
  for (let i = 0; i < 100 && !fs.existsSync(portFile); i++) await delay(100);
  if (!fs.existsSync(portFile)) throw new Error("Chrome did not create its DevTools port file");
  port = Number(fs.readFileSync(portFile, "utf8").split(/\r?\n/, 1)[0]);
  await pollJson(`http://127.0.0.1:${port}/json/version`);
  const results = [];
  for (const count of [1, 8, 32]) {
    const targetResponse = await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:${httpPort}/spheres_${count}.html`, { method: "PUT" });
    if (!targetResponse.ok) throw new Error(`target create failed: ${targetResponse.status}`);
    const target = await targetResponse.json();
    const cdp = await connect(target);
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 960, height: 600, deviceScaleFactor: 1, mobile: false });
    await pollJson(`http://127.0.0.1:${port}/json/list`, (tabs) => tabs.find((tab) => tab.id === target.id && tab.url.includes(`/spheres_${count}.html`)) || null);
    for (let trial = 0; trial < trials; trial++) {
      if (trial) {
        await cdp.send("Page.enable");
        await cdp.send("Page.navigate", { url: `http://127.0.0.1:${httpPort}/spheres_${count}.html?trial=${trial}` });
      }
      for (let wait = 0; wait < 100; wait++) {
        const ready = await cdp.send("Runtime.evaluate", { expression: "!!(window.anvil && window.anvil.exports.anvil_frame)", returnByValue: true });
        if (ready.result.value) break;
        await delay(50);
        if (wait === 99) throw new Error(`${count} sphere page did not initialize`);
      }
      const evaluated = await cdp.send("Runtime.evaluate", {
        expression: `(() => { const f=window.anvil.exports.anvil_frame; const frame=16.6667; for(let i=0;i<${warmupCount};i++) f(frame); if(window.gc) window.gc(); const start=performance.memory?.usedJSHeapSize ?? 0; let peak=start; const samples=[]; for(let i=0;i<${sampleCount};i++){ const t=performance.now(); f(frame); samples.push(performance.now()-t); const h=performance.memory?.usedJSHeapSize ?? 0; if(h>peak) peak=h; } const end=performance.memory?.usedJSHeapSize ?? 0; samples.sort((a,b)=>a-b); const canvas=document.createElement('canvas'); const gl=canvas.getContext('webgl'); const ext=gl && gl.getExtension('WEBGL_debug_renderer_info'); return {p50_ms:samples[Math.floor(samples.length*.50)],p95_ms:samples[Math.ceil(samples.length*.95)-1],max_ms:samples[samples.length-1],heap_start_bytes:start,heap_peak_bytes:peak,heap_end_bytes:end,webgl:!!gl,webgl_renderer:gl && ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unavailable'}; })()`,
        returnByValue: true,
        awaitPromise: true,
      });
      if (evaluated.exceptionDetails) throw new Error(JSON.stringify(evaluated.exceptionDetails));
      if (!evaluated.result.value.webgl) throw new Error("WebGL is unavailable; refusing to report the painter fallback as a browser ray benchmark");
      results.push({ spheres: count, trial, ...evaluated.result.value });
    }
    cdp.ws.close();
  }
  const depthPixels = {};
  for (const order of ["far_near", "near_far"]) {
    const targetResponse = await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:${httpPort}/depth_${order}.html`, { method: "PUT" });
    if (!targetResponse.ok) throw new Error(`depth target create failed: ${targetResponse.status}`);
    const target = await targetResponse.json();
    const cdp = await connect(target);
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 960, height: 600, deviceScaleFactor: 1, mobile: false });
    for (let wait = 0; wait < 100; wait++) {
      const ready = await cdp.send("Runtime.evaluate", { expression: "!!(window.anvil && window.anvil.exports.anvil_frame)", returnByValue: true });
      if (ready.result.value) break;
      await delay(50);
      if (wait === 99) throw new Error(`depth ${order} page did not initialize`);
    }
    const pixel = await cdp.send("Runtime.evaluate", {
      expression: "(() => { window.anvil.exports.anvil_frame(16.6667); return Array.from(document.getElementById('screen').getContext('2d').getImageData(480,324,1,1).data); })()",
      returnByValue: true,
    });
    if (pixel.exceptionDetails) throw new Error(JSON.stringify(pixel.exceptionDetails));
    depthPixels[order] = pixel.result.value;
    cdp.ws.close();
  }
  const frontColorVisible = (pixel) => pixel[0] > pixel[2] * 2 && pixel[0] > pixel[1] * 2;
  const depthOrderPass = JSON.stringify(depthPixels.far_near) === JSON.stringify(depthPixels.near_far) && frontColorVisible(depthPixels.far_near);
  if (!depthOrderPass) throw new Error(`WebGL sphere depth order failed: ${JSON.stringify(depthPixels)}`);
  const summaries = [1, 8, 32].map((spheres) => {
    const rows = results.filter((row) => row.spheres === spheres);
    return {
      spheres,
      p50_ms: rows.map((row) => row.p50_ms).sort((a, b) => a - b)[Math.floor(rows.length / 2)],
      p95_ms: Math.max(...rows.map((row) => row.p95_ms)),
      max_frame_ms: Math.max(...rows.map((row) => row.max_ms)),
      heap_peak_mb: Math.max(...rows.map((row) => row.heap_peak_bytes)) / (1024 * 1024),
    };
  });
  const failures = summaries.flatMap((row) => {
    const missed = [];
    if (row.p95_ms > budgets.p95_ms[row.spheres]) missed.push(`${row.spheres} spheres p95 ${row.p95_ms} ms > ${budgets.p95_ms[row.spheres]} ms`);
    if (row.max_frame_ms > budgets.max_frame_ms) missed.push(`${row.spheres} spheres max frame ${row.max_frame_ms} ms > ${budgets.max_frame_ms} ms`);
    if (row.heap_peak_mb > budgets.heap_peak_mb[row.spheres]) missed.push(`${row.spheres} spheres heap ${row.heap_peak_mb.toFixed(1)} MB > ${budgets.heap_peak_mb[row.spheres]} MB`);
    return missed;
  });
  const output = { chrome: await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(), platform: { os: os.platform(), release: os.release(), arch: os.arch(), cpu: os.cpus()[0]?.model }, warmup_frames: warmupCount, measured_frames_per_trial: sampleCount, trials, budgets, summaries, depth_pixels: depthPixels, depth_order_pass: depthOrderPass, results, failures };
  const outputPath = process.env.WASM_RAY_BENCH_OUTPUT || path.join(root, ".scratch/wasm_ray_sphere_chromium.json");
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));
  process.stdout.write(JSON.stringify(output, null, 2) + "\n");
  if (failures.length) process.exitCode = 1;
} finally {
  for (const child of children) {
    if (process.platform === "win32")
      spawnSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else child.kill();
  }
  server.close();
  try { fs.rmSync(temp, { recursive: true, force: true }); } catch {}
}
