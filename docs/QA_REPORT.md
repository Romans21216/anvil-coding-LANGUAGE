# Anvil QA Report

**Review date:** 2026-10-27
**Source format:** `.ANVL`
**Latest completed independent full review:** **85/100 — FAIL** (commit `8ae53c4daaed0d2160262aa24a2a0d5178235a96`) against the user's **98/100** threshold. It ran 59 Python tests, extension validation, Python compilation, an MSVC release build/run of `numeric_demo.ANVL` (output `17`), and `git diff --check`. It verified issue #23 still holds the full 450-item list. Findings are tracked in [#30](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/30) (non-finite UDP `receive()` bypass) and [#31](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/31) (stale verification metadata). The pushed candidate `6c52b959dc3d5d13d174e37e57006f63d4cda951` fixes both; all 61 Python tests, extension validation, and static checks pass, pending a new review. The previous 90/100 review of `2a745bb` remains historical: it passed the former 90-point bar but is below 98.
**Current passing threshold:** 98/100, set by the user on 2026-10-27. Historical reviews keep their original scores and results; a historical 90/100 PASS does not meet the new threshold.
**Review snapshot:** the latest reviewer evaluated exact commit `8ae53c4daaed0d2160262aa24a2a0d5178235a96`, reran all 59 Python tests, VS Code extension validation, Python compilation, built and ran `examples/numeric_demo.ANVL` with MSVC (output `17`), and passed `git diff --check`. It confirmed the full 450-item list remains in issue #23's body and comment, and repository files contain only the audited subset. It found the `receive()` input-validation gap and stale status metadata recorded in issues #30 and #31. Extension 0.1.4 remains installed; 0.1.7 is not installed per user preference. Visual highlighting in 0.1.7 remains unverified.

## Scope

Anvil is an early Windows-focused language and game-runtime prototype. The compiler validates BASIC/Lua-inspired `.ANVL` programs, emits C, and invokes MSVC to create a native `.exe`. The runtime provides fixed-size software 2D/3D drawing, keyboard camera controls, fixed-step updates, seeded random/noise functions, minimal numeric UDP, and the built-in `ray_sphere(x,y,z,radius)`. The ray sphere uses CPU BVH traversal, diffuse/specular lighting, and hard-shadow queries, with a documented 32-sphere per-batch limit. The compiler supports fixed-size global and function-local numeric arrays; each function call is capped at 8,192 local elements, with a 16 MiB active-allocation budget across calls.

This is not a production engine. Current physics supports up to 128 2D circle and axis-aligned box bodies, with configurable active capacity, fixed-step gravity/force integration, mixed-shape contacts, a four-pass solver, restitution, and Coulomb friction. It does not include continuous collision detection, polygon or 3D bodies, rotation, or joints. Assets, audio, cross-platform support, a Rust backend, GPU rendering, RTX/DXR, and Embree also remain unimplemented. Functions support numeric parameters, return values, recursion, function-local numeric state and arrays, `while` loops, inclusive numeric `for` loops, and fixed-size global numeric arrays with checked indexing. Structures and modules/imports remain unsupported. The `.ANVL` extension is the user's selected suffix.

## Verification

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -q` | PASS — current candidate: 61 tests, including numeric overflow plus NaN/finite/missing-socket UDP behavior; the latest critic ran 59 tests on `8ae53c4` |
| `npm test --prefix vscode-extension` | PASS — manifest/config and representative TextMate token scopes, including ray-backend, box-physics, capacity, and friction built-ins |
| MSVC release build of `game.ANVLproj` | PASS |
| MSVC release build/run of `examples/functions.ANVL` | PASS — output `13` |
| MSVC release build/run of `examples/numeric_demo.ANVL` | PASS — output `17`; generated numeric division links through the runtime guard |
| Nested `while` inside `if/else` and another `while` | PASS — independent build/run output `13` |
| New `examples/loops.ANVL` sample | PASS — MSVC release build and execution output `15` |
| Native runtime integration | PASS — fixed-step updates, delta, queued Space edge, and clean shutdown covered |
| Projected sphere bounds regression | PASS — production projection helper sampled centered, off-axis, and near-camera sphere surfaces |
| `examples/local_arrays.ANVL` | PASS — MSVC release build; output `27`; generated C unchanged on repeat build |
| Recursive maximum-size local arrays | PASS — controlled source-line diagnostic at the 16 MiB allocation budget, rather than process stack overflow |
| `examples/physics.ANVL` native release build | PASS — generated executable with MSVC |
| `examples/physics_boxes.ANVL` native release build | PASS — generated executable with MSVC; interactive window not launched |
| `examples/physics_friction.ANVL` native release build | PASS — generated executable with MSVC; interactive window not launched |
| VS Code extension installation | 0.1.4 remains installed; user declined installing 0.1.5 |
| VS Code package registration | PASS — 0.1.7 package declares language ID `anvil`, `.ANVL`/`.anvl`, and grammar `vscode-extension/syntaxes/anvil.tmLanguage.json` |
| Visible VS Code language mode/sample colors | PASS — 0.1.4 was opened on `examples/ray_backends.ANVL`; Anvil mode and visible highlighting for `ray_backend` and `ray_backend_available` were confirmed during installation verification. The independent evaluator confirmed installation and automated token tests, but did not take a fresh screenshot. |
| New physics built-ins visible highlighting | NOT VERIFIED in installed editor — automated grammar test passes for 0.1.7; 0.1.4 remains installed |
| Ray backend API sample | PASS — MSVC release build and execution of `examples/ray_backends.ANVL`; output `1`. BVH works; DXR/Embree are reported unavailable. |
| `git diff --check` | PASS — clean in independent review |
| Live game window in latest review | NOT INSPECTED |

These checks verify the prototype workflows and selected regression cases. They do not establish production readiness, cross-platform behavior, or performance.

The active physics capacity is configurable from 1 through the compiled maximum of 128. Allocation, integration, contact counting, solver resolution, and post-solver bounds now iterate only over active capacity. The fixed backing table remains 128 slots, but the pair scan uses the selected active limit.

## Latest independent review — commit `8ae53c4`

**85/100 — FAIL** against the required 98/100. Category totals: requirements 16/20; functionality and reliability 16/20; code quality and architecture 17/20; testing and verification 18/20; developer experience and delivery 18/20. The reviewer verified 59 Python tests, VS Code extension validation, Python compilation, MSVC `numeric_demo` build/run (output `17`), `git diff --check`, and issue #23's 450 unique sequential entries. It found: (1) `receive()` can return a NaN/infinity packet without the source-located guard (issue #30); and (2) the structured status files named stale commits and the state file claimed pushed work was local (issue #31). These findings reduce core functionality, input/edge validation, and results-recording scores. The user requires 98/100; this review does not pass.

## Historical independent 50-criterion review — commit `2a745bb`

The independent review of commit `f96a212` scored **87/100 (87%) — FAIL**. Although its 42 tests passed, the evaluator reproduced a Windows stack overflow (0xC00000FD) at recursion depth 20 when each recursive call declared an 8,192-element local array. This was tracked with exact reproduction steps in issue #21. Commit `8f82f1c` replaced stack arrays with checked heap allocations, frees them on explicit and implicit returns, and enforces a 16 MiB active-call budget. The independent reviewer evaluated that exact commit and scored it **91/100 (91%) — PASS**. A depth-1000 stress case now exits with a source-located allocation-budget error, while a 300-call loop completes without leaking its local arrays. A later physics review of the pre-synchronization tree (based on `b00f35a`) corrected its initial 89 score to **88/100 — FAIL**. After synchronizing records, installing and visibly checking 0.1.3, and resolving issue #22, reviews of `64a4101` and `ff88152` scored **91/100 — PASS** (16/20, 20/20, 17/20, 19/20, 19/20). The independent review of `7efdfb0` scored **90/100 — PASS** (16/20, 20/20, 17/20, 18/20, 19/20). Reviews of `0d3b5ed` and `51deb5d` scored **90/100 — PASS**. The review of `c4f3ec6` scored **88/100 — FAIL** because four docs contained stale complexity claims. Commit `560cee1` corrected those documents; a fresh independent review confirmed the fix and scored `560cee1` **90/100 — PASS** (16/20, 20/20, 17/20, 19/20, 18/20). The friction feature commit `f7c91b0` scored **87/100 — FAIL** (15/20, 20/20, 17/20, 18/20, 17/20) because of stale high-level feature and QA records plus missing friction edge-case tests. Follow-up commits `e1e3768` and `83891c6` synchronized the records and added those tests. Its independent review scored **90/100 — PASS** (16/20, 20/20, 17/20, 19/20, 18/20). The division-diagnostic commit `12b4e55` also scored **90/100 — PASS** with the same category totals; it reran all 56 tests, extension/Python validation, an MSVC numeric sample build/run, diff check, and verified the 450-item inventory. The reviewer found no defect in the new diagnostic, and item #48 is complete. Remaining deductions concern overall engine scope, compiler structure/platform breadth, and unverified new extension highlighting. See issues #8 and #24.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Compiler, runtime, language, extension, and documentation requirements are identified. |
| 2 | Implicit requirements addressed | 1 | The broad game-engine backlog is only partly implemented; planned systems remain. |
| 3 | Functionality matches intended goal | 1 | Working Windows prototype, but not the requested full engine. |
| 4 | Required deliverables present | 2 | Repository includes compiler, runtime, docs, examples, tests, and VS Code extension. |
| 5 | No essential feature missing | 1 | GPU renderer, assets, audio, 3D/advanced physics, and broader multiplayer remain unfinished. |
| 6 | Stated constraints respected | 2 | `.ANVL` is consistently used as requested. |
| 7 | Ambiguity resolved logically | 2 | Current C/MSVC prototype scope and limitations are documented. |
| 8 | Behavior matches documentation | 2 | Reviewer of `12b4e55` confirmed the runtime division guard, source-located error/exit behavior, regular division, and documentation agree. Earlier friction documentation findings were resolved and independently verified. |
| 9 | Important use cases supported | 1 | Simple native 2D/3D demonstrations work; broader engine use cases are missing. |
| 10 | Usable for intended purpose | 2 | Usable for small learning and prototyping scenes. |
| 11 | Core functionality works | 1 | **Latest finding:** `receive()` can return a non-finite UDP value without the promised expression diagnostic; tracked in issue #30. |
| 12 | Secondary functionality works | 2 | Timing, input, math/noise, networking primitive, and native-tested `while`/`for` loops are covered. |
| 13 | Primary workflows functional | 2 | Direct source and manifest build/run workflows pass. |
| 14 | Inputs validated | 1 | **Latest finding:** a full-size UDP NaN/infinity payload bypasses the numeric guard; issue #30. |
| 15 | Errors handled gracefully | 2 | The 16 MiB active-array budget fails with exit code 2 and a source-located diagnostic instead of exhausting the OS stack. |
| 16 | Edge cases covered | 1 | **Latest finding:** non-finite network payloads were not tested or rejected; issue #30. Other recursion, array, and physics edges remain covered. |
| 17 | Invalid inputs controlled | 1 | **Latest finding:** `receive()` accepts a full-size NaN/infinity packet into the numeric runtime; issue #30. |
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
| 31 | Automated tests provided | 2 | Latest independent review ran 59 Python tests successfully, including overflow, accumulation, and loop-step cases. |
| 32 | Core tests covered | 2 | Compiler, runtime, networking, projection, circle/box collisions, pool capacity, and generated executable paths are covered. |
| 33 | Failure scenarios tested | 2 | Invalid syntax, references, manifests, settings, and paths have regression tests. |
| 34 | Edge cases explicitly tested | 2 | The current suite covers recursive allocation exhaustion/cleanup plus physics contact timing, extreme velocity/coordinate bounds, and repeatability. |
| 35 | Integration behavior tested | 2 | Native runtime and compiler-to-executable flows are exercised. |
| 36 | Documented test commands work | 2 | Documented Python and npm checks pass. |
| 37 | Builds and compilation pass | 2 | MSVC builds pass for manifest, function, and physics samples. |
| 38 | Results recorded accurately | 1 | **Latest finding:** structured status and resumable state disagreed on reviewed/current/pushed commit IDs; issue #31. |
| 39 | Regression checks performed | 2 | The independent review reran all 59 tests, extension validation, Python compilation, MSVC numeric demo, and diff check. |
| 40 | Verified against original goal | 1 | The full suite verifies the current prototype, not the full requested engine breadth. |
| 41 | Installation instructions accurate | 2 | Python, MSVC, and VSIX workflows are documented. |
| 42 | Setup reproducible | 2 | Compiler, runtime, and extension checks have repeatable commands. |
| 43 | Usage understandable | 2 | Guides and examples explain the supported syntax and build path. |
| 44 | Design decisions documented | 2 | High-level evaluation and completion docs now describe per-body friction range 0–1, default 0.5, geometric-mean mixing, and normal-impulse clamping. The reviewer confirmed consistency; issue #27 is resolved. |
| 45 | Troubleshooting available | 2 | README and compiler guide provide setup/troubleshooting information. |
| 46 | Opens in intended environment | 2 | The evaluator confirmed extension 0.1.4 installed; visible Anvil mode had previously been verified for the ray-backend sample. |
| 47 | Editor integration works | 1 | **Problem:** new physics builtin highlighting has not been checked in an installed editor. **Evidence:** 0.1.7 grammar/package token checks pass, but the user kept 0.1.4 installed; it predates `body_create_box`, `physics_capacity`, and `body_friction`. **Impact:** visible syntax coloring for these built-ins is unverified in the user's editor. **Status:** pending user preference; tracked in issue [#24](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/24). |
| 48 | Deliverables organized | 2 | Source, runtime, examples, tests, docs, extension grammar, and packaged VSIX are in their expected folders; the reviewer confirmed a clean worktree before and after verification. |
| 49 | Limitations and assumptions disclosed | 2 | Prototype scope, Windows/MSVC backend, ray trace cap, and network limits are stated. |
| 50 | Practical for stated scope | 1 | Suitable for educational demos, not production game development. |
| | **Requirement fulfillment** | **16/20** | |
| | **Functionality and reliability** | **16/20** | |
| | **Code quality and architecture** | **17/20** | |
| | **Testing and verification** | **18/20** | |
| | **Developer experience and delivery** | **18/20** | |
| | **Total** | **85/100** | Latest review FAIL under the 98-point requirement. |

### Deduction details and follow-up

- **Criterion 2 — implicit requirements addressed (1/2).** **Problem/evidence:** The 450-item backlog still lists major engine and language systems that are absent, including assets, audio, advanced physics, structured multiplayer, portability, and tooling. **Impact:** Anvil only supports a narrow subset of the intended engine. **Recommended fix:** continue implementing backlog capabilities with linked tests and docs. **Status:** open; issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23) remains the user's master backlog.
- **Criterion 3 — functionality matches intended goal (1/2).** **Problem/evidence:** Current renderer and runtime are Windows/MSVC-focused; actual GPU rendering, DXR/Embree, mature asset pipeline, robust multiplayer, and many full-engine systems are missing. **Impact:** it does not yet fulfill the requested general 2D/3D engine. **Recommended fix:** implement remaining engine subsystems and portable backends. **Status:** open; see issues #5, #6, #7, #10, #11, and #15.
- **Criterion 5 — no essential feature missing (1/2).** **Problem/evidence:** GPU rasterization, DXR/Embree, joints, CCD, 3D physics, asset/audio pipelines, and robust multiplayer remain unavailable. **Impact:** important requested workflows cannot be built in Anvil today. **Recommended fix:** prioritize missing features by backlog and add executable integration evidence. **Status:** open; issues #5–#11 and #23.
- **Criterion 9 — important use cases supported (1/2).** **Problem/evidence:** mixed 2D circle/box contacts work, but no rotation, CCD, polygon or 3D body, asset/audio use, or secure multiplayer path exists. **Impact:** suitable use cases are limited to small demos and learning. **Recommended fix:** broaden physics and engine systems in staged releases. **Status:** open; issue #8 is updated with current physics scope.
- **Criteria 22 and 23 — readability and module responsibility (each 1/2).** **Problem/evidence:** `compiler/anvil.py` remains densely formatted and combines parsing, semantic validation, C generation, and build orchestration. **Impact:** feature additions increase maintenance and regression risk. **Recommended fix:** split the compiler into lexer/parser, semantic analysis, C backend, and build-driver modules, then format and test each boundary. **Status:** open; issue #12.
- **Criterion 27 — extensible architecture (1/2).** **Problem/evidence:** runtime and native toolchain are Windows/MSVC and C-only. **Impact:** additional host platforms and compiler backends require substantial rework. **Recommended fix:** define platform/runtime interfaces and add non-Windows and alternate code-generation targets. **Status:** open; issue #11.
- **Historical criterion 38 finding — resolved.** On `71b818b`, `docs/ANVIL_EVALUATION.txt` said item #46 remained pending review even though the ledger recorded it complete and the reviewer had confirmed the feature on `83cf626`. The follow-up corrected the wording; review of `2a745bb` confirmed consistency and issue #29 is closed. The prior count issue #28 is also closed.
- **Criterion 40 — verified against original goal (1/2).** **Problem/evidence:** tests cover the current prototype, not the full engine request. **Impact:** the suite cannot establish completion of missing systems. **Recommended fix:** map acceptance tests to every requested feature and backlog milestone as those systems are delivered. **Status:** open; matrix and issue #23 track remaining scope.
- **Criterion 47 — editor integration (1/2).** **Problem/evidence:** Extension 0.1.7 includes `body_friction` and automated token validation passes, but the user kept 0.1.4 installed; highlighting for newer built-ins has no visible editor verification. **Impact:** newly added highlighting is not confirmed in the user's editor. **Status:** pending user preference; exact evidence is tracked in issue [#24](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/24).
- **Historical criteria 8, 38, and 44 finding — resolved.** On `f7c91b0`, the main completion/evaluation docs had not incorporated friction or the current review/test/package snapshot. Commits `e1e3768` and `83891c6` corrected these records, and independent review confirmed the documentation against implementation and verification; issue #27 is closed. The 87/100 score remains valid for that exact older snapshot. The independent reviewer also confirmed zero-friction and mixed-coefficient regression tests in `83891c6`; issue #26 is closed.
- **Batch 3 tracking metadata note — resolved in the post-review docs sync.** The reviewer of `12b4e55` observed that `docs/IMPLEMENTATION_STATUS.json` still named `83891c6` as its repository head and item #48 was pending review at that snapshot. The current follow-up records the exact reviewed HEAD, promotes #48 to COMPLETE with test/build evidence, and synchronizes the cumulative state file. This was stale tracking metadata, not a runtime defect.
- **Criterion 50 — practical for intended scope (1/2).** **Problem/evidence:** the engine lacks production graphics, assets, audio, mature physics, robust networking, portability, and performance evidence. **Impact:** it is not ready for production games. **Recommended fix:** continue implementation, benchmark real workloads, and define release criteria. **Status:** open; issue #15 and backlog #23.

### Priorities from the review

1. Continue the game-engine backlog: GPU rendering, assets, audio, physics, richer data structures, robust networking, benchmarks, and portability.
2. Split and format the compiler into clear parser, validation, C generation, and build modules.
3. Keep evaluation scores and verification results synchronized with every fresh review.

## Bug tracking

Issues [#1](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/1)–[#4](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/4) track earlier corrected report defects and are closed. The detailed evaluator findings are recorded in [#13](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/13) (VS Code 0.1.3 install/highlighting), [#16](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/16) (historical QA synchronization), [#17](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/17) (finding classification), [#18](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/18) (tracked generated C), [#19](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/19) (test output side effects), [#20](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/20) (evaluation arithmetic), [#21](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/21) (recursive local-array stack exhaustion), and [#22](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/22) (QA synchronization after physics); resolved issues are closed. Broader implementation gaps remain open in [#5 GPU and ray-tracing backends](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/5), [#6 asset pipeline](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/6), [#7 audio](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/7), [#8 extended physics](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/8), [#9 remaining array forms/structures/modules](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/9), [#10 multiplayer](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/10), [#11 portability and Rust backend](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/11), [#12 compiler readability and modularity](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/12), [#14 performance benchmarks](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/14), and [#15 completion matrix/full-scope tracking](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/15).

