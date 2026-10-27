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
global_assignment = "set var(", IDENT, ") =", expression ;
cleanup_statement = "set var(", IDENT, ") = null" ;
line_end         = physical_newline | end_of_file ;
```

There must be at least one function. Function definitions are top-level and function names must be unique. Parameter names within a function must be unique. Functions can be declared in any order and may call themselves recursively. The compiler generates a numeric function prototype for every function before generating its body.

At most one `language version N` line may occur, and it must precede all source code; blank lines and comments may precede it. Only version 1 is supported. Malformed, repeated, misplaced, and unsupported declarations produce a source path and line diagnostic. Existing files without a declaration are interpreted as version 1.

Scalar globals are introduced by `set var(name) = expression`. Globals begin at zero. A global fixed-size numeric array is declared at top level as `array name(size)`; its elements begin at zero and `size` must be from 1 through 1,048,576.

## 3. Statements

Every statement below occupies a single source line, except that a block statement owns the following lines up to its matching `end`.

```ebnf
statement        = assignment | cleanup_statement | accumulation | array_write | function_call_statement | net_send_statement
                 | return_statement | if_statement | while_statement
                 | for_statement | engine_statement | display_statement ;
assignment       = "set var(", IDENT, ") =", expression
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
At most one `-l(x,y)` and one `-rotate(x,y,z)` modifier may appear on a display command; a repeated location or rotation modifier is invalid. Multiple `-rgb`/`-rgba` modifiers are accepted by the current compiler, and the first color modifier supplies the color while later color modifiers are ignored. The optional legacy integer suffix may appear before or after style modifiers, but at most one suffix is accepted.

The statements that may appear at file top level are limited to global `set var`, global array declarations, engine/project setup statements, `seed(expression)`, and `call fn(...)`. `add`, `sub`, `output`, local declarations, array writes, display commands, `if`, `while`, and `for` belong inside a function. Although the parser can form a top-level branch node, top-level control-flow blocks are rejected by C emission; they are not part of the accepted language.

The compatibility form `set var(name) = null` is accepted as a no-op (it neither clears nor changes the numeric variable). It remains in older examples as cleanup syntax; Anvil has no nullable scalar values.

### 3.1 Function locals and returns

`set local(name) = expression` declares function-local numeric state and initializes it to zero at function entry. Its assignment then sets the given value. `local(name)` reads the local. `add local(name) amount` and `sub local(name) amount` update it. Local state is function-scoped, not block-scoped. A local cannot use a parameter's name.

A function parameter is numeric. `var(name)` inside a function resolves to a same-named parameter when one exists; otherwise it refers to global numeric state. Writing `set/add/sub var(name)` follows the same parameter rule. Function locals do not shadow globals accessed with `var(name)`.

`output expression` returns one number from the current function. A function that reaches its end without returning yields `0`. There are no declared return types, multiple return values, or structured return statements. `fn(update)` and `fn(draw)` are optional engine callbacks and must have no parameters.

### 3.2 Arrays

`array(name, index)` reads a numeric element. `set array(name, index) = expression` writes an element and is only valid in a function. Indexes are zero-based finite whole numbers in `[0, size)`. Invalid indexes terminate execution with a path-and-line diagnostic and exit code 2.

An array may be global or local to a function. Arrays cannot be resized. A function may declare at most 8,192 local array elements in total; active local-array storage across recursive calls is capped at 16 MiB. Local arrays are zero-initialized, allocated per invocation, and freed on every generated return. Allocation failure or budget exhaustion is a source-located runtime error. Each global array has a maximum size of 1,048,576 elements.

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
                 | "image_draw" | "image_draw_scaled" | "receive" | "body_create" | "body_create_box" | "body_destroy"
                 | "body_active" | "body_x" | "body_y" | "body_vx" | "body_vy"
                 | "body_set_velocity" | "body_force" | "body_restitution" | "body_friction"
                 | "body_collision" | "physics_capacity" | "physics_gravity" | "physics_step"
                 | "ray_backend" | "ray_backend_available" ;
key_name         = "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "I" | "J"
                 | "K" | "L" | "M" | "N" | "O" | "P" | "Q" | "R" | "S" | "T"
                 | "U" | "V" | "W" | "X" | "Y" | "Z" | "SPACE" | "UP" | "DOWN"
                 | "LEFT" | "RIGHT" | "ENTER" | "ESCAPE" ;
```

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

An expression must have the expected value kind. Most operators, variables, arrays, and function results are numeric. String literals are accepted only in string-taking built-ins and drawing text. The ray-backend functions require a string literal; mouse button functions require one of the string literals `"left"`, `"right"`, or `"middle"` at runtime. `image_load` accepts a path string literal. `net join` accepts a literal address. Drawing text accepts a string literal; the current dynamic form is a string literal followed by `+ var(name)`, formatted as a whole number. This limited form does not create a general string value.

Division by zero, including negative zero, is a runtime error with source path and line and exit code 2. Every numeric operation and numeric built-in result must be finite; NaN or infinity (including overflow and invalid math results) produces a source-located runtime error. Numeric values use the C backend's `double` representation; there are no integer, decimal, or user-defined numeric types in version 1.

## 5. Built-ins

All built-ins return a numeric result unless otherwise stated. Calls use parentheses and comma-separated arguments.

| Group | Function signatures | Meaning and limits |
|---|---|---|
| Clock/input | `time()`; `delta()`; `pressed(key)`; `held(key)`; `mouse_x()`; `mouse_y()`; `mouse_pressed(button)`; `mouse_held(button)`; `mouse_wheel()` | Runtime time, fixed-step delta, keyboard state, mouse position/button state, and wheel delta. Keys include the symbolic tokens `A`–`Z`, `SPACE`, arrows, `ENTER`, and `ESCAPE`; key inputs are numeric values and may also be supplied as numeric virtual-key codes. Mouse buttons are string literals `"left"`, `"right"`, or `"middle"`. Position is in fixed 960×600 virtual framebuffer pixels, with `-1` returned in letterbox bars or outside the window. Pressed state and wheel delta last through the next fixed update; held state ends on release or window focus loss. |
| 2D image assets | `image_load(path)`; `image_width(handle)`; `image_height(handle)`; `image_draw(handle,x,y)`; `image_draw_scaled(handle,x,y,width,height)`; `image_destroy(handle)` | `image_load` accepts uncompressed 24-bit/32-bit BMP paths relative to process working directory. It returns a positive generational handle or `0` on failure; the first allocations use handles 1–64, and reusing a released slot gets a new value so stale handles stay invalid. A 32-bit file with all alpha bytes clear is treated as opaque. Decoded image limits are 8,192 pixels per side, 16,777,216 pixels per image, and 128 MiB total. Draw operations alpha-blend with nearest-neighbor scaling and clip to the fixed 960×600 framebuffer. Width/height on an invalid handle return 0; draw/destroy return 1 for valid requests and 0 otherwise. Remaining handles are released when the game closes. |
| Random/noise | `seed(value)` statement; `rnd(low, high)`; `noise(x,y,z)`; `fbm(x,y,z,octaves,lacunarity,gain)` | Seeded pseudo-random values and 3D gradient/fractal noise. |
| Math | `floor(x)`; `ceil(x)`; `sqrt(x)`; `sin(x)`; `cos(x)`; `abs(x)`; `min(a,b)`; `max(a,b)` | Double-precision math helpers. Invalid/non-finite results are rejected. |
| Ray backend | `ray_backend(name)`; `ray_backend_available(name)` | String-literal names. `"bvh"` is selectable; only the CPU BVH backend is implemented. Availability queries for `"dxr"` and `"embree"` return false. Failed selection leaves the active backend unchanged. |
| Physics | `body_create(x,y,radius,mass)`; `body_create_box(x,y,width,height,mass)`; `physics_capacity(n)`; `body_destroy(handle)`; `body_active(handle)`; `body_x/y/vx/vy(handle)`; `body_set_velocity(handle,vx,vy)`; `body_force(handle,fx,fy)`; `body_restitution(handle,value)`; `body_friction(handle,value)`; `body_collision(a,b)`; `physics_gravity(x,y)`; `physics_step()` | Fixed-step 2D circle and axis-aligned box prototype; capacity 1–128; bounded bodies/velocities; restitution and Coulomb friction in [0,1]. Detailed solver contract and limits are in [the engine specification](ENGINE.md#fixed-step-2d-physics). |
| Network | `net host(port)`; `net join("IPv4",port)`; `net send(value)` statement; `receive()` | Experimental one-peer numeric UDP transport. `host`/`join` are top-level setup statements. It is not reliable, secure, or suitable for Internet games. |

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

`display` is a function-body statement. Supported primitives and argument counts are `rect(x,y,width,height)`, `circle(x,y,radius)`, `line(x1,y1,x2,y2[,thickness])`, `text(string)`, `cube(x,y,z,size)`, `sphere(x,y,z,radius)`, `ray_sphere(x,y,z,radius)`, and `plane(x,y,z,width,depth)`. A display command may add `-rgb(r,g,b)` or `-rgba(r,g,b,a)`; the default is opaque white. `display text(...)` requires `-l(x,y)` to provide its position. `-rotate(x,y,z)` supplies cube rotation. One optional integer suffix is accepted after the draw call, before or after style modifiers; it is retained as legacy syntax and has no documented semantic effect.

`ray_sphere` submits a sphere to the per-frame CPU BVH ray tracer. The current batch supports at most 32 ray-traced spheres. Hardware RTX/DXR and Embree are unavailable. Conventional 2D/3D primitives use the current fixed-size software renderer.

The native runtime starts when the program has an `update` or `draw` callback, or top-level engine configuration. It calls `update` at the configured fixed rate and `draw` to render. A `.ANVLproj` manifest may set `[engine].fixed_hz` from 1 through 240; default is 60. Without engine mode, a top-level `call fn(...)` invokes a function; absent explicit calls, a zero-argument `main` function is invoked and its numeric result is printed.

## 7. Static validation, runtime errors, and compilation

Before C generation, the compiler validates block structure, function/parameter uniqueness, known function names and arity, known global/local/array references, expression value kinds, array declarations and C-symbol collisions. The parser reports unsupported statements with source path and line. Runtime array-index, division, non-finite-number, local-array allocation, and active-memory-budget errors also include source path and line and exit with code 2.

The compiler emits ordinary C and links `runtime/anvil_runtime.c`; the current supported executable target is Windows/MSVC. Generated C is an implementation detail, not part of `.ANVL` syntax. A Rust backend, portable runtime, GPU rasterizer, DXR, Embree, 3D physics, general strings, structures, modules, dynamic arrays, audio, general asset import (beyond bounded uncompressed BMP sprites), and reliable multiplayer are outside version 1.

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
