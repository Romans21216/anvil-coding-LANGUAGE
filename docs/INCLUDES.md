# Anvil source includes

Anvil supports whole-file includes and selective function imports on both the C and direct native backends. Paths are quoted JSON-style strings relative to the including file; no package download or network access occurs.

## Import a function

```anvl
include fn(move) - "lib/player.ANVL"
fn(main)
  output call fn(move - player, 10)
end
```

The qualifier defaults to the filename without `.ANVL`. The library defines the ordinary `fn(move, distance)`. Inside it, unqualified calls resolve to its own helper functions, including recursive calls. Those helpers are compiled automatically as dependencies. Other files may define their own `move` and helper functions without collisions.

Only functions named by selective directives can be called through that qualifier. Add another directive to expose another function. A module's global variables and global arrays are private; function parameters, locals and local arrays retain their normal rules. A selected `draw`, `update` or `main` is private too: it does not register an entry callback. Call it explicitly from the entry's callback if needed.

Use aliases to distinguish files with the same name:

```anvl
include fn(move) - "input/player.ANVL" as input
include fn(move) - "simulation/player.ANVL" as simulation
fn(main)
  output call fn(move - input, call fn(move - simulation, 10))
end
```

Aliases and exported names are local to the file containing the include. Two different source files may use the same alias for different libraries. In one file, an alias must refer to one canonical module. Filenames such as `player.v2.ANVL` require an explicit identifier alias. Spaces around the qualifier dash are required: `move-player` remains a single ordinary function name, while `move - player` is qualified.

A canonical selectively imported module shares one state instance and runs its initializers once, even through multiple aliases. Modules can use whole-file includes for private helpers or selective imports for dependencies. Top-level statements expand depth-first at the first include position. Selective libraries allow numeric assignments, addition/subtraction, calls and seed configuration; engine configuration belongs in the entry or a whole-file include. Each backend's existing initialization restrictions still apply. Native console setup remains narrower than graphical setup.

Selected functions and their transitive helper functions are retained; other functions in that selective module are omitted on both backends. The compiler parses the entire source for syntax errors, but does not validate semantic references in omitted functions. All declared module globals, arrays and top-level initializers remain present because initialization can have observable effects. This is function-level selection, without statement-level constant folding or separately compiled linking.

Run `examples/selective_include_demo.ANVL` on either backend; it prints 50:

```powershell
python -m compiler.anvil examples/selective_include_demo.ANVL --backend native --output build/selective.exe
./build/selective.exe
```

## Include a whole file

```anvl
include "lib/numbers.ANVL"
fn(main)
  output call fn(scale-value, 7, 3)
end
```

Whole-file includes preserve the shared namespace for functions, globals and arrays. Repeated or diamond includes within that namespace merge a canonical file once. Duplicate functions/arrays still report both declarations. A whole-file include inside a selective module merges into that module's private namespace. Importing the same physical source both whole-file and selectively creates separate state instances; repeated aliases of the selective module share one instance.

`examples/include_demo.ANVL` demonstrates nested/repeated whole-file includes and prints 20. The native backend additionally omits functions unreachable from `main`, graphical callbacks and top-level calls; recursive and conditional calls are followed conservatively. Common semantic validation still applies to every function in the whole-file namespace. C retains that namespace's functions.

## Boundaries, diagnostics and limits

Includes are top-level only and require relative `.ANVL` paths (case-insensitive). Absolute, drive-relative, rooted-without-drive and control-character paths are rejected. For direct source builds, resolved includes must remain inside the entry's directory tree. For `.ANVLproj` builds on either backend, they may span the manifest's project tree. A symlink or `..` resolving outside the root is rejected.

The graph allows 256 file instances, 64 nested files and 4 MiB each of physical UTF-8 source and expanded source. A source merged into multiple private namespaces consumes an instance and expanded bytes for each namespace; aliases reusing the same module do not. Cycles report their chain and include site. Invalid UTF-8, missing files, invalid directives and exceeded limits are compile errors. Each file may declare the supported language version first. `parse_syntax` reads no includes; `parse` resolves the graph and validates bindings. Identifier prefix `_anvil_include` is compiler-owned (including names that sanitize to that prefix).

Unknown qualifiers, unexported functions, arity errors and selected source errors retain the original physical filename and line. Native numeric/index runtime errors use pooled UTF-8 source paths, including Unicode paths. The transitional MSVC route explicitly uses UTF-8 source/execution encoding so its diagnostics retain those paths too (#81). General runtime string values are still absent.

Expression nesting is limited to 64 levels and statement nesting to 128 blocks. Split deeper expressions into intermediate variables and blocks into helper functions. A missing file/boundary error names the include site; source errors name the original file. Native project manifests accept a Unicode `name`, an `entry` inside the project and `[engine].fixed_hz` from 1–240 (default 60). Native updates, `time()` and `delta()` share that configured rate. Unsupported native features fail explicitly without C/Rust fallback.

Extension package 0.1.12 includes automated TextMate checks for selectors and qualified calls. Installed 0.1.4 is preserved; new tokens have not been visibly verified in that installed editor. Versioned package resolution, registries, separately compiled objects, binary plugins, resource packaging and Forge artifacts remain future work. Full requirements remain exclusively in GitHub issue #23 and its comments; current independent evaluation evidence is in [QA_REPORT.md](QA_REPORT.md).
