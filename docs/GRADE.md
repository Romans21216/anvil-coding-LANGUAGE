# Anvil scorecard: how the grade is measured

The grade is not an opinion. `tools/grade_anvil.py` compiles and runs every check
below and prints a score; `tests/test_grade.py` fails the build if the score
drops under 80/100. Reproduce it from the repository root:

```powershell
python tools/grade_anvil.py
```

This scorecard is the current grade. `docs/QA_REPORT.md` is a separate, historical
independent review with its own 50-criterion rubric; where the two disagree, this
page and `tools/grade_anvil.py` describe the language as it is today.

## How the score works

The rubric holds 25 checks, weighted to 100 points. A check passes only when the
program compiles and its exact stdout matches on **both** backends, unless the
check is marked otherwise (C-only, native-only, or a compiler diagnostic). Open
gaps are included on purpose, so the score cannot inflate itself.

| Area | Points | What it tests |
|---|---|---|
| First contact | 15 | The first minute: hello world, the ask-name greeting program, variables and joins |
| Core syntax | 20 | Precedence, `%`, `if`/`elif`/`else`, `repeat`/`for`/`while`, functions returning values |
| Text toolkit | 20 | Join, `len`, case, `left`/`right`, `mid`/`char`, `trim`/`number`, `chr`/`ord`, `contains` family, text ordering |
| Data | 15 | Fixed arrays; text-returning functions (C); **growable lists** (open gap) |
| Diagnostics | 15 | Caret diagnostics with the source line; bare names hint at `var(...)`; **text returns on native** (open gap) |
| Shell | 8 | Assignment echo and reuse; blocks spanning lines |
| Learning path | 7 | Ten tutorial lessons present and runnable |

## Current result

```
Score: 100/100  ->  10.0/10
```

Every check passes. The rubric is the same instrument that reported 7.1, 9.0 and
9.5 earlier — nothing was removed or reweighted to reach 100; the two gaps it
counted (text returns on native, growable lists) were implemented instead.

## Why these weights

A beginner language is judged by how fast the first success comes and how far it
carries you before the tooling gets in the way. First contact plus core syntax is
35 points; text is where beginners spend their time, so it is another 20. Data,
diagnostics and the shell carry 23, and the learning path 7 — a language without
a tutorial is a language you bounce off.
