# units

Conversions people actually look up. Import by name:

```
library import units
```

## Temperature

| function | example |
|---|---|
| `celsius-to-fahrenheit(c)` | 100 → 212 |
| `fahrenheit-to-celsius(f)` | 212 → 100 |
| `celsius-to-kelvin(c)` | 0 → 273.15 |
| `kelvin-to-celsius(k)` | 273.15 → 0 |

## Distance

| function | example |
|---|---|
| `km-to-miles(km)` | 10 → 6.213712 |
| `miles-to-km(miles)` | 10 → 16.09344 |
| `meters-to-feet(meters)` | 10 → 32.808399 |
| `feet-to-meters(feet)` | 10 → 3.048 |

## Mass

| function | example |
|---|---|
| `kg-to-pounds(kg)` | 10 → 22.046226 |
| `pounds-to-kg(pounds)` | 10 → 4.535924 |

Every function is a single expression, so all ten are reentrant and none of them
touches a global. The factors are the usual exact definitions (0.3048 m per
foot, 0.45359237 kg per pound, 1.609344 km per mile).
