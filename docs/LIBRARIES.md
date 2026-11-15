# Libraries: one function per file

A library is a folder of `.ANVL` files, one function per file, where the file
name is the function name. A program imports it by name:

```
library import math

fn(main)
  output call fn(gcd, 48, 18)
end
call fn(main)
```

`library import math` looks for a folder named `libraries-math` (or
`libraries/math`), starting beside the file that wrote the line and then walking
up its parent folders. It finds `gcd.ANVL`, and that file must define
`fn(gcd, ...)`.

## What gets compiled

Only the functions the program calls. The compiler emits just the reachable
functions, so a library file nobody calls never reaches the generated C or the
executable.

That means a library can hold as many functions as you like without costing the
programs that use one of them.

## Which libraries are in this checkout

Five folders, 56 functions:

| library | functions |
| --- | --- |
| `essentials` | 21 - arithmetic, predicates, interpolation, the seeded random helpers |
| `math` | 9 - circle area, hypotenuse, primes, digit tricks, degree/radian |
| `units` | 10 - temperature, distance, weight |
| `geometry` | 8 - areas, perimeters, angle normalisation, point tests |
| `vector` | 8 - dot, length, reflect, rotate |

The `text` and `validate` libraries, and the `pad-left`/`text-repeat`/`text-reverse`
helpers, live on the language branch: they need `len`, `mid` and `ord`, which this
compiler does not have yet.

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
| `random-float(low, high, seed)` | uniform in `[low, high)` |
| `gcd(a, b)`, `lcm(a, b)` | greatest common divisor, least common multiple |
| `factorial(n)`, `fib(n)`, `power(base, exponent)`, `sum-to(n)` | arithmetic |
| `square(n)`, `is-even(n)`, `is-odd(n)` | arithmetic predicates |
| `is-prime(n)` | 1 when `n` is prime |
| `lerp(a, b, t)`, `map-range(value, inLow, inHigh, outLow, outHigh)` | interpolation |
| `percent-of(part, whole)`, `round-to(value, places)` | formatting |
| `distance(x1, y1, x2, y2)` | straight-line distance |
| `text-repeat(text, times)`, `pad-left(text, width)`, `text-reverse(text)` | text |

A program that calls one of these compiles only that function and whatever it
calls: `gcd` for `lcm`, the mixer for `random-range`. Both backends print the
same answers, including the pinned mixer value above.

Three things worth knowing:

- **`cube` is not included**: a function of that name collides with the runtime's
  `anvil_cube` symbol, so use `power(x, 3)`.
- **`clamp` and `sign` are builtins**, so their library files were removed: call
  them directly, with no import.
- **`starts_with` / `ends_with` are builtins**, so the library does not repeat them.
- **One text helper is not reentrant.** A local can hold a number but not text,
  so `text-reverse` accumulates in a global; calling it while it is already
  running would mix the results. `text-repeat`, `pad-left`, `pad-right` and
  `center` recurse instead (depth is bounded by the 256-character text limit),
  and `is-palindrome` compares mirrored characters.

## Other shipped libraries

Seven folders ship beside the compiler, imported the same way:

| import | folder | what it holds |
|---|---|---|
| `library import essentials` | `libraries-essentials/` | random-pipeline and the seeded helpers, gcd/lcm, factorial, fib, power, primes, lerp, map-range, percent-of, round-to, distance, three text helpers |
| `library import text` | `libraries-text/` | pad-right, center, capitalize, index-of, count-words, is-palindrome, left-of, right-of |
| `library import math` | `libraries-math/` | nth-prime, primes-below, digits-sum, reverse-number, is-palindrome-number, hypotenuse, area-circle, to-degrees, to-radians |
| `library import units` | `libraries-units/` | temperature, distance and mass conversions, ten functions |
| `library import validate` | `libraries-validate/` | is-empty, is-digit-text, is-alpha-text, is-number-text, is-space-text, is-upper-text |
| `library import geometry` | `libraries-geometry/` | area-rect, perimeter-rect, area-triangle, area-triangle-sides, circumference, point-in-rect, normalize-angle, distance-squared |
| `library import vector` | `libraries-vector/` | dot, length, normalize-x, normalize-y, rotate-x, rotate-y, reflect-x, reflect-y |

Each folder has its own README listing every function and its caveats. Only
`text-reverse` keeps an accumulator in a global (a local can hold a number but
not text), so it is the one text helper that is not reentrant; the rest recurse
or compare in place.

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
