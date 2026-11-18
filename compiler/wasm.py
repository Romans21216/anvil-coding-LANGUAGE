"""WebAssembly console backend (Part 8, 8.12 first slice).

The Windows runtime needs GDI, Win32 and sockets, so a browser target cannot
reuse it. This backend emits the same generated C but against
`runtime/anvil_wasm.c`, a small freestanding runtime whose only host dependency
is an imported `env.write(fd, ptr, len)`. Programs are limited to a console
subset; anything outside it is refused with a source-located error rather than
failing at link time.

Build:  python compiler/anvil.py hello.ANVL --backend wasm -o hello.wasm
Run:    node tools/wasm_host.mjs hello.wasm
"""

from __future__ import annotations

import json
import hashlib

import pathlib
import re
import shutil
import subprocess
import time
from functools import wraps
from urllib.parse import quote

from compiler.builtin_usage import used_builtins
from compiler.codegen import emit_c
from compiler.common import CompileError, c_name

ROOT = pathlib.Path(__file__).resolve().parents[1]

_asset_import_seconds = 0.0
_measure_asset_imports = False
_toolchain_peak_working_set_bytes: int | None = None
_toolchain_process_tree_peak_working_set_bytes: int | None = None


def measure_asset_imports(enabled: bool, *, reset: bool = False) -> None:
    global _asset_import_seconds, _measure_asset_imports
    global _toolchain_peak_working_set_bytes, _toolchain_process_tree_peak_working_set_bytes
    _measure_asset_imports = enabled
    if reset:
        _asset_import_seconds = 0.0
        _toolchain_peak_working_set_bytes = None
        _toolchain_process_tree_peak_working_set_bytes = None


def asset_import_time_seconds() -> float:
    return _asset_import_seconds


def toolchain_peak_working_set_bytes() -> int | None:
    return _toolchain_peak_working_set_bytes


def toolchain_process_tree_peak_working_set_bytes() -> int | None:
    return _toolchain_process_tree_peak_working_set_bytes


def _timed_asset_import(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        global _asset_import_seconds
        if not _measure_asset_imports:
            return function(*args, **kwargs)
        started = time.perf_counter()
        try:
            return function(*args, **kwargs)
        finally:
            _asset_import_seconds += time.perf_counter() - started
    return wrapped

ALLOWED_BUILTINS = {
    "abs",
    "ceil",
    "clamp",
    "floor",
    "len",
    "max",
    "mid",
    "min",
    "number",
    "round",
    "sqrt",
    "upper",
    "time",
    "delta",
    "pressed",
    "held",
    "mouse_x",
    "mouse_y",
    "mouse_pressed",
    "mouse_held",
    "mouse_wheel",
    "sin",
    "cos",
    "tan",
    "rnd",
    "save_number",
    "load_number",
    "save_text",
    "load_text",
    "save_exists",
    "save_delete",
    "save_error",
    "lower",
    "trim",
    "left",
    "right",
    "char",
    "contains",
    "starts_with",
    "ends_with",
    "ord",
    "chr",
    "noise",
    "fbm",
    "image_load",
    "image_width",
    "image_height",
    "image_draw",
    "image_draw_scaled",
    "image_draw_rotated",
    "image_draw_region",
    "image_tint",
    "image_flip",
    "image_destroy",
    "image_error",
    "sound_load",
    "sound_play",
    "sound_play_loop",
    "sound_pan",
    "sound_pitch",
    "sound_duration",
    "sound_group",
    "sound_group_volume",
    "sound_group_mute",
    "sound_group_gain",
    "sound_group_stop",
    "sound_stop",
    "sound_stop_all",
    "sound_volume",
    "sound_active",
    "sound_destroy",
    "sound_error",
    "camera_angle",
    "light",
    "light_ambient",
    "light_intensity",
    "model_draw",
    "model_draw_instance",
    "model_animate",
    "model_animation_length",
    "model_morph",
    "model_instance",
    "model_instance_destroy",
    "model_instance_morph",
    "ray_mesh",
    "mesh_drawn",
    "mesh_culled",
    "mesh_culling",
    "shadow",
    "screen_fade",
    "screen_fade_to",
    "screen_fade_alpha",
    "shadow_height",
    "shadow_alpha",
    "music_load",
    "music_play",
    "music_play_loop",
    "music_stop",
    "music_playing",
    "music_volume",
    "music_position",
    "music_length",
    "music_error",
    "body_create",
    "body_create_box",
    "body_destroy",
    "body_active",
    "body_x",
    "body_y",
    "body_vx",
    "body_vy",
    "body_set_velocity",
    "body_force",
    "body_restitution",
    "body_friction",
    "body_collision",
    "physics_capacity",
    "physics_gravity",
    "physics_step",
    "memory_images",
    "memory_audio",
    "memory_video",
    "memory_gpu",
    "memory_total",
    "buffer",
    "sprite_batch",
    "sprite_depth",
    "sprite_queued",
    "image_pixel",
    "particle_emit",
    "particle_count",
    "particle_clear",
    "particle_gravity",
    "ui_focus_add",
    "ui_focus_clear",
    "ui_focus_count",
    "ui_focus_next",
    "ui_focus_prev",
    "ui_focus_set",
    "ui_focus",
    "ui_focus_at",
    "ui_focus_activate",
    "ui_focus_label",
    "ui_accessible",
    "scene_change",
    "scene_name",
    "scene_target",
    "scene_changing",
    "scene_changed",
    "scene_progress",
    "save_version",
    "save_set_version",
}

ENGINE_STATEMENT = re.compile(r"^\s*engine\b", re.MULTILINE)
SCENE_STATEMENT = re.compile(r"^\s*scene\s+(\w+)", re.MULTILINE)
DISPLAY_STATEMENT = re.compile(r"^\s*display\s+([a-z_]+)\s*\(", re.MULTILINE)
CAMERA_STATEMENT = re.compile(r"^\s*camera\b", re.MULTILINE)
ALLOWED_SHAPES = {
    "rect",
    "circle",
    "line",
    "text",
    "cube",
    "plane",
    "sphere",
    "ray_sphere",
}

HOST_PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
 body { margin:0; background:#0d1117; }
 canvas { display:block; margin:12px; background:#000; box-shadow:0 0 0 1px #30363d; }
 #out { position:fixed; left:12px; bottom:12px; color:#ff7b72; font:13px ui-monospace,monospace; white-space:pre-wrap; }
</style>
<canvas id="screen" width="960" height="600"></canvas>
<div id="out"></div>
<!-- Screen readers read focus announcements here; visually hidden but present. -->
<div id="announce" aria-live="polite" aria-atomic="true"
     style="position:absolute;width:1px;height:1px;margin:-1px;padding:0;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0"></div>
<script>
const canvas = document.getElementById("screen");
const context = canvas.getContext("2d");
context.imageSmoothingEnabled = false;
const errors = document.getElementById("out");
const announceRegion = document.getElementById("announce");
const utf8 = new TextDecoder();
const sourceMap = __SOURCE_MAP__;
const describeError = (error) => {
  const message = String((error && error.message) || error);
  if (message.startsWith("Anvil runtime error in fn(")) return message;
  const stack = String((error && error.stack) || error);
  for (const line of stack.split("\\n")) {
    for (const name of Object.keys(sourceMap)) {
      if (line.indexOf("." + name) >= 0) {
        const entry = sourceMap[name];
        return "Anvil runtime error in fn(" + entry.name + ") at line " + entry.line + ": " + stack.split("\\n")[0];
      }
    }
  }
  return stack;
};
function rgba(r, g, b, a) {
  return "rgba(" + r + "," + g + "," + b + "," + ((a === undefined ? 255 : a) / 255) + ")";
}
async function start() {
  try {
    if (location.protocol === "file:") {
      throw new Error("Serve this folder over HTTP (python -m http.server); browsers block wasm fetches from file:// URLs.");
    }
    const bytes = await (await fetch("__WASM__")).arrayBuffer();
    const module = await WebAssembly.compile(bytes);
    let memory = null;
    let app = null;
    const scene3dState = { active: false };
    const pageParams = new URLSearchParams(location.search);
    const forcePainter = pageParams.has("painter");
    const forceNoWebGL = pageParams.has("no_webgl");
    const skipSort = pageParams.has("nosort");
    const gpuTimerRequested = pageParams.get("anvil_gpu_timer") === "1";
    let gpuTimerExt = null;
    const gpuTimerQueries = [];
    let gpuTimerDisjoint = false;
    let glRenderer = null;
    const createGlRenderer = () => {
      if (glRenderer !== null) return glRenderer;
      if (forceNoWebGL) return (glRenderer = false);
      try {
        const canvas = document.createElement("canvas");
        canvas.width = 960;
        canvas.height = 600;
        const gl = canvas.getContext("webgl", { antialias: false, premultipliedAlpha: false });
        if (!gl) return (glRenderer = false);
        const fragmentDepth = gl.getExtension("EXT_frag_depth");
        gpuTimerExt = gpuTimerRequested ? gl.getExtension("EXT_disjoint_timer_query") : null;
        const compile = (type, source) => {
          const shader = gl.createShader(type);
          gl.shaderSource(shader, source);
          gl.compileShader(shader);
          if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            throw new Error(gl.getShaderInfoLog(shader));
          }
          return shader;
        };
        const program = gl.createProgram();
        gl.attachShader(program, compile(gl.VERTEX_SHADER,
          "attribute vec2 pos; attribute float depth; attribute vec4 colour;" +
          "varying vec4 v_colour;" +
          "void main() {" +
          "  float z = clamp(depth / 500.0, 0.0, 1.0) * 2.0 - 1.0;" +
          "  gl_Position = vec4(pos.x / 480.0 - 1.0, 1.0 - pos.y / 300.0, z, 1.0);" +
          "  v_colour = colour;" +
          "}"));
        gl.attachShader(program, compile(gl.FRAGMENT_SHADER,
          "precision mediump float; varying vec4 v_colour;" +
          "void main() { gl_FragColor = v_colour; }"));
        gl.linkProgram(program);
        if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
          throw new Error(gl.getProgramInfoLog(program));
        }
        const texturedProgram = gl.createProgram();
        gl.attachShader(texturedProgram, compile(gl.VERTEX_SHADER,
          "attribute vec2 pos; attribute float depth; attribute vec2 uv; attribute vec4 tint;" +
          "varying vec2 v_uv_depth; varying float v_inv_depth; varying vec4 v_tint;" +
          "void main(){ float z=clamp(depth/500.0,0.0,1.0)*2.0-1.0;" +
          "gl_Position=vec4(pos.x/480.0-1.0,1.0-pos.y/300.0,z,1.0);" +
          "float safeDepth=max(depth,0.0001); v_uv_depth=uv/safeDepth;" +
          "v_inv_depth=1.0/safeDepth; v_tint=tint; }"));
        gl.attachShader(texturedProgram, compile(gl.FRAGMENT_SHADER,
          "precision highp float; varying vec2 v_uv_depth; varying float v_inv_depth;" +
          "varying vec4 v_tint; uniform sampler2D image;" +
          "void main(){ vec2 uv=v_uv_depth/max(v_inv_depth,0.000001);" +
          "vec4 texel=texture2D(image,vec2(uv.x,1.0-uv.y));" +
          "vec4 colour=texel*v_tint; if(colour.a<=0.0) discard; gl_FragColor=colour; }"));
        gl.linkProgram(texturedProgram);
        if (!gl.getProgramParameter(texturedProgram, gl.LINK_STATUS)) {
          throw new Error(gl.getProgramInfoLog(texturedProgram));
        }
        let sphereProgram = null;
        if (fragmentDepth) {
          try {
            sphereProgram = gl.createProgram();
            gl.attachShader(sphereProgram, compile(gl.VERTEX_SHADER,
              "attribute vec2 pos;" +
              "attribute vec4 centerRadius;" +
              "attribute vec4 colour;" +
              "varying vec4 v_centerRadius;" +
              "varying vec4 v_colour;" +
              "void main() {" +
              "  gl_Position = vec4(pos.x / 480.0 - 1.0, 1.0 - pos.y / 300.0, 0.0, 1.0);" +
              "  v_centerRadius = centerRadius;" +
              "  v_colour = colour;" +
              "}"));
            gl.attachShader(sphereProgram, compile(gl.FRAGMENT_SHADER,
              "#extension GL_EXT_frag_depth : require\\n" +
              "precision highp float;" +
              "varying vec4 v_centerRadius;" +
              "varying vec4 v_colour;" +
              "uniform vec3 u_light;" +
              "uniform float u_focal;" +
              "uniform vec4 u_shadows[32];" +
              "uniform int u_sphereCount;" +
              "void main() {" +
              "  float py = 600.0 - gl_FragCoord.y;" +
              "  vec3 ray = normalize(vec3((gl_FragCoord.x - 480.0) / u_focal, (324.0 - py) / u_focal, 1.0));" +
              "  vec3 center = v_centerRadius.xyz;" +
              "  float radius = v_centerRadius.w;" +
              "  vec3 offset = -center;" +
              "  float halfB = dot(offset, ray);" +
              "  float c = dot(offset, offset) - radius * radius;" +
              "  float discriminant = halfB * halfB - c;" +
              "  if (discriminant < 0.0) discard;" +
              "  float root = sqrt(discriminant);" +
              "  float t = -halfB - root;" +
              "  if (t <= 0.001) t = -halfB + root;" +
              "  if (t <= 0.001) discard;" +
              "  vec3 point = ray * t;" +
              "  if (point.z <= 0.05) discard;" +
              "  vec3 normal = normalize(point - center);" +
              "  float diffuse = max(0.0, dot(normal, u_light));" +
              "  float shadowed = 0.0;" +
              "  if (diffuse > 0.0) {" +
              "    vec3 shadowOrigin = point + normal * 0.002;" +
              "    for (int i = 0; i < 32; ++i) {" +
              "      if (i >= u_sphereCount) break;" +
              "      vec3 shadowOffset = shadowOrigin - u_shadows[i].xyz;" +
              "      float shadowB = dot(shadowOffset, u_light);" +
              "      if (shadowB < 0.0) {" +
              "        float shadowC = dot(shadowOffset, shadowOffset) - u_shadows[i].w * u_shadows[i].w;" +
              "        float shadowD = shadowB * shadowB - shadowC;" +
              "        if (shadowD >= 0.0) {" +
              "          float shadowRoot = sqrt(shadowD);" +
              "          float shadowT = -shadowB - shadowRoot;" +
              "          if (shadowT <= 0.001) shadowT = -shadowB + shadowRoot;" +
              "          if (shadowT > 0.001) shadowed = 1.0;" +
              "        }" +
              "      }" +
              "      if (shadowed > 0.5) break;" +
              "    }" +
              "  }" +
              "  float brightness = shadowed > 0.5 ? 0.13 : 0.16 + 0.78 * diffuse;" +
              "  vec3 view = -ray;" +
              "  vec3 halfway = normalize(u_light + view);" +
              "  float specular = pow(max(0.0, dot(normal, halfway)), 28.0) * 0.22;" +
              "  vec3 rgb = min(v_colour.rgb * brightness + vec3(specular), vec3(1.0));" +
              "  gl_FragDepthEXT = clamp(point.z / 500.0, 0.0, 1.0);" +
              "  gl_FragColor = vec4(rgb, v_colour.a);" +
              "}"));
            gl.linkProgram(sphereProgram);
            if (!gl.getProgramParameter(sphereProgram, gl.LINK_STATUS)) {
              throw new Error(gl.getProgramInfoLog(sphereProgram));
            }
          } catch (error) {
            sphereProgram = null;
          }
        }
        gl.useProgram(program);
        gl.enable(gl.DEPTH_TEST);
        gl.depthFunc(gl.LEQUAL);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        glRenderer = {
          canvas,
          gl,
          program,
          texturedProgram,
          texturedPos: gl.getAttribLocation(texturedProgram, "pos"),
          texturedDepth: gl.getAttribLocation(texturedProgram, "depth"),
          texturedUv: gl.getAttribLocation(texturedProgram, "uv"),
          texturedTint: gl.getAttribLocation(texturedProgram, "tint"),
          texturedImage: gl.getUniformLocation(texturedProgram, "image"),
          textureCache: new Map(),
          texturedBuffers: new Map(),
      texturedVertexPool: new Float32Array(0),
      texturedVertexPoolIndex: 0,
      texturedCurrentRun: null,
          pos: gl.getAttribLocation(program, "pos"),
          depth: gl.getAttribLocation(program, "depth"),
          colour: gl.getAttribLocation(program, "colour"),
          sphere: sphereProgram ? {
            program: sphereProgram,
            pos: gl.getAttribLocation(sphereProgram, "pos"),
            centerRadius: gl.getAttribLocation(sphereProgram, "centerRadius"),
            colour: gl.getAttribLocation(sphereProgram, "colour"),
            light: gl.getUniformLocation(sphereProgram, "u_light"),
            focal: gl.getUniformLocation(sphereProgram, "u_focal"),
            shadows: gl.getUniformLocation(sphereProgram, "u_shadows[0]"),
            sphereCount: gl.getUniformLocation(sphereProgram, "u_sphereCount"),
          } : null,
        };
      } catch (error) {
        glRenderer = false;
      }
      return glRenderer;
    };
    const drawGl = (list, texturedList, spheres) => {
      const renderer = createGlRenderer();
      if (!renderer) return false;
      const { canvas, gl } = renderer;
      if (rendererDiagnostics) {
        const stats = window.__anvilTexturedRendererStats ||
          (window.__anvilTexturedRendererStats = { triangles: 0, batches: 0, buffer_allocations: 0, draw_calls: 0, uploaded_bytes: 0 });
        stats.triangles += texturedList.reduce((total, item) => total + (item.batch ? item.count : 1), 0);
      }
      gl.viewport(0, 0, 960, 600);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      const stride = 7 * 4;
      const upload = (entries, depthTest) => {
        if (!entries.length) return;
        gl.useProgram(renderer.program);
        const data = new Float32Array(entries.length * 3 * 7);
        let at = 0;
        for (const entry of entries) {
          for (const corner of [[entry[0], entry[1], entry[2]], [entry[3], entry[4], entry[5]], [entry[6], entry[7], entry[8]]]) {
            data[at++] = corner[0];
            data[at++] = corner[1];
            data[at++] = corner[2];
            data[at++] = entry[9] / 255;
            data[at++] = entry[10] / 255;
            data[at++] = entry[11] / 255;
            data[at++] = entry[12] / 255;
          }
        }
        const buffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
        gl.enableVertexAttribArray(renderer.pos);
        gl.vertexAttribPointer(renderer.pos, 2, gl.FLOAT, false, stride, 0);
        gl.enableVertexAttribArray(renderer.depth);
        gl.vertexAttribPointer(renderer.depth, 1, gl.FLOAT, false, stride, 2 * 4);
        gl.enableVertexAttribArray(renderer.colour);
        gl.vertexAttribPointer(renderer.colour, 4, gl.FLOAT, false, stride, 3 * 4);
        if (depthTest) gl.enable(gl.DEPTH_TEST);
        else gl.disable(gl.DEPTH_TEST);
        gl.drawArrays(gl.TRIANGLES, 0, entries.length * 3);
        gl.deleteBuffer(buffer);
      };
      upload(list.filter((entry) => entry[13] !== 1), true);
      const texturedBatches = [];
      let texturedBatch = null;
      for (const entry of texturedList) {
        if (entry.batch && entry.run) {
          texturedBatches.push({ key: entry.run.key, entries: [entry], run: entry.run });
          continue;
        }
        const layer = entry.batch ? entry.layer : entry[19];
        const pointer = entry.batch ? entry.pointer : entry[20];
        const width = entry.batch ? entry.width : entry[21];
        const height = entry.batch ? entry.height : entry[22];
        const cacheKey = pointer + ":" + width + ":" + height + ":" + layer;
        if (!texturedBatch || texturedBatch.key !== cacheKey) {
          texturedBatch = { key: cacheKey, entries: [] };
          texturedBatches.push(texturedBatch);
        }
        texturedBatch.entries.push(entry);
      }
      for (const batch of texturedBatches) {
        const entries = batch.entries;
        const first = entries[0];
        const pointer = first.batch ? first.pointer : first[20];
        const width = first.batch ? first.width : first[21];
        const height = first.batch ? first.height : first[22];
        const triangleCount = batch.run ? batch.run.count : entries.reduce((total, item) => total + (item.batch ? item.count : 1), 0);
        const cacheKey = pointer + ":" + width + ":" + height;
        let texture = renderer.textureCache.get(cacheKey);
        if (!texture) {
          if (!memory || width <= 0 || height <= 0) continue;
          const source = new Uint32Array(memory.buffer, pointer, width * height);
          const rgba = new Uint8Array(width * height * 4);
          for (let pixel = 0; pixel < source.length; pixel++) {
            const packed = source[pixel], at = pixel * 4;
            rgba[at] = packed >>> 16; rgba[at + 1] = packed >>> 8;
            rgba[at + 2] = packed; rgba[at + 3] = packed >>> 24;
          }
          texture = gl.createTexture();
          gl.bindTexture(gl.TEXTURE_2D, texture);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
          gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
          gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, width, height, 0, gl.RGBA, gl.UNSIGNED_BYTE, rgba);
          renderer.textureCache.set(cacheKey, texture);
        } else gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.useProgram(renderer.texturedProgram);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texture);
        gl.uniform1i(renderer.texturedImage, 0);
        const vertices = batch.run
          ? renderer.texturedVertexPool.subarray(batch.run.start * 27, (batch.run.start + batch.run.count) * 27)
          : entries[0].vertices;
        const bufferKey = batch.key;
        let buffer = renderer.texturedBuffers.get(bufferKey);
        if (!buffer) {
          buffer = gl.createBuffer();
          if (!buffer) continue;
          renderer.texturedBuffers.set(bufferKey, buffer);
          if (rendererDiagnostics) window.__anvilTexturedRendererStats.buffer_allocations += 1;
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
        gl.bufferData(gl.ARRAY_BUFFER, vertices.subarray(0, triangleCount * 27), gl.DYNAMIC_DRAW);
        if (rendererDiagnostics) {
          const stats = window.__anvilTexturedRendererStats;
          stats.batches += 1;
          stats.draw_calls += 1;
          stats.uploaded_bytes += triangleCount * 27 * Float32Array.BYTES_PER_ELEMENT;
        }
        const stride = 9 * 4;
        gl.enableVertexAttribArray(renderer.texturedPos);
        gl.vertexAttribPointer(renderer.texturedPos, 2, gl.FLOAT, false, stride, 0);
        gl.enableVertexAttribArray(renderer.texturedDepth);
        gl.vertexAttribPointer(renderer.texturedDepth, 1, gl.FLOAT, false, stride, 2 * 4);
        gl.enableVertexAttribArray(renderer.texturedUv);
        gl.vertexAttribPointer(renderer.texturedUv, 2, gl.FLOAT, false, stride, 3 * 4);
        gl.enableVertexAttribArray(renderer.texturedTint);
        gl.vertexAttribPointer(renderer.texturedTint, 4, gl.FLOAT, false, stride, 5 * 4);
        gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL);
        gl.drawArrays(gl.TRIANGLES, 0, triangleCount * 3);
      }
      if (spheres.length && renderer.sphere) {
        const shader = renderer.sphere;
        const shadowData = new Float32Array(32 * 4);
        for (let index = 0; index < Math.min(32, spheres.length); index++) {
          const sphere = spheres[index];
          shadowData.set([sphere[0], sphere[1], sphere[2], sphere[3]], index * 4);
        }
        const drawSpheres = spheres.sort((a, b) => b[2] - a[2]);
        const vertices = new Float32Array(drawSpheres.length * 60);
        let vertexCount = 0;
        const appendVertex = (x, y, centerRadius, colour) => {
          let at = vertexCount++ * 10;
          vertices[at++] = x;
          vertices[at++] = y;
          vertices[at++] = centerRadius[0];
          vertices[at++] = centerRadius[1];
          vertices[at++] = centerRadius[2];
          vertices[at++] = centerRadius[3];
          vertices[at++] = colour[0];
          vertices[at++] = colour[1];
          vertices[at++] = colour[2];
          vertices[at] = colour[3];
        };
        for (const sphere of drawSpheres) {
          const [cx, cy, cz, radius, r, g, b, a, , , , focal] = sphere;
          if (cz + radius <= 0.05) continue;
          const denominator = cz * cz - radius * radius;
          let left = 0, right = 960, top = 0, bottom = 600;
          if (denominator > 1e-9) {
            const xRoot = radius * Math.sqrt(Math.max(0, cx * cx + cz * cz - radius * radius));
            const yRoot = radius * Math.sqrt(Math.max(0, cy * cy + cz * cz - radius * radius));
            const minX = (cx * cz - xRoot) / denominator;
            const maxX = (cx * cz + xRoot) / denominator;
            const minY = (cy * cz - yRoot) / denominator;
            const maxY = (cy * cz + yRoot) / denominator;
            left = Math.max(0, 480 + focal * minX);
            right = Math.min(960, 480 + focal * maxX);
            top = Math.max(0, 324 - focal * maxY);
            bottom = Math.min(600, 324 - focal * minY);
          }
          if (left >= right || top >= bottom) continue;
          const color = [r / 255, g / 255, b / 255, a / 255];
          const centerRadius = [cx, cy, cz, radius];
          appendVertex(left, top, centerRadius, color);
          appendVertex(right, top, centerRadius, color);
          appendVertex(right, bottom, centerRadius, color);
          appendVertex(left, top, centerRadius, color);
          appendVertex(right, bottom, centerRadius, color);
          appendVertex(left, bottom, centerRadius, color);
        }
        if (vertexCount) {
          const first = spheres[0];
          gl.useProgram(shader.program);
          gl.uniform3f(shader.light, first[8], first[9], first[10]);
          gl.uniform1f(shader.focal, first[11]);
          gl.uniform4fv(shader.shadows, shadowData);
          gl.uniform1i(shader.sphereCount, Math.min(32, spheres.length));
          const buffer = gl.createBuffer();
          gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
          gl.bufferData(gl.ARRAY_BUFFER, vertices.subarray(0, vertexCount * 10), gl.DYNAMIC_DRAW);
          const stride = 10 * 4;
          gl.enableVertexAttribArray(shader.pos);
          gl.vertexAttribPointer(shader.pos, 2, gl.FLOAT, false, stride, 0);
          gl.enableVertexAttribArray(shader.centerRadius);
          gl.vertexAttribPointer(shader.centerRadius, 4, gl.FLOAT, false, stride, 2 * 4);
          gl.enableVertexAttribArray(shader.colour);
          gl.vertexAttribPointer(shader.colour, 4, gl.FLOAT, false, stride, 6 * 4);
          gl.enable(gl.DEPTH_TEST);
          gl.depthFunc(gl.LEQUAL);
          gl.enable(gl.BLEND);
          gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
          if (gpuTimerExt && gpuTimerRequested) {
            const query = gpuTimerExt.createQueryEXT();
            gpuTimerExt.beginQueryEXT(gpuTimerExt.TIME_ELAPSED_EXT, query);
            gl.drawArrays(gl.TRIANGLES, 0, vertexCount);
            gpuTimerExt.endQueryEXT(gpuTimerExt.TIME_ELAPSED_EXT);
            gpuTimerQueries.push(query);
          } else {
            gl.drawArrays(gl.TRIANGLES, 0, vertexCount);
          }
          gl.deleteBuffer(buffer);
        }
      }
      upload(list.filter((entry) => entry[13] === 1), false);
      context.drawImage(canvas, 0, 0);
      return true;
    };
    const imageCache = new Map();
    const audioState = { ctx: null, voices: new Map(), nextVoice: 0, active: 0 };
    const musicState = { source: null, mediaNode: null, gain: null, startedAt: 0, loop: false, length: 0, error: "" };
    const readCString = (pointer) => {
      const bytes = new Uint8Array(memory.buffer);
      let end = pointer;
      while (end < bytes.length && bytes[end] !== 0) end++;
      return utf8.decode(bytes.subarray(pointer, end));
    };
    const triangles = [];
    const texturedTriangles = [];
    const sphereImpostors = [];
    let rendererDiagnostics = new URLSearchParams(location.search).get("anvil_debug") === "1";
    if (gpuTimerRequested) {
      window.__anvilGpuTimer = {
        available: () => !!(createGlRenderer() && gpuTimerExt),
        collect: () => {
          const renderer = createGlRenderer();
          if (!renderer || !gpuTimerExt) return { available: false, samples_ms: [], disjoint: false };
          if (renderer.gl.getParameter(gpuTimerExt.GPU_DISJOINT_EXT)) gpuTimerDisjoint = true;
          const samples = [];
          for (let index = gpuTimerQueries.length - 1; index >= 0; index--) {
            const query = gpuTimerQueries[index];
            if (!gpuTimerExt.getQueryObjectEXT(query, gpuTimerExt.QUERY_RESULT_AVAILABLE_EXT)) continue;
            const ns = gpuTimerExt.getQueryObjectEXT(query, gpuTimerExt.QUERY_RESULT_EXT);
            gpuTimerExt.deleteQueryEXT(query);
            gpuTimerQueries.splice(index, 1);
            samples.push(ns / 1e6);
          }
          return { available: true, samples_ms: samples, pending: gpuTimerQueries.length, disjoint: gpuTimerDisjoint };
        },
      };
    }
    const audioContext = () => {
      if (!audioState.ctx) {
        const Ctor = window.AudioContext || window.webkitAudioContext;
        if (!Ctor) return null;
        audioState.ctx = new Ctor();
      }
      if (audioState.ctx.state === "suspended") audioState.ctx.resume();
      return audioState.ctx;
    };
    const resumeAudio = () => {
      if (audioState.ctx && audioState.ctx.state === "suspended") {
        audioState.ctx.resume();
      }
    };
    window.addEventListener("keydown", resumeAudio);
    window.addEventListener("pointerdown", resumeAudio);
    const audioGroups = [];
    const groupVolume = { 0: 1, 1: 1, 2: 1, 3: 1 };
    const groupMuted = { 0: false, 1: false, 2: false, 3: false };
    const audioGroup = (index) => {
      const ctx = audioState.ctx;
      if (!audioGroups[0]) {
        audioGroups[0] = ctx.createGain();
        audioGroups[0].gain.value = groupMuted[0] ? 0 : groupVolume[0];
        audioGroups[0].connect(ctx.destination);
        for (let slot = 1; slot <= 3; slot++) {
          audioGroups[slot] = ctx.createGain();
          audioGroups[slot].gain.value = groupMuted[slot] ? 0 : groupVolume[slot];
          audioGroups[slot].connect(audioGroups[0]);
        }
      }
      return audioGroups[index] || audioGroups[1];
    };
    window.anvilAudio = () => ({
      active: audioState.active,
      voices: audioState.voices.size,
      state: audioState.ctx ? audioState.ctx.state : "none",
      sampleRate: audioState.ctx ? audioState.ctx.sampleRate : 0,
      groups: audioGroups.map((node) => (node ? node.gain.value : 1)),
      music: {
        playing: musicState.source ? true : false,
        position: musicState.source && audioState.ctx
          ? audioState.ctx.currentTime - musicState.startedAt
          : 0,
      },
    });
    const tintedSurface = (pointer, width, height, tintR, tintG, tintB) => {
      const key = pointer + ":" + tintR + ":" + tintG + ":" + tintB;
      let offscreen = imageCache.get(key);
      if (offscreen) return offscreen;
      const source = new Uint32Array(memory.buffer, pointer, width * height);
      offscreen = document.createElement("canvas");
      offscreen.width = width;
      offscreen.height = height;
      const surface = offscreen.getContext("2d");
      const image = surface.createImageData(width, height);
      const out = new Uint32Array(image.data.buffer);
      for (let index = 0; index < width * height; index++) {
        const pixel = source[index];
        const a = (pixel >>> 24) & 255;
        const r = Math.round((((pixel >>> 16) & 255) * tintR) / 255);
        const g = Math.round((((pixel >>> 8) & 255) * tintG) / 255);
        const b = Math.round(((pixel & 255) * tintB) / 255);
        out[index] = ((a << 24) | (b << 16) | (g << 8) | r) >>> 0;
      }
      surface.putImageData(image, 0, 0);
      imageCache.set(key, offscreen);
      return offscreen;
    };
    const stopMusicPlayback = () => {
      const source = musicState.source;
      if (source) {
        try {
          if (typeof source.pause === "function") {
            source.pause();
            source.currentTime = 0;
          } else {
            source.stop();
          }
        } catch (error) { /* playback already ended */ }
      }
      musicState.source = null;
      musicState.mediaNode = null;
      musicState.gain = null;
      musicState.startedAt = 0;
      musicState.length = 0;
    };
    let pendingFade = 0;
    // Saves live in IndexedDB so a project is not capped by localStorage's small
    // string quota. Anvil's save API is synchronous, so the whole namespace is
    // read into a Map before the module starts; writes land in the Map at once
    // and reach IndexedDB in the background. Where IndexedDB is unavailable -
    // the Node harness, a locked-down browser - the same interface is backed by
    // localStorage, and any saves left there by an older build are carried over
    // once.
    const openSaveStore = async () => {
      // Its own cache, not the wasm `memory` object: the two are unrelated and
      // a name collision here fails at the first save.
      const cache = new Map();
      const localStore = () => ({
        backend: "localStorage",
        get: (key) => {
          try {
            const value = localStorage.getItem(key);
            return value === null ? undefined : value;
          } catch (error) {
            return undefined;
          }
        },
        set: (key, value) => {
          try {
            localStorage.setItem(key, value);
          } catch (error) {
            console.warn("Anvil: the save could not be written", error);
          }
        },
        remove: (key) => {
          try {
            const existed = localStorage.getItem(key) !== null;
            localStorage.removeItem(key);
            return existed;
          } catch (error) {
            return false;
          }
        },
      });
      if (!window.indexedDB) return localStore();
      let db;
      try {
        db = await new Promise((resolve, reject) => {
          const request = indexedDB.open("anvil-saves", 1);
          request.onupgradeneeded = () => {
            const upgraded = request.result;
            if (!upgraded.objectStoreNames.contains("saves")) {
              upgraded.createObjectStore("saves");
            }
          };
          request.onsuccess = () => resolve(request.result);
          request.onerror = () => reject(request.error);
          request.onblocked = () => reject(new Error("the database is blocked"));
        });
        const rows = await new Promise((resolve, reject) => {
          const request = db.transaction("saves", "readonly").objectStore("saves").openCursor();
          const found = [];
          request.onsuccess = () => {
            const cursor = request.result;
            if (!cursor) {
              resolve(found);
              return;
            }
            found.push([cursor.key, cursor.value]);
            cursor.continue();
          };
          request.onerror = () => reject(request.error);
        });
        for (const [key, value] of rows) {
          if (typeof key === "string" && typeof value === "string") cache.set(key, value);
        }
      } catch (error) {
        console.warn("Anvil: IndexedDB is unavailable, saves use localStorage", error);
        return localStore();
      }
      // Carry over saves written by a build that used localStorage.
      try {
        const legacy = [];
        for (let index = 0; index < localStorage.length; index++) {
          const key = localStorage.key(index);
          if (key && key.indexOf("anvil:") === 0) {
            legacy.push([key, localStorage.getItem(key)]);
          }
        }
        for (const [key, value] of legacy) {
          if (value === null || cache.has(key)) continue;
          const tx = db.transaction("saves", "readwrite");
          tx.objectStore("saves").put(value, key);
          await new Promise((resolve, reject) => {
            tx.oncomplete = resolve;
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error || new Error("migration aborted"));
          });
          cache.set(key, value);
          localStorage.removeItem(key);
        }
      } catch (error) {
        console.warn("Anvil: old saves could not be migrated", error);
      }
      const persist = (key, value, removing) => {
        try {
          const store = db.transaction("saves", "readwrite").objectStore("saves");
          if (removing) store.delete(key);
          else store.put(value, key);
        } catch (error) {
          console.warn("Anvil: the save could not be persisted", error);
        }
      };
      return {
        backend: "indexedDB",
        get: (key) => cache.get(key),
        set: (key, value) => {
          cache.set(key, value);
          persist(key, value, false);
        },
        remove: (key) => {
          const existed = cache.has(key);
          cache.delete(key);
          persist(key, undefined, true);
          return existed;
        },
      };
    };
    const saveStore = await openSaveStore();
    window.anvilSaveBackend = saveStore.backend;
    const imports = { env: {
      fade(alpha) {
        pendingFade = alpha;
      },
      /* The focused control's accessible label, for the aria-live region. */
      announce(pointer, length) {
        const text = utf8.decode(new Uint8Array(memory.buffer, pointer, length));
        if (announceRegion) announceRegion.textContent = text;
        if (window.anvilAnnouncer) window.anvilAnnouncer(text);
      },
      write(fd, pointer, length) {
        const view = new Uint8Array(memory.buffer, pointer, length);
        const text = utf8.decode(view);
        if (fd === 2) console.error(text);
        else console.log(text);
      },
      runtime_error(messagePointer, functionPointer, line) {
        throw new Error(
          "Anvil runtime error in fn(" + readCString(functionPointer) +
          ") at line " + line + ": " + readCString(messagePointer)
        );
      },
      clear(r, g, b, a) {
        context.fillStyle = rgba(r, g, b, a);
        context.fillRect(0, 0, canvas.width, canvas.height);
      },
      rect(x, y, w, h, r, g, b, a) {
        context.fillStyle = rgba(r, g, b, a);
        context.fillRect(x, y, w, h);
      },
      circle(x, y, radius, r, g, b, a) {
        context.fillStyle = rgba(r, g, b, a);
        context.beginPath();
        context.arc(x, y, Math.abs(radius), 0, Math.PI * 2);
        context.fill();
      },
      line(x1, y1, x2, y2, thickness, r, g, b, a) {
        context.strokeStyle = rgba(r, g, b, a);
        context.lineWidth = Math.max(1, thickness);
        context.beginPath();
        context.moveTo(x1, y1);
        context.lineTo(x2, y2);
        context.stroke();
      },
      text(x, y, pointer, length, r, g, b, a) {
        const view = new Uint8Array(memory.buffer, pointer, length);
        context.fillStyle = rgba(r, g, b, a);
        context.font = "20px 'Segoe UI', system-ui, sans-serif";
        context.textBaseline = "top";
        context.fillText(utf8.decode(view), x, y);
      },
      image_draw(pointer, width, height, dx, dy, dw, dh, angle, tintR, tintG, tintB, flipX, flipY) {
        const offscreen = tintedSurface(pointer, width, height, tintR, tintG, tintB);
        context.save();
        context.translate(dx + dw / 2, dy + dh / 2);
        if (angle) context.rotate((angle * Math.PI) / 180);
        context.scale(flipX ? -1 : 1, flipY ? -1 : 1);
        context.drawImage(offscreen, -dw / 2, -dh / 2, dw, dh);
        context.restore();
      },
      image_region(pointer, width, height, sx, sy, sw, sh, dx, dy, dw, dh, tintR, tintG, tintB, flipX, flipY) {
        const offscreen = tintedSurface(pointer, width, height, tintR, tintG, tintB);
        context.save();
        context.translate(dx + dw / 2, dy + dh / 2);
        context.scale(flipX ? -1 : 1, flipY ? -1 : 1);
        context.drawImage(offscreen, sx, sy, sw, sh, -dw / 2, -dh / 2, dw, dh);
        context.restore();
      },
      music_play(pointer, frames, channels, rate, volume, loop) {
        const ctx = audioContext();
        if (!ctx || frames <= 0) return 0;
        stopMusicPlayback();
        const samples = new Int16Array(memory.buffer, pointer, frames * channels);
        const buffer = ctx.createBuffer(channels, frames, rate);
        for (let channel = 0; channel < channels; channel++) {
          const data = buffer.getChannelData(channel);
          for (let frame = 0; frame < frames; frame++) {
            data[frame] = samples[frame * channels + channel] / 32768;
          }
        }
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        source.loop = !!loop;
        const gain = ctx.createGain();
        gain.gain.value = volume;
        source.connect(gain).connect(audioGroup(1));
        source.onended = () => {
          if (musicState.source === source) musicState.source = null;
        };
        source.start();
        musicState.source = source;
        musicState.gain = gain;
        musicState.startedAt = ctx.currentTime;
        musicState.loop = !!loop;
        musicState.length = frames / rate;
        return 1;
      },
      music_stream(urlPointer, duration, volume, loop) {
        const ctx = audioContext();
        if (!ctx || !(duration > 0)) return 0;
        stopMusicPlayback();
        const audio = new Audio();
        audio.preload = "metadata";
        audio.loop = !!loop;
        audio.src = new URL(readCString(urlPointer), document.baseURI).href;
        const mediaNode = ctx.createMediaElementSource(audio);
        const gain = ctx.createGain();
        gain.gain.value = volume;
        mediaNode.connect(gain).connect(audioGroup(1));
        musicState.source = audio;
        musicState.mediaNode = mediaNode;
        musicState.gain = gain;
        musicState.length = duration;
        musicState.loop = !!loop;
        musicState.error = "";
        audio.onplaying = () => {
          if (musicState.source === audio && errors.textContent === musicState.error)
            errors.textContent = "";
        };
        audio.onended = () => {
          if (musicState.source === audio) musicState.source = null;
        };
        audio.onerror = () => {
          if (musicState.source === audio) {
            musicState.error = "the streamed music file could not be loaded or decoded";
            errors.textContent = musicState.error;
            musicState.source = null;
          }
        };
        audio.play().catch(() => {
          if (musicState.source === audio) {
            musicState.error = "browser playback was blocked; start music after a user gesture";
            errors.textContent = musicState.error;
            musicState.source = null;
          }
        });
        return 1;
      },
      music_stop() {
        stopMusicPlayback();
      },
      music_playing() {
        if (!musicState.source) return 0;
        if (typeof musicState.source.paused === "boolean")
          return !musicState.source.paused && !musicState.source.ended ? 1 : 0;
        return 1;
      },
      music_volume(volume) {
        if (musicState.gain) musicState.gain.gain.value = volume;
      },
      music_position() {
        if (!musicState.source) return 0;
        if (typeof musicState.source.currentTime === "number")
          return musicState.source.currentTime;
        if (!audioState.ctx) return 0;
        const elapsed = audioState.ctx.currentTime - musicState.startedAt;
        if (musicState.loop && musicState.length > 0) {
          return elapsed % musicState.length;
        }
        return Math.min(elapsed, musicState.length);
      },
      sound_play(pointer, frames, channels, rate, volume, loop, group) {
        const ctx = audioContext();
        if (!ctx || frames <= 0) return 0;
        const samples = new Int16Array(memory.buffer, pointer, frames * channels);
        const buffer = ctx.createBuffer(channels, frames, rate);
        for (let channel = 0; channel < channels; channel++) {
          const data = buffer.getChannelData(channel);
          for (let frame = 0; frame < frames; frame++) {
            data[frame] = samples[frame * channels + channel] / 32768;
          }
        }
        const source = ctx.createBufferSource();
        source.buffer = buffer;
        const gain = ctx.createGain();
        gain.gain.value = volume;
        const panner = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
        source.connect(gain);
        const destination = audioGroup((group === undefined ? 1 : group));
        if (panner) gain.connect(panner).connect(destination);
        else gain.connect(destination);
        source.loop = loop !== 0 && loop !== undefined;
        audioState.nextVoice += 1;
        const voice = audioState.nextVoice;
        audioState.voices.set(voice, { source, gain, panner, group: group || 1 });
        audioState.active += 1;
        source.onended = () => {
          if (audioState.voices.delete(voice)) {
            audioState.active = Math.max(0, audioState.active - 1);
          }
        };
        source.start();
        return voice;
      },
      sound_stop(voice) {
        const entry = audioState.voices.get(voice);
        if (!entry) return;
        try { entry.source.stop(); } catch (error) { /* already ended */ }
      },
      sound_stop_all() {
        for (const entry of audioState.voices.values()) {
          try { entry.source.stop(); } catch (error) { /* already ended */ }
        }
        audioState.voices.clear();
        audioState.active = 0;
      },
      sound_volume(voice, volume) {
        const entry = audioState.voices.get(voice);
        if (entry) entry.gain.gain.value = volume;
      },
      sound_pan(voice, pan) {
        const entry = audioState.voices.get(voice);
        if (entry && entry.panner) entry.panner.pan.value = pan;
      },
      sound_pitch(voice, rate) {
        const entry = audioState.voices.get(voice);
        if (entry) entry.source.playbackRate.value = rate;
      },
      sound_group_volume(group, volume) {
        if (group >= 0 && group <= 3) groupVolume[group] = volume;
        if (audioState.ctx && group >= 0 && group <= 3) audioGroup(group).gain.value = volume;
      },
      sound_group_mute(group, muted) {
        if (group >= 0 && group <= 3) groupMuted[group] = !!muted;
        if (audioState.ctx && group >= 0 && group <= 3) {
          audioGroup(group).gain.value = muted ? 0 : groupVolume[group] ?? 1;
        }
      },
      sound_group_stop(group) {
        let stopped = 0;
        for (const [voice, entry] of audioState.voices) {
          if (group === 0 || entry.group === group) {
            try { entry.source.stop(); } catch (error) { /* already ended */ }
            audioState.voices.delete(voice);
            audioState.active = Math.max(0, audioState.active - 1);
            stopped += 1;
          }
        }
        return stopped;
      },
      sound_active() {
        return audioState.active;
      },
      triangle(x1, y1, z1, x2, y2, z2, x3, y3, z3, r, g, b, a, layer) {
        if (glRenderer && glRenderer !== false) glRenderer.texturedCurrentRun = null;
        triangles.push([x1, y1, z1, x2, y2, z2, x3, y3, z3, r, g, b, a, layer]);
      },
      textured_triangle(pointer, count, pixels, width, height, layer) {
        const source = new Float64Array(memory.buffer, pointer, count * 19);
        const renderer = createGlRenderer();
        let vertices;
        if (renderer && !forcePainter) {
          const current = renderer.texturedCurrentRun;
          const key = pixels + ":" + width + ":" + height + ":" + layer;
          if (!current || current.key !== key) {
            renderer.texturedCurrentRun = { key, start: renderer.texturedVertexPoolIndex, count: 0 };
          }
          const run = renderer.texturedCurrentRun;
          const needed = (renderer.texturedVertexPoolIndex + count) * 27;
          let pool = renderer.texturedVertexPool;
          if (pool.length < needed) {
            const maximumFloats = Math.floor(48 * 1024 * 1024 / Float32Array.BYTES_PER_ELEMENT);
            if (needed > maximumFloats) throw new Error("textured vertex pool budget exceeded");
            let capacity = Math.max(27, pool.length);
            while (capacity < needed) capacity = Math.min(maximumFloats, Math.max(capacity + 27, capacity * 2));
            const grown = new Float32Array(capacity);
            grown.set(pool.subarray(0, renderer.texturedVertexPoolIndex * 27));
            pool = renderer.texturedVertexPool = grown;
          }
          vertices = pool;
          let at = renderer.texturedVertexPoolIndex * 27;
          for (let triangle = 0; triangle < count; triangle++) {
            const base = triangle * 19;
            for (const corner of [0, 5, 10]) {
              vertices[at++] = source[base + corner]; vertices[at++] = source[base + corner + 1];
              vertices[at++] = source[base + corner + 2]; vertices[at++] = source[base + corner + 3];
              vertices[at++] = source[base + corner + 4]; vertices[at++] = source[base + 15] / 255;
              vertices[at++] = source[base + 16] / 255; vertices[at++] = source[base + 17] / 255;
              vertices[at++] = source[base + 18] / 255;
            }
          }
          run.count += count;
          renderer.texturedVertexPoolIndex += count;
          if (texturedTriangles.length && texturedTriangles[texturedTriangles.length - 1].run === run) {
            texturedTriangles[texturedTriangles.length - 1] = { batch: true, count: run.count, pointer: pixels, width, height, layer, run };
          } else texturedTriangles.push({ batch: true, count: run.count, pointer: pixels, width, height, layer, run });
          return;
        }
        if (!vertices || vertices.length !== count * 27) {
          vertices = new Float32Array(count * 27);
        }
        let at = 0;
        for (let triangle = 0; triangle < count; triangle++) {
          const base = triangle * 19;
          for (const corner of [0, 5, 10]) {
            vertices[at++] = source[base + corner]; vertices[at++] = source[base + corner + 1];
            vertices[at++] = source[base + corner + 2]; vertices[at++] = source[base + corner + 3];
            vertices[at++] = source[base + corner + 4]; vertices[at++] = source[base + 15] / 255;
            vertices[at++] = source[base + 16] / 255; vertices[at++] = source[base + 17] / 255;
            vertices[at++] = source[base + 18] / 255;
          }
        }
        texturedTriangles.push({ batch: true, vertices, count, pointer: pixels, width, height, layer });
      },
      sphere_impostor_available() {
        if (forcePainter || !scene3dState.active) return 0;
        const renderer = createGlRenderer();
        const available = !!(renderer && renderer.sphere);
        if (rendererDiagnostics && window.__anvilSphereImpostorAvailable === undefined)
          window.__anvilSphereImpostorAvailable = available;
        return available ? 1 : 0;
      },
      sphere_impostor(x, y, z, radius, r, g, b, a, lightX, lightY, lightZ, focal) {
        sphereImpostors.push([x, y, z, radius, r, g, b, a, lightX, lightY, lightZ, focal]);
      },
      scene_mode(enabled) {
        scene3dState.active = enabled !== 0;
      },
      present() {
        if (rendererDiagnostics && sphereImpostors.length) {
          window.__anvilSphereImpostorCalls =
            (window.__anvilSphereImpostorCalls || 0) + sphereImpostors.length;
          rendererDiagnostics = false;
        }
        if (triangles.length || texturedTriangles.length || sphereImpostors.length) {
          if (!forcePainter && scene3dState.active && drawGl(triangles, texturedTriangles, sphereImpostors)) {
            triangles.length = 0;
            texturedTriangles.length = 0;
            sphereImpostors.length = 0;
          } else {
            if (!skipSort) triangles.sort(
              (first, second) =>
                first[13] - second[13] ||
                second[2] + second[5] + second[8] - (first[2] + first[5] + first[8])
            );
            for (const t of triangles) {
              context.fillStyle = "rgba(" + t[9] + "," + t[10] + "," + t[11] + "," + (t[12] / 255) + ")";
              context.beginPath();
              context.moveTo(t[0], t[1]);
              context.lineTo(t[3], t[4]);
              context.lineTo(t[6], t[7]);
              context.closePath();
              context.fill();
            }
            triangles.length = 0;
            for (const t of texturedTriangles) {
              if (t.batch) {
                for (let triangle = 0; triangle < t.count; triangle++) {
                  const base = triangle * 27;
                  const vertex = (corner) => base + corner * 9;
                  const i0 = vertex(0), i1 = vertex(1), i2 = vertex(2);
                  const points = [[t.vertices[i0], t.vertices[i0 + 1]],
                    [t.vertices[i1], t.vertices[i1 + 1]],
                    [t.vertices[i2], t.vertices[i2 + 1]]];
                  const source = [[t.vertices[i0 + 3] * t.width, (1 - t.vertices[i0 + 4]) * t.height],
                    [t.vertices[i1 + 3] * t.width, (1 - t.vertices[i1 + 4]) * t.height],
                    [t.vertices[i2 + 3] * t.width, (1 - t.vertices[i2 + 4]) * t.height]];
                  const [s0, s1, s2] = source;
                  const det = s0[0] * (s1[1] - s2[1]) + s1[0] * (s2[1] - s0[1]) + s2[0] * (s0[1] - s1[1]);
                  if (!Number.isFinite(det) || Math.abs(det) < 1e-8) continue;
                  const affine = (axis) => {
                    const [p0, p1, p2] = points.map((point) => point[axis]);
                    const a = (p0 * (s1[1] - s2[1]) + p1 * (s2[1] - s0[1]) + p2 * (s0[1] - s1[1])) / det;
                    const c = (p0 * (s2[0] - s1[0]) + p1 * (s0[0] - s2[0]) + p2 * (s1[0] - s0[0])) / det;
                    const e = (p0 * (s1[0] * s2[1] - s2[0] * s1[1]) + p1 * (s2[0] * s0[1] - s0[0] * s2[1]) + p2 * (s0[0] * s1[1] - s1[0] * s0[1])) / det;
                    return [a, c, e];
                  };
                  const [a, c, e] = affine(0), [b, d, f] = affine(1);
                  const image = tintedSurface(t.pointer, t.width, t.height,
                    Math.round(t.vertices[i0 + 5] * 255),
                    Math.round(t.vertices[i0 + 6] * 255),
                    Math.round(t.vertices[i0 + 7] * 255));
                  const pattern = context.createPattern(image, "repeat");
                  pattern.setTransform(new DOMMatrix([a, b, c, d, e, f]));
                  context.save();
                  context.beginPath(); context.moveTo(...points[0]);
                  context.lineTo(...points[1]); context.lineTo(...points[2]);
                  context.closePath();
                  context.globalAlpha = Math.max(0, Math.min(1, t.vertices[i0 + 8]));
                  context.fillStyle = pattern;
                  context.fill();
                  context.restore();
                }
              } else {
                context.fillStyle = "rgba(" + t[15] + "," + t[16] + "," + t[17] + "," + (t[18] / 255) + ")";
                context.beginPath(); context.moveTo(t[0], t[1]);
                context.lineTo(t[5], t[6]); context.lineTo(t[10], t[11]);
                context.closePath(); context.fill();
              }
            }
            texturedTriangles.length = 0;
            for (const sphere of sphereImpostors) {
              const depth = Math.max(0.05, sphere[2]);
              const radius = sphere[3] * sphere[11] / depth;
              context.fillStyle = rgba(sphere[4], sphere[5], sphere[6], sphere[7]);
              context.beginPath();
              context.ellipse(480 + sphere[0] * sphere[11] / depth,
                324 - sphere[1] * sphere[11] / depth, radius, radius, 0, 0, Math.PI * 2);
              context.fill();
            }
            sphereImpostors.length = 0;
          }
        }
        if (glRenderer && glRenderer !== false) {
          glRenderer.texturedVertexPoolIndex = 0;
          glRenderer.texturedCurrentRun = null;
        }
        // The fade sits above everything the frame drew, including 3D.
        if (pendingFade > 0) {
          context.fillStyle = "rgba(0,0,0," + Math.min(1, pendingFade / 255) + ")";
          context.fillRect(0, 0, canvas.width, canvas.height);
        }
      },
      save_read(pointer, out, capacity) {
        const value = saveStore.get("anvil:" + readCString(pointer));
        if (value === undefined) return -1;
        const bytes = new TextEncoder().encode(value);
        const view = new Uint8Array(memory.buffer, out, Math.min(bytes.length, capacity));
        view.set(bytes.subarray(0, view.length));
        return view.length;
      },
      save_write(pointer, valuePointer) {
        saveStore.set("anvil:" + readCString(pointer), readCString(valuePointer));
      },
      save_delete(pointer) {
        return saveStore.remove("anvil:" + readCString(pointer)) ? 1 : 0;
      },
    }};
    const instance = await WebAssembly.instantiate(module, imports);
    memory = instance.exports.memory;
    app = instance;
    // Exposed so a test page or console can step frames deterministically.
    window.anvil = instance;
    const keyCodes = { Space: 32, Enter: 13, Escape: 27, ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40 };
    const keyCode = (event) => {
      if (event.code && event.code.indexOf("Key") === 0) return event.code.charCodeAt(3);
      if (keyCodes[event.code] !== undefined) return keyCodes[event.code];
      return event.keyCode || 0;
    };
    // A keyup or mouseup that happens while another window has focus is never
    // delivered here, so the module would keep the key held forever and the
    // next press would not count as a fresh press. Releasing every input on
    // focus loss and on a hidden tab makes the next press a clean press.
    window.addEventListener("blur", () => {
      if (app) app.exports.anvil_input_release();
    });
    document.addEventListener("visibilitychange", () => {
      if (app && document.hidden) app.exports.anvil_input_release();
    });
    window.addEventListener("keydown", (event) => {
      if (!app) return;
      app.exports.anvil_key(keyCode(event), 1);
      if ([32, 37, 38, 39, 40].indexOf(keyCode(event)) >= 0) event.preventDefault();
    });
    window.addEventListener("keyup", (event) => {
      if (app) app.exports.anvil_key(keyCode(event), 0);
    });
    canvas.addEventListener("mousemove", (event) => {
      if (!app) return;
      const rect = canvas.getBoundingClientRect();
      app.exports.anvil_mouse(
        (event.clientX - rect.left) * canvas.width / rect.width,
        (event.clientY - rect.top) * canvas.height / rect.height
      );
    });
    canvas.addEventListener("mousedown", (event) => {
      if (app) app.exports.anvil_mouse_button([0, 2, 1][event.button] || 0, 1);
    });
    canvas.addEventListener("mouseup", (event) => {
      if (app) app.exports.anvil_mouse_button([0, 2, 1][event.button] || 0, 0);
    });
    canvas.addEventListener("wheel", (event) => {
      if (app) app.exports.anvil_wheel(event.deltaY);
    }, { passive: true });
    if (instance.exports.main) instance.exports.main();
    if (instance.exports.anvil_frame) {
      let last = performance.now();
      const tick = (now) => {
        const delta = now - last;
        last = now;
        try {
          instance.exports.anvil_frame(delta);
        } catch (error) {
          errors.textContent = describeError(error);
          console.error(errors.textContent);
          return;
        }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  } catch (error) {
    errors.textContent = describeError(error);
  }
}
start();
</script>
</html>
"""


def _find_tool(name: str) -> str | None:
    return shutil.which(name)


def validate(
    source_path: pathlib.Path, functions, top, source_text: str | None = None
) -> list[str]:
    text = source_text
    if text is None:
        text = pathlib.Path(source_path).read_text(encoding="utf-8")
    for match in DISPLAY_STATEMENT.finditer(text):
        if match.group(1) == "ray_triangle":
            line = text.count("\n", 0, match.start()) + 1
            raise CompileError(
                f"{source_path}:{line}: display ray_triangle(...) is not available "
                "in the wasm backend yet"
            )
        if match.group(1) == "ray_sphere":
            scene = SCENE_STATEMENT.search(text)
            if scene is None or scene.group(1) != "3d":
                line = text.count("\n", 0, match.start()) + 1
                raise CompileError(
                    f"{source_path}:{line}: display ray_sphere(...) requires scene 3d"
                )
        if match.group(1) in ALLOWED_SHAPES:
            continue
        line = text.count("\n", 0, match.start()) + 1
        raise CompileError(
            f"{source_path}:{line}: display {match.group(1)}(...) is not available "
            "in the wasm backend yet"
        )
    match = re.search(r"\bframe_capture\s*\(", text)
    if match:
        line = text.count("\n", 0, match.start()) + 1
        raise CompileError(
            f"{source_path}:{line}: 'frame_capture' is not available in the wasm "
            "backend yet (the canvas cannot be read back synchronously)"
        )
    match = re.search(r"-wrap\(", text)
    if match:
        line = text.count("\n", 0, match.start()) + 1
        raise CompileError(
            f"{source_path}:{line}: the -wrap modifier is not available in the "
            "wasm backend yet"
        )
    match = re.search(r"\btext_width\s*\(", text)
    if match:
        line = text.count("\n", 0, match.start()) + 1
        raise CompileError(
            f"{source_path}:{line}: 'text_width' is not available in the wasm "
            "backend yet"
        )
    match = re.search(r"-texture\(", text)
    if match:
        line = text.count("\n", 0, match.start()) + 1
        raise CompileError(
            f"{source_path}:{line}: the -texture modifier is not available in "
            "the wasm backend yet"
        )
    match = ENGINE_STATEMENT.search(text)
    if match:
        line = text.count("\n", 0, match.start()) + 1
        raise CompileError(
            f"{source_path}:{line}: 'engine' statements are not available in "
            "the wasm backend yet"
        )
    # The wasm model paths share the depth-tested triangle renderer. Static
    # models, morph groups, animated node poses and skinned vertex influences
    # are baked before submission; textured materials still need a separate path.
    model_calls = re.compile(
        r'\b(model_draw|model_draw_instance|ray_mesh)\s*\(\s*"((?:[^"\\]|\\.)*)"'
    )
    for match in model_calls.finditer(text):
        try:
            asset = json.loads('"' + match.group(2) + '"')
        except ValueError:
            continue
        is_ray_mesh = match.group(1) == "ray_mesh"
        is_instance_draw = match.group(1) == "model_draw_instance"
        if is_ray_mesh:
            scene = SCENE_STATEMENT.search(text)
            if scene is None or scene.group(1) != "3d":
                line = text.count("\n", 0, match.start()) + 1
                raise CompileError(
                    f"{source_path}:{line}: ray_mesh(...) requires scene 3d"
                )
        from compiler import gltf

        try:
            model = gltf.ensure_model(
                asset, pathlib.Path(source_path), include_textures=True
            )
        except gltf.ModelError:
            continue  # the C generator reports the real problem with the file
        # Static morph targets are supported by both model_draw and ray_mesh;
        # animated node groups use the same baked data and the runtime pose
        # evaluator; both lowerings submit their effective weights per group.
        if is_instance_draw and (model.get("skinned") or not model.get("morph_count")):
            line = text.count("\n", 0, match.start()) + 1
            raise CompileError(
                f"{source_path}:{line}: model_draw_instance requires an unskinned "
                "model with morph targets"
            )
    used = used_builtins(functions, top)
    for name in used:
        if name in ALLOWED_BUILTINS:
            continue
        for index, line_text in enumerate(text.splitlines(), 1):
            if re.search(rf"\b{re.escape(name)}\s*\(", line_text):
                raise CompileError(
                    f"{source_path}:{index}: '{name}' is not available in the wasm "
                    "backend yet"
                )
        raise CompileError(
            f"{source_path}: '{name}' is not available in the wasm backend yet"
        )
    return used



IMAGE_LOAD = re.compile(r'image_load\(\s*"((?:\\.|[^"\\])*)"')
MAX_BAKED_IMAGE_BYTES = 4 * 1024 * 1024


def _bmp_pixels(path: pathlib.Path) -> tuple[int, int, list[int]]:
    """Decode an uncompressed 4/8/24/32-bit BMP into 0xAARRGGBB pixels."""
    data = path.read_bytes()
    if len(data) < 54 or data[:2] != b"BM":
        raise ValueError("not a BMP file")
    offset = int.from_bytes(data[10:14], "little")
    width = int.from_bytes(data[18:22], "little", signed=True)
    height = int.from_bytes(data[22:26], "little", signed=True)
    bits = int.from_bytes(data[28:30], "little")
    if bits not in (4, 8, 24, 32):
        raise ValueError(f"{bits}-bit BMPs are not supported (4, 8, 24 or 32 only)")
    if width <= 0 or height == 0 or width > 8192 or abs(height) > 8192:
        raise ValueError("the image is outside the 8,192-pixel limit")
    header_size = int.from_bytes(data[14:18], "little")
    palette: list[tuple[int, int, int]] = []
    if bits in (4, 8):
        default = 1 << bits
        count = int.from_bytes(data[46:50], "little") or default
        count = min(count, default)
        base = 14 + header_size
        for index in range(count):
            at = base + index * 4
            if at + 3 >= len(data):
                raise ValueError("the palette is truncated")
            palette.append((data[at + 2], data[at + 1], data[at]))
    top_down = height < 0
    rows = abs(height)
    stride = ((width * bits + 7) // 8 + 3) & ~3
    if offset + stride * rows > len(data):
        raise ValueError("the file is too short for its declared size")
    pixels: list[int] = []
    for row in range(rows):
        source_row = row if top_down else rows - row - 1
        base = offset + source_row * stride
        for column in range(width):
            if bits == 4:
                packed = data[base + column // 2]
                index = (packed & 0x0F) if column & 1 else (packed >> 4)
                if index >= len(palette):
                    raise ValueError("a pixel index is outside the palette")
                red, green, blue = palette[index]
                alpha = 255
            elif bits == 8:
                index = data[base + column]
                if index >= len(palette):
                    raise ValueError("a pixel index is outside the palette")
                red, green, blue = palette[index]
                alpha = 255
            else:
                at = base + column * (bits // 8)
                blue, green, red = data[at], data[at + 1], data[at + 2]
                alpha = data[at + 3] if bits == 32 else 255
            pixels.append((alpha << 24) | (red << 16) | (green << 8) | blue)
    return width, rows, pixels


@_timed_asset_import
def bake_images(source_path: pathlib.Path, text: str) -> str:
    """Bake literal image_load() BMPs into C arrays the runtime can serve."""
    images: dict[str, tuple[int, int, list[int]]] = {}
    total_bytes = 0
    for match in IMAGE_LOAD.finditer(text):
        literal = match.group(1).replace("\\\\", "\\")
        if literal in images:
            continue
        target = (source_path.parent / literal).resolve()
        line = text.count("\n", 0, match.start()) + 1
        try:
            width, height, pixels = _bmp_pixels(target)
        except FileNotFoundError:
            raise CompileError(
                f"{source_path}:{line}: image_load cannot read \"{literal}\""
            ) from None
        except ValueError as error:
            raise CompileError(
                f"{source_path}:{line}: image_load \"{literal}\": {error}"
            ) from None
        total_bytes += len(pixels) * 4
        if total_bytes > MAX_BAKED_IMAGE_BYTES:
            raise CompileError(
                f"{source_path}:{line}: baked images exceed the 4 MiB budget"
            )
        images[literal] = (width, height, pixels)
    if not images:
        return "\nvoid anvil_wasm_register_images(void) {}\n"
    chunks = ["\n/* Baked images: the browser cannot read files synchronously. */"]
    for index, (_literal, (width, height, pixels)) in enumerate(images.items()):
        chunks.append(f"static const unsigned int anvil_baked_pixels_{index}[] = {{")
        row: list[str] = []
        for pixel in pixels:
            row.append(f"0x{pixel:08x}u")
            if len(row) == 12:
                chunks.append("  " + ", ".join(row) + ",")
                row = []
        if row:
            chunks.append("  " + ", ".join(row) + ",")
        chunks.append("};")
    chunks.append("static const AnvilWasmImage anvil_baked_images[] = {")
    for index, (literal, (width, height, _pixels)) in enumerate(images.items()):
        escaped = literal.replace("\\", "\\\\")
        chunks.append(f'  {{"{escaped}", {width}, {height}, anvil_baked_pixels_{index}}},')
    chunks.append("};")
    chunks.append(
        "void anvil_wasm_register_images(void) {\n"
        f"  anvil_wasm_set_images(anvil_baked_images, {len(images)});\n"
        "}\n"
    )
    return "\n".join(chunks)

SOUND_LOAD = re.compile(r'sound_load\(\s*"((?:\\.|[^"\\])*)"')
MAX_BAKED_SOUND_BYTES = 8 * 1024 * 1024
MAX_BAKED_MUSIC_BYTES = 16 * 1024 * 1024

MUSIC_LOAD = re.compile(r'music_load\(\s*"((?:\\.|[^"\\])*)"')

_WAV_PCM_SUBFORMAT_GUID = bytes.fromhex("0100000000001000800000aa00389b71")


def _wav_pcm_info(fmt: bytes, data_size: int) -> tuple[int, int, int, int]:
    """Validate supported PCM format metadata and return channels/rate/frames/stride."""
    if len(fmt) < 16:
        raise ValueError("the file has no fmt or data chunk")
    tag = int.from_bytes(fmt[0:2], "little")
    channels = int.from_bytes(fmt[2:4], "little")
    rate = int.from_bytes(fmt[4:8], "little")
    byte_rate = int.from_bytes(fmt[8:12], "little")
    block_align = int.from_bytes(fmt[12:14], "little")
    bits = int.from_bytes(fmt[14:16], "little")
    if tag == 0xFFFE:
        if (len(fmt) < 40 or int.from_bytes(fmt[16:18], "little") < 22 or
                int.from_bytes(fmt[18:20], "little") != bits or
                fmt[24:40] != _WAV_PCM_SUBFORMAT_GUID):
            raise ValueError("WAVE_FORMAT_EXTENSIBLE must contain PCM samples")
    elif tag != 1:
        raise ValueError("compressed WAVs are not supported (PCM only)")
    if channels not in (1, 2):
        raise ValueError("only mono or stereo WAVs are supported")
    if bits not in (8, 16):
        raise ValueError("only 8- or 16-bit PCM is supported")
    if not 8000 <= rate <= 192000:
        raise ValueError("the sample rate is outside 8,000-192,000")
    frame_bytes = channels * (bits // 8)
    if byte_rate != rate * frame_bytes or block_align != frame_bytes:
        raise ValueError("the WAV byte rate or block alignment does not match its format")
    if data_size % frame_bytes:
        raise ValueError("the WAV data size is not aligned to a complete sample frame")
    frames = data_size // frame_bytes
    if frames == 0:
        raise ValueError("the WAV holds no samples")
    return channels, rate, frames, frame_bytes


def _wav_pcm(path: pathlib.Path) -> tuple[int, int, int, list[int]]:
    """Decode a PCM WAV into (channels, rate, frames, interleaved int16)."""
    data = path.read_bytes()
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a RIFF WAVE file")
    position = 12
    fmt = None
    payload = None
    while position + 8 <= len(data):
        chunk = data[position : position + 4]
        size = int.from_bytes(data[position + 4 : position + 8], "little")
        body = data[position + 8 : position + 8 + size]
        position += 8 + size + (size & 1)
        if chunk == b"fmt ":
            fmt = body
        elif chunk == b"data":
            payload = body
        if fmt is not None and payload is not None:
            break
    if fmt is None or payload is None:
        raise ValueError("the file has no fmt or data chunk")
    channels, rate, frames, frame_bytes = _wav_pcm_info(fmt, len(payload))
    bits = int.from_bytes(fmt[14:16], "little")
    samples: list[int] = []
    for index in range(frames * channels):
        if bits == 8:
            samples.append((payload[index] - 128) << 8)
        else:
            at = index * 2
            samples.append(int.from_bytes(payload[at : at + 2], "little", signed=True))
    return channels, rate, frames, samples


def _wav_stream_info(path: pathlib.Path) -> tuple[int, int, int]:
    """Read PCM metadata without decoding or retaining the music sample data."""
    size = path.stat().st_size
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise ValueError("not a RIFF WAVE file")
        riff_end = int.from_bytes(header[4:8], "little") + 8
        if riff_end > size:
            raise ValueError("the RIFF container is truncated")
        position = 12
        fmt = None
        data_size = None
        while position + 8 <= riff_end:
            stream.seek(position)
            chunk_header = stream.read(8)
            if len(chunk_header) != 8:
                break
            chunk = chunk_header[:4]
            chunk_size = int.from_bytes(chunk_header[4:], "little")
            body = position + 8
            chunk_end = body + chunk_size
            if chunk_end > riff_end:
                raise ValueError("a RIFF chunk is truncated")
            if chunk == b"fmt ":
                stream.seek(body)
                fmt = stream.read(min(chunk_size, 64))
            elif chunk == b"data":
                data_size = chunk_size
            position = chunk_end + (chunk_size & 1)
    if fmt is None or data_size is None:
            raise ValueError("the file has no fmt or data chunk")
    channels, rate, frames, _frame_bytes = _wav_pcm_info(fmt, data_size)
    return channels, rate, frames


def _music_stream_target(source_path: pathlib.Path, text: str, out: pathlib.Path):
    match = MUSIC_LOAD.search(text)
    if not match:
        return None
    literal = match.group(1).replace("\\\\", "\\")
    source = (source_path.parent / literal).resolve()
    digest = hashlib.sha256(literal.encode("utf-8")).hexdigest()[:16]
    relative = pathlib.Path(f"{out.stem}_assets") / f"music-{digest}.wav"
    url = quote(relative.as_posix(), safe="/-_.")
    return source, out.parent / relative, url


@_timed_asset_import
def bake_music(
    source_path: pathlib.Path, text: str, *, stream_url: str | None = None
) -> str:
    """Emit metadata for browser-streamed music or PCM for host-only callers."""
    match = MUSIC_LOAD.search(text)
    if not match:
        return "\nvoid anvil_wasm_register_music(void) {}\n"
    literal = match.group(1).replace("\\\\", "\\")
    target = (source_path.parent / literal).resolve()
    line = text.count("\n", 0, match.start()) + 1
    try:
        if stream_url is not None:
            channels, rate, frames = _wav_stream_info(target)
            samples = None
        else:
            channels, rate, frames, samples = _wav_pcm(target)
    except FileNotFoundError:
        raise CompileError(
            f'{source_path}:{line}: music_load cannot read "{literal}"'
        ) from None
    except ValueError as error:
        raise CompileError(
            f'{source_path}:{line}: music_load "{literal}": {error}'
        ) from None
    if samples is not None and len(samples) * 2 > MAX_BAKED_MUSIC_BYTES:
        raise CompileError(
            f"{source_path}:{line}: baked music exceeds the 16 MiB budget"
        )
    chunks = ["\n/* Music metadata; linked WASM builds stream the sidecar WAV. */"]
    if samples is not None:
        chunks.append("static const short anvil_baked_music_pcm[] = {")
    if samples is not None:
        row: list[str] = []
        for sample in samples:
            row.append(str(sample))
            if len(row) == 16:
                chunks.append("  " + ", ".join(row) + ",")
                row = []
        if row:
            chunks.append("  " + ", ".join(row) + ",")
        chunks.append("};")
    escaped = literal.replace("\\", "\\\\").replace('"', '\\"')
    escaped_url = (
        '"' + stream_url.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if stream_url is not None
        else "NULL"
    )
    pcm_pointer = "anvil_baked_music_pcm" if samples is not None else "NULL"
    chunks.append(
        "static const AnvilWasmMusic anvil_baked_music = "
        f'{{"{escaped}", {escaped_url}, {channels}, {rate}, {frames}, '
        f"{frames / rate:.17g}, {pcm_pointer}}};"
    )
    chunks.append(
        "void anvil_wasm_register_music(void) {\n"
        "  anvil_wasm_set_music(&anvil_baked_music);\n"
        "}\n"
    )
    return "\n".join(chunks)


@_timed_asset_import
def bake_sounds(source_path: pathlib.Path, text: str) -> str:
    """Bake literal sound_load() WAVs into C arrays the runtime can serve."""
    sounds: dict[str, tuple[int, int, int, list[int]]] = {}
    total = 0
    for match in SOUND_LOAD.finditer(text):
        literal = match.group(1).replace("\\\\", "\\")
        if literal in sounds:
            continue
        target = (source_path.parent / literal).resolve()
        line = text.count("\n", 0, match.start()) + 1
        try:
            channels, rate, frames, samples = _wav_pcm(target)
        except FileNotFoundError:
            raise CompileError(
                f'{source_path}:{line}: sound_load cannot read "{literal}"'
            ) from None
        except ValueError as error:
            raise CompileError(
                f'{source_path}:{line}: sound_load "{literal}": {error}'
            ) from None
        total += len(samples) * 2
        if total > MAX_BAKED_SOUND_BYTES:
            raise CompileError(
                f"{source_path}:{line}: baked sounds exceed the 8 MiB budget"
            )
        sounds[literal] = (channels, rate, frames, samples)
    chunks: list[str] = ["\n/* Baked sounds: the browser cannot stream from disk. */"]
    for index, (_literal, (_channels, _rate, _frames, samples)) in enumerate(
        sounds.items()
    ):
        chunks.append(f"static const short anvil_baked_sound_{index}[] = {{")
        row: list[str] = []
        for sample in samples:
            row.append(str(sample))
            if len(row) == 16:
                chunks.append("  " + ", ".join(row) + ",")
                row = []
        if row:
            chunks.append("  " + ", ".join(row) + ",")
        chunks.append("};")
    if sounds:
        chunks.append("static const AnvilWasmSound anvil_baked_sounds[] = {")
        for index, (literal, (channels, rate, frames, _samples)) in enumerate(
            sounds.items()
        ):
            escaped = literal.replace("\\", "\\\\")
            chunks.append(
                f'  {{"{escaped}", {channels}, {rate}, {frames}, anvil_baked_sound_{index}}},'
            )
        chunks.append("};")
    chunks.append(
        "void anvil_wasm_register_sounds(void) {\n"
        f"  anvil_wasm_set_sounds(anvil_baked_sounds, {len(sounds)});\n"
        "}\n"
        if sounds
        else "void anvil_wasm_register_sounds(void) {}\n"
    )
    return "\n".join(chunks)

def build(
    source_path: pathlib.Path,
    functions,
    top,
    variables,
    arrays,
    out: pathlib.Path,
    fixed_hz: int,
    project_name: str,
    emit_c_path: pathlib.Path | None = None,
    phase_callback=None,
    debug_info: bool = False,
) -> None:
    global _toolchain_peak_working_set_bytes, _toolchain_process_tree_peak_working_set_bytes
    validate(source_path, functions, top)
    generated = emit_c(
        source_path,
        functions,
        top,
        variables,
        arrays,
        fixed_hz,
        project_name,
        runtime_header="anvil_wasm.h",
        minimal_includes=True,
        debug_line_tables=debug_info,
    )
    source_text = source_path.read_text(encoding="utf-8")
    music_asset = _music_stream_target(source_path, source_text, out)
    generated += bake_images(source_path, source_text)
    generated += bake_sounds(source_path, source_text)
    generated += bake_music(
        source_path,
        source_text,
        stream_url=music_asset[2] if music_asset else None,
    )
    if phase_callback is not None:
        phase_callback("generated")
    source_map = {
        c_name(name): {"name": name, "line": node.line}
        for name, node in functions.items()
    }
    if emit_c_path is not None:
        emit_c_path.parent.mkdir(parents=True, exist_ok=True)
        emit_c_path.write_text(generated, encoding="utf-8")
        if phase_callback is not None:
            phase_callback("emitted")
        return
    clang = _find_tool("clang")
    if clang is None:
        raise CompileError(
            "the wasm backend needs clang and wasm-ld on PATH; install LLVM or "
            "select --backend c"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = out.parent / ".anvil-cache"
    cache.mkdir(exist_ok=True)
    c_path = cache / (out.stem + ".wasm.c")
    c_path.write_text(generated, encoding="utf-8")
    if phase_callback is not None:
        phase_callback("before_link")
    command = [
        clang,
        "--target=wasm32-unknown-unknown",
        "-nostdlib",
        "-O2",
        f"-I{ROOT / 'runtime'}",
        f"-Wl,--no-entry",
        "-Wl,--export=main",
        "-Wl,--export-memory",
        "-o",
        str(out),
        str(c_path),
        str(ROOT / "runtime" / "anvil_wasm.c"),
    ]
    if debug_info:
        # Retain DWARF line tables in the WebAssembly module so browser
        # debuggers can map instruction addresses through the #line directives
        # emitted for Anvil statements.
        command.insert(3, "-gline-tables-only")
    if _measure_asset_imports:
        from tempfile import TemporaryFile

        from compiler.process_memory import (
            peak_working_set_bytes,
            sample_process_tree_peak_working_set_bytes,
        )

        with TemporaryFile() as stdout_file, TemporaryFile() as stderr_file:
            process = subprocess.Popen(command, stdout=stdout_file, stderr=stderr_file)
            _toolchain_process_tree_peak_working_set_bytes = (
                sample_process_tree_peak_working_set_bytes(process)
            )
            returncode = process.wait()
            _toolchain_peak_working_set_bytes = peak_working_set_bytes(process._handle)
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace")
    else:
        result = subprocess.run(command, capture_output=True, text=True)
        stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
    if returncode != 0:
        raise CompileError(
            "wasm build failed:\n" + (stderr or stdout).strip()
        )
    if music_asset:
        music_source, music_destination, _music_url = music_asset
        music_destination.parent.mkdir(parents=True, exist_ok=True)
        if music_source.resolve() != music_destination.resolve():
            shutil.copy2(music_source, music_destination)
    page = out.with_suffix(".html")
    page.write_text(
        HOST_PAGE.replace("__TITLE__", out.stem)
        .replace("__WASM__", out.name)
        .replace("__SOURCE_MAP__", json.dumps(source_map)),
        encoding="utf-8",
    )
    out.with_suffix(".map.json").write_text(
        json.dumps(source_map, indent=2) + "\n", encoding="utf-8"
    )
    if phase_callback is not None:
        phase_callback("linked")
