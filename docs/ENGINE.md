# Anvil Engine Runtime

The initial runtime targets Windows and keeps the engine surface intentionally small. `fn(update)` runs at a fixed simulation rate (60 Hz by default), then the runtime clears its fixed-size 960×600 frame, calls `fn(draw)`, and presents the software-rendered pixels in a native window. `.ANVLproj` can set `engine.fixed_hz` from 1 to 240. `delta()` reports the fixed update step; `time()` reports elapsed wall time.

## Available commands

```anv
scene 3d
camera perspective 0 3 8
camera fov(70)
camera control(4, 80)
clear rgba(11, 16, 27, 255)

fn(draw)
  display cube(0, 0, 0, 2) -rgb(88, 164, 255) -rotate(0, time(), 0)
  display ray_sphere(-2, 0, 0, 1) -rgb(172, 106, 255)
  display rect(20, 20, 160, 40) -rgba(40, 70, 110, 255)
  display text("Hello") -l(28, 28) -rgb(245, 248, 255)
end
```

Current drawing primitives are `rect`, `circle`, `line`, `text`, `cube`, `sphere`, `ray_sphere`, and `plane`. `ray_sphere(x,y,z,radius)` is a built-in per-pixel ray-traced sphere. The renderer builds a bounding volume hierarchy (BVH) for ray-traced spheres and uses it for closest-hit and hard-shadow queries; diffuse lighting and a specular highlight are included. The current trace scene is limited to 32 spheres per batch. Colors use `-rgb(r,g,b)` or `-rgba(r,g,b,a)`. Text position uses `-l(x,y)`. `cube` accepts `-rotate(x,y,z)`. `scene 2d` uses an orthographic projection for 3D primitives; `scene 3d` uses the perspective camera set by `camera perspective x y z`. Screen-space 2D primitives remain usable in either mode, so a scene can mix HUD shapes and 3D objects.

`camera fov(degrees)` sets the horizontal field of view (clamped to 20–120 degrees). `camera control(move_speed, turn_speed)` enables keyboard movement during fixed updates: W/S move forward/backward, A/D strafe, Q/E move vertically, and the arrow keys turn and look up/down. Movement uses the fixed update step, so it is independent of frame rate. The sample world demonstrates these controls and ray-traced spheres.

The renderer uses hand-written C software rasterization for conventional primitives and CPU BVH ray tracing for `ray_sphere`. It is useful for a small starter game and for learning; it lacks GPU acceleration/DXR, mesh import, texture mapping, robust near-plane clipping, resize handling, and production-grade rasterization. Text uses the Windows GDI font path.

## Math, time, and input

- `delta()` and `time()` return seconds.
- `pressed(SPACE)` is a key-down edge preserved until the next fixed update; `held(SPACE)` stays true while a key is down. Letter keys and arrow keys are supported.
- `rnd(low, high)` returns an inclusive integer. `seed(value)` makes the xorshift generator repeatable.
- `noise(x,y,z)` is deterministic gradient noise; `fbm(x,y,z,octaves,lacunarity,gain)` combines octaves.
- Math calls include `floor`, `ceil`, `sqrt`, `sin`, `cos`, `abs`, `min`, and `max`.

## Fixed-step 2D circle physics

The runtime has a deterministic circle-body system with a fixed capacity of 128 bodies. A body is created with `body_create(x, y, radius, mass)`, which returns a numeric handle or `-1` when its arguments are invalid or the body table is full. A mass of `0` creates an immovable body; dynamic bodies require mass from `0.000001` through `1e12`. Radius must be from `0.000001` through `1e6`, and initial coordinates must be within ±1e9. Each body is a circle in world units. Handles include a generation value, so a destroyed body's stale handle does not silently refer to a later body that reuses its slot.

Call `physics_step()` once per `fn(update)` to integrate gravity and queued forces using the engine's fixed `delta()`. The default gravity is `(0, -9.81)`; `physics_gravity(x, y)` changes it, with each component limited to ±1e6. `body_force(handle, x, y)` accumulates force (each input and the accumulated components are limited to ±1e12) until the next step, and `body_set_velocity(handle, vx, vy)` sets a dynamic body's velocity (each component limited to ±1e6). `body_restitution(handle, amount)` sets bounce from `0` (no bounce) to `1` (fully elastic). The step resolves circle-circle overlaps with a bounded four-pass impulse and positional-correction solver, then returns the number of overlapping pairs found at the start of the step. `body_collision(a, b)` queries current circle overlap; `body_x`, `body_y`, `body_vx`, and `body_vy` read position/velocity; `body_active` checks a handle; `body_destroy` releases it. Status functions return `1` on success and `0` on failure; invalid handles return `0` for `body_active`/collision and `-1` for numeric queries. Static bodies ignore force/velocity changes. Coordinates are bounded to ±1e9 world units, radii to 1e6, and speed to 1e6 units/second.

This is 2D circle physics only: no polygon shapes, friction, joints, continuous collision detection, broad-phase acceleration, 3D physics, or spatial-units conversion. Pair checking is O(n²) over the 128 body slots. See `examples/physics.ANVL` for an executable input-and-rendering sample.

Bindings written with `set var(name)` are global numeric state unless shadowed by a function parameter. Functions accept numeric parameters (`fn(name, value, ...)`), return numeric values with `output expression`, support recursion, and can declare function-local numeric state with `set local(name) = expression`. `while condition ... end` and inclusive numeric `for local(index) = start to end [step amount] ... end` loops are supported. Engine callbacks `fn(update)` and `fn(draw)` must remain zero-argument. The compiler rejects strings in numeric expressions before C generation. Keep update/draw work small: the current loop does not implement interpolation, job scheduling, or a scene graph.

## Planned extensions

Sprites and asset handles, audio, 3D physics, polygon collision, a GPU-backed DXR renderer, persistence, mouse/controller input, platform backends, and profiling tools remain future work. The compiler rejects statements that have not been implemented instead of silently treating them as active features.

