import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = process.cwd();
const counts = [1000, 10000, 100000, 200000];
const warmup = Number(process.env.ANVIL_BENCH_WARMUP || 30);
const samples = Number(process.env.ANVIL_BENCH_SAMPLES || 120);
const temp = fs.mkdtempSync(path.join(os.tmpdir(), "anvil-wasm-texture-bench-"));

function png1x1() {
  const crc32 = (data) => {
    let c = 0xffffffff;
    for (const byte of data) { c ^= byte; for (let bit = 0; bit < 8; bit++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1)); }
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type, data) => { const name = Buffer.from(type); const body = Buffer.concat([name, data]); const length = Buffer.alloc(4); length.writeUInt32BE(data.length); const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(body)); return Buffer.concat([length, body, crc]); };
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]), chunk("IHDR", Buffer.from([0,0,0,1,0,0,0,1,8,6,0,0,0])), chunk("IDAT", Buffer.from([120,156,99,248,207,192,240,31,0,5,0,1,255])), chunk("IEND", Buffer.alloc(0))]);
}

function writeModel(file, count, crossNearPlane = false) {
  const positions = new Float32Array(count * 9);
  const uv = new Float32Array(count * 6);
  for (let triangle = 0; triangle < count; triangle++) {
    const p = triangle * 9, t = triangle * 6;
    // Keep geometry tiny and in-frustum to measure upload/submission cost.
    positions.set(crossNearPlane
      ? [-0.002, -0.002, 4.2, 0.002, -0.002, 4.2, 0, 0.002, 4.98]
      : [-0.002, -0.002, 0, 0.002, -0.002, 0, 0, 0.002, 0], p);
    uv.set([0, 0, 1, 0, 0.5, 1], t);
  }
  const pos = Buffer.from(positions.buffer), tex = Buffer.from(uv.buffer);
  const image = png1x1();
  const binary = Buffer.concat([pos, tex, image]);
  const doc = {
    asset: { version: "2.0" }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0, TEXCOORD_0: 1 }, material: 0 }] }],
    materials: [{ pbrMetallicRoughness: { baseColorTexture: { index: 0 } } }],
    textures: [{ source: 0 }], images: [{ uri: `data:image/png;base64,${image.toString("base64")}` }],
    buffers: [{ uri: `data:application/octet-stream;base64,${binary.toString("base64")}`, byteLength: binary.length }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: pos.length }, { buffer: 0, byteOffset: pos.length, byteLength: tex.length }],
    accessors: [{ bufferView: 0, componentType: 5126, count: count * 3, type: "VEC3" }, { bufferView: 1, componentType: 5126, count: count * 3, type: "VEC2" }],
  };
  fs.writeFileSync(file, JSON.stringify(doc));
}

try {
  const results = [];
  for (const count of counts) {
    const dir = path.join(temp, String(count)); fs.mkdirSync(dir);
    writeModel(path.join(dir, "mesh.gltf"), count);
    const source = path.join(dir, "bench.ANVL"), output = path.join(dir, "bench.wasm");
    fs.writeFileSync(source, ["scene 3d", "camera perspective 0 0 12", "camera fov(70)", "fn(draw)", '  set var(ok) = model_draw("mesh.gltf", 0, 0, 0, 1, 0, 0, 0)', "end", ""].join("\n"));
    const built = spawnSync("python", [path.join(root, "compiler/anvil.py"), source, "--backend", "wasm", "-o", output], { encoding: "utf8", timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
    if (built.status !== 0) throw new Error(`compile ${count} textured triangles failed: ${built.stdout}\n${built.stderr}`);
    const capture = spawnSync("node", [path.join(root, "tools/capture_wasm_mask.mjs"), dir, "bench.html"], { encoding: "utf8", timeout: 300000, maxBuffer: 16 * 1024 * 1024, env: { ...process.env, ANVIL_WASM_BENCH_FRAMES: String(samples), ANVIL_WASM_BENCH_WARMUP: String(warmup), ANVIL_WASM_CAPTURE_FRAMES: "1" } });
    if (capture.status !== 0) throw new Error(`capture ${count} textured triangles failed: ${capture.stderr}`);
    const result = JSON.parse(capture.stdout.trim().split(/\r?\n/).at(-1));
    results.push({ triangles: count, ...result.benchmark });
    process.stdout.write(JSON.stringify(results.at(-1)) + "\n");
  }
  const clippedDir = path.join(temp, "near_plane_200000"); fs.mkdirSync(clippedDir);
  writeModel(path.join(clippedDir, "mesh.gltf"), 200000, true);
  const clippedSource = path.join(clippedDir, "near_plane.ANVL"), clippedOutput = path.join(clippedDir, "near_plane.wasm");
  fs.writeFileSync(clippedSource, ["scene 3d", "camera perspective 0 0 5", "camera fov(70)", "fn(draw)", '  set var(ok) = model_draw("mesh.gltf", 0, 0, 0, 1, 0, 0, 0)', "end", ""].join("\n"));
  const clippedBuild = spawnSync("python", [path.join(root, "compiler/anvil.py"), clippedSource, "--backend", "wasm", "-o", clippedOutput], { encoding: "utf8", timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
  if (clippedBuild.status !== 0) throw new Error(`compile near-plane clipping scene failed: ${clippedBuild.stdout}\n${clippedBuild.stderr}`);
  const clippedCapture = spawnSync("node", [path.join(root, "tools/capture_wasm_mask.mjs"), clippedDir, "near_plane.html"], { encoding: "utf8", timeout: 300000, maxBuffer: 16 * 1024 * 1024, env: { ...process.env, ANVIL_WASM_BENCH_FRAMES: String(samples), ANVIL_WASM_BENCH_WARMUP: String(warmup), ANVIL_WASM_CAPTURE_FRAMES: "1" } });
  if (clippedCapture.status !== 0) throw new Error(`capture near-plane clipping scene failed: ${clippedCapture.stderr}`);
  const clippedResult = JSON.parse(clippedCapture.stdout.trim().split(/\r?\n/).at(-1));
  results.push({ scenario: "near_plane_200000", triangles: 200000, ...clippedResult.benchmark });
  process.stdout.write(JSON.stringify(results.at(-1)) + "\n");
  const alternatingDir = path.join(temp, "alternating"); fs.mkdirSync(alternatingDir);
  writeModel(path.join(alternatingDir, "a.gltf"), 1);
  writeModel(path.join(alternatingDir, "b.gltf"), 1);
  const alternatingSource = path.join(alternatingDir, "alternating.ANVL");
  const alternatingOutput = path.join(alternatingDir, "alternating.wasm");
  fs.writeFileSync(alternatingSource, [
    "scene 3d", "camera perspective 0 0 12", "camera fov(70)", "fn(draw)",
    '  set var(a1) = model_draw("a.gltf", -1, 0, 0, 1, 0, 0, 0)',
    '  set var(b) = model_draw("b.gltf", 0, 0, 0, 1, 0, 0, 0)',
    '  set var(a2) = model_draw("a.gltf", 1, 0, 0, 1, 0, 0, 0)',
    "end", "",
  ].join("\n"));
  const alternatingBuild = spawnSync("python", [path.join(root, "compiler/anvil.py"), alternatingSource, "--backend", "wasm", "-o", alternatingOutput], { encoding: "utf8", timeout: 300000, maxBuffer: 16 * 1024 * 1024 });
  if (alternatingBuild.status !== 0) throw new Error(`compile alternating texture scene failed: ${alternatingBuild.stdout}\n${alternatingBuild.stderr}`);
  const alternatingCapture = spawnSync("node", [path.join(root, "tools/capture_wasm_mask.mjs"), alternatingDir, "alternating.html"], { encoding: "utf8", timeout: 300000, maxBuffer: 16 * 1024 * 1024, env: { ...process.env, ANVIL_WASM_BENCH_FRAMES: String(samples), ANVIL_WASM_BENCH_WARMUP: String(warmup), ANVIL_WASM_CAPTURE_FRAMES: "1" } });
  if (alternatingCapture.status !== 0) throw new Error(`capture alternating texture scene failed: ${alternatingCapture.stderr}`);
  const alternatingResult = JSON.parse(alternatingCapture.stdout.trim().split(/\r?\n/).at(-1));
  results.push({ scenario: "texture_A_B_A", triangles: 3, ...alternatingResult.benchmark });
  process.stdout.write(JSON.stringify(results.at(-1)) + "\n");
  const report = { chrome: process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe", warmup_frames: warmup, measured_frames: samples, budgets: { textured_triangles_per_frame: 200000, one_texture_material_run: { draw_calls_per_frame: 1, persistent_vertex_buffers: 1 }, alternating_texture_runs: { pattern: "A/B/A", draw_calls_per_frame: 3, preserve_submission_order: true }, max_texture_runs_per_frame: 256, p95_ms_max: 20, max_frame_ms_max: 25, heap_peak_mb_max: 50, wasm_memory_peak_pages_max: 320, large_scene_200000: { p95_ms_max: 40, max_frame_ms_max: 50, heap_peak_mb_max: 100, wasm_memory_peak_pages_max: 600 }, near_plane_clipping_200000: { p95_ms_max: 80, max_frame_ms_max: 100, heap_peak_mb_max: 160, wasm_memory_peak_pages_max: 600, submitted_triangles_per_frame: 400000 } }, results };
  const output = process.env.ANVIL_BENCH_OUTPUT || path.join(os.tmpdir(), "anvil_wasm_textured_submission.json");
  fs.writeFileSync(output, JSON.stringify(report, null, 2));
  process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  for (const row of results.filter((item) => item.scenario !== "texture_A_B_A")) {
    const budget = row.scenario === "near_plane_200000" ? report.budgets.near_plane_clipping_200000 : row.triangles > 100000 ? report.budgets.large_scene_200000 : report.budgets;
    if (row.p95_ms > budget.p95_ms_max || row.max_ms > budget.max_frame_ms_max || row.heap_peak_mb > budget.heap_peak_mb_max || row.wasm_memory_peak_pages > budget.wasm_memory_peak_pages_max || row.renderer_per_frame_max.draw_calls !== 1 || row.renderer_total.buffer_allocations !== 1) process.exitCode = 1;
  }
  if (alternatingResult.benchmark.renderer_per_frame_max.draw_calls !== 3 || alternatingResult.benchmark.renderer_total.buffer_allocations !== 2 || alternatingResult.benchmark.p95_ms > report.budgets.p95_ms_max || alternatingResult.benchmark.max_ms > report.budgets.max_frame_ms_max || alternatingResult.benchmark.heap_peak_mb > report.budgets.heap_peak_mb_max || alternatingResult.benchmark.wasm_memory_peak_pages > report.budgets.wasm_memory_peak_pages_max) process.exitCode = 1;
} finally { fs.rmSync(temp, { recursive: true, force: true }); }
