# math

Number-theory and geometry helpers beyond the Essentials library. Import by
name:

```
library import math
```

| function | result |
|---|---|
| `nth-prime(n)` | the nth prime; `nth-prime(10)` is 29 |
| `primes-below(n)` | how many primes are smaller than n; 20 → 8 |
| `digits-sum(n)` | sum of the decimal digits; 12345 → 15 |
| `reverse-number(n)` | digits reversed; 1234 → 4321, -1234 → -4321 |
| `is-palindrome-number(n)` | `1` when the number reads the same backwards |
| `hypotenuse(a, b)` | √(a² + b²) |
| `area-circle(radius)` | π r² |
| `to-degrees(radians)`, `to-radians(degrees)` | angle conversion |

`sin`, `cos`, `sqrt`, `floor`, `ceil`, `round`, `abs`, `min` and `max` are
builtins, and `power` lives in Essentials.

## Worth knowing

- `nth-prime` and `primes-below` divide by every candidate up to √n, which is
  fine for the sizes a beginner program uses and slow for very large inputs.
- `reverse-number` and `digits-sum` work on whole numbers; anything after the
  decimal point is dropped.
- Nothing here needs a global, so every function is reentrant.
