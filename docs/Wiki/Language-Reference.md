# Language Reference

For the complete normative grammar and version 1 behavior contract, see the [formal language specification](../LANGUAGE_SPEC.md).

Anvil files are UTF-8 `.ANVL` text. `#` starts a comment outside quoted strings. Names are case-sensitive. `end` closes functions, `if` blocks, `while` loops, and `for` loops; indentation is optional.

## Language versions

Files may begin with `language version 1` to pin the syntax version. The declaration must appear before other source code and may appear only once. Blank lines and comments can precede it. Omitting the declaration keeps legacy files on version 1. The compiler rejects malformed or unsupported declarations with the source path and line, rather than silently interpreting a future syntax version as the current one.

## Functions, parameters, and returns

```anv
fn(double, value)
  output var(value) * 2
end

fn(main)
  set local(result) = call fn(double, 6)
  output local(result)
end

call fn(main)
```

`fn(name)` defines a zero-argument function. `fn(name, first, second)` defines numeric parameters. `output expression` returns a number; a function without `output` returns zero. `call fn(name, arguments...)` works as a statement or numeric expression. Recursive calls work in the generated C. `while condition ... end` repeats while its numeric condition is nonzero.

`var(name)` refers to global numeric state unless a parameter with that name shadows it inside the current function. `set local(name) = expression` declares function-local numeric state, initialized to zero on each call. Read it with `local(name)` and update it with `add local(name) amount` or `sub local(name) amount`. Locals are visible only in the function where declared.

`set var(name) = expression`, `add var(name) amount`, and `sub var(name) amount` operate on globals, except that a parameter of the same name is used inside that function. Globals are numeric doubles.

## Fixed-size arrays

Declare a global array at top level or a local array inside a function with `array name(size)`. Arrays are zero-initialized numeric doubles and cannot be resized. Local arrays are heap allocated per call, freed on return, and only visible in their declaring function. Local storage is capped at 8,192 elements per function call and 16 MiB across all active calls; allocation failure reports source location. Each global array can contain up to 1,048,576 elements. Read with `array(name, index)` and write inside a function with `set array(name, index) = expression`. Indexes are zero-based; dynamic invalid, fractional, negative, or out-of-range indexes terminate with a source-location diagnostic. See [the language guide](../LANGUAGE.md#fixed-size-numeric-arrays) for a complete sample.

## Expressions and control flow

Operators are `+`, `-`, `*`, `/`, `%`, comparisons (`=`, `==`, `!=`, `<`, `<=`, `>`, `>=`), and logical `and`/`or`. Multiplication/division/remainder bind more tightly than addition/subtraction, then comparisons, `and`, and `or`. Logical operators short-circuit, so a skipped right operand (including a function call) is not evaluated. Parentheses group expressions. Division by zero produces a runtime source-path/line diagnostic and exits with code 2; ordinary nonzero division remains floating point. Numeric expressions that produce NaN or infinity (including overflow or invalid math inputs) also report the source location and exit with code 2, including when the value would otherwise only feed a comparison.

`while condition` checks its numeric condition before each pass. The body repeats until the condition evaluates to zero. The body should update state used by the condition so the loop can terminate. Loops may be nested.

`for local(index) = start to end [step amount]` runs an inclusive numeric range. Start, end, and step are evaluated once. The default step is `1`; a negative step counts downward, and a zero step runs no iterations. The variable is function-local and retains its final value. A parameter cannot be used as the control variable; nested `for` loops must use different local names.

```anv
fn(sum-odd, limit)
  set local(total) = 0
  for local(index) = 1 to var(limit) step 2
    add local(total) local(index)
  end
  output local(total)
end
```

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
```

```anv
fn(clamp-low, value, lower)
  if var(value) < var(lower)
    output var(lower)
  else
    output var(value)
  end
end
```

The current language has `if`/`else`/`end`, `while`/`end`, numeric `for`/`end` loops, and fixed-size numeric arrays. User-defined structures, static types, modules, and general-purpose strings are not implemented.

## Built-ins

- Time/input: `time()`, `delta()`, `pressed(KEY)`, `held(KEY)`, `mouse_x()`, `mouse_y()`, `mouse_pressed("left"|"right"|"middle")`, `mouse_held(...)`, and `mouse_wheel()`. Mouse coordinates use the virtual 960×600 framebuffer and return `-1` outside the game viewport, including letterbox bars. Button-down edges and wheel detents are available through the next fixed update; held state ends on release or focus loss.
- Random/noise: `seed(value)`, `rnd(low, high)`, `noise(x, y, z)`, `fbm(x, y, z, octaves, lacunarity, gain)`.
- Math: `floor`, `ceil`, `sqrt`, `sin`, `cos`, `abs`, `min`, `max`.
- Drawing: `rect`, `circle`, `line`, `text`, `cube`, `sphere`, `ray_sphere`, `plane`.
- Ray-tracing backend control: `ray_backend(name)`, `ray_backend_available(name)`.
- Networking prototype: `net host(port)`, `net join("IPv4", port)`, `net send(number)`, `receive()`.
- Physics: `body_create` (circle), `body_create_box` (axis-aligned box), `physics_capacity` (configure 1–128 slots), `body_destroy`, `body_active`, body position/velocity queries, `body_set_velocity`, `body_force`, `body_restitution`, `body_friction` (Coulomb coefficient 0–1; default 0.5), `body_collision`, `physics_gravity`, and `physics_step` for fixed-step 2D shapes.

See `docs/LANGUAGE.md` for the complete current syntax and `docs/ENGINE.md` for graphics details.

