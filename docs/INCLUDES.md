# Anvil source includes

Use a top-level directive to compose local Anvil source libraries:

```anvl
include "lib/numbers.ANVL"
fn(main)
  output call fn(scale-value, 7, 3)
end
```

Both the C and direct native backends accept includes. `examples/include_demo.ANVL` demonstrates nested and repeated includes and prints 20:

```powershell
python -m compiler.anvil examples/include_demo.ANVL --backend native --output build/include_demo.exe
./build/include_demo.exe
```

An include path is a quoted JSON-style string, relative to the including file. Use forward slashes for portable paths. The extension must be `.ANVL` (case-insensitive); absolute paths, drive-relative paths and control characters are rejected. Includes are permitted only at top level. No network access or package download occurs.

For a direct source build, all resolved includes must stay inside the entry file's directory tree. For a C-backed `.ANVLproj` build, they may use the manifest's whole project tree, including sibling libraries of a nested entry. Resolving a symlink or `..` outside that root is rejected. Native project manifests remain unsupported.

The compiler resolves each canonical file once. Repeated and diamond includes therefore neither duplicate definitions nor rerun initializers. Top-level statements are expanded depth-first at the include's position; their existing backend restrictions still apply. Native console programs currently accept top-level seed configuration and an explicit main call; native graphical setup supports numeric initialization and helper calls. Included library initialization is ordinary Anvil code, not an automatic plugin loader.

Functions, globals and global arrays share one program namespace across included files. Forward references between files work. Duplicate functions and arrays diagnose both source locations. Undefined references, expression errors, and native numeric/index diagnostics retain original filenames and physical line numbers. Numeric native runtime diagnostics are pooled UTF-8 data, so long or non-ASCII source paths do not require fixed-size stack text buffers. This does not add general runtime string values to the language.

The graph is bounded to 256 distinct files, 64 nested files and 4 MiB of aggregate UTF-8 source. Cycles report their chain and include site. Missing files, invalid UTF-8, invalid directives and exceeded limits are compile errors. Each file may declare the supported language version before its own other source code. `parse_syntax` remains a pure syntax phase; `parse` resolves the graph and validates the merged program.

The native backend compiles functions reachable from the console entry, graphical draw/update callbacks and top-level calls/expressions. Recursive calls are followed. The analysis conservatively considers calls in all branches; it does not perform statement-level constant folding. Unused functions are omitted, including input imports and runtime helpers they alone would request. Parsing and common semantic validation still apply to all included code; backend-specific unsupported operations in unreachable functions do not get emitted. All declared global storage and top-level initializers remain present because initialization may have observable effects. C output retains all functions and preserves the existing broader runtime build path.

This is source composition and native function selection. Namespaced modules, public/private exports, separately compiled object files, package registries, versioned package resolution, binary plugins, resource packaging and Forge artifacts remain future work. The master backlog is only in GitHub issue #23 and its comments.

Extension package 0.1.10 adds tested include highlighting. Installed extension 0.1.4 remains unchanged per user preference; new highlighting has not been visually verified in that installed editor.

## Compiler depth limits and troubleshooting

The follow-up for issue #65 bounds expression delimiter nesting and recursive expression parser/emitter work to64 levels, including across nested function/array argument parsing. Quoted parentheses do not count as delimiters. Recursive statement code generation is protected by a128-block semantic limit. Split deeply nested expressions into intermediate variables and nested blocks into helper functions. These are compiler resource limits, not claims that the OS/type/runtime goals are complete.

A missing file or boundary error reports the include site; duplicate definitions name both declarations. A syntax/expression/configuration error should name the original physical file and line. Use an `.ANVLproj` project root for C builds whose entry lives below sibling library directories; direct source builds use the entry directory as the boundary. Package downloads, version solving and external plugin binaries are not performed.

The edfbe86 review found configuration provenance and deep-expression failures (#64/#65); the fixes and new CLI regressions are pending independent review. Its125-test count and71/100 score apply to that prior snapshot.
