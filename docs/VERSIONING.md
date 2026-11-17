# Versioning and stability policy

Anvil source files may begin with one optional declaration:

```anv
language version 1
```

Version 1 is the current language. Files without the line are treated as
version 1, so existing programs keep building.

## What "version 1" promises

Stable syntax and behaviour — a program that compiles today keeps compiling and
keeps producing the same output on the same backend:

- `fn(name, params...)` definitions, `call fn(...)`, `output`, recursion
- `set`/`add`/`sub` on `var(name)`, `set local(name)`, `local(name)`
- `if`/`elif`/`else`, `while`, `for local(i) = a to b [step s]`, `repeat`,
  `stop`, `break`, `continue`
- Fixed-size arrays (`array name(size)`, `array(name, i)`, `set array(...)`)
- Growable lists (`list name`, `add`, `count`, `array(name, i)`)
- Text literals with the four escapes, `&` joining, text comparison, and the
  documented text builtins
- `say`, `write`, `ask`, `press enter`, `wait`, top-level calls and top-level
  `set`/`seed` initialisation
- Numbers: six fractional digits, trailing zeros trimmed, no exponent notation
- Diagnostics: `path:line: message` with a caret, compile errors exit 1,
  runtime errors exit 2

**Additive changes stay in version 1.** New builtins, new statements, better
error messages and new optimisations (such as removing unreachable functions)
do not change the meaning of an existing program, so they ship without a version
bump.

## What is experimental

These may change shape or disappear without a version bump:

- the `--backend native` compiler (its supported subset grows; see
  [BACKENDS.md](BACKENDS.md))
- the 2D engine, physics, images, ray tracing and networking APIs
- the REPL's presentation (not the language it runs)
- anything under `runtime/native/`

Experimental features are always marked in [LANGUAGE_SPEC.md](LANGUAGE_SPEC.md),
the [migration guide](NATIVE_X64_COMPILER_MIGRATION.md), or the README.

## How breaking changes happen

A change that would alter the meaning of an existing version-1 program is a new
language version (`language version 2`). Version 1 files keep their old meaning;
a file opts in by declaring the new version. There is no version 2 yet.

## Compatibility tests

`tests/test_tutorial.py` compiles and runs every lesson in `docs/TUTORIAL.md`,
and `scripts/differential_probe.py` runs 100+ programs on both backends and
diffs their output. Both run on every change, so a compatibility break shows up
as a failing test rather than a surprise for users.
