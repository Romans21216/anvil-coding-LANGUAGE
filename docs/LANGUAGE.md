# Anvil Language Guide

For the normative version 1 syntax and behavior contract, see the [formal language specification](LANGUAGE_SPEC.md).

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

A variable may carry an optional type: `set var(score): number = 0`, `set var(name): text = "Ada"`, `set var(alive): bool = true`. The three types are `number`, `text` and `bool`; `true` and `false` are the bool values, and a comparison (such as `2 > 1`) also counts as a bool. An annotated value must match, or the compiler reports `declared text but this value is a number` at that line before emitting anything. Unannotated variables keep inferring their type exactly as before, so existing programs are unchanged. A variable declared `: bool` prints as `true` or `false`; comparisons and `and`/`or`/`not` still produce numbers, so `say 1 = 1` prints `1`.

Comments begin with `#` outside a quoted string. Names are case-sensitive. A function parameter is numeric unless the body uses it as text — passing it to a text builtin, joining it with a text literal, comparing it with text, or returning it from a text-returning function — or unless every caller passes text; then it holds text. A function's `output` value is numeric unless it returns text (see Text and lists below). `output expression` returns a value from the current function; functions without an `output` return `0`. `call fn(name, arguments...)` can be used as a statement or inside an expression. Recursive calls are supported by both backends. `while expression ... end` repeats its body while the numeric condition is nonzero. `for local(name) = start to end [step amount] ... end` iterates over an inclusive numeric range. A top-level `set var(name) = expression` initializes a global before `main` runs, in source order.

## Language version

An optional version declaration may appear once, before any other source code:

```anv
language version 1
```

Blank lines and comments may appear before it. Version 1 is the current language definition. If the declaration is omitted, the compiler treats the file as version 1 so existing `.ANVL` projects continue to build. Unsupported versions, malformed declarations, duplicates, and declarations after source code receive a path-and-line diagnostic. A future incompatible syntax change can introduce a newer version without silently changing the meaning of older files.

`var(name)` reads a global numeric variable, except that a function parameter with the same name takes precedence inside that function. `set local(name) = expression` declares function-local numeric state, initialized to `0` at function entry; `local(name)` reads it, and `add local(name) amount` / `sub local(name) amount` update it. Local names are visible only in their declaring function. Existing `set var(name)` assignments continue to use global state unless `name` is a parameter of the current function. The compiler validates local/global references and function-call arity before generating C.

Arithmetic uses `+`, `-`, `*`, `/`, and `%`; division by a value equal to zero (including negative zero) terminates the program with exit code 2 and reports the `.ANVL` source path and line. Nonzero division keeps normal floating-point behavior. Every numeric expression must produce a finite value: overflow to positive/negative infinity or an invalid result such as `sqrt(-1)` reports the source path and line and exits with code 2. The check happens before comparisons too, so an overflowing intermediate cannot silently become a true/false result.

## Fixed-size numeric arrays

Declare a global numeric array at top level, or a function-local numeric array inside a function, using `array name(size)`. Both kinds are fixed-size and start with every element set to zero. A local array belongs to the current function call, so recursive calls and separate invocations get independent storage. Local arrays use checked heap allocation and are freed on every function return; each function call may declare up to 8,192 local elements, and all active local arrays in the process are limited to 16 MiB. Allocation failure or budget exhaustion prints the source path and line and exits with code 2. Globals may contain up to 1,048,576 elements each. Read an element using `array(name, index)` in any numeric expression and write it inside a function with `set array(name, index) = expression`. A local array is visible only inside its declaring function and cannot share a name with that function's parameter or scalar local. Indexes are zero-based and must be finite whole numbers from zero through `size - 1`; an invalid runtime index prints the source path and line and exits with code 2. Resizing and structures are not supported yet; text and growable lists are covered in the next section.

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

## Text and lists

Text literals are double-quoted and understand four backslash escapes: backslash-n adds a newline, backslash-t a tab, backslash-quote a double quote, and a doubled backslash one backslash. Any other backslash sequence stays as written, so a Windows path needs its backslashes doubled. A text value lives in a variable like a number, and `&` joins text and numbers:

```anv
set var(name) = "Ada"
say "Hello, " & var(name)   # Hello, Ada
say len(var(name))          # 3
say upper(var(name))        # ADA
```

Results can be stored back into a variable and are capped at 255 bytes; going past that stops with a clear error instead of truncating quietly. `len` counts bytes, so `len("héllo")` is 6. Comparisons work between text values (`=`, `!=`, `<`, `<=`, `>`, `>=`, alphabetically); comparing text with a number is a compile error. The text built-ins are `len`, `upper`, `lower`, `trim`, `left`, `right`, `char`, `mid`, `chr`, `ord`, `number`, and the 1/0 tests `contains`, `starts_with`, `ends_with`. Functions accept text parameters: `fn(greet, who)` with `output "hi " & var(who)` is called as `call fn(greet, "Ada")`, and a text argument passed to a numeric parameter is rejected at the call site. `say expr` prints a line, `write expr` prints without a newline, and `ask "prompt? ", var(x)` reads one line from the console.

`include fn(move) -- "lib/player.ANVL"` imports a single function; the file name becomes its qualifier, so it is called as `call fn(move--player, 10)` (`as alias` overrides the qualifier, and the single-dash form is accepted). Helpers the function calls are imported with it; anything unused is not. A selectively imported function cannot read module-level globals — pass values as parameters. A plain `include "lib/player.ANVL"` still shares one namespace exactly as before.

`enum Name value, value, value` declares named states at the top of a file; each value is a number counting from 0, so `if var(state) = playing` works and `say playing` prints its number. Value names are global: a duplicate, or one that collides with a function or variable, is an error.

`list name` declares a growable numeric list at top level, `add name value` appends to it, and `count(name)` reports how many values it holds. `array(name, index)` reads a 0-based slot and `remove name index` deletes one value, shifting the rest down and shrinking the count; removing an index that is not in the list changes nothing. `list name: text` declares a text list instead: `add` appends text values, `array(name, index)` reads one back as text, `count(name)` reports how many it holds, and `for each item in name` works the same way. A text list holds up to 256 values of up to 255 bytes each; reading past the end stops with `list index N is outside 0..M`. `for each item in name` walks the list in order, holding each value in `item` (`say var(item)`), and `break`/`continue` work inside it. Removing from a text list (`remove names 1`) shifts the following values down on both backends; an index outside the list changes nothing. A list holds up to 256 values.

```anv
list scores
add scores 10
add scores 20
say count(scores)      # 2
say array(scores, 1)   # 20
```

## Expressions

Supported arithmetic operators are `+`, `-`, `*`, `/`, and `%`; comparison operators are `=`, `==`, `!=`, `<`, `<=`, `>`, and `>=`; conditions can use `and` and `or`. Both logical operators short-circuit: `false and right` skips `right`, and `true or right` skips `right`, including calls with side effects. Arithmetic binds more tightly than comparisons, then `and`, then `or`. Numeric literals may be integers or decimals. `var(name)` reads a global or shadowing parameter; `local(name)` reads function-local state; `call fn(name, arguments...)` calls a function and evaluates to its return value (a number, or text when the function returns text).

`while condition` begins a loop and `end` closes it. The condition is checked before each iteration. Ensure the loop body changes state used by its condition so the loop can finish. Loops can be nested inside functions, branches, or other loops. `break` leaves the innermost loop immediately and `continue` jumps to the next iteration of the innermost loop; inside a `for` loop `continue` still applies the step, so the loop count is unchanged.

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

Top-level `import builtins` states that a program uses builtins; the compiler then resolves the actual set itself, from reachable code only, and `--print-imports` shows the answer (`builtins: floor, upper`). `import math`, `import text` and `import random` are accepted module names as well, and an unknown name is an error listing the available ones. Calling a builtin without the import still works — the import documents intent and lets a build be audited rather than gating the namespace.

An import that contributes nothing is a warning, not silence: `import math` in a program that never calls a math builtin prints `warning: import 'math' is never used` with the offending line and a caret, and the build continues. `--deny-warnings` turns that into a failed build, so a project can require a clean report.

Beyond imports, two more mistakes are reported rather than executed: a
statement after `output` in the same block (it can never run) and a `set local`
that nothing ever reads. Loop counters are exempt, because `for local(i) = ...`
exists to drive the loop. `number("abc")` is 0 at run time, so a literal that is not a number is reported at build time. A `for` loop that can never run — `step 0`, or a start past the end with the wrong direction — is reported instead of silently doing nothing. A function the program never calls, and a parameter its body never reads, are reported the same way. Only the entry file is checked, because an include or the stdlib is shared code whose callers may live elsewhere. A function with no `output` still runs, but its value is 0; using that
value (as in `say call fn(f, 1)`) is a warning rather than a silent zero.
 Dividing by a literal zero is reported the same way: `1 / 0` yields
infinity at run time, so the compiler says so at build time instead of
letting it pass silently. Both use the same warning channel with the source line
and a caret, and both fail the build under `--deny-warnings`.


Built-ins currently include `clock()`, `time()`, `delta()`, `pressed(KEY)`, `held(KEY)`, `mouse_x()`, `mouse_y()`, `mouse_pressed("left"|"right"|"middle")`, `mouse_held("left"|"right"|"middle")`, `mouse_wheel()`, `rnd(low,high)`, `seed(value)`, `noise(x,y,z)`, `fbm(x,y,z,octaves,lacunarity,gain)`, `floor`, `ceil`, `round`, `sqrt`, `sin`, `cos`, `abs`, `min`, `max`, and the text built-ins listed above. `random(seed)` is a builtin that runs the shipped 32-stage mixer without any include and returns a value in 0..4294967295, identical on both backends; `stdlib/random_pipeline.ANVL` holds that mixer, and it is also available as a normal function: `include "random_pipeline.ANVL"` and `call fn(random-pipeline, seed)` returns a value in 0..4294967295, identically on both backends. It is a hash-style mixer for reproducible sequences and checksum-like uses; it is not cryptographically secure, and a 1,000,000-seed measurement binned into 256 slices ranged from 2,982 to 5,139 per 3,906 expected, so it is not used as `rnd`'s source.

`clock()` returns milliseconds since the machine started and works in console programs, so `seed(clock())` gives a different sequence on each run; `time()` and `delta()` are scene-only values. `rnd(low, high)` returns whole numbers in the inclusive range, so a percentage roll uses a wide range such as `rnd(0, 1000000000)`. The implemented key names include letters, `SPACE`, `UP`, `DOWN`, `LEFT`, `RIGHT`, `ENTER`, and `ESCAPE`. Mouse coordinates use the fixed 960×600 virtual game frame and return `-1` when the pointer is in a letterbox bar or outside the window. Mouse pressed state is an edge held until the next fixed update; held state persists until button release or window focus loss. `mouse_wheel()` returns the signed wheel detents received during the current fixed update. The string-taking ray backend built-ins are described in the drawing section below.

When `image_load` returns `0`, `image_error()` returns a short reason: "cannot open the file", "the path is empty", "no free image slot", or "the file is not a readable 24- or 32-bit BMP within the limits". A successful load clears it.

The image/sprite built-ins are `image_load(path)`, `image_width(handle)`, `image_height(handle)`, `image_draw(handle,x,y)`, `image_draw_scaled(handle,x,y,width,height)`, and `image_destroy(handle)`. `image_load` accepts a quoted path relative to the process working directory and returns a positive numeric generational handle, or `0` if the file is missing/unsupported, limits are exceeded, or no slot is available. The first allocations use handles 1 through 64; reusing a released slot gets a new value, so a stale handle cannot alias a later image. The loader supports uncompressed 24-bit and 32-bit BMP files; PNG, JPEG, compressed BMP, and other formats are not supported. If a 32-bit BMP has all alpha bytes clear, it is treated as opaque to support files written with an unused reserved byte. Images are limited to 8,192 pixels per side, 16,777,216 total pixels per image, and 128 MiB combined decoded image data. `image_width` and `image_height` return 0 for invalid handles. Draw calls alpha-blend onto the software framebuffer using nearest-neighbor scaling and return 1 for a valid draw request or 0 for an invalid handle/arguments; draws outside the 960×600 viewport are clipped. `image_destroy(handle)` frees that resource and returns 1, or returns 0 for an invalid or already-released handle. The runtime releases all remaining images when the game closes. See `examples/image_sprite.ANVL` and its BMP asset.

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

Implemented draw commands are `rect`, `circle`, `line`, `text`, `cube`, `sphere`, `ray_sphere`, and `plane`. Screen-space image sprites use the `image_*` built-ins above, not the `display` command. `ray_sphere(x,y,z,radius)` is Anvil's built-in per-pixel ray-traced sphere function. It uses a CPU bounding volume hierarchy (BVH) to find the closest sphere hit and cast hard shadows, with diffuse and specular lighting. One ray-trace batch supports up to 32 spheres. `ray_backend("bvh")` selects the CPU BVH backend at runtime; `ray_backend_available("dxr")` and `ray_backend_available("embree")` query backend support. Both accept a string and return numeric `1` or `0`. An unsuccessful selection leaves the active backend unchanged and prints a diagnostic. Only BVH is implemented in the current build, so DXR and Embree checks return `0`. `-rgb` and `-rgba` set a color, `-l(x,y)` sets text position, and `-rotate(x,y,z)` rotates a cube. `camera fov` accepts 20–120 degrees as a horizontal field of view; camera movement is configured by `camera control(speed,turn_speed)`. The starter sample in `examples/first_world.ANVL` demonstrates both features and builds into a Windows executable.

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

Static types, dynamically sized arrays, structures, modules/imports, general asset formats and 3D mesh assets, sprite animation, audio, 3D/polygon physics, save files, full 2D/3D scene management, a GPU renderer, reliable Internet multiplayer, and Rust code generation are future work. Parameters, returns, recursion, function-local numeric variables and arrays, `while`/inclusive numeric `for` loops, fixed-size global numeric arrays, BMP-based 2D sprites, and fixed-step 2D circle/axis-aligned-box physics are supported, but the language and engine remain much smaller than a general-purpose game engine today.


Local multi-file source composition uses top-level `include "relative/library.ANVL"`. Both backends resolve the local include graph; the native backend compiles reachable functions and their runtime dependencies. See [include semantics and limits](INCLUDES.md). Namespaces, package registries and separate object linking remain unfinished.
