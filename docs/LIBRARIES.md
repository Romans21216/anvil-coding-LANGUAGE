# Libraries: one function per file

A library is a folder of `.ANVL` files, one function per file, where the file
name is the function name. A program imports it by name:

```
library import math

fn(main)
  say call fn(gcd, 48, 18)
end
call fn(main)
```

`library import math` looks for a folder named `libraries-math` (or
`libraries/math`), starting beside the file that wrote the line and then walking
up its parent folders. It finds `gcd.ANVL`, and that file must define
`fn(gcd, ...)`.

## What gets compiled

Only the functions the program calls. Both backends already emit just the
reachable functions, so a library file nobody calls never reaches the generated C
or the executable:

| program | generated C | native image |
|---|---|---|
| calls `gcd` only | contains `anvil_gcd`, no `anvil_lcm` | 3,072 B |
| calls `gcd` and `lcm` | both | 3,584 B |

That means a library can hold as many functions as you like without costing the
programs that use one of them.

## The rules

- **One function per file**, named after the file: `lcm.ANVL` must contain
  `fn(lcm, ...)`. A file that defines something else is rejected, and so is a
  file that defines more than one function. Functions the file *imports* do not
  count against it.
- **Functions are called normally**: `call fn(gcd, 48, 18)`. A library function
  is not a builtin; it is an ordinary Anvil function that happens to live on disk.
- **Names must not collide** with a function the program already defines, or with
  another imported library.
- **Importing the same library twice is harmless**; the function is registered
  once.
- **A missing library says where it looked**:
  `library 'algebra' not found; expected a folder named libraries-algebra or
  libraries/algebra beside main.ANVL or in a parent folder`.

## A library can import another library

A library file may declare its own dependency, and the search starts in that
file's folder and then walks up, so a folder at the project root is found:

```
project/
  main.ANVL                    library import a
  libraries-a/
    f.ANVL                     library import b     ← finds libraries-b upward
  libraries-b/
    g.ANVL                     fn(g, a) … end
```

`main` calls `f`, `f` calls `g`, and `main` never mentions `b`. The imported
functions travel with the file that needs them.

## Included files keep their imports

A file pulled in with `include fn(ratio) -- "ratio.ANVL"` carries the
`library import` lines at the top of *that* file, resolved beside it. The entry
program does not have to repeat the dependency. Whole-file includes
(`include "ratio.ANVL"`) have always behaved this way.

## What ships with the compiler

`library import essentials` finds `libraries-essentials/` next to the compiler
itself, so any program in any directory can use it without copying a folder:

| function | answer |
|---|---|
| `random-pipeline(seed)` | the 32-stage mixer; `random(12345)` is 1245520449 |
| `random-range(low, high, seed)` | whole number in `low..high` |
| `random-chance(percent, seed)` | 1 when a roll lands under `percent` |
| `gcd(a, b)`, `lcm(a, b)` | greatest common divisor, least common multiple |
| `factorial(n)`, `fib(n)`, `power(base, exponent)`, `sum-to(n)` | arithmetic |
| `is-prime(n)` | 1 when `n` is prime |
| `clamp(value, low, high)`, `sign(value)` | bounds and sign |
| `percent-of(part, whole)`, `round-to(value, places)` | formatting |
| `distance(x1, y1, x2, y2)` | straight-line distance |

A program that calls one of these compiles only that function and whatever it
calls: `gcd` for `lcm`, the mixer for `random-range`. Both backends print the
same answers, including the pinned mixer value above.

## Layout

```
project/
  main.ANVL                 library import math
  libraries-math/
    gcd.ANVL                 fn(gcd, a, b) … end
    lcm.ANVL                 fn(lcm, a, b) … end
```

`examples/library_demo.ANVL` and `examples/libraries-math/` are a working copy of
that layout.
