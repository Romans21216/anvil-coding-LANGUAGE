# Anvil QA Report

**Review date:** 2026-10-27
**Latest independent evaluation:** **72/100 - FAIL** for exact commit `900106eedc9f3aa09c5d2e909a033903a563c989` against **98/100**. Categories: requirements 11/20, functionality 19/20, architecture 13/20, testing 18/20, delivery 11/20.
**Current passing threshold:** 98/100. Historical reviews retain the threshold in force at the time; a previous 90/100 PASS does not pass the current bar.

**Historical native QA fixture repair:** the review of573cb44 found two `test_qa_report` fixture failures on `573cb44`. The follow-up now scopes rubric fixtures to the current table and changes subtotals dynamically; the focused tests and full 86-test suite pass locally. The fix is committed as `150a042`; a fresh review of `597867f44a5140db27fdce2e4f2339859ef96af8` confirmed the full suite passes and raised the testing subtotal. Review of `f330d4b` verified fractional formatting and closed issue #49. Review of `ade1ff6` opened #53 for signed-minimum rejection and #54 for missing non-finite arithmetic diagnostics. Review of `120482e` verified fixes for both, along with #52 range handling; issues #49 and #52–#54 are closed.

**Historical BMP implementation candidate:** source commit `9d9bf90e62e3e75ea94de7828d86800cbd382c99` adds bounded 24/32-bit BMP loading, generation-checked handles, image queries/release, and clipped/scaled alpha-blended 2D sprite drawing. The full suite passes (79 tests), the sprite sample builds with MSVC, extension 0.1.9 grammar validation, compileall, QA arithmetic, and diff checks pass. These checks are implementation evidence only. The later direct-native candidate received a 49/100 review on a pre-short-circuit-fix local snapshot; see the current native follow-up and full rubric below. Canonical issue #23 items #201 and #209 are under review, #202 awaits review, and #212 remains partial because rotation is not implemented.
**Historical C-backed review evidence:** the critic evaluated exact pushed follow-up commit `c10260483eab6b5adaadd261a66a92a9138b9ed8` and scored 92/100 (16/20, 20/20, 19/20, 19/20, 18/20). It reran 77 Python tests, extension validation, compileall, QA arithmetic, strict UTF-8 JSON parsing, status parity, and diff check. It verified all 26 audited rows total 450 (424 needing verification, 3 partial, 21 complete, 2 in progress), including items #391–394 complete. Issue #48's invalid-UTF-8/stale-SHA finding is fixed and closed; criterion 38 returned to 2/2. Native mouse integration covers resized viewport mapping, letterbox rejection, left/right/middle button edges and held states, and wheel accumulation/reset. No live mouse-enabled window was visually inspected and no code defect was found. Extension 0.1.4 remains installed per user preference, so newer visible highlighting remains unverified.
**Historical native finding:** exact commit `120482e85e77c19216a793ab17190dbf1ae025ff` scored 58/100, below the 98/100 threshold. All 89 tests passed. The reviewer verified fixes for fractional output, large values, signed minimum, and non-finite diagnostics; issues #49 and #52–#54 are closed. Native game-engine migration remains incomplete.

**Current review:** independent review of exact `900106eedc9f3aa09c5d2e909a033903a563c989` verified native mouse and all 102 tests. No new runtime defect was reproduced. README mismatch #59 reduced criterion 8 by one point; the documentation follow-up corrects it without claiming a new full score. Sample: 13,312-byte direct native PE.

**Verified flicker fix:** a persistent offscreen bitmap/DC composes each frame and one BitBlt presents it. Independent testing covers visible pixels during slow drawing, resize GDI counts, and injected bitmap-allocation failure. No new runtime defect was reproduced. No CUA was resumed after the prior physical-Escape stop.

**Verified keyboard milestone:** held()/pressed(), shared named/numeric keys, repeat suppression, release/focus clearing, short taps, update/draw-only edge lifetime and side-effecting arguments pass independent tests. The tests send bounded messages only to their generated window. No CUA was resumed and no manual live editor/sample inspection is claimed.

**Historical near-plane correction:** code commit `15ac43a8033557859db509ecca2fa8c88a13d7b7` plus synchronized records at `eec0608dd6f252090b50fda1027eba14c6af1292` addresses issue #47 with overflow-stable interpolation, finite-output checks, and viewport clipping before line-rasterizer integer conversion. The test-count record is 74. Independent review restored criteria 34 and 38 to 2/2 and scored the synchronized candidate 92/100. Visual rendering was not inspected.

**Formatting follow-up review:** candidate `3f77eee` was independently reviewed on exact commit `5072597`; all 72 tests, Black check, compileall, QA arithmetic, diff check, and 12-example generated-C parity pass. The critic scored this snapshot 92/100, still below 98.

**Resize behavior candidate `2962455`: implementation corresponds to issue #23 item #172 (“Add dynamic window resizing”), not item #144 (“Add compiler version reporting”). The critic found the previous tracking mismatch and issue #46 records it. The runtime feature preserves the 960×600 framebuffer and aspect ratio. All 73 Python tests pass; no runtime defect was reproduced. The corrected status ledger was independently reviewed on `f12c0ac`; criterion 38 is 2/2 and the score is 92/100. No live resize was visually inspected.

## Scope

Anvil is an early Windows-focused language and game-runtime prototype. The compiler validates BASIC/Lua-inspired `.ANVL` programs, accepts optional `language version 1` declarations (and defaults legacy files to version 1), emits C, and invokes MSVC to create a native `.exe`. The runtime provides fixed-size software 2D/3D drawing, keyboard camera controls, fixed-step updates, seeded random/noise functions, minimal numeric UDP, and the built-in `ray_sphere(x,y,z,radius)`. The ray sphere uses CPU BVH traversal, diffuse/specular lighting, and hard-shadow queries, with a documented 32-sphere per-batch limit. The compiler supports fixed-size global and function-local numeric arrays; each function call is capped at 8,192 local elements, with a 16 MiB active-allocation budget across calls.

This is not a production engine. Current physics supports up to 128 2D circle and axis-aligned box bodies, with configurable active capacity, fixed-step gravity/force integration, mixed-shape contacts, a four-pass solver, restitution, and Coulomb friction. It does not include continuous collision detection, polygon or 3D bodies, rotation, or joints. BMP image loading and screen-space sprite rendering are now implemented in the unreviewed candidate; general asset management, audio, cross-platform support, a Rust backend, GPU rendering, RTX/DXR, and Embree remain unimplemented. Functions support numeric parameters, return values, recursion, function-local numeric state and arrays, `while` loops, inclusive numeric `for` loops, and fixed-size global numeric arrays with checked indexing. Structures and modules/imports remain unsupported. The `.ANVL` extension is the user's selected suffix.

## Verification

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -q` | PASS — 102 tests independently rerun on exact native review candidate `900106e` |
| Canonical item #172 resize suite | PASS — all 74 suite tests passed on exact review candidate `eec0608` |
| Canonical item #185 near-plane clipping regression | PASS — native MSVC tests cover extreme finite segments, triangles, and sphere near caps on exact review candidate `eec0608` |
| `python -m unittest discover -s tests -p test_runtime.py -v` | PASS — 4 native runtime tests, including resize, clipping, and aspect-preserving viewport cases |
| `python -m unittest discover -s tests -p test_qa_report.py -v` | PASS — zero-score rubric accepted; mismatched category subtotal rejected |
| `python scripts/validate_qa_report.py` | PASS — synchronized rubric totals 72/100; category subtotals agree |
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
| `git diff --check` on latest reviewed implementation commit `65c15bf` | PASS |
| Spec conformance example | PASS — critic built with MSVC and ran the native executable; output `6` |
| Live game window in latest review | NOT INSPECTED |

These checks verify the prototype workflows and selected regression cases. They do not establish production readiness, cross-platform behavior, or performance.

The active physics capacity is configurable from 1 through the compiled maximum of 128. Allocation, integration, contact counting, solver resolution, and post-solver bounds now iterate only over active capacity. The fixed backing table remains 128 slots, but the pair scan uses the selected active limit.

## Historical independent review — window resize snapshot `bc4db99`

**91/100 — FAIL** against the required 98/100. Category totals: requirements 16/20; functionality and reliability 20/20; code quality and architecture 19/20; testing and verification 18/20; developer experience and delivery 18/20. The exact reviewed commit was `bc4db99368b3af2953e49adc4e4cbd8f5706bb4e`. The critic reran 73 Python tests, 3 native runtime tests, extension validation, compileall, the QA validator, and diff check. It verified the viewport geometry helper and inspected the WM_PAINT path, but did not visually launch a resized window. The audited ledgers contain 21 rows and total 450. Criterion 38 scores 1 because the prior ledger labeled dynamic window resizing as #144; canonical issue #23 comment 6451810775 defines it as #172. Issue #46 tracks the correction. Criterion 22 remains 2 after formatting; criterion 23 remains 2 for phase separation. Criterion 27 remains 1 for Windows/MSVC and C-only backend. Criterion 47 remains 1 because newer extension tokens are not visually verified. The 98-point threshold remains unmet; issues #12 and #45 are closed.

## Latest 50-criterion scoring — direct native commit `21fc960`

Independent reviewer evaluated exact pushed commit `21fc960b04c2df317f3e0b3580987526f14d63e2`: **73/100 — FAIL** against **98/100**. All99Python tests, extension validation, compileall, QA arithmetic, strict UTF-8 JSON and diff checks pass. Native2D example builds to a9,728-byte PE. Keyboard tests cover window-local transitions and actual generated globals; Win64 argument registers, RDI preservation, direction flag and system-key default forwarding were inspected. No new defect or manual live-window/editor inspection was reported.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Language/compiler/runtime and direct target are identified. |
| 2 | Implicit requirements addressed | 1 | Runtime/input support is growing; most engine/Forge breadth remains unavailable (open). |
| 3 | Functionality matches intended goal | 1 | Keyboard and mouse native 2D rectangles work; complete engine coverage remains missing (open). |
| 4 | Required deliverables present | 1 | Compiler, extension, tests and docs exist; native engine parity is missing (open). |
| 5 | No essential feature missing | 0 | GPU rendering, broader engine systems and Forge requirements remain absent (open). |
| 6 | Stated constraints respected | 1 | Native avoids C/Rust, but C is default; port remaining APIs before switching (open). |
| 7 | Ambiguity resolved logically | 2 | Direct machine-code/PE target follows user selection. |
| 8 | Behavior matches documentation | 1 | README at 900106e incorrectly says native mouse input is unavailable (#59). Corrected in documentation follow-up, not rescored. |
| 9 | Important use cases supported | 1 | Interactive 2D input works; native 3D/assets/physics/networking remain missing (open). |
| 10 | Usable for intended purpose | 1 | Usable for a small native demo; complete engine workflows remain unavailable (open). |
| 11 | Core functionality works | 1 | Buffered windows, fixed updates and keyboard state work; complete native engine core remains partial (open). |
| 12 | Secondary functionality works | 2 | Mouse position, buttons, wheel, capture, focus/cancel and keyboard regressions pass generated-app tests. |
| 13 | Primary workflows functional | 2 | Interactive sample compiles directly to PE and accepts keyboard/mouse input. |
| 14 | Inputs validated | 2 | Literal mouse button names and native arity are validated; numeric key checks remain covered. |
| 15 | Errors handled gracefully | 2 | Invalid native arity/features diagnose; buffered allocation-failure cleanup remains covered. |
| 16 | Edge cases covered | 2 | Tests cover signed/outside mouse coordinates, resize, capture, taps, wheel fractions, focus and draw-only scenes. |
| 17 | Invalid inputs controlled | 2 | Invalid/out-of-range numeric key queries safely return false, including1e300 and256. |
| 18 | Stable across repeated operations | 2 | All 102 tests pass, including mouse sequences, slow drawing and resize resources. |
| 19 | No known critical defects | 2 | Prior flicker fix remains verified; no new runtime defect was reproduced. |
| 20 | Components integrate | 2 | Keyboard/mouse share window dispatch and focus clearing; emitted PE consumes Win32 input. |
| 21 | Logical project structure | 2 | Input emitter, window emitter, encoder, examples, tests and docs are separated. |
| 22 | Readable and consistently formatted | 1 | Raw x64 bytes are hard to maintain; add instruction abstractions and formatting (open). |
| 23 | Clear module responsibilities | 1 | Input has its own module; instruction encoding/state/platform behavior remain coupled (open). |
| 24 | Consistent descriptive naming | 2 | Names are consistent and descriptive. |
| 25 | Duplication minimized | 1 | ABI/instruction patterns repeat; consolidate encoder helpers (open). |
| 26 | Dependencies appropriate | 2 | Direct backend imports Windows APIs without a C/Rust shim. |
| 27 | Supports future extensions | 1 | Labels/fixups provide a base; complete runtime and backend interfaces (open). |
| 28 | No unfinished placeholders | 1 | Input handlers are real; native graphics still restricts scenes and opaque rectangle coverage (open). |
| 29 | Configuration understandable | 1 | Backend choice documented; add native manifests and complete default migration (open). |
| 30 | Conventions followed | 1 | Win64/PE is exercised but manual; broaden ABI validation and abstractions (open). |
| 31 | Automated tests provided | 2 | Native compiler/runtime automated tests exist. |
| 32 | Core tests covered | 2 | Generated-app globals are inspected after window-local messages. |
| 33 | Failure scenarios tested | 2 | Invalid mouse arguments/keys and bitmap allocation-failure injection are covered. |
| 34 | Edge cases explicitly tested | 2 | Taps, repeats, simultaneous buttons, actual OS capture, wheel accumulation and draw-only behavior are tested. |
| 35 | Integration behavior tested | 2 | Generated PE is launched and actual client pixels sampled. |
| 36 | Documented test commands work | 2 | Documented Python and extension validation commands run successfully. |
| 37 | Builds and compilation pass | 2 | All 102 tests and static checks pass; native sample builds to 13,312 bytes. |
| 38 | Results recorded accurately | 2 | Current records agree on exact reviewed900106e, 72/100 and102tests. README correction is explicitly unscored. |
| 39 | Regression checks performed | 2 | Full suite and prior slow-draw/failure/resource regressions pass. |
| 40 | Verified against original goal | 0 | Only a prototype subset is verified; implement and verify full scope (open). |
| 41 | Installation instructions accurate | 1 | Subset installation is documented; complete native engine installation is missing (open). |
| 42 | Setup reproducible | 1 | Subset setup is reproducible; full engine setup is missing (open). |
| 43 | Usage understandable | 1 | Keyboard/mouse controls are documented after #59 correction; broader workflows remain unavailable (open). |
| 44 | Design decisions documented | 2 | Migration design and limits are documented. |
| 45 | Troubleshooting available | 0 | Native runtime troubleshooting remains limited; expand API/resource/platform failure guidance (open). |
| 46 | Opens in intended environment | 1 | CLI/editor automation works; complete native project/editor/runtime workflow (open). |
| 47 | Editor integration works | 1 | Grammar checks pass; current installed package is 0.1.4, fresh visual check absent (open). |
| 48 | Deliverables organized | 2 | Deliverables are organized and pushed. |
| 49 | Limitations disclosed | 2 | Native limitations are disclosed. |
| 50 | Practical for intended scope | 0 | Full game-engine/Forge scope remains incomplete (open). |
| | **Requirement fulfillment** | **11/20** | |
| | **Functionality and reliability** | **19/20** | |
| | **Code quality and architecture** | **13/20** | |
| | **Testing and verification** | **18/20** | |
| | **Developer experience and delivery** | **11/20** | |
| | **Total** | **72/100** | Exact commit `900106e`; FAIL against 98. |

### Deduction details and follow-up

- **Native mouse milestone: VERIFIED.** Client coordinates, all three buttons, repeats/taps, OS capture/release, focus/cancel, fractional wheel and draw-only consumption pass independent generated-app tests. Full score72/100 remains below98.
- **Native product scope: OPEN.** Native 3D/camera, other shapes, assets, physics, networking, project manifests, broader language parity and Forge requirements remain unfinished. C/MSVC remains the broader default path; the final no-C/no-Rust architecture is not yet achieved.
- **Architecture and delivery: OPEN.** Reduce raw opcode/ABI duplication and encoding/platform coupling; complete runtime/platform/project interfaces, troubleshooting and editor verification.
- **Defects:** #57 flicker and #58 metadata parity remain fixed. #59 records the README native-mouse contradiction, corrected in documentation follow-up; no new runtime defect was reproduced. The full backlog remains only in issue23/comments.


## Historical 50-criterion scoring — direct native commit `120482e`

Independent reviewer evaluated exact pushed commit `120482e85e77c19216a793ab17190dbf1ae025ff`: **58/100 — FAIL** against the active **98/100** threshold. All 89 tests passed. Relative to the 56/100 review of `ade1ff6`, criteria 15 and 19 each rose by one point after the signed-minimum and non-finite diagnostic fixes. Issues #49 and #52–#54 are closed. Full explanations are in `docs/ANVIL_EVALUATION.txt`.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | No-C/no-Rust and direct PE target are written down. |
| 2 | Implicit requirements addressed | 1 | Native runtime port is recognized but incomplete. |
| 3 | Functionality matches intended goal | 0 | Native output is a numeric console subset, not the requested engine. |
| 4 | Required deliverables present | 1 | Compiler milestone, tests and docs exist; runtime parity is missing. |
| 5 | No essential feature missing | 0 | Native graphics, engine runtime and game APIs are absent. |
| 6 | Stated constraints respected | 1 | Native mode avoids C/Rust; default still requires C/MSVC. |
| 7 | Ambiguity resolved logically | 2 | Direct x64/PE target follows user selection. |
| 8 | Behavior matches documentation | 1 | Migration doc names limits, but reviewed QA records claimed 86 passing tests when two failed. |
| 9 | Important use cases supported | 1 | Simple numeric workflows run; game workflows do not. |
| 10 | Usable for intended purpose | 0 | Native mode cannot build the intended game engine. |
| 11 | Core functionality works | 0 | Requested native game-engine core is absent. |
| 12 | Secondary functionality works | 1 | Legacy C engine works; native supports only a numeric subset. |
| 13 | Primary workflows functional | 1 | Simple .ANVL to EXE workflow works; projects and engine APIs do not. |
| 14 | Inputs validated | 1 | Parser validates input; native construct coverage is limited. |
| 15 | Errors handled gracefully | 2 | Non-finite arithmetic prints a line-numbered diagnostic and exits with code 2 (issue #54). |
| 16 | Edge cases covered | 1 | Loop, booleans, args and negative integer cases are tested; broader ABI/PE cases are not. |
| 17 | Invalid inputs controlled | 2 | Native output outside the formatter range receives a diagnostic and exit code 2. |
| 18 | Stable across repeated operations | 1 | Simple runs work; recursion and stress behavior are not verified. |
| 19 | No known critical defects | 2 | Fractional output, large-range rejection, signed minimum, and non-finite diagnostics pass native executable tests. |
| 20 | Components integrate | 1 | Parser/codegen/PE integrate for small numeric programs only. |
| 21 | Logical project structure | 2 | Compiler phase, native codegen and PE modules are separated. |
| 22 | Readable and consistently formatted | 1 | Raw instruction bytes and long encodings make changes difficult to review. |
| 23 | Clear module responsibilities | 1 | No typed IR; NativeCodegen combines lowering, frames, calls and runtime helper. |
| 24 | Consistent descriptive naming | 2 | Names are broadly descriptive. |
| 25 | Duplication minimized | 1 | Opcode and frame handling repeat ad hoc patterns. |
| 26 | Dependencies appropriate | 2 | Direct backend adds no third-party compiler/runtime dependency. |
| 27 | Supports future extensions | 1 | Labels/fixups/PE offer a base but no typed IR, allocator or runtime interface. |
| 28 | No unfinished placeholders | 0 | BUILTIN_NAMES is empty and _emit_builtin always rejects calls. |
| 29 | Configuration understandable | 1 | Only C/native backend choice; no target or optimization strategy. |
| 30 | Conventions followed | 1 | Hand-coded ABI and PE conventions lack systematic validation. |
| 31 | Automated tests provided | 2 | Dedicated native tests exist. |
| 32 | Core tests covered | 1 | Coverage exercises the narrow subset rather than full language/engine. |
| 33 | Failure scenarios tested | 1 | Native divide-by-zero, frame overflow and malformed PE error paths are missing. |
| 34 | Edge cases explicitly tested | 2 | Native tests cover negative numbers, multiple args, booleans, and ascending/descending/zero-step loops. |
| 35 | Integration behavior tested | 1 | CLI creates a runnable EXE; engine integration is absent. |
| 36 | Documented test commands work | 1 | Unittest and npm commands are documented and reproducible. |
| 37 | Builds and compilation pass | 2 | Critic reran all 89 tests; extension, compileall, QA, JSON, and diff checks passed. |
| 38 | Results recorded accurately | 2 | Exact review SHA and the prior QA failures/fix are recorded; current checks and fractional-output finding match reproduced evidence. |
| 39 | Regression checks performed | 2 | Focused QA regression tests and the full suite pass after the fixture repair. |
| 40 | Verified against original goal | 0 | The broad compiler/runtime/engine request remains incomplete. |
| 41 | Installation instructions accurate | 1 | Python/Windows command exists; no full native-engine install path. |
| 42 | Setup reproducible | 1 | Limited native command is reproducible; full deployment/setup is not. |
| 43 | Usage understandable | 1 | Numeric example explains a narrow workflow. |
| 44 | Design decisions documented | 2 | Migration architecture and stages are documented. |
| 45 | Troubleshooting available | 0 | Native diagnostics/troubleshooting guide is missing. |
| 46 | Opens in intended environment | 1 | CLI works; native project/editor/runtime integration is incomplete. |
| 47 | Editor integration works | 1 | Automated grammar test passes; visible installation/highlighting of current package was not checked. |
| 48 | Deliverables organized | 2 | Exact commit is pushed and files are organized. |
| 49 | Limitations disclosed | 2 | Unsupported native systems and large-value formatting limits are disclosed; issue #52 is filed and #49 is closed. |
| 50 | Practical for intended scope | 0 | Not a usable complete game-engine deliverable. |
| | **Requirement fulfillment** | **9/20** | |
| | **Functionality and reliability** | **12/20** | |
| | **Code quality and architecture** | **12/20** | |
| | **Testing and verification** | **14/20** | |
| | **Developer experience and delivery** | **11/20** | |
| | **Total** | **58/100** | Exact commit `120482e`; FAIL against 98. |

### Deduction details and follow-up

- **Criteria 2–6, 8–10:** the full native engine/runtime and native default are missing. Port language/runtime APIs, then switch default/remove C only after parity.
- **Criteria 11, 15, 19:** native game core is absent. The critic verified fractional formatting, large-range rejection, the signed minimum, and line-numbered non-finite diagnostics; issues #49 and #52–#54 are closed.
- **Criteria 14–18:** native error paths, zero division diagnostics, stack/ABI limits, recursion and stress cases need coverage.
- **Criteria 22–30:** raw opcode emission, no typed IR, empty builtin dispatch and missing runtime interfaces impede correctness and growth. Add typed IR, instruction helpers, explicit ABI/layout validation, and engine runtime abstraction.
- **Criteria 33, 37–39:** exact reviewed commit had 2 failures in `tests.test_qa_report`; fixtures included historical score tables and hardcoded 16/20. Fixed in commit `150a042` by scoping to current table and dynamically mutating subtotal; focused tests and all 86 full-suite tests pass. Independent review of commit `597867f` confirmed this fix and the full-suite pass. Tracking issue [#51](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/51) is closed after local verification.
- **Criteria 40, 50:** the full intended product remains incomplete; this numeric backend cannot create a 2D/3D game.
- **Criteria 41–47:** no complete native setup/troubleshooting/project workflow; live VS Code highlighting not verified.

## Latest 50-criterion scoring for review `c102604`

Historical context: the independent review of commit `f96a212` scored **87/100 (87%) — FAIL**. Although its 42 tests passed, the evaluator reproduced a Windows stack overflow (0xC00000FD) at recursion depth 20 when each recursive call declared an 8,192-element local array. This was tracked with exact reproduction steps in issue #21. Commit `8f82f1c` replaced stack arrays with checked heap allocations, frees them on explicit and implicit returns, and enforces a 16 MiB active-call budget. The independent reviewer evaluated that exact commit and scored it **91/100 (91%) — PASS**. A depth-1000 stress case now exits with a source-located allocation-budget error, while a 300-call loop completes without leaking its local arrays. A later physics review of the pre-synchronization tree (based on `b00f35a`) corrected its initial 89 score to **88/100 — FAIL**. After synchronizing records, installing and visibly checking 0.1.3, and resolving issue #22, reviews of `64a4101` and `ff88152` scored **91/100 — PASS** (16/20, 20/20, 17/20, 19/20, 19/20). The independent review of `7efdfb0` scored **90/100 — PASS** (16/20, 20/20, 17/20, 18/20, 19/20). Reviews of `0d3b5ed` and `51deb5d` scored **90/100 — PASS**. The review of `c4f3ec6` scored **88/100 — FAIL** because four docs contained stale complexity claims. Commit `560cee1` corrected those documents; a fresh independent review confirmed the fix and scored `560cee1` **90/100 — PASS** (16/20, 20/20, 17/20, 19/20, 18/20). The friction feature commit `f7c91b0` scored **87/100 — FAIL** (15/20, 20/20, 17/20, 18/20, 17/20) because of stale high-level feature and QA records plus missing friction edge-case tests. Follow-up commits `e1e3768` and `83891c6` synchronized the records and added those tests. Its independent review scored **90/100 — PASS** (16/20, 20/20, 17/20, 19/20, 18/20). The division-diagnostic commit `12b4e55` also scored **90/100 — PASS** with the same category totals; it reran all 56 tests, extension/Python validation, an MSVC numeric sample build/run, diff check, and verified the 450-item inventory. The reviewer found no defect in the new diagnostic, and item #48 is complete. Remaining deductions concern overall engine scope, compiler structure/platform breadth, and unverified new extension highlighting. See issues #8 and #24.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Compiler, runtime, language, extension, and documentation requirements are identified. |
| 2 | Implicit requirements addressed | 1 | The broad game-engine backlog is only partly implemented; planned systems remain. |
| 3 | Functionality matches intended goal | 1 | Working Windows prototype, but not the requested full engine. |
| 4 | Required deliverables present | 2 | Repository includes compiler, runtime, docs, examples, tests, and VS Code extension. |
| 5 | No essential feature missing | 1 | GPU renderer, assets, audio, 3D/advanced physics, and broader multiplayer remain unfinished. |
| 6 | Stated constraints respected | 2 | `.ANVL` is consistently used as requested. |
| 7 | Ambiguity resolved logically | 2 | Current C/MSVC prototype scope and limitations are documented. |
| 8 | Behavior matches documentation | 2 | Critic `65c15bf` confirmed the spec prohibits repeated `-l` and `-rotate` modifiers, matching compiler behavior; issue #43 is resolved. |
| 9 | Important use cases supported | 1 | Simple native 2D/3D demonstrations work; broader engine use cases are missing. |
| 10 | Usable for intended purpose | 2 | Usable for small learning and prototyping scenes. |
| 11 | Core functionality works | 2 | The reviewer confirmed `receive()` rejects a non-finite UDP value with the promised source-located diagnostic; issue #30 is resolved. |
| 12 | Secondary functionality works | 2 | Timing, input, math/noise, networking primitive, and native-tested `while`/`for` loops are covered. |
| 13 | Primary workflows functional | 2 | Direct source and manifest build/run workflows pass. |
| 14 | Inputs validated | 2 | Critic `0abba63` verified Arabic-Indic digits are rejected by the Anvil lexer and 5,000-digit array sizes return a controlled limit diagnostic; issues #37 and related verification are closed. |
| 15 | Errors handled gracefully | 2 | The Unicode number and extreme array-size cases now fail with source-located diagnostics and without tracebacks; independent critic verified on `0abba63`. |
| 16 | Edge cases covered | 2 | New regression tests cover Unicode decimal input and 5,000-digit array declarations; the critic confirmed 66 tests pass. |
| 17 | Invalid inputs controlled | 2 | Invalid Unicode numeric syntax and oversized arrays fail before C generation; verified on `0abba63`. |
| 18 | Stable across repeated operations | 2 | Compiler/runtime tests and repeatable random/noise checks pass. |
| 19 | No known critical defects | 2 | The recursive-array stack-exhaustion finding is fixed; the physics reviewer found no critical issue in the reviewed physics paths. |
| 20 | Components integrate | 2 | Compiler, generated C, runtime, manifest, extension, and networking sample integrate. |
| 21 | Logical project structure | 2 | Compiler, runtime, examples, tests, docs, and extension are organized. |
| 22 | Readable and consistently formatted | 2 | Independent review `5072597` confirmed Black 26.10.1 default formatting and no lines over 88 columns in the five cited compiler modules. |
| 23 | Clear module responsibilities | 2 | Independent review of `96b71fe` confirmed separate lexer, parser, semantic, expression, code-generation, build, CLI, and shared-definition modules, with a compatibility facade and phase tests. |
| 24 | Consistent descriptive naming | 2 | Anvil identity and `.ANVL` naming are consistent. |
| 25 | Duplication minimized | 2 | Reviewer found no material duplicate/unused code issue. |
| 26 | Dependencies appropriate | 2 | Core compiler uses Python standard library and the documented native toolchain. |
| 27 | Supports future extensions | 1 | Current runtime/backend is Windows/MSVC and C-only. |
| 28 | No unfinished placeholders | 2 | Unsupported capabilities are described as future work. |
| 29 | Configuration understandable | 2 | TOML project settings are explicit and validated. |
| 30 | Conventions followed | 2 | Current Python, C, TOML, and extension conventions are adequate. |
| 31 | Automated tests provided | 2 | The independent critic reran all 73 Python tests on exact candidate `f12c0ac`; extension and compileall checks also passed. |
| 32 | Core tests covered | 2 | Compiler, runtime, networking, projection, circle/box collisions, pool capacity, and generated executable paths are covered. |
| 33 | Failure scenarios tested | 2 | Invalid syntax, references, manifests, settings, and paths have regression tests. |
| 34 | Edge cases explicitly tested | 2 | Critic `eec0608` reran native MSVC regressions for the prior `±1e308` segment case, extreme triangle intersections, and viewport line clipping; all produce finite bounded results. |
| 35 | Integration behavior tested | 2 | Native runtime and compiler-to-executable flows are exercised. |
| 36 | Documented test commands work | 2 | Documented Python and npm checks pass. |
| 37 | Builds and compilation pass | 2 | MSVC builds pass for manifest, function, and physics samples. |
| 38 | Results recorded accurately | 2 | On follow-up review `c102604`, both status JSON files parse as strict UTF-8 and the critic confirmed the prior SHA/encoding finding (#48) is fixed. The ledger totals 450 with 26 audited rows and items #391–394 complete. |
| 39 | Regression checks performed | 2 | Critic `c102604` reran 77 tests, extension validation, compileall, QA arithmetic, strict JSON/status parity, and diff check; native mouse input integration passes. |
| 40 | Verified against original goal | 1 | The full suite verifies the current prototype, not the full requested engine breadth. |
| 41 | Installation instructions accurate | 2 | Python, MSVC, and VSIX workflows are documented. |
| 42 | Setup reproducible | 2 | Compiler, runtime, and extension checks have repeatable commands. |
| 43 | Usage understandable | 2 | Guides and examples explain the supported syntax and build path. |
| 44 | Design decisions documented | 2 | The language specification documents the one-location/one-rotation modifier rule; critic `65c15bf` confirmed it matches compiler behavior. Issue #43 is resolved. |
| 45 | Troubleshooting available | 2 | README and compiler guide provide setup/troubleshooting information. |
| 46 | Opens in intended environment | 2 | The evaluator confirmed extension 0.1.4 installed; visible Anvil mode had previously been verified for the ray-backend sample. |
| 47 | Editor integration works | 1 | **Problem:** newer grammar tokens are not verified in the installed editor. **Evidence:** automated grammar validation passes, but the user kept 0.1.4 installed. **Impact:** visible syntax coloring for newer built-ins remains unverified. **Status:** pending user preference; tracked in issue [#24](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/24). |
| 48 | Deliverables organized | 2 | Source, runtime, examples, tests, docs, extension grammar, and packaged VSIX are in their expected folders; the reviewer confirmed a clean worktree before and after verification. |
| 49 | Limitations and assumptions disclosed | 2 | Prototype scope, Windows/MSVC backend, ray trace cap, and network limits are stated. |
| 50 | Practical for stated scope | 1 | Suitable for educational demos, not production game development. |
| | **Requirement fulfillment** | **16/20** | |
| | **Functionality and reliability** | **20/20** | |
| | **Code quality and architecture** | **19/20** | |
| | **Testing and verification** | **19/20** | |
| | **Developer experience and delivery** | **18/20** | |
| | **Total** | **92/100** | Exact review `c102604`; FAIL under the 98-point requirement. |

### Deduction details and follow-up

- **Resolved QA arithmetic finding #44.** Review `0c75929` found that valid 0-point criterion rows were excluded by the validator. Commit `7c1385c` accepts scores 0–2 and adds valid-zero and malformed-subtotal regressions; the independent critic verified both. Issue #44 is closed.

- **Previous critic finding on `0abba63` (88/100 — FAIL; required pass score 98; resolved).** Issue [#43](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/43), labeled `Codex Bugs`, records exact reproduction: `display text("Hi") -l(1,2) -l(3,4)` is admitted by the repeated-style grammar but rejected by `emit_display` because a second location modifier remains in the command. Restrict the spec to at most one location and one rotation modifier. The critic confirmed prior findings #37–#42 were fixed; those issues have resolution comments and are closed.
- **Previous deductions on criteria 8 and 44 — resolved.** The `65c15bf` critic confirmed the duplicate-modifier grammar now matches the compiler. Broader requirement and practical-scope deductions remain because the engine is still a prototype. The latest review corrected input/error/edge-case rows 14–17 to 2 after verifying the new guards and regressions.

- **Issues #32, #33, and #34 — resolved:** the critic of `ed08f43` verified the 5,000-digit diagnostic, the progress wording fix, and the correction distinguishing the 64-test `ed08f43` run from the 63-test `2dd1d8e` run.
- **Issues #35 and #36 — resolved:** review `727d349` verified that rubric rows sum to 89 and the Markdown implementation ledger matches JSON. The evaluator's 89/100 score remains below the user's 98-point bar for broader engine-scope, architecture, and editor-verification reasons.
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

### Remaining deductions and follow-up

- **Issue #12 — compiler architecture and formatting: RESOLVED.** Independent review `5072597` confirmed the phase split, compatibility, phase tests, documentation, Black formatting, and 88-column limit. Issue #12 is closed.
- **Issue #45 — state-field ambiguity: RESOLVED.** The critic found that `current_active_item: 22` was ambiguous beside `last_completed_backlog_item: 104` and a zero in-progress count. The sync clears the active backlog item, documents no item as active, and stores `last_reviewed_rubric_criterion: 22` separately. The `Codex Bugs` issue is documented and closed after syncing.
- **Platform/backend breadth:** the project remains Windows/MSVC and generated-C only (criterion 27: 1/2).
- **Editor visual verification:** newer extension grammar is automated-tested but the user chose to keep extension 0.1.4 installed, so criterion 47 remains 1/2.
- **Engine scope:** asset/audio pipelines, GPU rendering, broad physics, and production multiplayer remain future work (criteria 2, 3, 5, 9, 40, and 50).

### Priorities from the review

1. Continue the game-engine backlog: GPU rendering, assets, audio, physics, richer data structures, robust networking, benchmarks, and portability.
2. Split and format the compiler into clear parser, validation, C generation, and build modules.
3. Keep evaluation scores and verification results synchronized with every fresh review.

## Bug tracking

Issues [#1](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/1)–[#4](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/4) track earlier corrected report defects and are closed. The detailed evaluator findings are recorded in [#13](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/13) (VS Code 0.1.3 install/highlighting), [#16](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/16) (historical QA synchronization), [#17](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/17) (finding classification), [#18](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/18) (tracked generated C), [#19](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/19) (test output side effects), [#20](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/20) (evaluation arithmetic), [#21](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/21) (recursive local-array stack exhaustion), and [#22](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/22) (QA synchronization after physics). Item #50 review findings [#37](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/37)–[#42](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/42) are fixed and closed after independent confirmation; the display grammar finding [#43](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/43) is fixed and closed; the QA arithmetic follow-up [#44](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/44) is fixed and closed. Broader implementation gaps remain open in [#5 GPU and ray-tracing backends](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/5), [#6 asset pipeline](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/6), [#7 audio](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/7), [#8 extended physics](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/8), [#9 remaining array forms/structures/modules](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/9), [#10 multiplayer](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/10), [#11 portability and Rust backend](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/11), [#12 compiler readability and modularity](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/12), [#14 performance benchmarks](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/14), and [#15 completion matrix/full-scope tracking](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/15).


### Fresh critic result — mouse input candidate `d757c79`

- **Exact reviewed commit:** `d757c797751f40eee47fd518c3cf6dd3a3ae790c`.
- **Score:** **91/100 — FAIL** against the required 98. Category scores: requirements 16/20; functionality/reliability 20/20; architecture 19/20; testing/verification 18/20; delivery 18/20. Full criterion vector: `2,1,1,2,1,2,2,2,1,2 / 2,2,2,2,2,2,2,2,2,2 / 2,2,2,2,2,2,1,2,2,2 / 2,2,2,2,2,2,2,1,2,1 / 2,2,2,2,2,2,1,2,2,1`.
- **Finding:** criterion 38 is 1/2 because `docs/IMPLEMENTATION_STATUS.json` and `docs/CODEX_AUTONOMOUS_STATE.json` are not valid UTF-8 JSON; permissive decoding also reveals a stale candidate SHA and pending status that do not match reviewed HEAD. Ledger counts still total 450.
- **Independent checks:** 77 Python tests, npm extension validation, Python compileall, QA validator invocation, and diff check passed. Mouse integration exercised resize-aware coordinates, letterbox exclusion, all three button edge/held/release states, and wheel reset. The existing QA validator still reported the old 92-point rubric, so this fresh result must replace it.
- **Limit:** no live mouse-enabled game window was visually inspected. No mouse implementation defect was reproduced.


### Fresh critic result — corrected status snapshot `c102604`

- **Exact reviewed commit:** `c10260483eab6b5adaadd261a66a92a9138b9ed8`.
- **Score:** **92/100 — FAIL** against 98. Categories: requirements 16/20; functionality/reliability 20/20; architecture 19/20; testing/verification 19/20; delivery 18/20. Criterion 38 is restored to 2/2; all other criterion scores match the previous review of `d757c79`.
- **Verification:** 77 Python tests; npm extension validation; compileall; QA validator (50 criteria total 92); strict UTF-8 parsing and status parity; and diff check all pass. The ledger has 26 audited items and totals `424 + 3 + 21 + 2 = 450`. Mouse integration passed synthetic native checks for resize-aware mapping, letterbox exclusion, three mouse-button states, and wheel reset.
- **Issue #48:** fixed in this snapshot and closed after strict JSON and rubric validation. The previous `d757c79` review remains recorded at 91/100; this exact follow-up snapshot scores 92/100.
- **Remaining gap:** partial criteria 2, 3, 5, 9, 27, 40, 47, and 50 leave the 98/100 threshold unmet by six points. No mouse code defect was found; no live mouse-enabled window was visually inspected.
