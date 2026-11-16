# ANVIL — work log

Everything built so far, what it was verified against, and where it lives.
Written 2026-11-14. Companion screenshots are in `docs/assets/`.

---

## 1. Where the work lives

There are two checkouts on this machine, and they are **not** the same lineage.

| Folder | Role | Git state |
| --- | --- | --- |
| `C:\Users\power\Documents\AnvilEngine-work` | the project — tracks `Romans21216/anvil-coding-LANGUAGE` | branch `main` (`ec98f8b`), plus local branch `anvil-slots` with this work |
| `C:\Users\power\Documents\buld\os\toolchain\anvil` | where the compiler/language work of this session happened | branch `codex/anvil-user-updates-2f0ac68`, **100 commits ahead / 73 behind** `main` |

The two branches have diverged. `main` is the newer, more modular compiler
(`compiler/lexer.py`, `module_loader.py`, `native_*.py`, function references) with a
graphics-first language. The branch carries an older compiler base plus this
session's work: the library system, the seven library folders, the linter, and a
set of runtime/compiler fixes. Anything marked **(main)** below exists in the
project folder; anything marked **(branch)** exists only in the other checkout.

---

## 2. ANVIL SLOTS — a complete 2D slot machine **(main)**

`examples/slots.ANVL`, ~380 lines, one file, **no image assets**: every symbol,
panel, button, payline and cabinet bulb is drawn with `rect`, `circle` and `line`.

- 3×3 reels, middle row pays.
- Weighted symbols: cherry 30%, lemon 24%, bell 16%, bar 12%, diamond 10%,
  seven 6%, wild 2%.
- Three of a kind pays ×5 (cherry) up to ×250 (wild); wild substitutes.
- Reels stop in turn (0.9 / 1.18 / 1.46 s), each with its own deceleration.
- Controls: `SPACE` or SPIN button, `←`/`→` or −/+ to change the bet, `P` for the
  paytable, `R` to reset. Mouse: the buttons are clickable.
- `docs/SLOTS.md` documents controls and the state machine;
  `docs/assets/slots.png` is a capture of a real build.

Verified by playing it, not by reading it: SPIN 200 → 195, bet 5 → 7 spending 7,
a forced jackpot paying 500 (CREDITS 695, BET 5, WIN 500, PAYOUT 500), paytable
open/close. Caught and fixed one real bug that way: the "NO WIN" and "NOT ENOUGH
CREDITS" lines drew over each other — the status block is now a single
if/else-if chain.

### The flicker

Reported as "all the buttons flicker". Measured by capturing 30 frames at 40 ms
and diffing them with PIL: the changed pixels formed two rows of dots across the
cabinet — **24 bulbs, flipping colour about twice a second**. The drawing branched
on `sin(time * 7) > 0.5` regardless of game state, and the bottom bulb row sits
directly on top of the buttons, which is why it read as the buttons flickering.

Fix: bulbs are steady while the machine is idle; on a win they run a **chase**
(each lamp's phase offset by its index) instead of all flashing together.

Evidence after the fix: **15 of 15 consecutive idle frame pairs pixel-identical**
(captured at 40 ms). On a win the bulb region changes every frame while the rest
of the frame stays still.

---

## 3. Libraries

One folder per library, one **function per file**, file name == function name,
plain `.anvl` source a user can read and edit.

```
library import essentials
```

loads `libraries-essentials/` (or `libraries/essentials/`) found beside the
importing file, in any parent folder, or beside the compiler. Every file in the
folder is parsed; functions you never call are pruned by reachability, so an
import costs nothing beyond the parse.

### Shipped in the project folder (54 functions)

| Library | Count | Functions |
| --- | --- | --- |
| essentials | 19 | clamp→builtin, distance, factorial, fib, gcd, is-even, is-odd, is-prime, lcm, lerp, map-range, percent-of, power, random-chance, random-float, random-pipeline, random-range, round-to, sign→builtin, square, sum-to |
| math | 9 | area-circle, digits-sum, hypotenuse, is-palindrome-number, nth-prime, primes-below, reverse-number, to-degrees, to-radians |
| units | 10 | celsius-to-fahrenheit, celsius-to-kelvin, fahrenheit-to-celsius, feet-to-meters, kelvin-to-celsius, kg-to-pounds, km-to-miles, meters-to-feet, miles-to-km, pounds-to-kg |
| geometry | 8 | area-rect, area-triangle, area-triangle-sides, circumference, distance-squared, normalize-angle, perimeter-rect, point-in-rect |
| vector | 8 | dot, length, normalize-x, normalize-y, reflect-x, reflect-y, rotate-x, rotate-y |

`docs/LIBRARIES.md` documents them; `examples/libraries_demo.ANVL` puts twenty of
them on one screen and is captured in `docs/assets/libraries.png`.

### Held back on the branch (17 functions) — they need text builtins

`len`, `mid` and `ord` do not exist in the project compiler, so these cannot run
there yet:

- text (8): capitalize, center, count-words, index-of, is-palindrome, left-of,
  pad-right, right-of
- validate (6): is-alpha-text, is-digit-text, is-empty, is-number-text,
  is-space-text, is-upper-text
- essentials (3): pad-left, text-repeat, text-reverse

They are written and tested on the branch (73 functions total there). Porting them
means adding text builtins to the language, not editing the library files.

### Things learned while building them (all encoded as rules)

- A library file holds **one function**, named after the file; a second definition
  is an error, not a warning.
- Library identity is by **aliased name** — an include registers its target as
  `helper--helper`, which is why the one-function rule exempts those.
- A library file **may** `include` another file and **may** `library import`
  another library; nested resolution walks the importing file's folder.
- A library a program imports but never calls reports `warning: import 'math' is
  never used`.
- Text helpers are recursive, never accumulator-based, so they stay reentrant.
- Every shipped function is exercised by a test — an unused function in a library
  folder would otherwise rot silently, because importing a folder parses all of it.

---

## 4. The `library import` port to the project compiler **(main, this session)**

Three files, no changes to the rest of the compiler:

| File | Change |
| --- | --- |
| `compiler/libraries.py` | **new** — folder search (own folder, 8 parents, then beside the compiler; `libraries-<name>/` or `libraries/<name>/`), file listing, and the one-function-per-file check |
| `compiler/parser.py` | recognises `library import <name>` at top level and emits a `library_import` node (nested use is refused: *"library import must be at top level"*) |
| `compiler/module_loader.py` | `load_library()` visits every `.ANVL` in the folder into the importing scope; `library_files` is collected and validated after the load, so a file that defines a differently-named function fails with *"a library file must define the function 'x' (one function per file)"* |

Verified: all 56 functions compile, and `examples/libraries_demo.ANVL` builds and
renders twenty exact values — gcd 6, lcm 36, factorial 720, fib 55, is-prime 1,
hypotenuse 5, to-degrees 180, nth-prime 29, primes-below 10, 100 C → 212 F,
−273.15 C → 0 K, 32 F → 0 C, area-rect 42, heron 6, point-in-rect 1,
normalize-angle 10, dot 11, length 5, rotate-x 0, reflect-y −3.

`tests/test_libraries.py` covers the feature itself (9 tests): every file becomes a
function, a file must define the function named after it, two functions in one
file are refused, a missing library says where it looked, importing twice is
harmless, a library in a parent folder is found, importing below top level is
refused, and the shipped folders are checked file by file.

Note: `display text` prints numbers as **whole numbers** in this compiler, so the
demo only uses examples with exact integer answers.

---

## 5. Compiler and runtime fixes made on the branch

Each of these was found by running code, and each is covered by a test.

| Fix | What was wrong | Evidence |
| --- | --- | --- |
| `anvil_str_cat` aliasing | a recursive text function joins into its own return buffer, so `a`/`b` could alias `dest`; reversing `"abc"` produced `ccb` | now `cba` |
| list reads past the count | `array(nums, 3)` on a 1-item list returned `0`, indistinguishable from a stored 0 | `path:4: list index 3 is outside 0..0`, exit 2 on both backends |
| missing prototype | `anvil_list_get` had no declaration in `anvil_runtime.h`, so generated C used an implicit `int` return and truncated doubles | added to the header; the previous attempt printed garbage |
| unterminated string | `say "abc` reported `invalid expression near '"abc'` | `unterminated string: no closing "` |
| duplicate `library import` | importing the same library twice failed on "already exists" | now idempotent |
| library file `include` | an included file's alias was counted as a second function definition | one-function rule excludes `--` aliases; test prints 18 |
| library file importing a library | the imported function was counted as the file's own | `ParsedProgram.library_functions` tracked |
| drawing without a scene | `display`/`clear`/`camera` outside a `scene 2d` program silently did nothing | warning: `display has no effect without a scene 2d program` |
| `camera` misuse | `camera 10, 10` gave `unsupported statement` | hint: `camera is written camera perspective <x,y,z>, camera fov(<degrees>) or camera control(...)` |
| runtime warnings | `/W4` build had C4996, C4701, C4456, C6385, C28183 | runtime now builds at `/W4` with **0 warnings**; `/analyze` findings either fixed (null-check ordering, `noreturn` on `anvil_str_overflow`, initialisers) or documented as an SDK false positive |

`count-words` also learned tabs, LF and CR as separators (was space-only).

---

## 6. Verification status

- Project folder (this checkout): **275 passed** (`python -m pytest tests -q`,
  184 s) after the library port — no regressions from the parser or loader changes.
- Branch: **622 passed, 1 skipped** (pytest) plus **116 differential probe cases,
  0 differences** between the C backend and the native x64 backend.
  Command: `python scripts/differential_probe.py` then `python -m pytest tests -q`.
- Project folder: the slot game and the library demo both build with `cl.exe` and
  were verified from screenshots of real runs.
- Edge cases are **measured on both backends first, then pinned** in tests — never
  inferred. `tests/test_library_edges.py` alone pins 45 degenerate behaviours
  (gcd(0,0)=0, factorial(-1)=0, power(2,-1)=0, normalize-angle(360)=0, …).

---

## 7. Open items

1. **Merge decision.** The branch is 100 ahead / 73 behind `main`. Porting it whole
   is a real rebase with real conflicts; the library system is already ported and
   working, so the remaining candidates are the runtime fixes (§5) and the linter.
2. **Text libraries** (17 functions) need `len`/`mid`/`ord` in the project compiler.
3. **`display text` number formatting** — fixed in the pass recorded in §9: every
   output path now uses one format (`%.15g`).
4. `stdlib/random_pipeline.ANVL` reports `warning: function 'random-pipeline' is
   never called` under `--check` on the branch (entry-file filter needs extending
   to stdlib paths).
5. `/analyze` still reports `C6001 Using uninitialized memory
   'anvil_images.pixels'` on the branch — a false positive (`static` ⇒ zero
   initialised), fixable honestly by writing `= {0}` at the declaration.

---

## 8. Commands

```bash
# build and run the slot machine
cd C:/Users/power/Documents/AnvilEngine-work
python compiler/anvil.py examples/slots.ANVL -o slots.exe && ./slots.exe

# build the library demo
python compiler/anvil.py examples/libraries_demo.ANVL -o libraries_demo.exe

# tests (branch checkout)
cd C:/Users/power/Documents/buld/os/toolchain/anvil
python scripts/differential_probe.py && python -m pytest tests -q
```

---

## 9. Text, print, diagnostics and quality-of-life built-ins

Driven by the defect list in `anvil.TXT` (PART 6 order). Everything here was
verified by compiling and running programs on this machine, and is covered by
`tests/test_text_and_print.py` (11 tests).

### Text is now a value that can be joined (B2, B13)

- `+` joins text. A number on either side of a text `+` is formatted with the
  single number format, so `"score " + var(score) + " / " + var(best)` works, as
  does a local or `call fn(...)` inside the chain. Before this only
  `"literal" + var(x)` compiled; `"n = " + 6` and `"n = " + local(v)` were
  rejected with *"expected a number, got a string"*.
- `print` (alias `say`) writes a line to the console from any function or from
  the top level; `print` alone writes a blank line. Before this, a program could
  only ever print `fn(main)`'s return value.
- Text supports `=`, `==` and `!=`; any other operator on text is a compile error
  that names the operator.
- Text built-ins: `len`, `ord`, `find`, `upper`, `lower`, `trim`, `mid`,
  `replace`, `chr`. Results live in a 256 KiB scratch arena, valid for the
  statement that consumes them.

### One number format (B1, B15)

Screen text used `%.0f`, so 12.566371 drew as "13" while the console printed
12.5663706143592. Every output path now formats through `ANVIL_NUMBER_FORMAT`
(`%.15g`) in the runtime, so console, `display text` and `print` cannot disagree.
Measured: `display text("area = " + 12.5663706143592)` draws the full value, and
`print` of the same number prints the identical text.

### Errors read like a modern compiler

`compiler/diagnostics.py` renders every CompileError as message +
`--> file:line:col` + source line + caret + `= help:`. The caret sits on the
offending token (an explicit needle, else the quoted token in the message).
Hints cover the mistakes people actually make: `else if`, text in a numeric
slot, `^` as power, bitwise operators, unknown name/function (did-you-mean via
difflib), undeclared local ("varl() reads a global"), missing `end`,
`display text` without `-l`, bad array index, native-backend gaps.

### Warnings

`compiler/lint.py` reports three non-fatal warnings with the same layout:
`display`/`clear` with no scene or draw callback (B6), `output` inside a loop
(B12 — it returns at the first iteration), and statements after `output`.

### `else if` works (B5)

`else if` parses as sugar for a nested `if` inside the `else` block, and one
`end` closes the whole chain. `else if` with no preceding `if` explains the
alternative instead of saying "unsupported statement".

### Built-ins that save time

`round(value[,places])`, `clamp`, `sign`, `pow`, `hypot`, `log`, `log10`, `exp`,
`tan`, `atan2`, and `mod` (floored: `mod(-5,3)` is 1, while `%` keeps C fmod's
-2). `round(2.715, 2)` is 2.72, `round(1234, -2)` is 1200.

`clamp` and `sign` were already shipped as library functions; the builtins win
the namespace, so `libraries-essentials/clamp.ANVL` and `sign.ANVL` were removed
(calling them needs no import, so nothing is lost).

### Version 2 top-level `var()` (usability bug)

In version 2 the parser rewrote every unquoted `var(` to `local(` before parsing
the statement — including at top level, where a local is illegal. Every
top-level assignment in a version-2 program therefore failed with "local
variables must be declared inside a function". The rewrite now applies only
inside a function; at top level `var()` is always the global.

### `--check`

`python compiler/anvil.py file.ANVL --check` parses, validates and prints
warnings without invoking a C compiler.

### Still open

- Text variables do not exist: text is built inside the statement that consumes
  it. String parameters and returns need a typed variable layer.
- The native x64 backend cannot format text; `print` and dynamic
  `display text` stop with an explicit error and a hint to use the C backend.
- `rnd(low, high)` is still inclusive on both ends and `%` is still C fmod; both
  are documented, and `mod` is the floored alternative.

## Defects B7, B9, B10, B11, B14, B16 closed

### Build-time rejects instead of run-time surprises

`check_literal_array_index` runs for both array reads (`expressions.py`) and
array writes (`codegen.py`). A literal index that is fractional, negative or
past the end of the array is now a compile error with the offending number
underlined, so `array(a, 1.5)` can no longer build and die at run time.
Computed indexes still take the run-time check.

`display` argument mistakes are diagnostics instead of silent behaviour:
repeated `-rgb`/`-rgba` (B9), the meaningless trailing integer after a draw
call (B10), an unknown `-colour(...)`-style modifier named directly (B11), and
`display text` without `-l(x, y)` explaining what is missing (B14).

### A call stack on fatal errors (B16)

Every Anvil function is emitted as a thin wrapper around `anvil_body_<name>`.
The wrapper pushes `anvil_frame_enter(name, path, line)` on entry and pops it
after the body returns, so `anvil_report_call_stack()` prints the chain of
callers on any fatal run-time error:

```
t.ANVL:3: division by zero
call stack (innermost first):
  in fn(inner), defined at t.ANVL:2
  in fn(outer), defined at t.ANVL:6
  in fn(main), defined at t.ANVL:9
```

The frame functions are part of the reserved runtime names, so user functions
cannot collide with them.

### Documented behaviour (B3, B8)

`LANGUAGE.md` now states that `rnd(low, high)` is inclusive on both ends and
that the native backend draws literal text only, with a pointer to build HUDs
that show numbers with the default C backend.

### `--check` now matches the build

`--check` used to stop after parsing and linting, so the new display and array
diagnostics were invisible to it: `--check` said "no errors" for a program that
failed to build. It now runs the selected backend's lowering without writing an
executable or invoking a C compiler, so check and build agree on every error.

Measured: `python compiler/anvil.py B9.ANVL --check` exits 1 with the repeated
`-rgb` diagnostic, and a valid program still prints "no errors" and exits 0.

## Part 8.7 item 3: published backend feature matrix and conformance suite

`tools/backend_matrix.py` compiles and runs one catalog of language features on
both declared backends and writes `docs/BACKEND_MATRIX.md`: a row counts as
supported only when the build succeeds and the program prints the expected
value, so capabilities are measured instead of inferred from docs.

Measured today (28 cases):

- 20 of 28 cases build and print the same value on the C and native backends.
- The native backend rejects `mod(...)`, `round(...)`, `print`, `len(...)`, and
  `clear` inside `fn(draw)` with source-located diagnostics.
- Console number formatting still differs: C prints `1 / 3` as
  `0.333333333333333` (`%.15g`), the native backend prints `0.333333`.
- `for local(i) = 3 to 1` runs zero iterations on both backends (the default
  step is `1`); descending loops need `step -1`, which both backends honour.

`tests/test_backend_matrix.py` regenerates the matrix and fails when the
committed document drifts, so backend changes cannot silently invalidate the
published capability table.

## Part 8 GATE 0: reproducible baseline benchmarks

`tools/benchmark.py` builds and runs `tools/benchmarks/console_workload.ANVL`
(arrays, calls, recursion, loops; common operator set only) and writes
`docs/BENCHMARKS.md` with machine and toolchain metadata. First baseline on
this Windows 11 / MSVC 14.51 machine, 10 runs:

- C backend: build median 1.320 s, EXE 288,768 bytes, run median 0.013 s.
- Native backend: build median 0.092 s, EXE 70,144 bytes, run median 0.005 s.
- Both backends print `36886024`, so the workload is a shared-semantics check,
  not just a timer.

`tests/test_benchmark_workload.py` builds the same workload on both backends and
fails if the printed values diverge, extending the differential conformance
suite beyond the small numeric cases.

## Native backend: literal `print`

The matrix showed `print` rejected by the native backend even for a plain string
literal, while `display text("literal")` already worked. The native backend now
emits the same `GetStdHandle`/`WriteFile` sequence for `print "literal"` and
appends a newline, so a literal line prints identically on both backends:

- `print "hello"` prints `hello` then the program's numeric result on both.
- A text expression (`print "score = " + var(score)`) still fails at compile
  time with the source line and a message that says the C backend is required.
- `tests/test_native_x64.py` covers both the literal success and the located
  rejection; `docs/BACKEND_MATRIX.md` now includes a `print-literal` row.

## Native backend: `mod` and `round` parity

The matrix showed `mod(...)` and `round(...)` rejected by the native backend.
Both now lower to SSE2 in `compiler/native_math.py`:

- `mod(x, y)` computes `x - y * floor(x / y)` (floored modulo, matching the C
  runtime) and exits 2 with `path:line: modulo by zero` on a zero divisor.
- `round(x)` computes `sign(x) * floor(abs(x) + 0.5)` (half away from zero);
  `round(-0.4)` prints `-0` on both backends.
- `round(value, places)` is still C-only and now fails with a located message
  that names the limit instead of a generic parse error.

Tests in `tests/test_native_x64.py` cover the matching values, the sign cases
and both rejections; `docs/BACKEND_MATRIX.md` regenerates with these rows
supported on both backends (20 of 29 shared cases).

## Native backend: top-level `print` and editor grammar alignment

- Top-level `print "literal"` now runs before `main` on the native backend,
  matching the C backend's setup order (`booting` then the program result).
  Covered by `tests/test_native_x64.py` and the `print-toplevel` matrix row.
- The VS Code TextMate grammar now scopes `print`/`say` as keywords and adds
  the numeric/text built-ins the C backend documents (`round`, `sign`, `pow`,
  `hypot`, `log`, `log10`, `exp`, `tan`, `atan2`, `mod`, `len`, `upper`,
  `lower`, `trim`, `mid`, `replace`, `find`, `ord`, `chr`). `npm test
  --prefix vscode-extension` checks the new scopes against real source lines.

### Test cleanliness on Windows

`tests/test_runtime.py` now uses `TemporaryDirectory(ignore_cleanup_errors=True)`
because a just-built probe executable can still be locked for a few milliseconds
by Windows after the child exits; the run's assertions passed while the temp-dir
teardown raised `WinError 5` and failed the test. The behaviour checks are
unchanged.

## Part 8 GATE 1: explicit UTF-8 code-point operations

The text contract documented bytes only, so an index could split a multi-byte
sequence and emit invalid UTF-8. The C runtime now also provides code-point
operations that decode UTF-8 and copy whole sequences:

- `utf8_len(text)` counts code points (`len` still counts bytes).
- `utf8_char(text, index)` returns one code point, empty when out of range.
- `utf8_mid(text, start, count)` slices whole code points.

`tests/test_text_and_print.py` covers `é` (2 bytes, 1 point), `🙂` (4 bytes,
1 point), a mixed slice and an out-of-range index; the console capture decodes
UTF-8 explicitly. `docs/LANGUAGE.md` documents both families, the editor grammar
scopes the new calls, and the matrix records `utf8-codepoints` as C-supported
with the native backend rejecting text built-ins (a documented gap).

## Part 8 GATE 2: formatter and format check

`compiler/formatter.py` re-indents `.ANVL` source without touching meaning
(indentation is cosmetic in Anvil). `--format` rewrites in place and
`--format-check` exits 1 when a file is not canonical, for CI or editor tasks.

- Two-space blocks; `else`/`else if` align with their `if`; blank lines keep no
  trailing spaces; `\r\n` is normalized.
- `tests/test_formatter.py` covers nested blocks, an `else if` chain,
  idempotence, the CLI exit codes, and that a formatted file still passes
  `--check`.
- Existing `examples/*.ANVL` already pass `--format-check`, so adopting the
  formatter causes no churn.

### `--deny-warnings`

Warnings already shared the error layout but always let the build continue.
`--deny-warnings` now prints them and exits 1 before any output is produced, so
CI can enforce a warning-free tree. `tests/test_text_and_print.py` checks the
failing exit code and the "treated as errors" note; `docs/LANGUAGE.md` documents
the flag next to the warning list.

## Part 8 GATE 1: LANGUAGE_SPEC.md matches the implemented language

The normative spec still said strings do not exist, display text took only
`STRING + var(name)`, repeated colour modifiers were ignored, and the legacy
integer suffix was accepted. All four were false. Updated:

- Text values, `+` joining, `%.15g` number formatting, and `print`/`say` are
  specified, with a grammar production for `print_statement` and
  `text_expression`, and a §3.4 section covering byte vs code-point built-ins,
  the scratch-arena lifetime, and the native literal-only limitation.
- Repeated colour modifiers are specified as invalid; a stray number after a
  display call is specified as a rejected diagnostic (both already implemented).
- Added a complete text-and-print conformance example, verified with `--check`.

## Native backend: `clear` inside `fn(draw)`

The matrix showed `clear` rejected inside a draw callback, so the same scene
compiled on C and failed on native. The native draw path now accepts a literal
`clear rgba(r,g,b,255)` and fills the client surface through the existing
rectangle kernel (whole client, opaque), which keeps the per-frame reset the C
backend provides. Transparent alpha is still rejected with a located diagnostic,
matching the scene-setup rule.

`tests/test_native_x64.py` covers acceptance and the alpha-255 rejection; the
`clear-inside-draw` matrix row now reads `builds` on both backends.

### Windows temp-dir teardown races (all test files)

A second suite hit the same `WinError 5` during `TemporaryDirectory` cleanup
(`test_native_projects.test_clock_title_and_shutdown`, removing a just-built
`input.exe`), after the assertions had passed. Every test file now uses
`TemporaryDirectory(ignore_cleanup_errors=True)`, matching the earlier runtime
fix, so a briefly locked executable cannot fail a green test. Behaviour checks
are unchanged.
