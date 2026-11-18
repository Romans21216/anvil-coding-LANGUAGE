# Anvil Language Specification — Version 1

**Status:** normative description of the `.ANVL` language accepted by the current compiler.
**Language version:** `1` (an omitted version declaration means version 1).
**Reference implementation:** `compiler/anvil.py`; runtime behavior is implemented in `runtime/anvil_runtime.c`.

This document specifies the language that exists today. It does not describe planned syntax. Anvil is a small, line-oriented, dynamically numeric language compiled ahead of time to ordinary C and linked with the Anvil runtime.

## 1. Source files and lexical rules

An `.ANVL` file is UTF-8 text. A source file consists of physical lines; each nonblank line contains one declaration or statement. Newlines terminate statements. Semicolons are not statement separators. Leading and trailing whitespace is ignored, and indentation has no syntactic meaning.

`#` begins a comment outside a double-quoted string and ends the current line. A quote preceded by an unescaped backslash does not end a string. Strings cannot span lines. Names are case-sensitive.

The lexical forms below use EBNF-style notation. `DIGIT` is an ASCII digit. `IDENT` starts with an ASCII letter or underscore and continues with word characters or hyphens; the implementation follows Python's Unicode `\w` rule for continuation characters.

```ebnf
DIGIT       = "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
LETTER      = "A"…"Z" | "a"…"z" ;
IDENT_START = LETTER | "_" ;
IDENT_CONT  = IDENT_START | DIGIT | "-" | UNICODE_WORD_CHARACTER ;
IDENT       = IDENT_START, { IDENT_CONT } ;
INTEGER     = DIGIT, { DIGIT } ;
NUMBER      = INTEGER, [ ".", { DIGIT } ], [ ("e" | "E"), [ "+" | "-" ], INTEGER ] ;
STRING      = '"', { ordinary_character | escape }, '"' ;
escape      = "\\", any_non_newline_character ;
whitespace  = ? one or more whitespace characters ? ;
blank_line  = whitespace, physical_newline | physical_newline ;
comment_line = whitespace, "#", { any_non_newline_character }, physical_newline ;
```

The compiler accepts a numeric literal only if it converts to a finite double. Unary `+` and `-` are operators, not part of the number token. String escapes are passed through to the generated C string literal; the stable portable subset is `\\`, `\"`, `\n`, and `\t`. General string values, concatenation, mutation, and string-returning functions are not part of version 1.

## 2. File structure and declarations

```ebnf
file             = { blank_line | comment_line }, [ version_line ], { blank_line | comment_line | top_item } ;
version_line     = "language", whitespace, "version", whitespace, INTEGER, line_end ;
top_item         = function_definition | global_array | top_level_statement ;
function_definition = "fn(", IDENT, [ ",", parameter_list ], ")", line_end,
                      { blank_line | comment_line | function_statement }, "end", line_end ;
parameter_list   = IDENT, { ",", IDENT } ;
global_array     = "array", whitespace, IDENT, "(", INTEGER, ")", line_end ;
function_statement = statement | local_array ;
block_item       = blank_line | comment_line | function_statement ;
local_array      = "array", whitespace, IDENT, "(", INTEGER, ")", line_end ;
top_level_statement = global_assignment | cleanup_statement | engine_statement | "seed(", expression, ")"
                    | "net host(", INTEGER, ")" | "net join(", STRING, ",", INTEGER, ")"
                    | function_call_statement ;
global_assignment = "set var(", IDENT, ")", [ ":", scalar_type ], " =", expression ;
# `set var(x) = null` is a compile error: null is not a value.
scalar_type      = "number" | "text" | "bool" ;
line_end         = physical_newline | end_of_file ;
```

There must be at least one function. Function definitions are top-level and function names must be unique. Parameter names within a function must be unique. Functions can be declared in any order and may call themselves recursively. Both backends bound the call chain: a call that grows the stack past a 512 KiB budget stops with `Anvil call depth exceeded the 512 KiB stack budget` and exit code 2 instead of an OS stack crash. The compiler generates a numeric function prototype for every function before generating its body.

At most one `language version N` line may occur, and it must precede all source code; blank lines and comments may precede it. Versions 1 and 2 are supported. Malformed, repeated, misplaced, and unsupported declarations produce a source path and line diagnostic. Existing files without a declaration are interpreted as version 1. This section defines version 1; version 2 changes and additions are listed in §8.

Scalar globals are introduced by `set var(name) = expression`. Globals begin at zero. An assignment may declare `: number`, `: text`, or `: bool`; a declared type is checked against the initial value and every later assignment to the same storage, and conflicting declarations are errors. Without an annotation, variables retain inferred types. `true` and `false` and comparison expressions are bool values; declared bool variables print as `true` or `false`. A global fixed-size numeric array is declared at top level as `array name(size)`; its elements begin at zero and `size` must be from 1 through 1,048,576.

## 3. Statements

Every statement below occupies a single source line, except that a block statement owns the following lines up to its matching `end`.

```ebnf
statement        = assignment | accumulation | array_write | function_call_statement | net_send_statement
                 | return_statement | if_statement | while_statement | loop_control
                 | for_statement | engine_statement | display_statement ;
loop_control     = "break" | "continue" ;  # innermost for/while/repeat
assignment       = "set var(", IDENT, ")", [ ":", scalar_type ], " =", expression
                 | "set local(", IDENT, ") =", expression ;
accumulation     = ("add" | "sub"), whitespace, "var(", IDENT, ")", whitespace, expression
                 | ("add" | "sub"), whitespace, "local(", IDENT, ")", whitespace, expression ;
array_write      = "set array(", IDENT, ",", expression, ") =", expression ;
function_call_statement = "call fn(", IDENT, [ ",", argument_list ], ")" ;
net_send_statement = "net send(", expression, ")" ;
display_statement = "display", whitespace, display_call, display_tail ;
display_tail     = { whitespace, display_style }, [ whitespace, INTEGER ], { whitespace, display_style } ;
display_call     = "rect(", expression, ",", expression, ",", expression, ",", expression, ")"
                 | "circle(", expression, ",", expression, ",", expression, ")"
                 | "line(", expression, ",", expression, ",", expression, ",", expression,
                   [ ",", expression ], ")"
                 | "text(", STRING, [ whitespace, "+", whitespace, "var(", IDENT, ")" ], ")"
                 | "cube(", expression, ",", expression, ",", expression, ",", expression, ")"
                 | "sphere(", expression, ",", expression, ",", expression, ",", expression, ")"
                 | "ray_sphere(", expression, ",", expression, ",", expression, ",", expression, ")"
                 | "ray_triangle(", expression, ",", expression, ",", expression, ",", expression, ",", expression, ",", expression, ",", expression, ",", expression, ",", expression, ")"
                 | "plane(", expression, ",", expression, ",", expression, ",", expression, ",", expression, ")" ;
display_style    = "-rgb(", expression, ",", expression, ",", expression, ")"
                 | "-rgba(", expression, ",", expression, ",", expression, ",", expression, ")"
                 | "-l(", expression, ",", expression, ")"
                 | "-rotate(", expression, ",", expression, ",", expression, ")" ;
return_statement = "output", whitespace, expression ;
if_statement    = "if", whitespace, expression, line_end,
                  { block_item }, [ "else", line_end, { block_item } ], "end" ;
while_statement = "while", whitespace, expression, line_end, { block_item }, "end" ;
for_statement   = "for local(", IDENT, ") =", expression, "to", expression,
                  [ "step", expression ], line_end, { block_item }, "end" ;
```

Semantic constraint for the grammar above: when `display_call` is `text(STRING)`, `display_tail` must contain at least one `-l(x,y)` location style; without it the compiler rejects the command.
At most one `-l(x,y)`, one `-rotate(x,y,z)`, and one color modifier (`-rgb` or `-rgba`) may appear on a display command. Repeating any of them is invalid. An unknown `-name(...)` suffix receives an unknown display modifier diagnostic. A trailing integer suffix is rejected because it has no effect; draw order follows source order.

The statements that may appear at file top level are limited to global `set var`, global array declarations, engine/project setup statements, `seed(expression)`, and `call fn(...)`. `add`, `sub`, `output`, local declarations, array writes, display commands, `if`, `while`, and `for` belong inside a function. `output` returns from that function immediately even when nested in a loop; the compiler warns when it appears inside `while` or `for`. Although the parser can form a top-level branch node, top-level control-flow blocks are rejected by C emission; they are not part of the accepted language.

The compatibility form `set var(name) = null` is accepted as a no-op (it neither clears nor changes the numeric variable). It remains in older examples as cleanup syntax; Anvil has no nullable scalar values.

### 3.1 Function locals and returns

`set local(name) = expression` declares function-local numeric state and initializes it to zero at function entry. Its assignment then sets the given value. `local(name)` reads the local. `add local(name) amount` and `sub local(name) amount` update it. Local state is function-scoped, not block-scoped. A local cannot use a parameter's name.

A function parameter is numeric. `var(name)` inside a function resolves to a same-named parameter when one exists; otherwise it refers to global numeric state. Writing `set/add/sub var(name)` follows the same parameter rule. Function locals do not shadow globals accessed with `var(name)`.

`output expression` returns one number from the current function. A function that reaches its end without returning yields `0`. There are no declared return types, multiple return values, or structured return statements. `fn(update)` and `fn(draw)` are optional engine callbacks and must have no parameters.

### 3.2 Arrays

`array(name, index)` reads a numeric element. `set array(name, index) = expression` writes an element and is only valid in a function. Indexes are zero-based finite whole numbers in `[0, size)`. Invalid indexes terminate execution with a path-and-line diagnostic and exit code 2.

An array may be global or local to a function. Arrays cannot be resized. The default project limit is 8,192 local array elements per function and 16 MiB of active local-array storage across recursive calls. An `.ANVLproj` may override these with `[memory].local_array_elements` (1–1,048,576) and `[memory].active_call_memory_mib` (1–2,048 MiB). The compiler rejects a function whose statically declared local arrays cannot fit its active-call budget; the shared budget also guards simultaneous recursive invocations at runtime. Local arrays are zero-initialized, allocated per invocation, and freed on every generated return. Allocation failure or budget exhaustion is a source-located runtime error. Each global array has a maximum size of 1,048,576 elements.

### 3.3 Branches and loops

`if expression` treats zero as false and any nonzero numeric result as true. One optional `else` is allowed. `end` closes the `if` and, when present, its `else` branch.

`while expression` checks its expression before every iteration and repeats while the result is nonzero. It has no implicit termination limit. `break` and `continue` are not supported.

`for local(i) = start to end [step amount]` evaluates `start`, `end`, and `step` once, then iterates inclusively in the direction of the step. The default step is `1`. Positive steps iterate while `i <= end`; negative steps iterate while `i >= end`. A zero step performs no iterations, leaving the loop variable equal to `start`. After a nonempty loop, the variable has the first value beyond the end condition. The loop variable is function-local, cannot be a parameter, and remains readable after the loop. Nested `for` loops must use different variable names.

## 4. Expressions and evaluation

```ebnf
expression       = logical_or ;
logical_or       = logical_and, { "or", logical_and } ;
logical_and      = comparison, { "and", comparison } ;
comparison       = sum, { compare_operator, sum } ;
sum              = product, { ("+" | "-"), product } ;
product          = unary, { ("*" | "/" | "%"), unary } ;
unary            = ( "+" | "-" ), unary | primary ;
primary          = NUMBER | STRING | "true" | "false" | key_name
                 | "var(", IDENT, ")" | "local(", IDENT, ")"
                 | "array(", IDENT, ",", expression, ")"
                 | "call fn(", IDENT, [ ",", argument_list ], ")"
                 | builtin_call | "(", expression, ")" ;
argument_list    = expression, { ",", expression } ;
compare_operator = "=" | "==" | "!=" | "<" | "<=" | ">" | ">=" ;
builtin_call     = builtin_name, "(", [ argument_list ], ")" ;
builtin_name     = "time" | "delta" | "rnd" | "noise" | "fbm" | "floor" | "ceil"
                 | "sqrt" | "sin" | "cos" | "abs" | "min" | "max" | "pressed"
                 | "held" | "mouse_x" | "mouse_y" | "mouse_pressed" | "mouse_held"
                 | "mouse_wheel" | "image_load" | "image_width" | "image_height" | "image_destroy"
                 | "image_draw" | "image_draw_scaled" | "image_draw_rotated" | "image_draw_region" | "image_tint" | "image_flip" | "sound_error" | "sound_load" | "sound_play"
                 | "sound_play_loop" | "sound_stop" | "sound_stop_all" | "sound_volume" | "sound_pan"
                 | "sound_pitch" | "sound_active" | "sound_destroy"
                 | "save_error" | "save_number" | "load_number" | "save_text" | "load_text"
                 | "save_exists" | "save_delete"
                 | "receive" | "body_create" | "body_create_box" | "body_destroy"
                 | "body_active" | "body_x" | "body_y" | "body_vx" | "body_vy"
                 | "body_set_velocity" | "body_force" | "body_restitution" | "body_friction"
                 | "body_collision" | "physics_capacity" | "physics_gravity" | "physics_step"
                 | "ray_backend" | "ray_backend_available" | "ray_resolution" | "ray_samples" ;
key_name         = "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "I" | "J"
                 | "K" | "L" | "M" | "N" | "O" | "P" | "Q" | "R" | "S" | "T"
                 | "U" | "V" | "W" | "X" | "Y" | "Z" | "SPACE" | "UP" | "DOWN"
                 | "LEFT" | "RIGHT" | "ENTER" | "ESCAPE" ;
```

User-defined function call arguments are evaluated exactly once, from left to
right, including nested calls. The compiler preserves this order regardless of
the selected C compiler. For example, in `call fn(pair, call fn(next), call
fn(next))`, the first `next` call supplies the first argument to `pair`.

All binary operators associate left-to-right. Precedence, from lowest to highest, is:

| Precedence | Operators |
|---:|---|
| 1 | `or` |
| 2 | `and` |
| 3 | `=`, `==`, `!=` |
| 4 | `<`, `<=`, `>`, `>=` |
| 5 | `+`, `-` |
| 6 | `*`, `/`, `%` |
| 7 | unary `+`, unary `-` |

Parentheses group expressions. `=` and `==` both mean numeric equality. Comparisons and logical operators return `1` for true and `0` for false. Logical `and` and `or` short-circuit: the right operand is evaluated only if needed. The words `true` and `false` are numeric values `1` and `0`.

The compiler also accepts the legacy compatibility form `compute(expression)` when it wraps an entire expression. It is not a callable built-in; nested or partial `compute(...)` forms are not supported.

An expression must have the expected value kind. Most operators, variables, arrays, and function results are numeric. String literals are accepted only in string-taking built-ins and drawing text. The ray-backend functions require a string literal; mouse button functions require one of the string literals `"left"`, `"right"`, or `"middle"` at runtime. `image_load` accepts a path string literal. `sound_load` accepts a path string literal. The save built-ins take a slot-name string literal. `net join` accepts a literal address. Drawing text accepts a string literal. After an initial literal, `+` may append numeric expressions (use parentheses to keep arithmetic together), and `&` follows the general text-join rules; numbers use the shared six-fractional-digit, trailing-zero-trimmed formatter.

Division by zero, including negative zero, is a runtime error with source path and line and exit code 2. Every numeric operation and numeric built-in result must be finite; NaN or infinity (including overflow and invalid math results) produces a source-located runtime error. Numeric values use the C backend's `double` representation; there are no integer, decimal, or user-defined numeric types in version 1.

## 5. Built-ins

All built-ins return a numeric result unless otherwise stated. Calls use parentheses and comma-separated arguments.

| Group | Function signatures | Meaning and limits |
|---|---|---|
| Clock/input | `time()`; `delta()`; `frame_tick()`; `frame_render()`; `frame_present()`; `pressed(key)`; `held(key)`; `mouse_x()`; `mouse_y()`; `mouse_pressed(button)`; `mouse_held(button)`; `mouse_wheel()` | Runtime elapsed time, fixed-step delta, the last frame's update (tick), draw (render) and presentation times in seconds, keyboard state, mouse position/button state, and wheel delta. Keys include the symbolic tokens `A`–`Z`, `SPACE`, arrows, `ENTER`, `TAB`, and `ESCAPE`; key inputs are numeric values and may also be supplied as numeric virtual-key codes. Mouse buttons are string literals `"left"`, `"right"`, or `"middle"`. Position is in fixed 960×600 virtual framebuffer pixels, with `-1` returned in letterbox bars or outside the window. Pressed state and wheel delta last through the next fixed update; held state ends on release or window focus loss. |
| Resource accounting | `memory_images()`; `memory_audio()`; `memory_video()`; `memory_gpu()`; `memory_total()`; `memory_report()` | Bytes currently held by each resource class. `memory_images` is the sum of decoded image pixels (4 bytes per pixel) and falls as images are destroyed; `memory_audio` is the decoded sample bytes of loaded sounds (48 kHz stereo 16-bit) and falls as sounds are destroyed; `memory_video` is every pixel surface the renderer holds: two 32-bit backbuffers plus the double-precision depth buffer (960x600x16 = 9,216,000 bytes on the C backend, 0 in the browser, where the page owns the canvas); `memory_gpu` is the subset a compositor can see, which is the two DIB sections (4,608,000 bytes on the C backend, 0 in the browser). Because rendering is CPU-side there is no GPU-visible memory beyond those backbuffers. `memory_total` sums images, audio and video. These are read-only counters for budgets, tests and in-game HUDs; the streaming-music staging buffer (32 KiB) is static and is not counted. `memory_report()` prints one row per live image and sound with its dimensions or frame count, its bytes, the Anvil `file:line` that allocated it, the Anvil call chain that reached the load (`main > setup > load_world`, or `top level` for a setup-block load, truncated with ` > ...` past eight names) and the asset path, then a `live allocations` total, and returns the live count so a program can warn above a threshold. The site is captured by the compiler, so loads through a literal `image_load()`/`sound_load()` are named; a handle loaded before the site fields existed reports `?:0`. C-backend only: `--backend wasm` raises a located "not available" diagnostic (a browser build bakes its assets at compile time and has no per-load call site). |
| Window flags | `window_on_top(on)`; `window_fullscreen(on)`; `window_scale(factor)`; `dpi_scale()` | `1` turns the flag on, `0` off, and both return `1` on success or `0` when there is no window. Always-on-top asks the OS to keep the window above other applications; turning it off lets the user click another program and have the game go behind it. Fullscreen switches the window to a borderless `WS_POPUP` covering the monitor and restores the previous style and rectangle when turned off; the fixed framebuffer is letterboxed as usual. The window is created per-monitor DPI aware and sized to 960x600 times the monitor scale, so it keeps its physical size on a 150% display; `dpi_scale()` returns that factor (1 at 96 DPI). `window_scale(factor)` resizes the client area to 960x600 x factor (clamped 0.25-4), leaves the framebuffer and its letterboxing unchanged, and returns the previous factor; a non-finite value leaves the scale alone. All four are C-backend only and raise a located diagnostic under `--backend native`. |
| UI focus and accessibility | `ui_focus_add(x,y,w,h,label)`; `ui_focus_clear()`; `ui_focus_count()`; `ui_focus_next()`; `ui_focus_prev()`; `ui_focus_set(handle)`; `ui_focus()`; `ui_focus_at(x,y)`; `ui_focus_activate()`; `ui_focus_label()`; `ui_accessible(on)` | A registry of focusable rectangles for a custom-drawn UI, where the engine owns what is easy to get wrong. `ui_focus_add` declares one region (a negative width or height is normalised) and returns a handle, or 0 when a coordinate is not finite, the label is longer than 95 bytes, or all 64 regions are taken; the label is never truncated, because a shortened label would announce a different control than the one drawn. `ui_focus_at` returns the topmost region containing a world point, with the last registered region winning so a later popup covers an earlier panel. `ui_focus_next`/`ui_focus_prev` move focus in registration order and wrap. `ui_focus_set` returns the handle focused before the call and leaves the focus alone for 0 or an unknown handle; `ui_focus` reads it back and `ui_focus_label` is the focused region's label (`""` when nothing is focused). A click focuses the topmost region under the press point and activates it; Enter or Space activates the focused region. `ui_focus_activate()` is the handle activated this frame (0 when none) and lasts one frame, like `pressed`. `ui_focus_clear` removes every region and returns how many were removed; handles are not stable across a clear. `ui_accessible(1)` switches announcements on and returns 1 when the channel is available: the focused label is written as the accessible name of a 1x1 child window and an MSAA focus event is raised on Windows, and written into an `aria-live` region on the wasm canvas page. Labels are announced when focus changes, not once per frame. C and wasm backends only: `--backend native` raises a located "not available" diagnostic. |
| Tilemaps | `tilemap_new(image,tile_w,tile_h,columns,rows)`; `tilemap_free(h)`; `tilemap_columns(h)`; `tilemap_rows(h)`; `tilemap_tiles(h)`; `tilemap_set(h,col,row,tile)`; `tilemap_get(h,col,row)`; `tilemap_fill(h,tile)`; `tilemap_area(h,tile,col,row,columns,rows)`; `tilemap_draw(h,x,y,scale)`; `tilemap_solid(h,tile,on)`; `tilemap_is_solid(h,tile)`; `tilemap_cell(h,x,y,scale)`; `tilemap_collide(h,x,y,w,h,scale)`; `tilemap_animate(h,tile,frames,fps)`; `tilemap_frame(h,tile)`; `tilemap_error()` | A grid of cells naming tiles in an image sheet: tile `t` is at `(t % tiles_per_row, t / tiles_per_row)` in the sheet, and tile `-1` is empty. `tilemap_new` returns a generational handle or 0 when the image, tile size (whole pixels, at least 1, no larger than the sheet) or grid (1..512 cells each side) is invalid; 16 maps can live at once. `tilemap_set` rejects cells or tiles outside their range and accepts -1 to clear a cell; `tilemap_fill` rewrites every cell and `tilemap_area` paints a rectangle clipped to the grid. `tilemap_draw` draws every non-empty cell at `(x + col*tile_w*scale, y + row*tile_h*scale)`, honours the 2D camera and sprite batching, and walks only the cell range that can reach the framebuffer (derived from the camera pan, the parallax factor and the zoom), so a 512x512 world costs the same per frame as a 20x12 one; it returns 1 for a valid call and 0 when there is no window, the tileset was destroyed or the arguments are not finite. `tilemap_columns`/`rows`/`tiles` return 0 and `tilemap_get` returns -1 for an invalid handle. `tilemap_solid` marks a tile index solid (the empty tile cannot be solid) and `tilemap_is_solid` reads it back; the per-map bitset is allocated the first time a map marks a tile, so maps that never collide cost nothing. `tilemap_cell` returns the tile under a world point, or -1 outside the grid. `tilemap_collide` tests the world rectangle `[x, x+w) x [y, y+h)` against solid cells, treating the map as drawn at the origin with `scale` (the same placement as `tilemap_draw(map, 0, 0, scale)`), and returns 1 when any overlapped cell is solid; a rectangle that misses the grid returns 0. `tilemap_animate` makes a tile cycle through `frames` consecutive indices at `fps` frames per second; frames advance left to right within the tile's row of the sheet and wrap at the row end, so an animation cannot bleed into the row below, and `frames` must fit that row (1 disables the animation). Animation is a render-time substitution: the cell keeps its base tile, so `tilemap_get`, `tilemap_cell`, solid flags and collision all keep answering with the base, and `tilemap_frame` reports the index currently drawn. `tilemap_error()` names the last draw failure. C-backend only: `--backend wasm` raises a located "not available" diagnostic. |
| 2D camera | `camera2d(pan_x,pan_y,zoom)`; `parallax(factor)` | Moves and scales every 2D draw (rect, circle, line, text position, sprite draws) with `screen = (world - pan) * zoom`; the default `0,0,1` is the identity, so existing programs are unchanged. `zoom` is clamped to 0.05–20 and a non-finite or non-positive zoom returns 0 and leaves the camera unchanged. The camera also inverts the mapping for `mouse_x`/`mouse_y`, so pointer coordinates are world coordinates. Text moves with the camera and its glyphs scale with the zoom (20 px at 1×, clamped to 6–720 px). `parallax` scales how much of the camera pan the following 2D draws follow: 1 (the default) is the world layer, 0.35 scrolls a backdrop slower, and 0 pins a layer — a HUD clear, a caption or a sky — to the screen. The factor is clamped to 0–4, a non-finite argument leaves the current value, and the call returns the previous factor so a draw can restore the state it found. Zoom and the mouse mapping are unaffected. 3D drawing is unaffected. C-backend only: `--backend native` raises a located "not available" diagnostic. |
| Particles | `particle_emit(x,y,vx,vy,life,size,r,g,b)`; `particle_count()`; `particle_clear()`; `particle_gravity(gy)` | A fixed pool of 4,096 particles. `particle_emit` returns 1, or 0 when the pool is full or an argument is non-finite, `life <= 0` or `size <= 0`; position is world-space (the 2D camera applies), velocity is pixels per second, `life` is seconds, `size` is the square side in pixels and colours clamp to 0–255. Particles advance in every fixed update by velocity, with `particle_gravity` adding a constant vertical acceleration (pixels per second squared, positive is down). They are drawn after the program's own draw pass as fading squares, with alpha going from 255 to 0 over their life, so they sit above the scene. `particle_count()` is the live count, `particle_clear()` empties the pool and returns how many it removed, and `particle_gravity` returns the value it applied. Destroying the window empties the pool. C-backend only: `--backend native` raises a located "not available" diagnostic. |
| 2D image assets | `image_load(path)`; `image_width(handle)`; `image_height(handle)`; `image_draw(handle,x,y)`; `image_draw_scaled(handle,x,y,width,height)`; `image_draw_rotated(handle,cx,cy,degrees,scale)`; `image_draw_region(handle,sx,sy,sw,sh,dx,dy,dw,dh)`; `image_tint(handle,r,g,b)`; `image_flip(handle,flip_x,flip_y)`; `image_destroy(handle)` | `image_load` accepts uncompressed 24-bit/32-bit BMP paths relative to process working directory (`--run` uses the project directory or standalone source directory). It returns a positive generational handle or `0` on failure; the first allocations use handles 1–64, and reusing a released slot gets a new value so stale handles stay invalid. A 32-bit file with all alpha bytes clear is treated as opaque. Decoded image limits are 8,192 pixels per side, 16,777,216 pixels per image, and 128 MiB total. Draw operations alpha-blend with nearest-neighbor scaling and clip to the fixed 960×600 framebuffer. `image_draw_rotated` draws centred on `cx,cy`, rotated clockwise by degrees and scaled uniformly; `image_draw_region` copies an atlas cell: the source rectangle must lie fully inside the image (a rect that does not returns 0 and draws nothing), and it scales into the destination rectangle. `image_tint` multiplies the sprite's colours (0–255 per channel, default 255 is unchanged) and `image_flip` mirrors it horizontally/vertically, both applied by every draw path, with flip mirrored inside an atlas cell, and reset when the image is destroyed. `image_error()` explains the most recent failure and names the exact limit (dimension, pixel count, memory budget, short file). Width/height on an invalid handle return 0; draw/destroy/tint/flip return 1 for valid requests and 0 otherwise. Remaining handles are released when the game closes. |
| Ray-traced meshes | `ray_mesh("path",x,y,z,scale,rx,ry,rz)` | C compiles static and animated `.gltf`/`.glb` mesh data and uses a cached per-geometry-group triangle BVH. Supports up to 200,000 triangles per mesh, 40 queued groups or instances per frame and 32 distinct cached groups; cached BVHs and per-frame posed copies share a 128 MiB budget. Animated node meshes snapshot posed triangles per instance and refit bounds each frame. `model_morph` weights apply to static groups and are blended before node transforms on animated groups; each group retains its glTF defaults until overridden. C skinned meshes are refused with a located error. Wasm `model_draw` and `ray_mesh` accept static and animated meshes, including morph targets with per-group defaults and `model_morph` overrides plus one skin with up to 64 joints, and submit triangles through the WebGL depth-tested renderer (both APIs share a 16,384-triangle frame budget); this is not ray tracing and does not add BVHs or ray-traced shadows. Returns 1 when accepted, 0 on invalid arguments or resource limits. |
| 3D models | `model_draw(path,x,y,z,scale,rx,ry,rz)` | Compiles a glTF model into the executable: the file is read at build time and its triangles become a static array, so the runtime never parses JSON and the model needs no shipping asset. Node transforms (matrix or TRS) are applied, per-triangle colour comes from `COLOR_0` when present and otherwise from the material's `baseColorFactor`, and drawing uses the scene camera, near-plane clip, depth buffer and the same directional light as `cube` (see 3D lighting). The model is scaled about its origin, rotated by `rx,ry,rz` degrees, then translated to `x,y,z`. Returns 1, or 0 for non-finite arguments, a zero scale, or when the model's bounding sphere is outside the view (culled). `mesh_culled()` and `mesh_drawn()` report how many models the current frame skipped and drew, and `mesh_culling(on)` turns the test off (returning the new state) for comparison. Supported: `.gltf` with a `.bin` or base64 data-URI buffer, `.glb` containers with JSON and BIN chunks, triangle/strip/fan primitives, a 200,000-triangle budget, paths relative to the main source file. A model whose file has one `skin` is baked as a skinned mesh instead: vertices keep four joint indices and four weights, and the runtime blends `nodeWorld * inverseBindMatrix` per joint (one skin, 1-64 joints). Static and animated models may carry up to eight morph targets; the importer keeps one POSITION delta per vertex per target and `model_morph` blends them. Each flattened mesh/node group starts with its own glTF default weights; node weights override the referenced mesh's defaults. `model_morph` overrides a target across all groups. Morph targets combined with skinning remain unsupported. Static, animated and skinned `model_draw` and static and animated unskinned `ray_mesh` support base-color PNG textures on C and WebAssembly. Skinned textured `ray_mesh` continues to use flat material color. Multiple skins, CUBICSPLINE animation keys, skinned meshes combined with morph targets, and sparse accessors remain unsupported. Available on C and WebAssembly; `--backend native` does not support 3D. |
| Audio | `sound_load(path)`; `sound_error()`; `sound_play(handle)`; `sound_play_loop(handle)`; `sound_stop(voice)`; `sound_stop_all()`; `sound_volume(voice,v)`; `sound_pan(voice,p)`; `sound_pitch(voice,r)`; `sound_active()`; `sound_destroy(handle)` | `sound_load` accepts a PCM or IMA ADPCM WAV path relative to the working directory: mono or stereo, 8- or 16-bit PCM at 8,000–192,000 Hz, or 4-bit IMA ADPCM (format tag 0x0011, block alignment 4·channels+4 to 4,096 bytes). ADPCM blocks are decoded to 16-bit before the same resampling step, and a file that would decode past 64 MiB is refused. The file is converted once to 48 kHz stereo at load, so playback is independent of the source rate. Loads return a slot handle from 1–16 or `0` on failure, and `sound_error()` names the reason (open failure, unreadable RIFF, non-PCM, channel/bit-depth/rate limits, per-sound or total budget, truncated data). Limits: 8 MiB decoded per sound, 48 MiB total, 8 simultaneous voices. `sound_play` returns a voice handle from 1–8, or `0` when every voice is busy or the audio device is unavailable; `sound_play_loop` repeats until stopped. `sound_volume` clamps to 0–1, `sound_pan` to -1..1, `sound_pitch` to 0.25–4 and each returns the applied value. Mixing runs on a bounded 3×10 ms `waveOut` queue (about 30 ms latency); the device is opened on first play, and a lost device falls back to silence with a readable error instead of crashing. `sound_destroy` frees a slot and stops its voices; remaining audio is released when the program closes. `sound_duration(handle)` returns the decoded length in seconds and `sound_rms(handle)` the root-mean-square amplitude of the decoded stereo samples (0-32767 scale), which is useful for meters and for checking imported audio. Mixer groups: `sound_group(handle,group)` moves a loaded sound to group 1–3 (default 1, invalid group returns 0); `sound_group_volume(group,v)` sets a group gain clamped to 0–1, where group 0 is the master applied to every sound; `sound_group_mute(group,on)` silences a group while keeping its volume; `sound_group_gain(group)` reads the effective gain, which is 0 while muted; `sound_group_stop(group)` stops every voice whose sound is in that group and returns how many it stopped, with group 0 stopping all of them. C-backend only: `--backend native` raises a located "not available" diagnostic. |
| 3D camera | `camera perspective x y z` statement; `camera fov(degrees)`; `camera_angle(yaw,pitch)`; `camera control(speed,turns_per_second)` | `camera perspective` places the camera. `camera_angle` sets its yaw and pitch in degrees programmatically (pitch clamped to -89..89, negative looks down) and returns 1, or 0 for non-finite values; arrow keys still steer it when `camera control` is active. `camera fov` sets the vertical field of view. |
| 3D morph targets | `model_morph(path,index,weight)` | A model may declare up to eight morph targets; the importer stores one POSITION delta per vertex per target (transformed into model space by the node's matrix) and per-group default weights. `model_morph` sets one target's weight, clamped to 0-1, for every group and returns the previous weight from the first geometry group; a non-finite weight leaves it alone and returns the current value. Untouched targets retain each group's glTF default. Node-level `weights` override the referenced mesh's defaults. An index outside 0-7, a non-finite weight or a model without targets is refused (the last at compile time, at the `model_morph` line). Blending is additive on the vertex position before the usual scale/rotate/translate; colour does not animate. In wasm, static and animated unskinned morphing is supported by both `model_draw` and `ray_mesh`; both use the depth-tested triangle renderer, while both APIs share a 16,384-triangle frame budget. Static morph groups use conservative bounds across defaults and every supported 0–1 override; animation and skin culling limits are described in the model guide. Wasm skinned `model_draw` and `ray_mesh` use the first clip or bind pose. |
| Independent model instances | `model_instance(path)`; `model_instance_morph(path,handle,index,weight)`; `model_draw_instance(path,handle,x,y,z,scale,rx,ry,rz)`; `model_instance_destroy(path,handle)` | Creates a generation-checked handle tied to a compiled unskinned glTF asset with morph targets. Store the returned handle in a variable before drawing. Each handle stores target overrides independently and `model_draw_instance` renders that copy using its own weights while preserving per-group defaults. `model_instance_morph` returns the previous target weight from the first geometry group; a fractional, negative or out-of-range index or non-finite weight returns 0 and leaves state unchanged. Destroy returns 1 for a live matching handle, otherwise 0; stale handles cannot alias reused slots. The runtime supports 64 live handles and returns 0 when full. C and wasm support static and animated unskinned morph models; skinned models and models without morph targets are rejected at compile time. The existing `model_morph` / `model_draw` pair remains asset-wide. |
| 3D model animation | `model_animate(path,seconds)`; `model_animation_length(path)` | A glTF model whose file has an `animations` clip is baked differently: triangles stay in node-local space and the node hierarchy plus keyframes ship with the model, so the runtime poses it per draw instead of at compile time. One clip is supported (the first), with translation, rotation and scale channels and `LINEAR` or `STEP` interpolation; rotations interpolate by slerp. `model_animate` sets that model's clip clock and returns the seconds it stored, `model_draw` samples the pose at that time, and the clip loops at its length (the time wraps, so a draw at exactly the length shows the first key). `model_animation_length` returns the clip length in seconds as a compile-time constant. The clock starts at 0, and calling `model_animate` on a model with no clip is a compile error. Culling and shadows are not applied to animated or skinned models. A skinned model uses the same clock: `model_animate` samples its joint channels, and with no clip it draws at the bind pose. Wasm supports unskinned animated models in `model_draw` and `ray_mesh` through the WebGL depth-tested triangle path; both APIs share a 16,384-triangle frame budget. Wasm skinned `model_draw` and `ray_mesh` use the first clip or bind pose. |
| 3D lighting | `light(x,y,z)`; `light_ambient(level)`; `light_intensity(level)` | One directional light shared by `cube`, `plane`, `sphere` and `model_draw` on C and wasm backends. `light` points the light at `(x,y,z)` (a direction toward the light; the vector is normalised on use, a zero or non-finite vector is rejected and returns 0, any other returns 1). `light_ambient` sets the floor every face keeps when it faces away (0-1, default 0.28) and `light_intensity` scales the lit part (0-2, default 1). Both return the previous value and ignore a non-finite argument. Shading is `ambient + (1 - ambient) * intensity * max(0, dot(normal, light))`, clamped to 0-1; model triangles are two-sided and light from either side. |
| Scene manager | `scene_change(name,seconds)`; `scene_name()`; `scene_target()`; `scene_changing()`; `scene_changed()`; `scene_progress()` | A scene change is a fade out, a swap of the current scene name while the screen is black, and a fade back in, which is the piece a program would otherwise re-implement around `screen_fade`. `scene_change` starts one and returns 1, or returns 0 and changes nothing when the name is empty or longer than 63 bytes, or when a transition is already running; a non-positive or non-finite duration changes the name immediately - one at a time, so a caller polls `scene_changing()` instead of stacking changes. The timeline is 45% fade out, a 10% black hold, and 45% fade in; the name swaps at the midpoint, which is inside the hold, so the change is never seen. `scene_name()` is the current scene (empty text before the first change) and `scene_target()` is the scene being changed to, empty again once the swap has happened. `scene_changed()` is 1 for the frame the name swapped - for a timed change it is set before that frame's draw, and for an immediate change the call itself sets it - so a program runs its scene setup once per change. `scene_progress()` is 0-1 across the transition and 1 when nothing is running. The transition owns `screen_fade` for its duration, so a program fade set at the same time is overwritten. C and wasm backends write the same overlay and timeline. |
| Screen fade | `screen_fade(alpha)`; `screen_fade_to(target,seconds)`; `screen_fade_alpha()` | Composites a black overlay over the finished frame, after every draw (2D, sprites, particles, 3D) and before the present, which is the primitive a scene transition, a menu or a hit flash is built from. `alpha` is 0-255 and is clamped; `screen_fade` sets it at once and returns the previous value, and a non-finite argument leaves it alone. `screen_fade_to` walks alpha to `target` over `seconds` of frame time (linear, clamped) and returns the previous value; a non-positive or non-finite duration applies the target immediately, so a caller can branch on the returned previous value to sequence a fade out and a fade in. `screen_fade_alpha` reads the current value. The overlay costs nothing while alpha is 0. C and wasm: the browser applies the same overlay above its canvas (including 3D) before the present. |
| Overhead shadows | `shadow(on)`; `shadow_height(y)`; `shadow_alpha(a)` | When on, `cube` and `model_draw` also draw their geometry flattened onto the horizontal plane at `shadow_height` (default 0), in black with `shadow_alpha` (default 150, clamped 0-255), before the object itself. This is an overhead-light shadow: it suits a camera looking down and does not depend on object rotation. `shadow` and `shadow_height` return the applied value; `shadow_alpha` returns the clamped alpha. Spheres, planes and ray-sphere primitives do not cast shadows. C-backend only. |
| Streaming music | `music_load(path)`; `music_play()`; `music_play_loop()`; `music_stop()`; `music_playing()`; `music_volume(v)`; `music_position()`; `music_length()`; `music_error()` | One music track, decoded from disk as it plays rather than held in memory: the mixer refills an 8192-frame (about 170 ms) staging buffer from the file and linearly resamples any 8,000–192,000 Hz 8/16-bit mono or stereo PCM WAV to the 48 kHz mix. `music_load` returns 1 and replaces the previous track, or 0 with a named `music_error()` for open failures, non-PCM/compressed files, 3+ channels, bit depths other than 8/16, rates outside the range and empty data. `music_length()` is the track duration in seconds. `music_play` and `music_play_loop` start from the beginning and return 0 when nothing is loaded or no audio device is available; a non-looping track stops itself at the end, a looping one wraps. `music_stop` stops and rewinds, returning 1. `music_position()` is the position in seconds and wraps on each loop. `music_volume(v)` clamps to 0–1 and is multiplied by the master group gain. C-backend only: `--backend native` raises a located "not available" diagnostic. |
| Saves | `save_number(slot,value)`; `load_number(slot)`; `save_text(slot,text)`; `load_text(slot)`; `save_exists(slot)`; `save_delete(slot)`; `save_error()`; `save_version()`; `save_set_version(n)` | One number or one <=255-byte text value per named slot, stored in `%LOCALAPPDATA%\Anvil\<project>` (the project name comes from the source file or manifest; `ANVIL_SAVE_DIR` overrides the root for hosts and tests). Slot names are 1–64 bytes from `A-Z`, `a-z`, `0-9`, `.`, `-` and `_`, must not start with a dot and must not contain `..`, so a save cannot escape its folder. Files carry an `ANVSAVE1` magic and a type byte: reading text as a number (or the reverse) returns `0`/empty text with a named `save_error()`, and a corrupt file is reported instead of reinterpreted. Writes go to a temporary file and replace the previous save atomically. A missing slot is a normal first run: `load_number` is 0, `load_text` is empty, `save_exists` is 0, and `save_error()` stays empty. `save_delete` returns 1 when a file was removed. A non-finite number is rejected on read. A project also carries one format version in `.version`, beside the slots: `save_version()` reports 0 on a fresh project and the stored value otherwise (a file edited to something unreadable returns 0 with a named error), and `save_set_version(n)` stores a whole number from 0 to 1000000, returns the version that was stored before the call and leaves it alone for anything else, so a game can branch on an old version, migrate its slots and then record the new one. A save whose magic names a newer format is reported as `the save needs a newer Anvil version` rather than as corrupt. C and wasm both store saves: the browser page uses IndexedDB (falling back to `localStorage` where it is unavailable, and migrating old `localStorage` saves once), so the ~5 MB quota is no longer a limit; `--backend native` raises a located "not available" diagnostic. |
| Random/noise | `seed(value)` statement; `rnd(low, high)`; `noise(x,y,z)`; `fbm(x,y,z,octaves,lacunarity,gain)` | Seeded pseudo-random values and 3D gradient/fractal noise. The same seed produces the same sequence on both backends. Noise coordinates must be finite and inside [-2147483648, 2147483647); `fbm` checks every octave, so a later scaled coordinate that leaves that interval stops with `Anvil noise coordinate range error`. |
| Text | `len(text)`; `upper(text)`; `lower(text)`; `trim(text)`; `left(text,n)`; `right(text,n)`; `char(text,n)`; `mid(text,start,count)`; `chr(n)`; `ord(text)`; `number(text)` | `len`, `char`, `ord` and `number` return numbers; the rest return text. `len` counts bytes, so `len("héllo")` is 6. `char` is 0-based and gives empty text past the end; `mid` clamps a negative start to 0 and a count past the end; `left`/`right` take text from either end; `trim` removes leading and trailing spaces. `chr(n)` gives the one-byte text for 1–255 and stops with `Anvil chr out of range` otherwise; `chr(0)` is empty text because Anvil text is zero-terminated, so `len(chr(0))` and `ord(chr(0))` are 0; `ord(text)` reads the first byte (0 for empty text); `number(text)` accepts optional surrounding spaces around a sign, digits, a fraction and an `e` exponent; the whole text must be a number, so a valid prefix followed by junk (`"12abc"`), a bare exponent marker (`"1e"`), hex (`"0x10"`), `inf`/`nan` and underscore grouping all read 0 instead of a truncated prefix, and a magnitude outside the finite binary64 range (for example `1e9999`) reads 0 as well. At most nine fraction digits are significant: further digits are ignored, so a long fraction cannot overflow. Text holds at most 255 bytes and stops with a clear error instead of truncating. |
| Text comparison | `contains(text, part)`; `starts_with(text, prefix)`; `ends_with(text, suffix)` | Return 1 or 0. `=`, `!=`, `<`, `<=`, `>`, `>=` also compare text with text, alphabetically. Comparing text with a number is a compile error. |
| Lists | `list name` statement; `add name value`; `count(name)`; `array(name,i)` | Growable numeric list declared at top level, holding up to 256 values. `add` appends, `count` reports the length, and `array(name,i)` reads a 0-based slot; a slot past the end stops with a clear bounds error. |
| Math | `floor(x)`; `ceil(x)`; `round(x)`; `sqrt(x)`; `sin(x)`; `cos(x)`; `tan(x)`; `abs(x)`; `min(a,b)`; `max(a,b)`; `%` operator | Double-precision math helpers. `round` sends halves away from zero, and `a % b` is the floating-point remainder with the sign of the left side. The C backend uses platform libm for `sin`, `cos` and `tan`; WASM uses freestanding helpers, checked against C through 1e20 radians. Above that documented WASM limit, angle reduction uses phase zero (`sin` and `tan` return 0; `cos` returns 1) because the freestanding implementation has no Payne–Hanek reduction table; C continues to use platform libm. The native backend refuses these functions with a located "not available" diagnostic. Invalid/non-finite results are rejected. |
| Ray backend | `ray_backend(name)`; `ray_backend_available(name)` | String-literal names. `"bvh"` is selectable; only the CPU BVH backend is implemented. Availability queries for `"dxr"` and `"embree"` return false. Failed selection leaves the active backend unchanged. |
| Ray resolution | `ray_resolution(step)` | C runtime integer step 1–8; returns the previous step, default 1. Larger values trace one ray per pixel block and fill the block. Invalid values return 0 without changing state. Not available in wasm. |
| Ray samples | `ray_samples(count)` | C runtime integer sample count 1–16; returns the previous count, default 1. Stratified samples average shaded color and hit coverage per pixel block. Invalid values return 0 without changing state. Not available in wasm. |
| Physics | `body_create(x,y,radius,mass)`; `body_create_box(x,y,width,height,mass)`; `physics_capacity(n)`; `body_destroy(handle)`; `body_active(handle)`; `body_x/y/vx/vy(handle)`; `body_set_velocity(handle,vx,vy)`; `body_force(handle,fx,fy)`; `body_restitution(handle,value)`; `body_friction(handle,value)`; `body_collision(a,b)`; `physics_gravity(x,y)`; `physics_step()` | Fixed-step 2D circle and axis-aligned box prototype; capacity 1–128; bounded bodies/velocities; restitution and Coulomb friction in [0,1]. Detailed solver contract and limits are in [the engine specification](ENGINE.md#fixed-step-2d-physics). |
| Network | `net host(port)`; `net join("IPv4",port)`; `net send(value)` statement; `receive()` | Experimental one-peer numeric UDP transport. Each datagram carries one 8-byte IEEE-754 double; datagrams of any other length and non-finite payloads (NaN, infinity) are ignored, and `receive()` keeps its previous value. `host`/`join` are top-level setup statements. It is not reliable, secure, or suitable for Internet games. |

## 6. Engine statements

Project/window setup statements are normally written at top level:

```ebnf
engine_statement = "scene", whitespace, ("2d" | "3d")
                 | "camera perspective", whitespace, camera_coordinate, whitespace, camera_coordinate, whitespace, camera_coordinate
                 | "camera fov(", expression, ")"
                 | "camera control(", expression, ",", expression, ")"
                 | "clear rgba(", expression, ",", expression, ",", expression, ",", expression, ")"
                 | "seed(", expression, ")"
                 | "net host(", INTEGER, ")"
                 | "net join(", STRING, ",", INTEGER, ")" ;
camera_coordinate = ? one whitespace-free expression token sequence accepted by the expression parser ? ;
```

`display` is a function-body statement. Supported primitives and argument counts are `rect(x,y,width,height)`, `circle(x,y,radius)`, `line(x1,y1,x2,y2[,thickness])`, `text(string)`, `cube(x,y,z,size)`, `sphere(x,y,z,radius)`, `ray_sphere(x,y,z,radius)`, and `plane(x,y,z,width,depth)`. A display command may add `-rgb(r,g,b)` or `-rgba(r,g,b,a)`; the default is opaque white. `display text(...)` requires `-l(x,y)` to provide its position. `-rotate(x,y,z)` supplies cube rotation. An integer suffix after a draw command is rejected because it has no effect; draw order follows source order. Dynamic text supports multiple numeric expressions after a literal prefix and uses the same six-fractional-digit, trailing-zero-trimmed number format as console output (`tests/test_number_format.py`, `tests/test_wasm.py`). On the C backend a text alpha below 255 blends the glyph coverage with the same per-pixel rule as the other primitives (`tests/test_text_alpha.py` measures the drawn result); the experimental native backend currently supports rectangles only and refuses text drawing before code generation.

`ray_sphere` submits a sphere to the per-frame CPU BVH ray tracer. The desktop C runtime supports up to 40 spheres per batch. The WebAssembly backend tessellates the primitive and caps its batch at 32. Hardware RTX/DXR and Embree are unavailable. Conventional 2D/3D primitives use the current fixed-size software renderer.

The runtime starts when the program has an `update` or `draw` callback, or top-level engine configuration. It calls `update` at the configured fixed rate and `draw` to render. In engine mode, top-level `call fn(...)` initializers run once after project setup and before the runtime loop. A `.ANVLproj` manifest may set `[engine].fixed_hz` from 1 through 240; default is 60. Without engine mode, a top-level `call fn(...)` invokes a function; absent explicit calls, a zero-argument `main` function is invoked and its numeric result is printed.

## 7. Static validation, runtime errors, and compilation

Before code generation, the compiler validates block structure, function/parameter uniqueness, known function names and arity, known global/local/array references, expression value kinds, array declarations and legacy C-symbol compatibility. Diagnostics default to a caret block under the source line; `--diagnostics editor` instead prints one `path:line:column: message` line per diagnostic, with a 1-based character column (a tab counts as one character) so editors and CI parsers can jump to the exact token. Unknown function and variable names add a `did you mean 'x'?` hint when exactly one declared name is within a small edit distance; names shorter than three characters are never corrected, and an ambiguous tie stays silent. The parser reports unsupported statements with source path and line. On the broader C backend, runtime array-index, division, non-finite-number, local-array allocation, and active-memory-budget errors include source path and line and exit with code 2. The experimental native subset's diagnostics are documented in its migration guide.

The default backend emits C and links `runtime/anvil_runtime.c` using Windows/MSVC for broader engine coverage. The experimental `--backend native` instead emits x64 machine code and a PE executable directly, including a limited buffered 2D rectangle/window runtime with fixed updates and keyboard input. Its current feature availability and diagnostics are listed in [the native migration guide](NATIVE_X64_COMPILER_MIGRATION.md); the broader engine/API descriptions above do not imply native-backend parity. Project manifests and their configurable update rate currently apply to the C backend; native scenes use 60 Hz. Generated C is not part of `.ANVL` syntax, and Rust output is not a target. Portable runtime, GPU rasterizer, DXR, Embree, 3D physics, wider string handling (Unicode casing, escapes beyond newline, tab, quote and backslash), structures, namespaced/separately compiled modules, audio, general asset import (beyond bounded uncompressed BMP sprites and compile-time glTF models), and reliable multiplayer remain unfinished. Text values with those four escapes, `&` joining, growable lists, and fixed-size arrays are implemented on both backends.

## 8. Conformance examples

The following is a complete numeric version-1 program:

```anv
language version 1
array values(3)

fn(sum, limit)
  set local(total) = 0
  for local(i) = 0 to var(limit) - 1
    set array(values, local(i)) = local(i) + 1
    add local(total) array(values, local(i))
  end
  output local(total)
end

fn(main)
  if call fn(sum, 3) == 6 and true
    output call fn(sum, 3)
  else
    output 0
  end
end

call fn(main)
```

For the reader-friendly guide and engine-specific examples, see [Language Guide](LANGUAGE.md), [Language Reference](Wiki/Language-Reference.md), and [Engine Guide](ENGINE.md).

Local multi-file source composition uses top-level `include "relative/library.ANVL"`. Both backends resolve the local include graph; the native backend compiles reachable functions and their runtime dependencies. See [include semantics and limits](INCLUDES.md). Namespaces, package registries and separate object linking remain unfinished.

Compiler resource validation bounds expressions to64 delimiter/parser levels and control-flow nesting to128 blocks before code generation. Both backends issue a source-located compile error above these limits; split complex code into variables and functions. String-literal parentheses are excluded from delimiter counting.

Native project builds accept `.ANVLproj` with `--backend native`. The existing `name` supplies the Unicode window title, `entry` resolves inside the project directory, and `[engine].fixed_hz` accepts integer rates1–240 (default60). Includes may span the project tree. Native graphical updates, `time()` and `delta()` use that rate. Direct source titles and console behavior retain their defaults. Unsupported native features fail explicitly without invoking C/Rust.

## Selective source functions

`include fn(move) - "lib/player.ANVL"` imports `move` with the filename qualifier; `call fn(move - player, 10)` invokes it. `as alias` overrides the qualifier. Helpers, globals and arrays are private to the canonical selectively imported module. Aliases/exports are local to the including file. Whole-file includes retain their shared namespace. See [include rules](INCLUDES.md) for dependency closure, initialization, diagnostics and limits.

## Version 2 additions

Version 2 retains the statements and expressions above, with these variable meanings and additions:

- `var(name)` is function-local state and may be used only in a function. `varl(name)` explicitly refers to global numeric state. `local(name)` remains supported. Version 1 keeps the global/parameter-shadowing meaning of `var(name)`.
- Top-level metadata uses `name "program name"`, `author("author name")`, and `version("version text")`. Each key can appear once. Values are quoted Unicode strings. The compiler embeds metadata in the executable; it is available through `--inspect-metadata`.
- `fnref(function)` produces an opaque callback handle assignable to a local or global variable. `call var(callback, args...)`, `call local(callback, args...)`, or `call varl(callback, args...)` invokes the stored target. Callback variables may also be copied or cleared with `null`. Targets assigned to one callback must agree on numeric arity; the initial callback lowering supports at most 15 numeric arguments. A callback cannot be passed or returned as a value, stored in an array, or used in numeric expressions. An unset callback fails at its call site.
- Selective imports and qualified calls accept the preferred double-dash form: `include fn(move) -- "lib/player.ANVL"` and `call fn(move -- player, 10)`. Existing single-dash forms remain accepted.
- Networking accepts `netip("IPv4")` (also `netIP`), `nethost(port) --local`, `nethost(port)`, and `netleave()`. `--local` binds loopback. Without it, the host binds the configured IPv4 address; the default `0.0.0.0` listens on all local interfaces. Firewall and router configuration determine external reachability.

The required build path is Anvil parsing and validation → generated C → the selected C compiler/linker → machine code and executable. The direct x64 backend is an optional experiment, not the required project architecture.
