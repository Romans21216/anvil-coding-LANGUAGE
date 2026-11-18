import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { spawn, spawnSync } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const root = process.cwd();
const chromePath = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const forceSwiftShader = process.env.WASM_RAY_SWIFTSHADER !== "0";
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

function writeTriangleModel(file, colour, morphDelta = null) {
  const positions = Buffer.from(new Float32Array([
    -1.4, -1.2, 0, 1.4, -1.2, 0, 0, 1.4, 0,
  ]).buffer);
  const indices = Buffer.from(new Uint16Array([0, 1, 2]).buffer);
  const deltas = morphDelta ? Buffer.from(new Float32Array([
    morphDelta[0], morphDelta[1], morphDelta[2],
    morphDelta[0], morphDelta[1], morphDelta[2],
    morphDelta[0], morphDelta[1], morphDelta[2],
  ]).buffer) : null;
  const indexPadding = deltas && (positions.length + indices.length) % 4 ? 2 : 0;
  const chunks = [positions, indices];
  if (indexPadding) chunks.push(Buffer.alloc(indexPadding));
  if (deltas) chunks.push(deltas);
  const binary = Buffer.concat(chunks);
  const primitive = { attributes: { POSITION: 0 }, indices: 1, material: 0 };
  const bufferViews = [
    { buffer: 0, byteOffset: 0, byteLength: positions.length },
    { buffer: 0, byteOffset: positions.length, byteLength: indices.length },
  ];
  const accessors = [
    { bufferView: 0, componentType: 5126, count: 3, type: "VEC3" },
    { bufferView: 1, componentType: 5123, count: 3, type: "SCALAR" },
  ];
  if (deltas) {
    primitive.targets = [{ POSITION: 2 }];
    bufferViews.push({ buffer: 0, byteOffset: positions.length + indices.length + indexPadding, byteLength: deltas.length });
    accessors.push({ bufferView: 2, componentType: 5126, count: 3, type: "VEC3" });
  }
  const document = {
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [{ ...(deltas ? { weights: [0] } : {}), primitives: [primitive] }],
    materials: [{ pbrMetallicRoughness: { baseColorFactor: [...colour, 1] } }],
    buffers: [{ uri: `data:application/octet-stream;base64,${binary.toString("base64")}`, byteLength: binary.length }],
    bufferViews,
    accessors,
  };
  fs.writeFileSync(file, JSON.stringify(document));
}

writeTriangleModel(path.join(temp, "mesh_far.gltf"), [0.05, 0.12, 0.95]);
writeTriangleModel(path.join(temp, "mesh_near.gltf"), [0.95, 0.08, 0.04]);
writeTriangleModel(path.join(temp, "mesh_morph.gltf"), [0.95, 0.08, 0.04], [2, 0, 0]);
for (const order of ["far_near", "near_far"]) {
  const meshes = {
    far: 'ray_mesh("mesh_far.gltf", 0, 0, 0, 1, 0, 0, 0)',
    near: 'ray_mesh("mesh_near.gltf", 0, 0, 1, 1, 0, 0, 0)',
  };
  const draws = order === "far_near" ? [meshes.far, meshes.near] : [meshes.near, meshes.far];
  const src = path.join(temp, `mesh_depth_${order}.ANVL`);
  const out = path.join(temp, `mesh_depth_${order}.wasm`);
  fs.writeFileSync(src, [
    "scene 3d", "camera perspective 0 0 8", "clear rgba(11, 16, 27, 255)",
    "fn(draw)", ...draws.map((line) => `  set var(ok) = ${line}`), "end", "",
  ].join("\n"));
  const built = spawnSync("python", [path.join(root, "compiler/anvil.py"), src, "--backend", "wasm", "-o", out], { encoding: "utf8", timeout: 300000 });
  if (built.status !== 0) throw new Error(`compile ray-mesh depth ${order} failed: ${built.stderr}`);
  files[`/mesh_depth_${order}.html`] = fs.readFileSync(out.replace(/\.wasm$/, ".html"));
  files[`/mesh_depth_${order}.wasm`] = fs.readFileSync(out);
}

for (const mode of ["default", "override"]) {
  const src = path.join(temp, `mesh_morph_${mode}.ANVL`);
  const out = path.join(temp, `mesh_morph_${mode}.wasm`);
  const calls = mode === "override"
    ? ['  set var(weight) = model_morph("mesh_morph.gltf", 0, 1)', '  set var(ok) = ray_mesh("mesh_morph.gltf", 0, 0, 0, 1, 0, 0, 0)']
    : ['  set var(ok) = ray_mesh("mesh_morph.gltf", 0, 0, 0, 1, 0, 0, 0)'];
  fs.writeFileSync(src, ["scene 3d", "camera perspective 0 0 8", "clear rgba(11, 16, 27, 255)", "fn(draw)", ...calls, "end", ""].join("\n"));
  const built = spawnSync("python", [path.join(root, "compiler/anvil.py"), src, "--backend", "wasm", "-o", out], { encoding: "utf8", timeout: 300000 });
  if (built.status !== 0) throw new Error(`compile ray-mesh morph ${mode} failed: ${built.stderr}`);
  files[`/mesh_morph_${mode}.html`] = fs.readFileSync(out.replace(/\.wasm$/, ".html"));
  files[`/mesh_morph_${mode}.wasm`] = fs.readFileSync(out);
}

for (const mode of ["default", "override"]) {
  const src = path.join(temp, `mesh_morph_draw_${mode}.ANVL`);
  const out = path.join(temp, `mesh_morph_draw_${mode}.wasm`);
  const calls = mode === "override"
    ? ['  set var(weight) = model_morph("mesh_morph.gltf", 0, 1)', '  set var(ok) = model_draw("mesh_morph.gltf", 0, 0, 0, 1, 0, 0, 0)']
    : ['  set var(ok) = model_draw("mesh_morph.gltf", 0, 0, 0, 1, 0, 0, 0)'];
  fs.writeFileSync(src, ["scene 3d", "camera perspective 0 0 8", "clear rgba(11, 16, 27, 255)", "fn(draw)", ...calls, "end", ""].join("\n"));
  const built = spawnSync("python", [path.join(root, "compiler/anvil.py"), src, "--backend", "wasm", "-o", out], { encoding: "utf8", timeout: 300000 });
  if (built.status !== 0) throw new Error(`compile model-draw morph ${mode} failed: ${built.stderr}`);
  files[`/mesh_morph_draw_${mode}.html`] = fs.readFileSync(out.replace(/\.wasm$/, ".html"));
  files[`/mesh_morph_draw_${mode}.wasm`] = fs.readFileSync(out);
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
const chromeArgs = ["--headless=new", "--no-sandbox"];
if (forceSwiftShader) chromeArgs.push("--enable-unsafe-swiftshader", "--use-gl=angle", "--use-angle=swiftshader-webgl");
chromeArgs.push(
  "--enable-webgl",
  "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
  "--js-flags=--expose-gc", "--remote-debugging-port=0",
  `--user-data-dir=${userData}`, "about:blank",
);
const chrome = spawn(chromePath, chromeArgs, { stdio: "ignore", windowsHide: true });
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
    const targetResponse = await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:${httpPort}/spheres_${count}.html?anvil_debug=1&anvil_gpu_timer=1`, { method: "PUT" });
    if (!targetResponse.ok) throw new Error(`target create failed: ${targetResponse.status}`);
    const target = await targetResponse.json();
    const cdp = await connect(target);
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 960, height: 600, deviceScaleFactor: 1, mobile: false });
    await pollJson(`http://127.0.0.1:${port}/json/list`, (tabs) => tabs.find((tab) => tab.id === target.id && tab.url.includes(`/spheres_${count}.html`)) || null);
    for (let trial = 0; trial < trials; trial++) {
      if (trial) {
        await cdp.send("Page.enable");
        await cdp.send("Page.navigate", { url: `http://127.0.0.1:${httpPort}/spheres_${count}.html?anvil_debug=1&anvil_gpu_timer=1&trial=${trial}` });
      }
      for (let wait = 0; wait < 100; wait++) {
        const ready = await cdp.send("Runtime.evaluate", { expression: "!!(window.anvil && window.anvil.exports.anvil_frame)", returnByValue: true });
        if (ready.result.value) break;
        await delay(50);
        if (wait === 99) throw new Error(`${count} sphere page did not initialize`);
      }
      const evaluated = await cdp.send("Runtime.evaluate", {
        expression: `(() => { const f=window.anvil.exports.anvil_frame; const frame=16.6667; for(let i=0;i<${warmupCount};i++) f(frame); if(window.gc) window.gc(); const start=performance.memory?.usedJSHeapSize ?? 0; let peak=start; const samples=[]; for(let i=0;i<${sampleCount};i++){ const t=performance.now(); f(frame); samples.push(performance.now()-t); const h=performance.memory?.usedJSHeapSize ?? 0; if(h>peak) peak=h; } const end=performance.memory?.usedJSHeapSize ?? 0; samples.sort((a,b)=>a-b); const canvas=document.createElement('canvas'); const gl=canvas.getContext('webgl'); const fragmentDepth=!!(gl && gl.getExtension('EXT_frag_depth')); const ext=gl && gl.getExtension('WEBGL_debug_renderer_info'); return {p50_ms:samples[Math.floor(samples.length*.50)],p95_ms:samples[Math.ceil(samples.length*.95)-1],max_ms:samples[samples.length-1],heap_start_bytes:start,heap_peak_bytes:peak,heap_end_bytes:end,webgl:!!gl,fragment_depth:fragmentDepth,sphere_impostor_available:!!window.__anvilSphereImpostorAvailable,sphere_impostor_calls:window.__anvilSphereImpostorCalls ?? 0,webgl_renderer:gl && ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unavailable'}; })()`,
        returnByValue: true,
        awaitPromise: true,
      });
      if (evaluated.exceptionDetails) throw new Error(JSON.stringify(evaluated.exceptionDetails));
      if (!evaluated.result.value.webgl) throw new Error("WebGL is unavailable; refusing to report the painter fallback as a browser ray benchmark");
      if (!evaluated.result.value.fragment_depth) throw new Error("EXT_frag_depth is unavailable; refusing to report the tessellation fallback as a sphere-impostor benchmark");
      if (!evaluated.result.value.sphere_impostor_available || evaluated.result.value.sphere_impostor_calls === 0) throw new Error("The host did not select the WebGL sphere-impostor path");
      if (!forceSwiftShader && evaluated.result.value.webgl_renderer.includes("SwiftShader")) throw new Error("Hardware WebGL was requested, but Chrome selected SwiftShader");
      const gpuTimer = await cdp.send("Runtime.evaluate", {
        expression: `(() => { const timer=window.__anvilGpuTimer; if(!timer || !timer.available()) return {available:false,samples_ms:[],disjoint:false}; const f=window.anvil.exports.anvil_frame; for(let i=0;i<90;i++) f(16.6667); return new Promise(resolve => { const samples=[]; let polls=0; const collect=()=>{ const batch=timer.collect(); samples.push(...batch.samples_ms); if(batch.disjoint || polls++ >= 200) return resolve({available:batch.available,samples_ms:samples,disjoint:batch.disjoint,pending:batch.pending}); if(samples.length>=60 && batch.pending===0) return resolve({available:batch.available,samples_ms:samples,disjoint:batch.disjoint,pending:batch.pending}); setTimeout(collect,25); }; collect(); }); })()`,
        returnByValue: true,
        awaitPromise: true,
      });
      if (gpuTimer.exceptionDetails) throw new Error(JSON.stringify(gpuTimer.exceptionDetails));
      const timerResult = gpuTimer.result.value;
      if (timerResult.available && !timerResult.disjoint && timerResult.samples_ms.length < 30) throw new Error(`GPU timer returned only ${timerResult.samples_ms.length} valid samples for ${count} spheres`);
      results.push({ spheres: count, trial, ...evaluated.result.value, gpu_timer_available: timerResult.available, gpu_timer_disjoint: timerResult.disjoint, gpu_timer_sample_count: timerResult.samples_ms.length, gpu_timer_p50_ms: timerResult.available && !timerResult.disjoint ? timerResult.samples_ms.slice().sort((a,b)=>a-b)[Math.floor(timerResult.samples_ms.length*.5)] : null, gpu_timer_p95_ms: timerResult.available && !timerResult.disjoint ? timerResult.samples_ms.slice().sort((a,b)=>a-b)[Math.ceil(timerResult.samples_ms.length*.95)-1] : null, gpu_timer_max_ms: timerResult.available && !timerResult.disjoint ? Math.max(...timerResult.samples_ms) : null });
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
  const meshDepthPixels = {};
  for (const order of ["far_near", "near_far"]) {
    const targetResponse = await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:${httpPort}/mesh_depth_${order}.html`, { method: "PUT" });
    if (!targetResponse.ok) throw new Error(`ray-mesh depth target create failed: ${targetResponse.status}`);
    const target = await targetResponse.json();
    const cdp = await connect(target);
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 960, height: 600, deviceScaleFactor: 1, mobile: false });
    for (let wait = 0; wait < 100; wait++) {
      const ready = await cdp.send("Runtime.evaluate", { expression: "!!(window.anvil && window.anvil.exports.anvil_frame)", returnByValue: true });
      if (ready.result.value) break;
      await delay(50);
      if (wait === 99) throw new Error(`ray-mesh depth ${order} page did not initialize`);
    }
    const evaluated = await cdp.send("Runtime.evaluate", {
      expression: "(() => { const canvas=document.createElement('canvas'); const gl=canvas.getContext('webgl'); if(!gl) throw new Error('WebGL unavailable'); window.anvil.exports.anvil_frame(16.6667); return Array.from(document.getElementById('screen').getContext('2d').getImageData(480,324,1,1).data); })()",
      returnByValue: true,
    });
    if (evaluated.exceptionDetails) throw new Error(JSON.stringify(evaluated.exceptionDetails));
    meshDepthPixels[order] = evaluated.result.value;
    cdp.ws.close();
  }
  const meshDepthOrderPass = JSON.stringify(meshDepthPixels.far_near) === JSON.stringify(meshDepthPixels.near_far) && frontColorVisible(meshDepthPixels.far_near);
  if (!meshDepthOrderPass) throw new Error(`WebGL ray-mesh depth order failed: ${JSON.stringify(meshDepthPixels)}`);
  const morphPixels = {};
  for (const mode of ["default", "override"]) {
    const targetResponse = await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:${httpPort}/mesh_morph_${mode}.html`, { method: "PUT" });
    if (!targetResponse.ok) throw new Error(`ray-mesh morph target create failed: ${targetResponse.status}`);
    const target = await targetResponse.json();
    const cdp = await connect(target);
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 960, height: 600, deviceScaleFactor: 1, mobile: false });
    for (let wait = 0; wait < 100; wait++) {
      const ready = await cdp.send("Runtime.evaluate", { expression: "!!(window.anvil && window.anvil.exports.anvil_frame)", returnByValue: true });
      if (ready.result.value) break;
      await delay(50);
      if (wait === 99) throw new Error(`ray-mesh morph ${mode} page did not initialize`);
    }
    const evaluated = await cdp.send("Runtime.evaluate", {
      expression: "(() => { const gl=document.createElement('canvas').getContext('webgl'); if(!gl) throw new Error('WebGL unavailable'); window.anvil.exports.anvil_frame(16.6667); return Array.from(document.getElementById('screen').getContext('2d').getImageData(480,324,1,1).data); })()",
      returnByValue: true,
    });
    if (evaluated.exceptionDetails) throw new Error(JSON.stringify(evaluated.exceptionDetails));
    morphPixels[mode] = evaluated.result.value;
    cdp.ws.close();
  }
  const morphDefaultVisible = frontColorVisible(morphPixels.default);
  const morphOverrideMoved = JSON.stringify(morphPixels.default) !== JSON.stringify(morphPixels.override) && morphPixels.override[0] < 40 && morphPixels.override[1] < 40 && morphPixels.override[2] < 60;
  if (!morphDefaultVisible || !morphOverrideMoved) throw new Error(`WebGL ray-mesh morph failed: ${JSON.stringify(morphPixels)}`);
  const modelDrawMorphPixels = {};
  for (const mode of ["default", "override"]) {
    const targetResponse = await fetch(`http://127.0.0.1:${port}/json/new?http://127.0.0.1:${httpPort}/mesh_morph_draw_${mode}.html`, { method: "PUT" });
    if (!targetResponse.ok) throw new Error(`model-draw morph target create failed: ${targetResponse.status}`);
    const target = await targetResponse.json();
    const cdp = await connect(target);
    await cdp.send("Runtime.enable");
    await cdp.send("Emulation.setDeviceMetricsOverride", { width: 960, height: 600, deviceScaleFactor: 1, mobile: false });
    for (let wait = 0; wait < 100; wait++) {
      const ready = await cdp.send("Runtime.evaluate", { expression: "!!(window.anvil && window.anvil.exports.anvil_frame)", returnByValue: true });
      if (ready.result.value) break;
      await delay(50);
      if (wait === 99) throw new Error(`model-draw morph ${mode} page did not initialize`);
    }
    const evaluated = await cdp.send("Runtime.evaluate", {
      expression: "(() => { const gl=document.createElement('canvas').getContext('webgl'); if(!gl) throw new Error('WebGL unavailable'); window.anvil.exports.anvil_frame(16.6667); return Array.from(document.getElementById('screen').getContext('2d').getImageData(480,324,1,1).data); })()",
      returnByValue: true,
    });
    if (evaluated.exceptionDetails) throw new Error(JSON.stringify(evaluated.exceptionDetails));
    modelDrawMorphPixels[mode] = evaluated.result.value;
    cdp.ws.close();
  }
  const modelDrawMorphPass = frontColorVisible(modelDrawMorphPixels.default) &&
    JSON.stringify(modelDrawMorphPixels.default) !== JSON.stringify(modelDrawMorphPixels.override) &&
    modelDrawMorphPixels.override[0] < 40 && modelDrawMorphPixels.override[1] < 40 && modelDrawMorphPixels.override[2] < 60;
  if (!modelDrawMorphPass) throw new Error(`WebGL model-draw morph failed: ${JSON.stringify(modelDrawMorphPixels)}`);
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
  const gpuRows = results.filter((row) => row.gpu_timer_available && !row.gpu_timer_disjoint);
  const gpuTimerSummary = gpuRows.length ? Object.fromEntries([1, 8, 32].map((spheres) => { const rows = gpuRows.filter((row) => row.spheres === spheres); return [spheres, rows.length ? { samples: rows.reduce((sum,row)=>sum+row.gpu_timer_sample_count,0), p50_ms: Math.max(...rows.map(row=>row.gpu_timer_p50_ms)), p95_ms: Math.max(...rows.map(row=>row.gpu_timer_p95_ms)), max_ms: Math.max(...rows.map(row=>row.gpu_timer_max_ms)) } : null]; })) : null;
  const output = { chrome: await (await fetch(`http://127.0.0.1:${port}/json/version`)).json(), renderer_mode: forceSwiftShader ? "swiftshader" : "hardware-required", metric_scope: "CPU-side anvil_frame JavaScript/WASM call duration; excludes asynchronous GPU execution; heap is performance.memory JS heap", gpu_metric_scope: "EXT_disjoint_timer_query TIME_ELAPSED_EXT around the sphere impostor drawArrays command; reports GPU elapsed time where supported and non-disjoint", gpu_timer_summary: gpuTimerSummary, platform: { os: os.platform(), release: os.release(), arch: os.arch(), cpu: os.cpus()[0]?.model }, warmup_frames: warmupCount, measured_frames_per_trial: sampleCount, trials, budgets, summaries, depth_pixels: depthPixels, depth_order_pass: depthOrderPass, ray_mesh_depth_pixels: meshDepthPixels, ray_mesh_depth_order_pass: meshDepthOrderPass, ray_mesh_morph_pixels: morphPixels, ray_mesh_morph_pass: morphDefaultVisible && morphOverrideMoved, model_draw_morph_pixels: modelDrawMorphPixels, model_draw_morph_pass: modelDrawMorphPass, results, failures };
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
