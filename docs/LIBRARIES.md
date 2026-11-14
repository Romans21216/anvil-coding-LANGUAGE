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

`library import math` looks beside the entry file for a folder named
`libraries-math` (or `libraries/math`), finds `gcd.ANVL`, and that file must
define `fn(gcd, ...)`.

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
  file that defines more than one function.
- **Functions are called normally**: `call fn(gcd, 48, 18)`. A library function
  is not a builtin; it is an ordinary Anvil function that happens to live on disk.
- **Names must not collide** with a function the program already defines, or with
  another imported library.
- **A missing library says where it looked**:
  `library 'algebra' not found; expected a folder named libraries-algebra or
  libraries/algebra beside main.ANVL`.

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
