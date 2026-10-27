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

## Expressions

Supported arithmetic operators are `+`, `-`, `*`, `/`, and `%`; comparison operators are `=`, `==`, `!=`, `<`, `<=`, `>`, and `>=`; conditions can use `and` and `or`. Arithmetic binds more tightly than comparisons, then `and`, then `or`. Numeric literals may be integers or decimals. `var(name)` reads a global or shadowing parameter; `local(name)` reads function-local state; `call fn(name, arguments...)` calls a function and evaluates to its numeric return value.

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

Built-ins currently include `time()`, `delta()`, `pressed(KEY)`, `held(KEY)`, `rnd(low,high)`, `seed(value)`, `noise(x,y,z)`, `fbm(x,y,z,octaves,lacunarity,gain)`, `floor`, `ceil`, `sqrt`, `sin`, `cos`, `abs`, `min`, and `max`. The implemented key names include letters, `SPACE`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `ENTER`, and `ESCAPE`.

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

Implemented draw functions are `rect`, `circle`, `line`, `text`, `cube`, `sphere`, `ray_sphere`, and `plane`. `ray_sphere(x,y,z,radius)` is Anvil's built-in per-pixel ray-traced sphere function. It uses a CPU bounding volume hierarchy (BVH) to find the closest sphere hit and cast hard shadows, with diffuse and specular lighting. One ray-trace batch supports up to 32 spheres. `-rgb` and `-rgba` set a color, `-l(x,y)` sets text position, and `-rotate(x,y,z)` rotates a cube. `camera fov` accepts 20–120 degrees as a horizontal field of view; camera movement is configured by `camera control(speed,turn_speed)`. The starter sample in `examples/first_world.ANVL` demonstrates both features and builds into a Windows executable.

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

Static types, arrays, structures, modules/imports, assets/sprites, audio, collision/physics, save files, full 2D/3D scene management, a GPU renderer, reliable Internet multiplayer, and Rust code generation are future work. Parameters, returns, recursion, function-local numeric variables, `while` loops, and inclusive numeric `for` loops are supported, but the language and engine remain much smaller than a general-purpose game engine today.

