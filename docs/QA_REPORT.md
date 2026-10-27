# Anvil QA Report

**Review date:** 2026-10-27
**Source format:** `.ANVL`
**Latest completed independent full review:** **87/100 — FAIL** (commit `f96a212`; threshold: 90/100)
**Review snapshot:** the table below records the independent review of `f96a212`, which found uncontrolled process stack exhaustion for valid recursion with large local arrays. The current worktree switches local arrays to checked heap allocation with guaranteed return cleanup and a 16 MiB active-allocation cap; its 43-test suite passes, but that fix has not yet been independently rescored.

## Scope

Anvil is an early Windows-focused language and game-runtime prototype. The compiler validates BASIC/Lua-inspired `.ANVL` programs, emits C, and invokes MSVC to create a native `.exe`. The runtime provides fixed-size software 2D/3D drawing, keyboard camera controls, fixed-step updates, seeded random/noise functions, minimal numeric UDP, and the built-in `ray_sphere(x,y,z,radius)`. The ray sphere uses CPU BVH traversal, diffuse/specular lighting, and hard-shadow queries, with a documented 32-sphere per-batch limit. The compiler supports fixed-size global and function-local numeric arrays; each function call is capped at 8,192 local elements, with a 16 MiB active-allocation budget across calls.

This is not a production engine. Assets, audio, physics, cross-platform support, a Rust backend, GPU rendering, RTX/DXR, and Embree remain unimplemented. Functions support numeric parameters, return values, recursion, function-local numeric state and arrays, `while` loops, inclusive numeric `for` loops, and fixed-size global numeric arrays with checked indexing. Structures and modules/imports remain unsupported. The `.ANVL` extension is the user's selected suffix.

## Verification

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | PASS — 43 tests, including function-local arrays, recursive allocation-budget failure, cleanup, and bounds |
| `npm test --prefix vscode-extension` | PASS — manifest/config and representative TextMate token scopes |
| MSVC release build of `game.ANVLproj` | PASS |
| MSVC release build/run of `examples/functions.ANVL` | PASS — output `13` |
| Nested `while` inside `if/else` and another `while` | PASS — independent build/run output `13` |
| New `examples/loops.ANVL` sample | PASS — MSVC release build and execution output `15` |
| Native runtime integration | PASS — fixed-step updates, delta, queued Space edge, and clean shutdown covered |
| Projected sphere bounds regression | PASS — production projection helper sampled centered, off-axis, and near-camera sphere surfaces |
| `examples/local_arrays.ANVL` | PASS — MSVC release build; output `27`; generated C unchanged on repeat build |
| Recursive maximum-size local arrays | PASS — controlled source-line diagnostic at the 16 MiB allocation budget, rather than process stack overflow |
| VS Code extension installation | PASS — VS Code 1.143.1 lists `anvil-engine.anvil-language-support@0.1.2` after installing the project VSIX |
| VS Code package registration | PASS — 0.1.2 package declares language ID `anvil`, `.ANVL`/`.anvl`, and grammar `vscode-extension/syntaxes/anvil.tmLanguage.json` |
| Visible VS Code language mode/sample colors | PASS — VS Code status bar shows Anvil for `examples/arrays.ANVL`; the open sample visibly highlights array declarations, indexing, function syntax, keywords, and numbers. |
| Live game window in latest review | NOT INSPECTED |

These checks verify the prototype workflows and selected regression cases. They do not establish production readiness, cross-platform behavior, or performance.

## Independent 50-criterion review

The latest independent review of commit `f96a212` scored **87/100 (87%) — FAIL**. All 42 tests, the extension check, Python compilation, and local-array example passed, but an evaluator reproduced a Windows stack overflow (0xC00000FD) at recursion depth 20 when each valid function call declared an 8,192-element local array. The source respected the documented per-function limit; the implementation nevertheless exhausted the native stack without an Anvil diagnostic. This is tracked with exact steps in issue #21. The current changes replace stack arrays with checked heap allocations, free local arrays on return, and enforce a 16 MiB total active-call budget; 43 tests now pass, including a stress test that verifies a source-line error instead of stack overflow. The fix is committed after local verification; independent rescore is pending. Other findings remain compiler density (22: 1), module boundaries (23: 1), Windows/C backend portability (27: 1), and incomplete engine scope (2, 3, 5, 9, 40, 50). Issues #19 and #20 are resolved.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Compiler, runtime, language, extension, and documentation requirements are identified. |
| 2 | Implicit requirements addressed | 1 | The broad game-engine backlog is only partly implemented; planned systems remain. |
| 3 | Functionality matches intended goal | 1 | Working Windows prototype, but not the requested full engine. |
| 4 | Required deliverables present | 2 | Repository includes compiler, runtime, docs, examples, tests, and VS Code extension. |
| 5 | No essential feature missing | 1 | GPU renderer, assets, audio, physics, and broader multiplayer remain unfinished. |
| 6 | Stated constraints respected | 2 | `.ANVL` is consistently used as requested. |
| 7 | Ambiguity resolved logically | 2 | Current C/MSVC prototype scope and limitations are documented. |
| 8 | Behavior matches documentation | 2 | Latest review found language/compiler/engine guides aligned after fixes. |
| 9 | Important use cases supported | 1 | Simple native 2D/3D demonstrations work; broader engine use cases are missing. |
| 10 | Usable for intended purpose | 2 | Usable for small learning and prototyping scenes. |
| 11 | Core functionality works | 2 | Compiler, native runtime, camera, rendering, and CPU BVH ray spheres build. |
| 12 | Secondary functionality works | 2 | Timing, input, math/noise, networking primitive, and native-tested `while`/`for` loops are covered. |
| 13 | Primary workflows functional | 2 | Direct source and manifest build/run workflows pass. |
| 14 | Inputs validated | 2 | Syntax, arity, references, manifest fields, paths, rates, and ports are checked. |
| 15 | Errors handled gracefully | 1 | On f96a212, recursive maximum-size local arrays exhausted the OS stack without an Anvil error; the current unscored worktree replaces them with checked heap storage and a source-located 16 MiB budget error. |
| 16 | Edge cases covered | 1 | The f96a212 tests missed cumulative recursion stack use; current worktree adds budget-exhaustion coverage, pending independent review. |
| 17 | Invalid inputs controlled | 2 | Malformed inputs are rejected before generating/building C. |
| 18 | Stable across repeated operations | 2 | Compiler/runtime tests and repeatable random/noise checks pass. |
| 19 | No known critical defects | 1 | The f96a212 evaluator reproduced stack exhaustion for valid recursive local arrays; current heap-budget fix is not yet independently verified. |
| 20 | Components integrate | 2 | Compiler, generated C, runtime, manifest, extension, and networking sample integrate. |
| 21 | Logical project structure | 2 | Compiler, runtime, examples, tests, docs, and extension are organized. |
| 22 | Readable and consistently formatted | 1 | Compiler remains densely formatted; reformatting is still recommended. |
| 23 | Clear module responsibilities | 1 | Parsing, validation, C generation, and build orchestration remain concentrated in `compiler/anvil.py`. |
| 24 | Consistent descriptive naming | 2 | Anvil identity and `.ANVL` naming are consistent. |
| 25 | Duplication minimized | 2 | Reviewer found no material duplicate/unused code issue. |
| 26 | Dependencies appropriate | 2 | Core compiler uses Python standard library and the documented native toolchain. |
| 27 | Supports future extensions | 1 | Current runtime/backend is Windows/MSVC and C-only. |
| 28 | No unfinished placeholders | 2 | Unsupported capabilities are described as future work. |
| 29 | Configuration understandable | 2 | TOML project settings are explicit and validated. |
| 30 | Conventions followed | 2 | Current Python, C, TOML, and extension conventions are adequate. |
| 31 | Automated tests provided | 2 | At the f96a212 review snapshot, 42 Python tests covered global and function-local numeric arrays. The current suite has 43 tests after adding the recursive memory-budget regression. |
| 32 | Core tests covered | 2 | Compiler, runtime, networking, projection, and generated executable paths are covered. |
| 33 | Failure scenarios tested | 2 | Invalid syntax, references, manifests, settings, and paths have regression tests. |
| 34 | Edge cases explicitly tested | 1 | The f96a212 suite lacked recursive allocation exhaustion coverage; a budget regression test now exists in the current worktree. |
| 35 | Integration behavior tested | 2 | Native runtime and compiler-to-executable flows are exercised. |
| 36 | Documented test commands work | 2 | Documented Python and npm checks pass. |
| 37 | Builds and compilation pass | 2 | MSVC builds pass for manifest and function samples. |
| 38 | Results recorded accurately | 2 | The previous 87-point review's row/category mismatch is corrected; the f96a212 review used the 42-test count, and the latest local verification records 43 tests. |
| 39 | Regression checks performed | 2 | The full 42-test f96a212 suite passed; the current 43-test suite also passes after the memory-budget fix. |
| 40 | Verified against original goal | 1 | Tests verify the prototype, not the full requested engine breadth. |
| 41 | Installation instructions accurate | 2 | Python, MSVC, and VSIX workflows are documented. |
| 42 | Setup reproducible | 2 | Compiler, runtime, and extension checks have repeatable commands. |
| 43 | Usage understandable | 2 | Guides and examples explain the supported syntax and build path. |
| 44 | Design decisions documented | 2 | Runtime, compiler backend, renderer, ray tracing, and networking limits are described. |
| 45 | Troubleshooting available | 2 | README and compiler guide provide setup/troubleshooting information. |
| 46 | Opens in intended environment | 2 | VS Code reports extension 0.1.2 installed, has `examples/arrays.ANVL` open, and its accessibility tree reports Anvil language mode; earlier screenshot recorded visible highlighting. |
| 47 | Editor integration works | 2 | Extension 0.1.2 is installed; grammar tests pass and issue #13 records the visual highlighting check. |
| 48 | Deliverables organized | 2 | The array generated C file is tracked; all six tracked generated C hashes remained unchanged through the full test suite, and the worktree stayed clean. |
| 49 | Limitations and assumptions disclosed | 2 | Prototype scope, Windows/MSVC backend, ray trace cap, and network limits are stated. |
| 50 | Practical for stated scope | 1 | Suitable for educational demos, not production game development. |
| | **Requirement fulfillment** | **16/20** | |
| | **Functionality and reliability** | **17/20** | |
| | **Code quality and architecture** | **17/20** | |
| | **Testing and verification** | **18/20** | |
| | **Developer experience and delivery** | **19/20** | |
| | **Total** | **87/100 — FAIL** | |

### Priorities from the review

1. Continue the game-engine backlog: GPU rendering, assets, audio, physics, richer data structures, robust networking, benchmarks, and portability.
2. Split and format the compiler into clear parser, validation, C generation, and build modules.
3. Keep evaluation scores and verification results synchronized with every fresh review.

## Bug tracking

Issues [#1](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/1)–[#4](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/4) track earlier corrected report defects and are closed. The detailed findings from the array review are recorded in [#16](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/16) (QA record synchronization), [#17](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/17) (finding classification), [#18](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/18) (tracked generated C), [#19](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/19) (test output side effects), and [#20](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/20) (evaluation arithmetic); those fixes are closed. Issue [#13](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/13) records verified installation and highlighting for extension 0.1.2. The latest reproduced stack-exhaustion finding is documented in open issue [#21](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/21); its fix and fresh score are pending independent verification. Broader implementation gaps remain open in [#5 GPU and ray-tracing backends](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/5), [#6 asset pipeline](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/6), [#7 audio](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/7), [#8 physics](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/8), [#9 remaining array forms/structures/modules](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/9), [#10 multiplayer](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/10), [#11 portability and Rust backend](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/11), [#12 compiler readability and modularity](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/12), [#14 performance benchmarks](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/14), and [#15 completion matrix/full-scope tracking](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/15).

