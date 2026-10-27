# Anvil QA Report

**Review date:** 2026-10-27
**Source format:** `.ANVL`
**Latest completed independent full review:** **91/100 — PASS** (commit `64a4101`; threshold: 90/100).
**Review snapshot:** the independent reviewer evaluated commit `64a4101`, reran all 46 Python tests and extension validation, and scored 91/100. The prior 88/100 result was corrected from 89 after checking the category arithmetic; it describes the pre-synchronization working tree based on `b00f35a` and is retained as historical evidence. The older 91/100 review of `8f82f1c` applies only to that revision.

## Scope

Anvil is an early Windows-focused language and game-runtime prototype. The compiler validates BASIC/Lua-inspired `.ANVL` programs, emits C, and invokes MSVC to create a native `.exe`. The runtime provides fixed-size software 2D/3D drawing, keyboard camera controls, fixed-step updates, seeded random/noise functions, minimal numeric UDP, and the built-in `ray_sphere(x,y,z,radius)`. The ray sphere uses CPU BVH traversal, diffuse/specular lighting, and hard-shadow queries, with a documented 32-sphere per-batch limit. The compiler supports fixed-size global and function-local numeric arrays; each function call is capped at 8,192 local elements, with a 16 MiB active-allocation budget across calls.

This is not a production engine. Physics currently supports at most 128 2D circles, fixed-step gravity/force integration, overlap queries, and a four-pass circle contact solver; it does not include continuous collision detection, polygon or 3D bodies, friction, or joints. Assets, audio, cross-platform support, a Rust backend, GPU rendering, RTX/DXR, and Embree also remain unimplemented. Functions support numeric parameters, return values, recursion, function-local numeric state and arrays, `while` loops, inclusive numeric `for` loops, and fixed-size global numeric arrays with checked indexing. Structures and modules/imports remain unsupported. The `.ANVL` extension is the user's selected suffix.

## Verification

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | PASS — 46 tests, including physics integration, contact timing, post-solver velocity/coordinate bounds, and repeatability |
| `npm test --prefix vscode-extension` | PASS — manifest/config and representative TextMate token scopes |
| MSVC release build of `game.ANVLproj` | PASS |
| MSVC release build/run of `examples/functions.ANVL` | PASS — output `13` |
| Nested `while` inside `if/else` and another `while` | PASS — independent build/run output `13` |
| New `examples/loops.ANVL` sample | PASS — MSVC release build and execution output `15` |
| Native runtime integration | PASS — fixed-step updates, delta, queued Space edge, and clean shutdown covered |
| Projected sphere bounds regression | PASS — production projection helper sampled centered, off-axis, and near-camera sphere surfaces |
| `examples/local_arrays.ANVL` | PASS — MSVC release build; output `27`; generated C unchanged on repeat build |
| Recursive maximum-size local arrays | PASS — controlled source-line diagnostic at the 16 MiB allocation budget, rather than process stack overflow |
| `examples/physics.ANVL` native release build | PASS — generated executable with MSVC |
| VS Code extension installation | PASS — `anvil-engine.anvil-language-support@0.1.3` installed over 0.1.2 |
| VS Code package registration | PASS — 0.1.3 package declares language ID `anvil`, `.ANVL`/`.anvl`, and grammar `vscode-extension/syntaxes/anvil.tmLanguage.json` |
| Visible VS Code language mode/sample colors | PASS — `examples/physics.ANVL` opened in Anvil language mode with visible token coloring for physics built-ins, declarations, control flow, strings, and numeric literals. |
| Live game window in latest review | NOT INSPECTED |

These checks verify the prototype workflows and selected regression cases. They do not establish production readiness, cross-platform behavior, or performance.

## Independent 50-criterion review

The independent review of commit `f96a212` scored **87/100 (87%) — FAIL**. Although its 42 tests passed, the evaluator reproduced a Windows stack overflow (0xC00000FD) at recursion depth 20 when each recursive call declared an 8,192-element local array. This was tracked with exact reproduction steps in issue #21. Commit `8f82f1c` replaced stack arrays with checked heap allocations, frees them on explicit and implicit returns, and enforces a 16 MiB active-call budget. The independent reviewer evaluated that exact commit and scored it **91/100 (91%) — PASS**. A depth-1000 stress case now exits with a source-located allocation-budget error, while a 300-call loop completes without leaking its local arrays. A later physics review of the pre-synchronization tree (based on `b00f35a`) corrected its initial 89 score to **88/100 — FAIL**: criteria 1–10 = 16, 11–20 = 20, 21–30 = 17, 31–40 = 18, and 41–50 = 17. Its deductions included stale QA records and no visible 0.1.3 check at review time. After synchronizing the records, installing and visibly checking 0.1.3, and resolving issue #22, an independent reviewer evaluated commit `64a4101`, reran 46 tests and extension validation, and scored **91/100 — PASS**. Issues #19–#22 are resolved.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Compiler, runtime, language, extension, and documentation requirements are identified. |
| 2 | Implicit requirements addressed | 1 | The broad game-engine backlog is only partly implemented; planned systems remain. |
| 3 | Functionality matches intended goal | 1 | Working Windows prototype, but not the requested full engine. |
| 4 | Required deliverables present | 2 | Repository includes compiler, runtime, docs, examples, tests, and VS Code extension. |
| 5 | No essential feature missing | 1 | GPU renderer, assets, audio, 3D/advanced physics, and broader multiplayer remain unfinished. |
| 6 | Stated constraints respected | 2 | `.ANVL` is consistently used as requested. |
| 7 | Ambiguity resolved logically | 2 | Current C/MSVC prototype scope and limitations are documented. |
| 8 | Behavior matches documentation | 2 | Latest review found language/compiler/engine guides aligned after fixes. |
| 9 | Important use cases supported | 1 | Simple native 2D/3D demonstrations work; broader engine use cases are missing. |
| 10 | Usable for intended purpose | 2 | Usable for small learning and prototyping scenes. |
| 11 | Core functionality works | 2 | Compiler, native runtime, camera, rendering, CPU BVH ray spheres, and limited 2D circle physics build. |
| 12 | Secondary functionality works | 2 | Timing, input, math/noise, networking primitive, and native-tested `while`/`for` loops are covered. |
| 13 | Primary workflows functional | 2 | Direct source and manifest build/run workflows pass. |
| 14 | Inputs validated | 2 | Syntax, arity, references, manifest fields, paths, rates, and ports are checked. |
| 15 | Errors handled gracefully | 2 | The 16 MiB active-array budget fails with exit code 2 and a source-located diagnostic instead of exhausting the OS stack. |
| 16 | Edge cases covered | 2 | Tests cover recursion isolation, allocation limits, array bounds, stale physics handles, capacity, collision timing, numeric clamps, and repeated physics output. |
| 17 | Invalid inputs controlled | 2 | Malformed inputs are rejected before generating/building C. |
| 18 | Stable across repeated operations | 2 | Compiler/runtime tests and repeatable random/noise checks pass. |
| 19 | No known critical defects | 2 | The recursive-array stack-exhaustion finding is fixed; the physics reviewer found no critical issue in the reviewed physics paths. |
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
| 31 | Automated tests provided | 2 | Current suite contains 46 Python tests, including physics native integration and physics edge regressions. |
| 32 | Core tests covered | 2 | Compiler, runtime, networking, projection, and generated executable paths are covered. |
| 33 | Failure scenarios tested | 2 | Invalid syntax, references, manifests, settings, and paths have regression tests. |
| 34 | Edge cases explicitly tested | 2 | The current suite covers recursive allocation exhaustion/cleanup plus physics contact timing, extreme velocity/coordinate bounds, and repeatability. |
| 35 | Integration behavior tested | 2 | Native runtime and compiler-to-executable flows are exercised. |
| 36 | Documented test commands work | 2 | Documented Python and npm checks pass. |
| 37 | Builds and compilation pass | 2 | MSVC builds pass for manifest, function, and physics samples. |
| 38 | Results recorded accurately | 2 | The report identifies the reviewed commit, 46-test result, current physics scope, installed VS Code 0.1.3, and historical 88-point result. The independent 64a4101 review confirmed the record. |
| 39 | Regression checks performed | 2 | Independent physics review reran all 46 tests and extension validation; targeted tests also cover solver clamps and contact timing. |
| 40 | Verified against original goal | 1 | Tests verify the prototype, not the full requested engine breadth. |
| 41 | Installation instructions accurate | 2 | Python, MSVC, and VSIX workflows are documented. |
| 42 | Setup reproducible | 2 | Compiler, runtime, and extension checks have repeatable commands. |
| 43 | Usage understandable | 2 | Guides and examples explain the supported syntax and build path. |
| 44 | Design decisions documented | 2 | Runtime, compiler backend, renderer, ray tracing, and networking limits are described. |
| 45 | Troubleshooting available | 2 | README and compiler guide provide setup/troubleshooting information. |
| 46 | Opens in intended environment | 2 | VS Code 1.143.1 has 0.1.3 installed and `examples/physics.ANVL` open in Anvil language mode. |
| 47 | Editor integration works | 2 | Extension tests pass; visible physics syntax coloring was confirmed after installing 0.1.3. |
| 48 | Deliverables organized | 2 | The array generated C file is tracked; all six tracked generated C hashes remained unchanged through the full test suite, and the worktree stayed clean. |
| 49 | Limitations and assumptions disclosed | 2 | Prototype scope, Windows/MSVC backend, ray trace cap, and network limits are stated. |
| 50 | Practical for stated scope | 1 | Suitable for educational demos, not production game development. |
| | **Requirement fulfillment** | **16/20** | |
| | **Functionality and reliability** | **20/20** | |
| | **Code quality and architecture** | **17/20** | |
| | **Testing and verification** | **19/20** | |
| | **Developer experience and delivery** | **19/20** | |
| | **Total** | **91/100 — PASS** | |

### Priorities from the review

1. Continue the game-engine backlog: GPU rendering, assets, audio, physics, richer data structures, robust networking, benchmarks, and portability.
2. Split and format the compiler into clear parser, validation, C generation, and build modules.
3. Keep evaluation scores and verification results synchronized with every fresh review.

## Bug tracking

Issues [#1](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/1)–[#4](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/4) track earlier corrected report defects and are closed. The detailed evaluator findings are recorded in [#13](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/13) (VS Code 0.1.3 install/highlighting), [#16](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/16) (historical QA synchronization), [#17](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/17) (finding classification), [#18](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/18) (tracked generated C), [#19](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/19) (test output side effects), [#20](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/20) (evaluation arithmetic), [#21](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/21) (recursive local-array stack exhaustion), and [#22](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/22) (QA synchronization after physics); resolved issues are closed. Broader implementation gaps remain open in [#5 GPU and ray-tracing backends](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/5), [#6 asset pipeline](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/6), [#7 audio](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/7), [#8 extended physics](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/8), [#9 remaining array forms/structures/modules](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/9), [#10 multiplayer](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/10), [#11 portability and Rust backend](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/11), [#12 compiler readability and modularity](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/12), [#14 performance benchmarks](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/14), and [#15 completion matrix/full-scope tracking](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/15).

