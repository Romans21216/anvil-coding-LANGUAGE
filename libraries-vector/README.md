# vector

Two-dimensional vector math for movement, aiming and bouncing. Import by name:

```
library import vector
```

| function | result |
|---|---|
| `dot(ax, ay, bx, by)` | 1,2 · 3,4 → 11 |
| `length(ax, ay)` | 3,4 → 5 |
| `normalize-x(ax, ay)`, `normalize-y(ax, ay)` | 3,4 → 0.6, 0.8; 0,0 → 0, 0 |
| `rotate-x(x, y, degrees)`, `rotate-y(x, y, degrees)` | 1,0 rotated 180° → -1, 0 |
| `reflect-x(x, y, nx, ny)`, `reflect-y(x, y, nx, ny)` | bounce v off a surface with normal n |

## Why pairs of functions

Anvil functions return one number, so a vector operation comes as two functions
sharing the same arguments:

```anvl
library import vector

set var(x) = 3
set var(y) = 4
say call fn(length, var(x), var(y))          # 5
say call fn(normalize-x, var(x), var(y))     # 0.6
say call fn(normalize-y, var(x), var(y))     # 0.8
```

## Worth knowing

- `normalize-x` / `normalize-y` answer `0` for a zero-length vector instead of
  dividing by zero.
- `reflect-*` expects a **unit** normal (`nx, ny` of length 1); `normalize-*` is
  there to make one.
- Angles are degrees, counter-clockwise, matching `rotate` in scene programs.
- Everything is numeric, so all eight functions are reentrant and none of them
  touches a global.
