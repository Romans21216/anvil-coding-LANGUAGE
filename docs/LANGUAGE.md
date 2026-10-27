# Anvil Language Guide

Anvil uses UTF-8 text in `.ANVL` files. Its syntax is designed to read like a small BASIC/Lua-inspired scripting language: define a function with `fn(name)` or `fn(name, parameter, ...)`, indent the body for readability, and close it with `end`. Indentation is optional; `end` defines the block.

```anv
# A tiny complete program
set var(score) = 12

fn(add-bonus)
  add var(score) 5
  output var(score)
end

fn(main)
  if call fn(add-bonus) >= 17
    output 17
  else
    output 0
  end
end

call fn(main)
```

Comments begin with `#` outside a quoted string. Names are case-sensitive. Function parameters and return values are numeric. `output expression` returns a value from the current function; functions without an `output` return `0`. `call fn(name, arguments...)` can be used as a statement or inside a numeric expression. Recursive calls are supported by the generated C functions. `while expression ... end` repeats its body while the numeric condition is nonzero. `for local(name) = start to end [step amount] ... end` iterates over an inclusive numeric range.

`var(name)` reads a global numeric variable, except that a function parameter with the same name takes precedence inside that function. `set local(name) = expression` declares function-local numeric state, initialized to `0` at function entry; `local(name)` reads it, and `add local(name) amount` / `sub local(name) amount` update it. Local names are visible only in their declaring function. Existing `set var(name)` assignments continue to use global state unless `name` is a parameter of the current function. The compiler validates local/global references and function-call arity before generating C.

Arithmetic uses `+`, `-`, `*`, `/`, and `%`; division by a value equal to zero (including negative zero) terminates the program with exit code 2 and reports the `.ANVL` source path and line. Nonzero division keeps normal floating-point behavior.

## Fixed-size numeric arrays

Declare a global numeric array at top level, or a function-local numeric array inside a function, using `array name(size)`. Both kinds are fixed-size and start with every element set to zero. A local array belongs to the current function call, so recursive calls and separate invocations get independent storage. Local arrays use checked heap allocation and are freed on every function return; each function call may declare up to 8,192 local elements, and all active local arrays in the process are limited to 16 MiB. Allocation failure or budget exhaustion prints the source path and line and exits with code 2. Globals may contain up to 1,048,576 elements each. Read an element using `array(name, index)` in any numeric expression and write it inside a function with `set array(name, index) = expression`. A local array is visible only inside its declaring function and cannot share a name with that function's parameter or scalar local. Indexes are zero-based and must be finite whole numbers from zero through `size - 1`; an invalid runtime index prints the source path and line and exits with code 2. Resizing, strings, and structures are not supported yet.

```anv
array scores(4)

fn(main)
  for local(index) = 0 to 3
    set array(scores, local(index)) = local(index) * 10
  end
  output array(scores, 2) + array(scores, 3) # prints 50
end

call fn(main)
```

Function-local arrays use the same syntax and live for one function invocation:

```anv
fn(sum-offset, offset)
  array values(3)
  for local(index) = 0 to 2
    set array(values, local(index)) = var(offset) + local(index)
  end
  output array(values, 0) + array(values, 1) + array(values, 2)
end
```

The runnable example is `examples/local_arrays.ANVL`; it prints `27`.

## Expressions

Supported arithmetic operators are `+`, `-`, `*`, `/`, and `%`; comparison operators are `=`, `==`, `!=`, `<`, `<=`, `>`, and `>=`; conditions can use `and` and `or`. Both logical operators short-circuit: `false and right` skips `right`, and `true or right` skips `right`, including calls with side effects. Arithmetic binds more tightly than comparisons, then `and`, then `or`. Numeric literals may be integers or decimals. `var(name)` reads a global or shadowing parameter; `local(name)` reads function-local state; `call fn(name, arguments...)` calls a function and evaluates to its numeric return value.

`while condition` begins a loop and `end` closes it. The condition is checked before each iteration. Ensure the loop body changes state used by its condition so the loop can finish. Loops can be nested inside functions, branches, or other loops.

```anv
fn(sum-to, limit)
  set local(index) = 1
  set local(total) = 0
  while local(index) <= var(limit)
    add local(total) local(index)
    add local(index) 1
  end
  output local(total)
end

call fn(sum-to, 5) # prints 15
```

`for local(index) = start to end [step amount]` evaluates its start, end, and step expressions once. The default step is `1`; negative steps count downward, and both endpoints are included when reached. A zero step runs zero iterations. The loop variable is a function-local numeric variable and retains its final value after the loop. A loop variable cannot be a function parameter, and nested `for` loops must use different local variable names.

```anv
fn(count-down)
  set local(total) = 0
  for local(index) = 5 to 1 step -2
    add local(total) local(index)
  end
  output local(index) # returns -1 after the loop; total is 9
end
```

Built-ins currently include `time()`, `delta()`, `pressed(KEY)`, `held(KEY)`, `rnd(low,high)`, `seed(value)`, `noise(x,y,z)`, `fbm(x,y,z,octaves,lacunarity,gain)`, `floor`, `ceil`, `sqrt`, `sin`, `cos`, `abs`, `min`, and `max`. The implemented key names include letters, `SPACE`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `ENTER`, and `ESCAPE`. The string-taking ray backend built-ins are described in the drawing section below.

The fixed-step physics built-ins are `body_create(x,y,radius,mass)`, `body_create_box(x,y,width,height,mass)`, `physics_capacity(n)`, `body_destroy(handle)`, `body_active(handle)`, `body_x(handle)`, `body_y(handle)`, `body_vx(handle)`, `body_vy(handle)`, `body_set_velocity(handle,vx,vy)`, `body_force(handle,fx,fy)`, `body_restitution(handle,value)`, `body_friction(handle,value)`, `body_collision(first,second)`, `physics_gravity(x,y)`, and `physics_step()`. Circle and centered axis-aligned box creation return a numeric body handle or `-1` on invalid input/capacity exhaustion. `physics_capacity(n)` sets the active body-slot limit to an integer from 1 through 128 and returns the configured capacity, or `-1` if invalid or if live slots would be excluded. `body_friction` accepts values from 0 (frictionless) through 1 (maximum supported), defaulting to 0.5 per body. Status calls return `1` or `0`; invalid body queries return `-1`. `physics_step()` uses the engine fixed delta and returns its initial overlap-pair count. The runtime resolves circle-circle, box-box, and circle-box contacts; see [the physics section in the engine guide](ENGINE.md#fixed-step-2d-physics) for limits and numeric bounds.

## Drawing and input

`scene 2d` / `scene 3d`, `camera perspective x y z`, `camera fov(degrees)`, `camera control(move_speed,turn_speed)`, and `clear rgba(r,g,b,a)` configure the native window runtime. Camera movement uses WASD, Q/E for vertical movement, and the arrow keys for looking when camera controls are enabled. Draw commands belong inside `fn(draw)`:

```anv
fn(draw)
  display rect(40, 60, 180, 90) -rgb(55, 85, 130)
  display cube(0, 0, 0, 1.5) -rgb(235, 150, 74) -rotate(0, time(), 0)
  display ray_sphere(-2, 0, 0, 0.8) -rgb(172, 106, 255)
  display text("Score: " + var(score)) -l(20, 24) -rgb(245, 245, 255)
end
```

Implemented draw functions are `rect`, `circle`, `line`, `text`, `cube`, `sphere`, `ray_sphere`, and `plane`. `ray_sphere(x,y,z,radius)` is Anvil's built-in per-pixel ray-traced sphere function. It uses a CPU bounding volume hierarchy (BVH) to find the closest sphere hit and cast hard shadows, with diffuse and specular lighting. One ray-trace batch supports up to 32 spheres. `ray_backend("bvh")` selects the CPU BVH backend at runtime; `ray_backend_available("dxr")` and `ray_backend_available("embree")` query backend support. Both accept a string and return numeric `1` or `0`. An unsuccessful selection leaves the active backend unchanged and prints a diagnostic. Only BVH is implemented in the current build, so DXR and Embree checks return `0`. `-rgb` and `-rgba` set a color, `-l(x,y)` sets text position, and `-rotate(x,y,z)` rotates a cube. `camera fov` accepts 20–120 degrees as a horizontal field of view; camera movement is configured by `camera control(speed,turn_speed)`. The starter sample in `examples/first_world.ANVL` demonstrates both features and builds into a Windows executable.

## Multiplayer

The current experimental API is `net host(port)`, `net join("IPv4",port)`, `net send(number)`, and `receive()`. It transfers a single numeric value over UDP to one LAN peer. See [MULTIPLAYER.md](MULTIPLAYER.md) for setup and limitations. It is a prototype transport primitive, not a complete game networking stack.

## Project and file formats

`.ANVL` is the source extension. `.ANVLproj` is the TOML project manifest. It accepts a project `name`, an `entry` path that must stay inside the project folder, and optional `[engine].fixed_hz` from 1 to 240. Unsupported settings are reported instead of silently ignored.

```toml
name = "First World"
entry = "examples/first_world.ANVL"

[engine]
fixed_hz = 60
```

## Not implemented yet

Static types, dynamically sized arrays, structures, modules/imports, assets/sprites, audio, 3D/polygon physics, save files, full 2D/3D scene management, a GPU renderer, reliable Internet multiplayer, and Rust code generation are future work. Parameters, returns, recursion, function-local numeric variables and arrays, `while`/inclusive numeric `for` loops, fixed-size global numeric arrays, and fixed-step 2D circle/axis-aligned-box physics are supported, but the language and engine remain much smaller than a general-purpose game engine today.

