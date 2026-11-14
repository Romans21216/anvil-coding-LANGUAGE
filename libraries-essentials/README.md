# Essentials

The library that ships with the compiler. Import it by name from anywhere:

```
library import essentials
```

Every file holds one function named after the file. Only the functions a program
calls are compiled, so importing all 23 costs nothing for the ones you skip.

## Random

| function | result |
|---|---|
| `random-pipeline(seed)` | the 32-stage mixer that backs `random()`; `random-pipeline(12345)` is 1245520449 |
| `random-range(low, high, seed)` | whole number in `low..high` inclusive |
| `random-chance(percent, seed)` | `1` when a roll lands under `percent`, else `0` |
| `random-float(low, high, seed)` | uniform in `[low, high)`; `0, 1, 12345` → 0.289995 |

## Numbers

| function | result |
|---|---|
| `gcd(a, b)`, `lcm(a, b)` | greatest common divisor, least common multiple |
| `factorial(n)` | `n!`; `1` for 0, `0` below zero |
| `fib(n)` | nth Fibonacci number, `fib(10)` is 55 |
| `power(base, exponent)` | integer power; `0` for a negative exponent |
| `sum-to(n)` | 1 + 2 + … + n |
| `square(n)` | n · n |
| `is-prime(n)` | `1` when prime |
| `is-even(n)`, `is-odd(n)` | parity |
| `clamp(value, low, high)` | value pulled into range |
| `sign(value)` | -1, 0 or 1 |
| `lerp(a, b, t)` | `a` at t=0, `b` at t=1 |
| `map-range(value, inLow, inHigh, outLow, outHigh)` | linear remap |
| `percent-of(part, whole)` | `25, 200` → 12.5 |
| `round-to(value, places)` | `3.14159, 2` → 3.14 |
| `distance(x1, y1, x2, y2)` | straight-line distance |

## Text

| function | result |
|---|---|
| `text-repeat(text, times)` | `"ab", 3` → `ababab` |
| `pad-left(text, width)` | spaces until the text is `width` long |
| `text-reverse(text)` | `"abc"` → `cba` |

## Worth knowing

- Text is capped at 255 characters by the language. A helper that would go past
  it stops with `text is limited to 255 characters` rather than truncating, and
  because the text helpers recurse, that cap is also what bounds their depth.
- `starts_with`, `ends_with`, `upper`, `lower`, `trim`, `mid`, `len` and
  `contains` are **builtins**, not library functions.
- A function named `cube` is refused: the runtime already owns `anvil_cube`.
  Use `power(x, 3)`.
- `text-repeat` and `pad-left` recurse and are reentrant. `text-reverse` still
  keeps its accumulator in a global (a local can hold a number but not text),
  so **it is not reentrant**.
- Functions call each other freely (`lcm` uses `gcd`, `round-to` uses `power`,
  `random-range` uses the mixer). Only what you call gets compiled.
