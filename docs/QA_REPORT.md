# Anvil QA Report

**Review date:** 2026-10-27
**Source format:** `.ANVL`
**Latest completed independent full review:** **90/100 — PASS** (commit `560cee1`; threshold: 90/100).
**Review snapshot:** the independent reviewer evaluated exact commit `560cee133023ca0cb737669bb6841509d7f503d3`, reran all 52 Python tests, VS Code extension validation, and Python compilation, confirmed extension 0.1.4 remains installed, built `examples/physics_boxes.ANVL` with MSVC, and passed `git diff --check`. Extension 0.1.6 is packaged but not installed per user preference. The reviewer confirmed corrected documentation accurately describes active-capacity loops and O(c²) pair checking for c∈[1,128].

## Scope

Anvil is an early Windows-focused language and game-runtime prototype. The compiler validates BASIC/Lua-inspired `.ANVL` programs, emits C, and invokes MSVC to create a native `.exe`. The runtime provides fixed-size software 2D/3D drawing, keyboard camera controls, fixed-step updates, seeded random/noise functions, minimal numeric UDP, and the built-in `ray_sphere(x,y,z,radius)`. The ray sphere uses CPU BVH traversal, diffuse/specular lighting, and hard-shadow queries, with a documented 32-sphere per-batch limit. The compiler supports fixed-size global and function-local numeric arrays; each function call is capped at 8,192 local elements, with a 16 MiB active-allocation budget across calls.

This is not a production engine. Current physics supports up to 128 2D circle and axis-aligned box bodies, with a configurable active pool limit, fixed-step gravity/force integration, mixed-shape overlap queries, and a four-pass contact solver; it does not include continuous collision detection, polygon or 3D bodies, friction, rotation, or joints. Assets, audio, cross-platform support, a Rust backend, GPU rendering, RTX/DXR, and Embree also remain unimplemented. Functions support numeric parameters, return values, recursion, function-local numeric state and arrays, `while` loops, inclusive numeric `for` loops, and fixed-size global numeric arrays with checked indexing. Structures and modules/imports remain unsupported. The `.ANVL` extension is the user's selected suffix.

## Verification

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | PASS — 52 tests, including mixed-shape solver cases and configurable pool growth, exhaustion, shrinking, and invalid values |
| `npm test --prefix vscode-extension` | PASS — manifest/config and representative TextMate token scopes, including ray-backend, box-physics, and capacity built-ins |
| MSVC release build of `game.ANVLproj` | PASS |
| MSVC release build/run of `examples/functions.ANVL` | PASS — output `13` |
| Nested `while` inside `if/else` and another `while` | PASS — independent build/run output `13` |
| New `examples/loops.ANVL` sample | PASS — MSVC release build and execution output `15` |
| Native runtime integration | PASS — fixed-step updates, delta, queued Space edge, and clean shutdown covered |
| Projected sphere bounds regression | PASS — production projection helper sampled centered, off-axis, and near-camera sphere surfaces |
| `examples/local_arrays.ANVL` | PASS — MSVC release build; output `27`; generated C unchanged on repeat build |
| Recursive maximum-size local arrays | PASS — controlled source-line diagnostic at the 16 MiB allocation budget, rather than process stack overflow |
| `examples/physics.ANVL` native release build | PASS — generated executable with MSVC |
| `examples/physics_boxes.ANVL` native release build | PASS — generated executable with MSVC; interactive window not launched |
| VS Code extension installation | 0.1.4 remains installed; user declined installing 0.1.5 |
| VS Code package registration | PASS — 0.1.6 package declares language ID `anvil`, `.ANVL`/`.anvl`, and grammar `vscode-extension/syntaxes/anvil.tmLanguage.json` |
| Visible VS Code language mode/sample colors | PASS — 0.1.4 was opened on `examples/ray_backends.ANVL`; Anvil mode and visible highlighting for `ray_backend` and `ray_backend_available` were confirmed during installation verification. The independent evaluator confirmed installation and automated token tests, but did not take a fresh screenshot. |
| New physics built-ins visible highlighting | NOT VERIFIED in installed editor — automated grammar test passes for 0.1.6; 0.1.4 remains installed |
| Ray backend API sample | PASS — MSVC release build and execution of `examples/ray_backends.ANVL`; output `1`. BVH works; DXR/Embree are reported unavailable. |
| `git diff --check` | PASS — clean in independent review |
| Live game window in latest review | NOT INSPECTED |

These checks verify the prototype workflows and selected regression cases. They do not establish production readiness, cross-platform behavior, or performance.

The active physics capacity is configurable from 1 through the compiled maximum of 128. Allocation, integration, contact counting, solver resolution, and post-solver bounds now iterate only over active capacity. The fixed backing table remains 128 slots, but the pair scan uses the selected active limit.

## Independent 50-criterion review

The independent review of commit `f96a212` scored **87/100 (87%) — FAIL**. Although its 42 tests passed, the evaluator reproduced a Windows stack overflow (0xC00000FD) at recursion depth 20 when each recursive call declared an 8,192-element local array. This was tracked with exact reproduction steps in issue #21. Commit `8f82f1c` replaced stack arrays with checked heap allocations, frees them on explicit and implicit returns, and enforces a 16 MiB active-call budget. The independent reviewer evaluated that exact commit and scored it **91/100 (91%) — PASS**. A depth-1000 stress case now exits with a source-located allocation-budget error, while a 300-call loop completes without leaking its local arrays. A later physics review of the pre-synchronization tree (based on `b00f35a`) corrected its initial 89 score to **88/100 — FAIL**. After synchronizing records, installing and visibly checking 0.1.3, and resolving issue #22, reviews of `64a4101` and `ff88152` scored **91/100 — PASS** (16/20, 20/20, 17/20, 19/20, 19/20). The independent review of `7efdfb0` scored **90/100 — PASS** (16/20, 20/20, 17/20, 18/20, 19/20). Reviews of `0d3b5ed` and `51deb5d` scored **90/100 — PASS**. The review of `c4f3ec6` scored **88/100 — FAIL** because four docs contained stale complexity claims. Commit `560cee1` corrected those documents; a fresh independent review confirms the fix and scores `560cee1` **90/100 — PASS** (16/20, 20/20, 17/20, 19/20, 18/20). It reran all 52 tests and the extension, Python, MSVC, and diff checks. The old 88/100 result remains valid for its exact snapshot; issue #25 is resolved. Other deductions concern overall engine scope, compiler structure/platform breadth, and unverified new extension highlighting. See issues #8 and #24.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Compiler, runtime, language, extension, and documentation requirements are identified. |
| 2 | Implicit requirements addressed | 1 | The broad game-engine backlog is only partly implemented; planned systems remain. |
| 3 | Functionality matches intended goal | 1 | Working Windows prototype, but not the requested full engine. |
| 4 | Required deliverables present | 2 | Repository includes compiler, runtime, docs, examples, tests, and VS Code extension. |
| 5 | No essential feature missing | 1 | GPU renderer, assets, audio, 3D/advanced physics, and broader multiplayer remain unfinished. |
| 6 | Stated constraints respected | 2 | `.ANVL` is consistently used as requested. |
| 7 | Ambiguity resolved logically | 2 | Current C/MSVC prototype scope and limitations are documented. |
| 8 | Behavior matches documentation | 2 | Independent review confirmed docs match runtime bounds: passes use active capacity and pair checks are O(c²), c∈[1,128]. The prior stale-text finding is resolved in commit `560cee1` and issue #25. |
| 9 | Important use cases supported | 1 | Simple native 2D/3D demonstrations work; broader engine use cases are missing. |
| 10 | Usable for intended purpose | 2 | Usable for small learning and prototyping scenes. |
| 11 | Core functionality works | 2 | Compiler, native runtime, camera, rendering, CPU BVH ray spheres, and limited 2D circle/axis-aligned-box physics build. |
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
| 31 | Automated tests provided | 2 | Independent review ran 52 Python tests successfully. |
| 32 | Core tests covered | 2 | Compiler, runtime, networking, projection, circle/box collisions, pool capacity, and generated executable paths are covered. |
| 33 | Failure scenarios tested | 2 | Invalid syntax, references, manifests, settings, and paths have regression tests. |
| 34 | Edge cases explicitly tested | 2 | The current suite covers recursive allocation exhaustion/cleanup plus physics contact timing, extreme velocity/coordinate bounds, and repeatability. |
| 35 | Integration behavior tested | 2 | Native runtime and compiler-to-executable flows are exercised. |
| 36 | Documented test commands work | 2 | Documented Python and npm checks pass. |
| 37 | Builds and compilation pass | 2 | MSVC builds pass for manifest, function, and physics samples. |
| 38 | Results recorded accurately | 2 | QA records identify reviewed commit `560cee1`, 52 tests, extension 0.1.4 installed, and 0.1.6 packaged but not installed. |
| 39 | Regression checks performed | 2 | Independent review reran all 52 tests and extension validation; native integration covers mixed-shape solver and pool-capacity boundaries. |
| 40 | Verified against original goal | 1 | Tests verify the prototype, not the full requested engine breadth. |
| 41 | Installation instructions accurate | 2 | Python, MSVC, and VSIX workflows are documented. |
| 42 | Setup reproducible | 2 | Compiler, runtime, and extension checks have repeatable commands. |
| 43 | Usage understandable | 2 | Guides and examples explain the supported syntax and build path. |
| 44 | Design decisions documented | 2 | Corrected docs explain active-capacity iteration and O(c²) pair work for c∈[1,128]; independent review confirmed this against implementation at `560cee1`. Issue #25 is resolved. |
| 45 | Troubleshooting available | 2 | README and compiler guide provide setup/troubleshooting information. |
| 46 | Opens in intended environment | 2 | The evaluator confirmed extension 0.1.4 installed; visible Anvil mode had previously been verified for the ray-backend sample. |
| 47 | Editor integration works | 1 | **Problem:** new physics builtin highlighting has not been checked in an installed editor. **Evidence:** 0.1.6 grammar/package token checks pass, but the user kept 0.1.4 installed; it predates `body_create_box` and `physics_capacity`. **Impact:** visible syntax coloring for these built-ins is unverified in the user's editor. **Recommended fix/status:** install 0.1.6 and open `physics_boxes.ANVL` if the user later approves; currently pending by user choice. |
| 48 | Deliverables organized | 2 | Source, runtime, examples, tests, docs, extension grammar, and packaged VSIX are in their expected folders; the reviewer confirmed a clean worktree before and after verification. |
| 49 | Limitations and assumptions disclosed | 2 | Prototype scope, Windows/MSVC backend, ray trace cap, and network limits are stated. |
| 50 | Practical for stated scope | 1 | Suitable for educational demos, not production game development. |
| | **Requirement fulfillment** | **16/20** | |
| | **Functionality and reliability** | **20/20** | |
| | **Code quality and architecture** | **17/20** | |
| | **Testing and verification** | **19/20** | |
| | **Developer experience and delivery** | **18/20** | |
| | **Total** | **90/100 — PASS** | |

### Deduction details and follow-up

- **Criterion 2 — implicit requirements addressed (1/2).** **Problem/evidence:** The 450-item backlog still lists major engine and language systems that are absent, including assets, audio, advanced physics, structured multiplayer, portability, and tooling. **Impact:** Anvil only supports a narrow subset of the intended engine. **Recommended fix:** continue implementing backlog capabilities with linked tests and docs. **Status:** open; issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23) remains the user's master backlog.
- **Criterion 3 — functionality matches intended goal (1/2).** **Problem/evidence:** Current renderer and runtime are Windows/MSVC-focused; actual GPU rendering, DXR/Embree, mature asset pipeline, robust multiplayer, and many full-engine systems are missing. **Impact:** it does not yet fulfill the requested general 2D/3D engine. **Recommended fix:** implement remaining engine subsystems and portable backends. **Status:** open; see issues #5, #6, #7, #10, #11, and #15.
- **Criterion 5 — no essential feature missing (1/2).** **Problem/evidence:** GPU rasterization, DXR/Embree, friction, joints, CCD, 3D physics, asset/audio pipelines, and robust multiplayer remain unavailable. **Impact:** important requested workflows cannot be built in Anvil today. **Recommended fix:** prioritize missing features by backlog and add executable integration evidence. **Status:** open; issues #5–#11 and #23.
- **Criterion 9 — important use cases supported (1/2).** **Problem/evidence:** mixed 2D circle/box contacts work, but no rotation, CCD, polygon or 3D body, asset/audio use, or secure multiplayer path exists. **Impact:** suitable use cases are limited to small demos and learning. **Recommended fix:** broaden physics and engine systems in staged releases. **Status:** open; issue #8 is updated with current physics scope.
- **Criteria 22 and 23 — readability and module responsibility (each 1/2).** **Problem/evidence:** `compiler/anvil.py` remains densely formatted and combines parsing, semantic validation, C generation, and build orchestration. **Impact:** feature additions increase maintenance and regression risk. **Recommended fix:** split the compiler into lexer/parser, semantic analysis, C backend, and build-driver modules, then format and test each boundary. **Status:** open; issue #12.
- **Criterion 27 — extensible architecture (1/2).** **Problem/evidence:** runtime and native toolchain are Windows/MSVC and C-only. **Impact:** additional host platforms and compiler backends require substantial rework. **Recommended fix:** define platform/runtime interfaces and add non-Windows and alternate code-generation targets. **Status:** open; issue #11.
- **Criterion 40 — verified against original goal (1/2).** **Problem/evidence:** 50 tests verify current compiler/runtime/physics behavior, but do not cover the full engine request. **Impact:** the test suite cannot establish completion of missing systems. **Recommended fix:** map acceptance tests to every requested feature and backlog milestone as those systems are delivered. **Status:** open; matrix and issue #23 track remaining scope.
- **Criterion 47 — editor integration (1/2).** **Problem/evidence:** Extension 0.1.6 includes `body_create_box` and `physics_capacity`, and automated token validation passes, but the user kept 0.1.4 installed; the new built-ins have no visible editor verification. **Impact:** newly added highlighting is not confirmed in the user's editor. **Recommended fix:** if later approved, install 0.1.6 and inspect `examples/physics_boxes.ANVL`. **Status:** pending user preference; exact evidence is tracked in issue [#24](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/24).
- **Historical criteria 8 and 44 finding — resolved.** Review of `c4f3ec6` found four stale complexity descriptions. Commit `560cee1` corrected them, and independent review confirmed active-capacity iteration and O(c²) pair checking. Issue [#25](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/25) records the verified resolution; the 88/100 score remains the result for the older exact commit only.
- **Criterion 50 — practical for intended scope (1/2).** **Problem/evidence:** the engine lacks production graphics, assets, audio, mature physics, robust networking, portability, and performance evidence. **Impact:** it is not ready for production games. **Recommended fix:** continue implementation, benchmark real workloads, and define release criteria. **Status:** open; issue #15 and backlog #23.

### Priorities from the review

1. Continue the game-engine backlog: GPU rendering, assets, audio, physics, richer data structures, robust networking, benchmarks, and portability.
2. Split and format the compiler into clear parser, validation, C generation, and build modules.
3. Keep evaluation scores and verification results synchronized with every fresh review.

## Bug tracking

Issues [#1](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/1)–[#4](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/4) track earlier corrected report defects and are closed. The detailed evaluator findings are recorded in [#13](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/13) (VS Code 0.1.3 install/highlighting), [#16](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/16) (historical QA synchronization), [#17](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/17) (finding classification), [#18](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/18) (tracked generated C), [#19](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/19) (test output side effects), [#20](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/20) (evaluation arithmetic), [#21](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/21) (recursive local-array stack exhaustion), and [#22](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/22) (QA synchronization after physics); resolved issues are closed. Broader implementation gaps remain open in [#5 GPU and ray-tracing backends](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/5), [#6 asset pipeline](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/6), [#7 audio](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/7), [#8 extended physics](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/8), [#9 remaining array forms/structures/modules](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/9), [#10 multiplayer](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/10), [#11 portability and Rust backend](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/11), [#12 compiler readability and modularity](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/12), [#14 performance benchmarks](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/14), and [#15 completion matrix/full-scope tracking](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/15).

