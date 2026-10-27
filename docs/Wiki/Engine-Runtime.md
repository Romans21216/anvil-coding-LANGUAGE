# Engine Runtime

The native runtime also includes deterministic fixed-step 2D physics for circles and axis-aligned boxes. Programs can configure the active body-slot limit up to 128. Read the [physics API and limits](../ENGINE.md#fixed-step-2d-physics); run `examples/physics.ANVL` or `examples/physics_boxes.ANVL` for playable samples.

The current native runtime uses a fixed 960 by 600 software pixel buffer. It has a fixed-step update callback (60 Hz by default) and a draw callback. A project may set `[engine].fixed_hz` from 1 to 240 in its `.ANVLproj` file.

## 2D and 3D drawing

Screen-space `rect`, `circle`, `line`, and `text` commands can be mixed with `cube`, raster `sphere`, `plane`, and `ray_sphere`. Conventional geometry uses CPU software rasterization and a depth buffer. `scene 2d` selects orthographic projection for 3D primitives; `scene 3d` uses the perspective camera.

## Camera

`camera perspective x y z` sets the camera position. `camera fov(degrees)` selects a horizontal field of view from 20 through 120 degrees. `camera control(move_speed, turn_speed)` enables WASD translation, Q/E vertical movement, and arrow-key look controls. Camera updates use the fixed simulation step.

## Built-in CPU BVH ray tracing

`display ray_sphere(x, y, z, radius) -rgb(r, g, b)` is the built-in ray-traced sphere draw function. It uses per-pixel CPU rays and a BVH for closest sphere and hard-shadow queries, with diffuse and specular lighting. A trace batch supports up to 32 spheres. Projection bounds use exact sphere tangent extents and are covered by a compiled C regression harness that samples off-axis and near-camera sphere surfaces.

BVH CPU ray tracing is the only implemented ray-tracing backend. DXR and Embree are not implemented. Conventional rendering also has no GPU backend, window resizing, texture mapping, mesh import, or robust production clipping across all primitive paths.

`ray_backend("bvh")` selects the ray-tracing backend at runtime, and `ray_backend_available("dxr")` checks whether a named backend is available. Both return numeric `1` or `0`. A failed selection keeps the current backend and prints a diagnostic. This build implements only `bvh`; DXR and Embree currently return unavailable.

Mouse input is available as `mouse_x()`, `mouse_y()`, `mouse_pressed("left"|"right"|"middle")`, `mouse_held(...)`, and `mouse_wheel()`. Pointer coordinates map through the centered aspect-preserving viewport to the virtual 960×600 framebuffer; a pointer in letterbox space returns `-1`. Button edges and wheel detents are consumed at fixed-update boundaries. `examples/mouse_input.ANVL` shows a click counter and cursor marker.

