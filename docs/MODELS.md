# 3D models (glTF)

`model_draw("model.gltf", x, y, z, scale, rx, ry, rz)` draws a glTF model with
the scene camera, near-plane clipping, the depth buffer and the same flat light
as `cube`. The same call accepts binary `.glb` files, including their embedded
JSON and BIN chunks. Both the C and WebAssembly backends bake model data during
the build and render it through their normal 3D triangle paths.

The model is not loaded at runtime. The compiler reads the file while building,
applies node transforms, bakes one flat colour per triangle and emits a static
`double` array into the generated C. Baked values use 17 significant decimal
digits so geometry and bounds round-trip the imported binary64 values. Nothing
is parsed at startup and the model does not have to ship beside the executable
(the source `.gltf` must still exist to rebuild). Paths are resolved relative to
the main `.ANVL` file.

Model and external-buffer paths must resolve inside the project folder, even
when an absolute path or symlink is used. In-root subfolders are supported;
parent-directory escapes are rejected. Import limits are 64 MiB per model
container, 256 MiB per buffer, 64 MiB for decoded accessor data, 200,000
triangles and 512 MiB of estimated generated geometry.

The GLB path imports geometry, node transforms and supported material/vertex
colours. Static unskinned `model_draw` calls on the C backend also render
base-color PNG textures using `TEXCOORD_0`; images can be external, data-URI or
embedded in a bufferView. Sampling uses nearest-neighbour filtering and REPEAT
wrapping. WebAssembly `model_draw` and `ray_mesh`, plus C `ray_mesh`, still use
`baseColorFactor` for textured models. `examples/glb_model.ANVL` shows the
`model_draw` path with the bundled `examples/ray_mesh.glb` asset.

```anvil
scene 3d
camera perspective 0 2 6
camera fov(60)

fn(draw)
  display plane(0, -1, 0, 12, 12) -rgb(33, 47, 64)
  set var(ok) = model_draw("models/teapot.gltf", 0, 0, 0, 1, 0, 0, 0)
end
```

Arguments after the path are position, uniform scale, then rotation in degrees
around X, Y and Z. The order is scale, rotate, translate.

## What is imported

| Feature | Support |
| --- | --- |
| `.gltf` JSON | Yes |
| `.glb` container | Yes; JSON and BIN chunks, unknown chunks skipped |
| Buffers | External `.bin`, `data:` base64 URI, or the GLB BIN chunk |
| Node hierarchy | Yes; matrix or translation/rotation/scale, 64 levels deep |
| Primitives | TRIANGLES, TRIANGLE_STRIP, TRIANGLE_FAN |
| Positions | `POSITION` as VEC3 float |
| Indices | ubyte/ushort/uint, or none (sequential) |
| Colour | `COLOR_0` (averaged per triangle) or material `baseColorFactor` |
| Base-color texture | Static unskinned `model_draw` on C and WebAssembly; PNG RGB/RGBA, `TEXCOORD_0`, REPEAT wrapping |
| Animation | One clip; TRANSLATION/ROTATION/SCALE channels, `LINEAR` and `STEP` keys |
| Skin | One skin, 1-64 joints, four influences per vertex, optional bind matrices |
| Morph targets | Up to eight `POSITION` deltas, per-mesh default weights |
| Budget | 200,000 triangles, checked at compile time |

`ray_mesh` uses `baseColorFactor` for textured models. Textures on animated,
skinned or morphed `model_draw` models are not supported yet.
PNG textures must be non-interlaced 8-bit RGB/RGBA, use `TEXCOORD_0`, and use
REPEAT wrapping; unsupported texture formats, UV sets, texture transforms or
wrap modes produce a located compile error. `COLOR_0` multiplies texture RGB;
`baseColorFactor` multiplies texture RGB and alpha. Sparse accessors, `CUBICSPLINE` keys,
multiple skins or clips, morph targets combined with a skin, and primitive
modes other than triangles/strips/fans are also refused with a located compile
error.

## Shading

Each triangle is flat-shaded with the scene light, so curved models show facets.
Colours from glTF are linear; Anvil multiplies them by 255 without a colour
transform, so a `baseColorFactor` of `[1, 0, 0, 1]` renders as red but is not
gamma-managed.

The scene light is controlled by `light(x,y,z)`, `light_ambient(level)` and
`light_intensity(level)` on the C and wasm backends. Model triangles are
two-sided. The wasm renderer uses the same ambient-plus-directional shading
formula as C; browser fixtures cover custom lighting and color output.

## Error messages

A missing or malformed model stops the build at the `model_draw` line, naming
the resolved path and the reason — for example `cannot find model
'models/teapot.gltf'` or `unsupported GLB version 1; only version 2 is
supported`. Nothing is silently skipped.

## Culling

Each model carries a bounding sphere computed while compiling. Every frame the
runtime tests that sphere against the view frustum and skips models that are
entirely behind the camera or entirely outside the viewport, so their triangles
are never transformed or rasterised. `mesh_culled()` and `mesh_drawn()` report
the counts for the current frame; `mesh_culling(0)` turns the test off and
`mesh_culling(1)` restores it.

Measured here with 20 off-screen models of 2,048 triangles each (40,960
triangles): 3.83 ms per frame with culling off, 0.20 ms with it on, an 18.9x
reduction in render time for that scene. Culling only helps when models are
outside the view; visible models take the normal path.

## Animation

A model whose file has an `animations` clip is baked in **node-local** space:
the node hierarchy (parent index plus base translation/rotation/scale) and the
keyframes ship with the model, and `model_draw` poses the hierarchy on the CPU
for that draw. A static model keeps the cheaper world-space bake.

```
set var(t) = model_animate("walk.gltf", 0.6)
set var(ok) = model_draw("walk.gltf", 0, 0, 0, 1, 0, 0, 0)
```

- One clip (the first) is imported. Channels may target any node with
  `translation`, `rotation` or `scale`; `LINEAR` and `STEP` samplers are
  supported, and rotations interpolate with slerp. `CUBICSPLINE` is refused at
  compile time.
- A node that uses a `matrix` instead of TRS is decomposed into TRS; a matrix
  that collapses an axis is refused, because it cannot be posed.
- `model_animate(path, seconds)` stores that model's clip clock and returns it.
  The clock wraps at the clip length, so playback loops: a draw at exactly the
  length shows the first key. `model_animation_length(path)` is the length in
  seconds, resolved at compile time.
- The clock starts at 0, which is the rest pose at the first key. Calling
  `model_animate` on a model with no clip is a compile error naming the line.
- The runtime keeps 32 clip clocks. A posed model (animated or skinned) that
  would need slot 32 or higher is refused at its `model_draw` line instead of
  silently reading clock 0 forever; static models past that point still build,
  because they never read a clock.
- Animated models skip the bounding-sphere culling test and overhead shadows;
  the whole hierarchy is drawn every frame.
- Wasm samples animated models in `model_draw` and `ray_mesh` using the WebGL
  depth-tested triangle path. Both APIs support one skin with up to 64 joints
  and four influences per vertex, using the first animation clip or bind pose.
  Skin draws skip culling and overhead shadows. The C backend still refuses
  skinned `ray_mesh` because its BVH path has no skinning support.

`tests/test_gltf_animation.py` measures ink bounds: a translation track moves
the triangle by the expected amount at half a second and a quarter of the way,
a rotation track changes its silhouette, a STEP track holds its left key until
the next one, and the clip wraps at its length.

## Skins

A model whose file has one `skin` is baked as a skinned mesh. Each vertex keeps
its mesh-space position, colour, four joint indices (`JOINTS_0`) and four
weights (`WEIGHTS_0`); the weights are normalised at import. The runtime
composes every joint as

```
jointMatrix[i] = nodeWorld[skin.joints[i]] * inverseBindMatrix[i]
```

and blends the four influences per vertex, then applies the usual model
placement and shading. One skin with 1-64 joints is supported; a primitive
missing `JOINTS_0` or `WEIGHTS_0`, a bind-matrix count that does not match the
joint list, and a second skin are refused at compile time with a located error.

`inverseBindMatrices` is optional in glTF. When a skin omits it, every joint
binds in mesh space, which the importer models as an identity matrix per joint.
A skinned primitive that also declares morph targets is refused: the skinned
draw path has no morph input, so accepting it would render the base shape and
quietly drop the targets.

A skinned model shares the animation clock: `model_animate(path, seconds)`
drives its joint channels. C and wasm `model_draw` pose it; wasm `ray_mesh` uses
the same skinned triangle submission. Both wasm APIs sample the first clip and
draw the bind pose when no clip exists. The C BVH `ray_mesh` path does not
support skinning. A vertex whose four weights are all zero keeps its mesh-space
position rather than collapsing to the origin.

`tests/test_gltf_skins.py` measures ink: a fully weighted joint moves the mesh
by the joint's animated translation, a 50/50 blend between a moving joint and a
static one lands half way, and a clip-less rig draws at rest. Malformed inputs
and the C `ray_mesh` limitation report the source line. `tests/test_wasm.py`
compares animated skinned `ray_mesh` and `model_draw` Node triangle streams and
checks their shared per-frame budget. Browser parity compares a 50/50 animated
skinned joint blend in `model_draw` against C with an offset, 58-degree, yawed
and pitched camera plus custom light direction, ambient floor and intensity,
while the skinned instance is translated, scaled and rotated.

## Morph targets

A static model may declare up to eight morph targets. The importer keeps one
`POSITION` delta per vertex per target (transformed into model space by the
node's matrix) and the mesh's default `weights`.

```
set var(previous) = model_morph("face.gltf", 0, 0.75)
set var(ok) = model_draw("face.gltf", 0, 0, 0, 1, 0, 0, 0)
```

- Every primitive in the model must declare the same number of targets, so the
  per-vertex delta stride is uniform; a mismatch, a target without a `POSITION`
  delta, or more than eight targets is refused at compile time.
- `model_morph(path, index, weight)` clamps the weight to 0-1, stores the
  override for that model asset and returns the previous value from its first
  geometry group, so a caller can restore it. A non-finite weight leaves the
  stored value alone.
- For independently deforming copies, create a handle with
  `model_instance(path)`, set weights with
  `model_instance_morph(path, handle, index, weight)`, and draw that copy with
  `model_draw_instance(path, handle, x, y, z, scale, rx, ry, rz)`. The draw API
  supports unskinned models with morph targets, including animated models. Each
  handle owns only its overrides; untouched targets keep each group's glTF
  defaults. The morph setter returns the previous value for the first geometry
  group's target. Its index must be an integer naming a present target; an
  invalid index or non-finite weight returns 0 and leaves the state unchanged.
  Store the returned handle in a variable before drawing it.
- `model_instance_destroy(path, handle)` releases a handle and returns 1, or 0
  for a stale or mismatched handle. The runtime keeps 64 live handles and uses
  generation-checked reuse, so destroyed handles cannot affect later instances.
  Creation returns 0 when the bounded table is full. C and wasm share these
  semantics. Existing `model_morph` and `model_draw` retain their asset-wide
  behavior.
- The weights start at the mesh's `weights` array the first time the model is
  drawn or a weight is set (so setting one weight before the first draw keeps
  the rest at their defaults), and stay per model for the life of the process.
  Animated, skinned and morphing model assets share a 32-slot runtime state
  table; registering a stateful asset beyond that limit is refused at compile
  time.
- Blending is additive on the vertex position before scale/rotate/translate;
  vertex colour does not animate. Static morph draws use per-geometry
  conservative bounds that cover default weights and every supported 0–1
  override, so fully offscreen groups can be culled without clipping a deformed
  pose. Animated and skinned draws bypass culling; wasm also bypasses this cull
  when shadows are enabled.
- C supports morph targets on static models and on animated, unskinned models;
  morph targets combined with skinning remain unsupported. Wasm
  `model_draw` and `ray_mesh` support static and animated unskinned morphs
  with per-group defaults and `model_morph` overrides. Skinned wasm
  `model_draw` and `ray_mesh` are supported; the C backend's skinned
  `ray_mesh` remains unsupported. Both model APIs share the wasm 16,384-triangle frame
  budget, with over-budget calls rejected before drawing.

`tests/test_gltf_morph.py` measures ink: weight 1 moves the triangle the whole
delta, 0.5 moves it half way, a mesh default of 1.0 is applied on the first
draw, weights clamp while returning the previous value, a model without targets
refuses `model_morph` at its source line, and wasm coverage verifies per-group
defaults and an override through both `model_draw` and `ray_mesh`.

