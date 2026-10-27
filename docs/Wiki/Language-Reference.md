# Language Reference

Anvil files are UTF-8 `.ANVL` text. `#` starts a comment outside quoted strings. Names are case-sensitive. `end` closes functions and `if` blocks; indentation is optional.

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

`fn(name)` defines a zero-argument function. `fn(name, first, second)` defines numeric parameters. `output expression` returns a number; a function without `output` returns zero. `call fn(name, arguments...)` works as a statement or numeric expression. Recursive calls work in the generated C.

`var(name)` refers to global numeric state unless a parameter with that name shadows it inside the current function. `set local(name) = expression` declares function-local numeric state, initialized to zero on each call. Read it with `local(name)` and update it with `add local(name) amount` or `sub local(name) amount`. Locals are visible only in the function where declared.

`set var(name) = expression`, `add var(name) amount`, and `sub var(name) amount` operate on globals, except that a parameter of the same name is used inside that function. Globals are numeric doubles.

## Expressions and control flow

Operators are `+`, `-`, `*`, `/`, `%`, comparisons (`=`, `==`, `!=`, `<`, `<=`, `>`, `>=`), and logical `and`/`or`. Multiplication/division/remainder bind more tightly than addition/subtraction, then comparisons, `and`, and `or`. Parentheses group expressions.

```anv
fn(clamp-low, value, lower)
  if var(value) < var(lower)
    output var(lower)
  else
    output var(value)
  end
end
```

The current language has `if`/`else`/`end`, but does not yet have loops, arrays, user-defined structures, static types, modules, or general-purpose strings.

## Built-ins

- Time/input: `time()`, `delta()`, `pressed(KEY)`, `held(KEY)`.
- Random/noise: `seed(value)`, `rnd(low, high)`, `noise(x, y, z)`, `fbm(x, y, z, octaves, lacunarity, gain)`.
- Math: `floor`, `ceil`, `sqrt`, `sin`, `cos`, `abs`, `min`, `max`.
- Drawing: `rect`, `circle`, `line`, `text`, `cube`, `sphere`, `ray_sphere`, `plane`.
- Networking prototype: `net host(port)`, `net join("IPv4", port)`, `net send(number)`, `receive()`.

See `docs/LANGUAGE.md` for the complete current syntax and `docs/ENGINE.md` for graphics details.

