# geometry

Shape math that a beginner program reaches for. Import by name:

```
library import geometry
```

| function | example |
|---|---|
| `area-rect(width, height)` | 3, 4 → 12 |
| `perimeter-rect(width, height)` | 3, 4 → 14 |
| `area-triangle(base, height)` | 6, 4 → 12 |
| `area-triangle-sides(a, b, c)` | 3, 4, 5 → 6 (Heron); 1, 1, 10 → 0 |
| `circumference(radius)` | 1 → 6.283185 |
| `point-in-rect(x, y, left, top, width, height)` | 5, 5, 0, 0, 10, 10 → 1 |
| `normalize-angle(degrees)` | -90 → 270, 450 → 90 |
| `distance-squared(x1, y1, x2, y2)` | 0, 0, 3, 4 → 25 |

## Worth knowing

- `point-in-rect` includes the edges and the corners; a point exactly on the
  border answers `1`.
- `area-triangle-sides` refuses sides that cannot close a triangle by answering
  `0` instead of producing a NaN from a negative area.
- `normalize-angle` loops, so any size of input works, including -720 and 1080.
- `distance-squared` avoids the square root when you only need to compare
  distances, which is faster and exact.
- Nothing here uses a global, so every function is reentrant.
