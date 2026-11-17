# Forward-porting this branch onto GitHub `main`

Status: **not merged**. This branch (4 commits) and `origin/main` (73 commits) are
two parallel lineages of the same prototype, not a fast-forward. A trial merge
produced conflicts in 14 files (44 hunks); either side taken wholesale deletes
the other side's features. This page records the measured state so the port can
be planned instead of discovered again.

## What each side has

| Area | This branch | `origin/main` |
| --- | --- | --- |
| `say` / `write` / text builtins (`len`, `upper`, `mid`, `trim`, …) | **yes** | **no** |
| Text function parameters and text returns | **yes** (this branch) | no |
| Growable lists (`list`, `add`, `count`) | **yes** | no |
| `break` / `continue` | **yes** | no |
| Reachability filtering in the C backend | **yes** | no |
| REPL with persistent block state | **yes** | partial |
| Selective imports (`include fn(x) - "f" as y`) | no | **yes** |
| Image module (`runtime/anvil_image.c`) | no | **yes** |
| Network packet/config modules | no | **yes** |
| Modular compiler (`callables.py`, `module_loader.py`, `native_*.py`, `program_metadata.py`, `runtime_modules.py`, `display_syntax.py`) | no (monolithic files) | **yes** |
| Windows file icons (`assets/icons/…`) | no | **yes** |

The architecture difference is the real blocker: `main` split the compiler into
modules, while every language feature here lives in `compiler/codegen.py`,
`compiler/expressions.py` and `compiler/native_codegen.py`. A merge has to
re-express this branch's features inside `main`'s modules; rebasing cannot do it.

## Conflict map from the trial merge

- `compiler/native_codegen.py` — 15 hunks
- `compiler/codegen.py` — 8 hunks
- `compiler/expressions.py`, `compiler/parser.py` — 6 hunks
- `runtime/anvil_runtime.c` — main deleted 723 lines this branch depends on
  (text buffer pool, `anvil_str_cat`, list helpers)
- `docs/*`, `tests/*` — the rest

## Suggested order (if the port is scheduled)

1. Take `main`'s module split as the base.
2. Port the text layer (`say`/`write`, builtin registry, `ANVIL_TEXT_BUFFERS`)
   into `native_text.py` + `runtime/anvil_runtime.c`.
3. Port lists, `break`/`continue` and reachability.
4. Port text parameters last: the classifier (`semantics.py`) has to land in
   `main`'s `callables.py`/`program_metadata.py` split, and the native join
   buffer preservation goes into `native_codegen.py`.
5. Only then port selective imports and the image/network modules back — they
   are `main`-only, so they can also stay unported if this branch becomes the
   base instead.

Nothing in this repository depends on the merge: this branch builds, passes its
suite, and its examples run on both backends.
