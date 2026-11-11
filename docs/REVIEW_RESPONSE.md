# Response to the commit review and the language roadmap

Two documents were reviewed against this codebase: a commit review (P0–P2
findings, 79/100) and a language roadmap (priorities 1–9). This page records
what changed, what is verified, and what is still open. Verification means a
test in `tests/` or a case in `scripts/differential_probe.py` that compiles and
runs the same program on both backends and compares output.

## What this batch changed

| Change | Where | Verified by |
|---|---|---|
| Unreachable functions no longer reach generated C (the native backend already did this) | `compiler/codegen.py` | `tests/test_deadcode.py` (C text, native image, engine callbacks, recursion, both outputs) |
| The REPL remembers multi-line blocks that only change state, so `repeat 3 … end` then `say var(x)` shows the new value; blocks that print are not replayed | `compiler/repl.py` | `tests/test_repl.py` (block persistence, no double-applied mutation, no replayed output) |
| `break` and `continue` in `for`/`while`/`repeat`, both backends, nested loops | `compiler/parser.py`, `compiler/codegen.py`, `compiler/native_codegen.py` | `tests/test_break_continue.py` (both backends, nested loops, error outside a loop) |
| `set var(x) = null` is an explicit error instead of a silent no-op that left `x` undefined | `compiler/parser.py` | manual + diagnostics suite |
| Native backend names unsupported builtins (`image_load() is not available…`) and reuses the spelling suggestions (`random` → `rnd`) | `compiler/native_codegen.py` | `tests/test_native_x64.py` |
| Language spec, guide and README reconciled with the implementation (text, lists, arrays, escapes, break/continue, native limits) | `docs/LANGUAGE_SPEC.md`, `docs/LANGUAGE.md`, `README.md` | examples in the docs are run by the suite |
| Backend capability matrix | `docs/BACKENDS.md` | each row names its test file |
| Versioning and stability policy | `docs/VERSIONING.md` | tutorial and probe run on every change |
| Compile-time and executable-size measurements | `tools/bench_anvil.py` | measured below |

### Measured this machine (Windows 11, MSVC 2022, `python tools/bench_anvil.py`)

| program | backend | compile (median) | exe bytes |
|---|---|---|---|
| tiny (hello) | native | 0.002 s | 2,560 |
| tiny (hello) | C | 2.265 s | 143,360 |
| texty (text + loop + calls) | native | 0.002 s | 6,144 |
| texty (text + loop + calls) | C | 2.000 s | 148,992 |
| big (40 helpers, 1 unused) | native | 0.002 s | 2,560 |
| big (40 helpers, 1 unused) | C | 1.815 s | 143,360 |

The C timings are dominated by `cl.exe`, not by Anvil. The `big` row shows
reachability at work: the 41 helper functions are unreachable, so both backends
emit the same tiny program. These are single-machine observations, not a
performance claim.

## Commit review findings

| Finding | Status | Notes |
|---|---|---|
| **P0** integrate this branch onto current GitHub `main` | **Not done** | This checkout has no configured upstream remote and the review's snapshot is not available here. The work above was made directly against this tree, not rebased onto newer history. Forward-porting needs the upstream repository. |
| **P1** REPL state is replay-observable; block mutations lost | **Done** | Mutations were already replayed correctly (a fresh program each prompt, so no double application — covered by a regression). Multi-line state-only blocks are now remembered; blocks that print are not replayed. |
| **P1** C backend emits every function | **Done** | `emit_c` now filters with the same `reachable_functions` the native backend uses, rooted at top-level calls, `main`, and active `draw`/`update`. `tests/test_deadcode.py` asserts the unused helper is absent from generated C and from the native image. |
| **P1** one typed intermediate representation | **Not started** | Large architectural change. The two string-classification heuristics that motivated it were fixed directly this cycle (`&` is a top-level join operator, joins of builtins are text), which removed the visible mismatches. |
| **P1** define and verify backend parity | **Done (documented)** | `docs/BACKENDS.md` is a capability matrix where each row names the test that proves it, and every native gap is a source-located error rather than a mis-compile. |
| **P1** measure performance and executable size | **Done (first pass)** | `tools/bench_anvil.py` reports compile time and exe size for three programs on both backends; numbers above. No optimization work was done off the back of it. |
| **P2** reconcile the language specification | **Done** | Text, joining, escapes, lists, arrays, text-returning functions and break/continue are documented as present; the "unfinished" list now names only what is genuinely missing; native limits are listed in both the spec and the migration guide. |
| **P2** strengthen what 100/100 means | **Done** | `docs/GRADE.md` states that the scorecard covers a narrow beginner workflow set and points to `docs/QA_REPORT.md` as a separate historical review. |
| **P2** language/version and stability policy | **Done** | `docs/VERSIONING.md`: what version 1 promises, what is experimental, how breaking changes become version 2, and which tests enforce compatibility. |

## Language roadmap priorities

| Priority | Status | Notes |
|---|---|---|
| 1. General function arguments (text in/out) | **Not done** | Text *returns* work on both backends; text *parameters* are rejected on both with a clear message. This is the next feature to build; it needs a documented ABI (pointers in integer registers, or pointer bits carried in the existing XMM slots). |
| 2. Simple types and real booleans | **Not started** | `true`/`false` remain numeric aliases; no annotations or version 2 syntax. |
| 3. Complete the string model | **Documented, not changed** | Bytes are the defined unit (`len("héllo")` is 6) and this is now stated in the spec, guide and README. Unicode code-point indexing is not implemented. |
| 4. Growable, typed collections | **Not started** | `list` holds numbers only, capped at 256 entries with a clear error. |
| 5. Records and enumerations | **Not started** | |
| 6. Explicit function references | **Not started** | |
| 7. Control-flow completeness | **Done for break/continue** | Both commands work in nested `for`/`while`/`repeat` on both backends (`continue` applies the `for` step). `match`/`case` is not started and should follow enums. |
| 8. Module and package syntax | **Not started** | Whole-file `include` only; selective imports and namespaces remain open. |
| 9. Error and optional-value handling | **Partially done** | The confusing `null` no-op is now an explicit error. No `result`/`option` type yet; file/image/network calls still report failure as `0`/`-1`/handle values. |

## What remains, in the order I would take it

1. **Text function parameters** (roadmap 1) — the single biggest usability gap,
   and the roadmap's own success criterion.
2. **A typed expression representation** (review P1) — stops the class of bug
   where the semantic classifier and the expression parser disagree; two such
   bugs were found and fixed by hand this cycle.
3. **Optional type annotations** (roadmap 2) with a `language version 2` line.
4. **Selective imports** (roadmap 8) and **records/enums** (roadmap 5), which
   unlock non-toy programs.
5. **Forward-port onto current `main`** (review P0) once the upstream remote is
   available.

## Reproducing everything on this page

```powershell
python -m pytest tests -q            # full suite
python scripts/differential_probe.py # both backends, one program at a time
python tools/grade_anvil.py          # beginner scorecard (10.0/10 on this commit)
python tools/bench_anvil.py          # compile time and executable size
```
