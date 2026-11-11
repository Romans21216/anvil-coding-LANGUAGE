# Anvil

**Anvil** is a small BASIC/Lua-inspired game language with its own `.ANVL` source format. The current default compiler emits C and invokes MSVC for broader engine coverage. An experimental direct x64 backend (`--backend native`) writes a Windows `.exe` without emitting C/Rust or invoking another compiler; it supports numeric programs and an initial 2D window runtime. The project target is a complete Anvil-owned compiler and runtime with no C or Rust dependency.

Try the language without writing a file first:

```powershell
python compiler/anvil.py --hello    # builds and runs a greeting program
python compiler/anvil.py --repl
anvil> name = "Ada"
anvil> say "Hello, " & name
```

The shell runs each statement with the real compiler and remembers your work: assignments, `add`/`sub`, list and array declarations, and `ask` answers. A bare expression prints its value, so `1 + 2` and `count(nums)` work like a calculator:

```
anvil> list nums
anvil> add nums 5
anvil> count(nums)
1
anvil> ask "name? ", var(who)
name? Ada
anvil> say "hello, " & var(who)
hello, Ada
```

`:vars` shows what the shell remembers and `:clear` forgets it. `docs/TUTORIAL.md` walks through ten small programs that are built and run by the test suite. `docs/GRADE.md` publishes the beginner-language scorecard and how to reproduce it (`python tools/grade_anvil.py`, currently 10.0/10).

## What works now

- Text equality in conditions (`if var(answer) = "yes"`, `!=` too) on both backends; comparing text with a number is a compile error.
- `ask "Name? ", var(name)` reads one console line into a text variable (optional prompt; CR/LF stripped), in both backends. When the variable holds numbers (`set var(age) = 0` first), `ask` reads a number instead — whole numbers, negatives, and decimals parse on both backends; non-numeric input reads as 0. Several `ask` statements in one program work on both backends, including lines that arrive together through a pipe.
- Text variables and `&` joining (C and native backends): `set var(name) = "Ada"`, then `say "Hello, " & var(name)`. Numbers join automatically (`var(score) & "!"`), results can be stored back into variables, and values are capped at 255 characters with a clear error instead of silent truncation.
- Text functions count bytes, not letters: `len("héllo")` is 6 and `char("héllo", 1)` returns the second byte of `é`. Plain ASCII behaves exactly as you would expect; both backends agree byte for byte.
- Text literals understand four escapes — newline, tab, a double quote, and a backslash itself — written as backslash-n, backslash-t, backslash-quote and a doubled backslash. Any other backslash sequence stays as written, so Windows paths need doubled backslashes.
- `repeat <count>` runs a block that many times (`repeat 3` … `end`), accepting any expression; zero or negative counts run nothing. Both backends.
- Unused functions are absent from generated code: the compiler emits only functions reachable from the top-level calls, `main`, and active `draw`/`update` callbacks. Both backends.
- `stop` ends the program immediately with exit code 0 (statements after it never run); a skipped `stop` lets the program finish. Both backends.
- `break` leaves the innermost `for`, `while` or `repeat` loop; `continue` skips to the next iteration (a `for` loop still applies its step). Both backends, including nested loops.
- Text ordering: `<`, `<=`, `>`, `>=` compare text alphabetically (`if var(name) < "m"`), matching text against text only. Both backends.
- `starts_with(text, prefix)` / `ends_with(text, suffix)` report 1 when the text begins or ends with the given text; a suffix longer than the text never matches. Both backends.
- `contains(text, needle)` reports 1 when the needle occurs in the text, else 0; an empty needle always counts as contained. Both backends.
- `left(text, count)` / `right(text, count)` take text from either end (`left("Anvil", 3)` = "Anv", `right("Anvil", 3)` = "vil"); a count past the text gives the whole text, and a zero or negative count gives empty text. Both backends.
- `%` gives the floating-point remainder (`7 % 3` is 1, `7.5 % 2` is 1.5) on both backends.
- Growable lists: `list nums` declares one, `add nums 5` appends, `count(nums)` reports how many, and `array(nums, i)` reads a slot (0-based). Lists hold up to 256 values and stop with a clear bounds error past that. Both backends.
- Fixed-size arrays work on both backends, at the top of the file or inside a function (`array scores(5)`): reads and writes are bounds-checked, and a function's own array is private to each call, so recursion keeps separate copies. The native backend limits a function's local arrays to 4 KB of stack until stack probing lands.
- Runtime errors (numeric overflow, array bounds, text range) go to stderr with the source location on both backends, so program output stays clean.
- Numbers print the same way on both backends: up to six fractional digits, trailing zeros trimmed, no exponent notation (`1 / 3` prints `0.333333`, `0.000001` stays `0.000001`). The native backend prints whole parts up to 9.2e18 and then stops with `Anvil output out of range`; the C backend keeps going to about 1e63.
- Variables take optional `number`, `text` and `bool` annotations (`set var(alive): bool = true`); a mismatch is a source-located error, and unannotated variables still infer their type.
- Functions both take and return text on both backends: `fn(greet, who) output "hi " & var(who) end` called as `call fn(greet, "Ada")`. A parameter is text when the body uses it as text (a join with a literal, a text builtin, a text comparison, or returning it from a text-returning function) or when every caller passes text; otherwise it stays a number, and a mismatch is reported at the call site.
- `mid(text, start, count)` extracts a bounded slice: the count clamps to the text's end, a start past the end or a negative count gives empty text. Both backends.
- `char(text, n)` yields the nth character as text, 0-based; out-of-range indexes give empty text. Both backends.
- `number(text)` parses a text value into a number: optional spaces and sign, digits, a fraction, and an `e` exponent (`number("1e3")` = 1000). Hex, `inf` and `nan` read as 0, and non-numeric input reads as 0. Both backends.
- `trim(text)` removes leading and trailing spaces/tabs (inner spaces survive); an all-whitespace value becomes empty. Both backends.
- `chr(n)` / `ord(text)` convert between numbers and characters (`chr(65)` = "A", `ord("A")` = 65; `ord` reads the first character, `chr` accepts 0-255 and stops with an error outside that range). Both backends.
- `upper(text)` / `lower(text)` convert case and yield text, usable anywhere text works (say, `&` joins, assignments); other characters pass through unchanged. Both backends.
- `round(x)` rounds to the nearest whole number, halves away from zero (2.5 → 3, -2.5 → -3), in both backends.
- `len(var(name))` counts the characters of a text value (both backends); `len(42)` is a compile error.
- `press enter` pauses until the player presses Enter (extra typed text is discarded), in both backends.
- `wait <seconds>` pauses console programs (`wait 2`), accepting expressions and clamping negatives to no delay.
- Prefix `not` negates conditions (`if not var(dead)`), with `not a = b` reading as "a is not equal to b"; C `and`/`or`/comparison results are now real doubles, so they print and store correctly.
- `elif` chains keep multi-branch decisions flat (`if … elif … elif … else … end`) in both backends.
- `write` prints like `say` but without ending the line, so several writes build one line of output. Both backends.
- `say` prints text and values on one line (`say "Score: ", score`), with `\n`/`\t`/`\\`/`"` escapes, in both console and engine programs.
- A Windows C backend for numeric globals, checked fixed-size global and function-local arrays, function-local variables, parameterized and recursive functions with numeric return values, calls, branches, inclusive `for`/`while` loops, input, time, seeded random numbers, gradient noise, and fractal noise.
- An experimental direct x64/PE32+ backend for numeric functions, checked fixed-size global arrays (up to 16 MiB total program data), arithmetic, comparisons, branches, loops, and console output rounded to six fractional digits. Its initial Win32 2D runtime supports a resizable window, buffered opaque rectangles, `fn(draw)`, fixed 60 Hz `fn(update)`, `time()`/`delta()`/`compute()`, and `held(key)`/`pressed(key)`. Trigonometry (`sin`/`cos`) runs on the x87 stack with exact `fprem1` range reduction, so large or negative angles match the C backend's libm results. It emits the EXE directly from `.ANVL` and imports Windows APIs without a C/Rust runtime shim. Full native engine parity remains incomplete.
- A small native software renderer for 2D rectangles, circles, lines and text, plus shaded 3D cubes, spheres, and grid planes with a perspective camera and depth buffer.
- Keyboard camera movement/look, adjustable field of view, and a built-in BVH-accelerated CPU ray-traced sphere with shadows and specular lighting.
- Keyboard edge/held state, configurable fixed-step updates, deterministic RNG and noise helpers.
- Resize-aware mouse position, per-update button edges, held buttons, and signed wheel input in virtual framebuffer coordinates.
- 2D sprite resources loaded from bounded uncompressed 24-bit/32-bit BMP files, with alpha blending, nearest-neighbor scaling, clipping, and explicit release.
- A first LAN multiplayer primitive: opt-in UDP host/join and exchanging one numeric value.
- A configurable fixed-step 2D circle and axis-aligned box-body system (up to 128 slots) with forces, gravity, restitution, mixed-shape collision response, and Coulomb friction.
- A VS Code language extension and a browser-based preview workbench.

This is an early prototype. Conventional primitives use a fixed-size software rasterizer, and ray-traced spheres use CPU BVH traversal; hardware DXR is not implemented. Image loading supports uncompressed BMP only; 3D mesh textures, image compression, and sprite animation are not implemented. Physics supports up to 128 fixed-step 2D circles and axis-aligned boxes, including mixed-shape contacts and per-body Coulomb friction, but has no rotation, continuous collision detection, or broad phase. The networking sample is a bare LAN prototype, not a secure or reliable Internet multiplayer stack. Rust output, audio, 3D physics, a full editor, portability, and performance benchmarks are future work. “Hyper-efficient” is a design goal, not a measured result.

## Diagnose without building

Every compiler error now shows the source line and points at the token that
caused it, so a failing build reads like this:

```
examples/broken.ANVL:3: undefined variable 'missing'
    3 |     total = hp + missing
                       ^
```

`--check` runs the lexer, parser and semantic passes without writing C, an EXE
or any other artifact, which is the fast way to validate a file after an edit
and the mode an editor or CI job should call:

```powershell
python compiler/anvil.py examples/first_world.ANVL --check
python compiler/anvil.py game.ANVLproj --check
```

## Build an EXE

On Windows, install Python 3.11 or newer and Visual Studio 2022 Build Tools with the **Desktop development with C++** workload. MSVC is the verified compiler. Then run:

```powershell
python compiler/anvil.py examples/first_world.ANVL --release --generated-c build/first_world.c --output build/first_world.exe
python compiler/anvil.py game.ANVLproj --release --output build/first_world.exe
python compiler/anvil.py examples/loops.ANVL --release --output build/loops.exe
python compiler/anvil.py examples/arrays.ANVL --release --output build/arrays.exe
python compiler/anvil.py examples/physics.ANVL --release --output build/physics.exe
python compiler/anvil.py examples/physics_boxes.ANVL --release --output build/physics_boxes.exe
python compiler/anvil.py examples/physics_friction.ANVL --release --output build/physics_friction.exe
python compiler/anvil.py examples/image_sprite.ANVL --release --output build/image_sprite.exe
```

This writes inspectable C and compiles it with MSVC. To only translate Anvil to C, add `--emit-c build/first_world.c`. The generated C is ordinary C, while the runtime currently targets Windows.

To try the experimental direct backend, only Python 3.11 or newer is required on Windows x64:

```powershell
python compiler/anvil.py examples/functions.ANVL --backend native --output build/functions-native.exe
python compiler/anvil.py examples/native_2d.ANVL --backend native --output build/native_2d.exe
./build/native_2d.exe
```

This backend writes x64 machine code and a PE32+ executable directly. In the native 2D sample, Left/Right move the panel, Space pauses the animated marker, and R resets its position. Left drag positions the panel, the wheel moves it horizontally, right click pauses, and middle click resets. Closing the window ends the program. Native rendering supports opaque rectangles in client pixels, with keyboard input and client-pixel mouse queries for pointer position, three buttons, and vertical wheel input. Other shapes, text, 3D, assets, physics, networking, and project manifests remain unavailable on this path. See [the native compiler migration plan](docs/NATIVE_X64_COMPILER_MIGRATION.md) for its exact limits and status.

The direct backend also supports basic math, deterministic seeded integer random numbers, gradient noise and fBm. Build `examples/native_procedural.ANVL` with `--backend native` for terrain generated by an Anvil-written procedural runtime. Space or left click regenerates it. See the migration guide for numeric domains and remaining native limitations; package registries/binary plugins and Forge targets remain unfinished.

## Run checks

```powershell
python -m unittest discover -s tests -v
python scripts/validate_qa_report.py
npm ci --prefix vscode-extension
npm test --prefix vscode-extension
```

The numeric sample builds and prints `17`. The starter world builds into a native Windows executable. Run it to open the game window.

## Files

- [Language guide](docs/LANGUAGE.md)
- [Formal language specification](docs/LANGUAGE_SPEC.md)
- [Backend capability matrix](docs/BACKENDS.md)
- [Versioning and stability policy](docs/VERSIONING.md)
- [Response to the commit review and language roadmap](docs/REVIEW_RESPONSE.md)
- [Engine runtime](docs/ENGINE.md)
- [Completion matrix](docs/COMPLETION_MATRIX.md)
- [Audited implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Autonomous development progress](docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md)
- [Multiplayer prototype](docs/MULTIPLAYER.md)
- [Compiler and build](docs/COMPILER.md)
- [Starter world](examples/first_world.ANVL)
- [LAN counter sample](examples/network_counter.ANVL)
- [LAN client sample](examples/network_client.ANVL)
- [Numeric compiler sample](examples/numeric_demo.ANVL)
- [Function parameters and local variables sample](examples/functions.ANVL)
- [While and numeric for loop sample](examples/loops.ANVL)
- [Fixed-size arrays sample](examples/arrays.ANVL)
- [2D circle physics sample](examples/physics.ANVL)
- [2D boxes and mixed-shape physics sample](examples/physics_boxes.ANVL)
- [Mouse input sample](examples/mouse_input.ANVL)
- [BMP image sprite sample](examples/image_sprite.ANVL)
- [VS Code extension](vscode-extension/README.md)
- [Full improvement backlog](docs/IMPROVEMENT_BACKLOG.md)
- [Wiki pages](docs/Wiki/Home.md)
- [Contribution and bug reporting rules](CONTRIBUTING.md)

`.ANVL` is the source extension and `.ANVLproj` is the TOML project manifest. The compiler resolves the manifest's entry path within the project folder and applies its project name and fixed update rate. Anvil is a working project name; it has not had trademark clearance.

## Troubleshooting

- **No C compiler found:** install the Visual Studio Build Tools C++ workload, then rerun the command from a new PowerShell session.
- **Manifest entry is rejected:** use a path relative to `game.ANVLproj`; entries must stay inside that project folder.
- **VS Code validation cannot find a package:** run `npm ci --prefix vscode-extension` once, then rerun the validation command.

The `.ANVL` suffix is used here for Anvil source; the name also appears in an unrelated metadata serialization format, so the suffix is not globally unique.


Local multi-file source composition uses top-level `include "relative/library.ANVL"`. Both backends resolve the local include graph; the native backend compiles reachable functions and their runtime dependencies. See [include semantics and limits](docs/INCLUDES.md). Namespaces, package registries and separate object linking remain unfinished.
