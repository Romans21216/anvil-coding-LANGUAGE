# 3D models (glTF)

`model_draw("model.gltf", x, y, z, scale, rx, ry, rz)` draws a glTF model with
the scene camera, near-plane clipping, the depth buffer and the same flat light
as `cube`.

The model is not loaded at runtime. The compiler reads the file while building,
applies node transforms, bakes one flat colour per triangle and emits a static
`double` array into the generated C. Nothing is parsed at startup and the model
does not have to ship beside the executable (the source `.gltf` must still exist
to rebuild). Paths are resolved relative to the main `.ANVL` file.

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
| Budget | 200,000 triangles, checked at compile time |

Not supported yet, and reported as a located compile error: skins, morph
targets, animations, textures, sparse accessors and primitive modes other than
triangles/strips/fans.

## Shading

Each triangle is flat-shaded with the scene light, so curved models show facets.
Colours from glTF are linear; Anvil multiplies them by 255 without a colour
transform, so a `baseColorFactor` of `[1, 0, 0, 1]` renders as red but is not
gamma-managed.

## Error messages

A missing or malformed model stops the build at the `model_draw` line, naming
the resolved path and the reason — for example `cannot find model
'models/teapot.gltf'` or `binary .glb containers are not supported`. Nothing is
silently skipped.

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
