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

### Shipped in the project folder (56 functions)

| Library | Count | Functions |
| --- | --- | --- |
| essentials | 21 | clamp, distance, factorial, fib, gcd, is-even, is-odd, is-prime, lcm, lerp, map-range, percent-of, power, random-chance, random-float, random-pipeline, random-range, round-to, sign, square, sum-to |
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
3. **`display text` number formatting** rounds to whole numbers — fractional
   results cannot be shown exactly yet.
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
