# Anvil implementation status

The full 450-item list is maintained only in the body and comments of GitHub issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23). This compact ledger records evidence only for items already audited or in progress; it does not duplicate the full item list. `IMPLEMENTATION_STATUS.json` holds the same audited subset as structured data.

Updated 2026-10-27. Latest independent review is exact commit `597867f44a5140db27fdce2e4f2339859ef96af8` at 54/100 — FAIL against 98. The reviewer passed all 86 tests and confirmed the QA fix. Native fractional output truncation remains open in issue #49. Prior direct-native score 50/100 applies to 573cb44; prior C-backed 92/100 remains tied to c102604.

## Status counts

- COMPLETE: 21
- PARTIALLY IMPLEMENTED: 5
- NOT IMPLEMENTED: 0
- BLOCKED: 0
- NEEDS VERIFICATION: 420
- IN PROGRESS: 4

Item #172 resize was reviewed on `f12c0ac` (92/100), and item #185 on `eec0608` (92/100). The latest corrected status snapshot `c102604` scored 92/100, below the 98/100 threshold; its UTF-8/status mismatch is fixed. Candidate `9d9bf90` adds BMP resources and sprites and is pending independent review.

## Audited current items

| # | Item | Status | Evidence and remaining work |
|---:|---|---|---|
| 46 | Add short-circuit Boolean evaluation. | COMPLETE | `compiler/anvil.py` maps `and`/`or` to C `&&`/`||`; the native side-effect test confirms false `and` / true `or` skip calls while true `and` / false `or` execute them. The independent reviewer confirmed behavior on `83cf626` (57 tests passed). The overall QA score was 89/100 due to unrelated stale count text in the QA report; see issue #28. |
| 47 | Add explicit overflow behavior. | COMPLETE | `anvil_check_number` guards arithmetic and all numeric built-in results, including `receive()`. Native cases cover arithmetic, comparison, invalid math, accumulation, loop-step overflow, end-to-end NaN/finite UDP datagrams, and no-socket receive behavior. The full suite passed on the reviewed compiler refactor (72 tests); extension and static checks pass; independent review of `15439b5` confirmed the behavior. Issues #30 and #31 are resolved and closed. Overall QA remains below 98/100. |
| 48 | Add division-by-zero diagnostics. | COMPLETE | `compiler/anvil.py` lowers `/` through `anvil_divide`; `runtime/anvil_runtime.c` reports path/line and exits 2 on zero (including negative zero). Native tests cover zero diagnostic and regular division; the independent reviewer confirmed the behavior on commit `12b4e55` (90/100 PASS). Runtime detection only; no compile-time constant analysis. |
| 49 | Add language feature versioning. | COMPLETE | Optional leading `language version 1` declaration; unversioned files keep version 1 behavior. Independent review `ed08f43` verified all 64 tests and the 5,000-digit source-located diagnostic. Issues #32/#33 are fixed and closed. Only version 1 is implemented. |
| 50 | Publish a complete formal language specification. | COMPLETE | `docs/LANGUAGE_SPEC.md` records the v1 contract and links from README/guide/wiki; its example builds and prints `6`. Critic `65c15bf` confirmed the duplicate-modifier rule matches compiler behavior and issues #37–#43 are resolved. The critic verified 67 tests on `65c15bf`; independent review of `96b71fe` passed 72 tests and confirmed compiler compatibility. Latest overall score is 90/100, below 98 because of broader engine scope, platform limits, and editor verification; QA issue #44 is closed. |
| 101 | Separate lexical analysis from parsing. | COMPLETE | Independent critic `96b71fe` confirmed lexer/parser module separation, preserved CLI/facade behavior, 72 passing tests, and byte-identical generated C for 12 examples. Formatting follow-up is tracked separately in issue #12. |
| 102 | Separate parsing from semantic validation. | COMPLETE | `parse_syntax` produces a `ParsedProgram`; `validate_program` resolves references and C symbol collisions. Phase-boundary tests and the independent critic verified the split on exact review `96b71fe`. |
| 103 | Separate semantic validation from C generation. | COMPLETE | `compiler/semantics.py` validates before `compiler/codegen.py` emits C. The independent critic confirmed generated output is byte-identical for 12 representative examples against `854d36c`. |
| 104 | Separate C generation from build orchestration. | COMPLETE | `compiler/codegen.py`, `compiler/build.py`, and `compiler/cli.py` have separate responsibilities. The critic confirmed both CLI invocation forms and the 21-definition legacy facade. Issue #12 is resolved and closed. |
| 172 | Add dynamic window resizing. | IN PROGRESS | `runtime/anvil_projection.h::anvil_compute_viewport` computes a centered aspect-preserving viewport; `runtime/anvil_runtime.c` paints the fixed 960×600 image into the current client area. `tests/test_runtime.py` covers wide, tall, same-aspect, and invalid client sizes. The game window is already created with `WS_OVERLAPPEDWINDOW`; internal framebuffer resolution remains fixed. Canonical backlog source is issue #23 comment 6451810775; item #144 remains unverified. The critic confirmed the tracking correction on `f12c0ac`; a live resize was not visually inspected. |
| 185 | Add robust near-plane clipping. | IN PROGRESS | Commit `cfce407` adds camera-space clipping for triangles, grid segments, and sphere hits. Commit `15ac43a` fixes the overflow reproduced by review `4bc8bc3` using stable interpolation, finite-output checks, and pre-raster screen clipping. Critic `eec0608` confirmed the regression fix and all 74 tests. No live window was visually inspected; far-plane and side-frustum clipping remain out of scope. |
| 201 | Add texture file loading. | PARTIALLY IMPLEMENTED | `runtime/anvil_runtime.c::anvil_image_load` safely loads bounded uncompressed BMP images; other formats and 3D texture mapping remain unsupported. Full test suite and sample build pass; independent review pending. |
| 202 | Add texture unloading. | IN PROGRESS | Explicit `image_destroy`, shutdown cleanup, and generation-checked stale-handle rejection are implemented and tested; independent review pending. |
| 209 | Add sprite rendering. | IN PROGRESS | `image_draw` / `image_draw_scaled` render clipped, alpha-blended screen-space BMP sprites; native regression and `examples/image_sprite.ANVL` pass/build. Independent review pending. |
| 212 | Add sprite rotation and scaling. | PARTIALLY IMPLEMENTED | Nearest-neighbor scaling is implemented and tested; sprite rotation remains absent. |
| 391 | Add mouse input support. | COMPLETE | `mouse_x()`, `mouse_y()`, `mouse_pressed(button)`, `mouse_held(button)`, and `mouse_wheel()` are added to the compiler/runtime. Native integration coverage verifies input edges, wheel detents, resize mapping, and letterbox rejection. Independent critic verified the implementation and native regressions on `d757c79`; live mouse-window visual inspection remains absent. |
| 392 | Add mouse position tracking. | COMPLETE | Pointer coordinates are mapped through the current aspect-preserving viewport into the fixed 960×600 frame; letterbox bars return `-1`. Native test coverage is added; independent critic verified the implementation on `d757c79`; live mouse-window visual inspection remains absent. |
| 393 | Add mouse button events. | COMPLETE | Left/right/middle button edges and held state are captured; focus loss clears held state. Native regression covers left click edge, held, release, and edge clearing. Independent critic verified the implementation on `d757c79`; live mouse-window visual inspection remains absent. |
| 394 | Add mouse wheel input. | COMPLETE | Signed wheel detents are exposed for a single fixed update. Native regression covers positive and negative signed detents and reset on the next update; independent critic verified the implementation on `d757c79`. Live mouse-window visual inspection remains absent. |
| 301 | Improve the existing bounded 2D circle physics prototype. | PARTIALLY IMPLEMENTED | runtime/anvil_runtime.c: bounded fixed-step circle/axis-aligned-box solver; docs/ENGINE.md. No CCD, rotation, broad phase, joints, 3D bodies, or complete stability coverage. Issue #8; commit `f7c91b0`. |
| 302 | Make the current 128-body limit configurable where feasible. | COMPLETE | runtime/anvil_runtime.c: physics_capacity and active-capacity-bounded loops; tests/test_compiler.py: growth, exhaustion, invalid values, refused shrink, shrink after release. The configured active pool still has a fixed compiled maximum of 128 slots. Issue #8; commit `560cee1`. |
| 303 | Add rectangle collision bodies. | COMPLETE | runtime/anvil_runtime.c: axis-aligned rectangle bodies and box contacts; examples/physics_boxes.ANVL. Rectangles are axis aligned and cannot rotate. Issue #8; commit `0d3b5ed`. |
| 311 | Add friction. | COMPLETE | `runtime/anvil_runtime.c` implements Coulomb tangent impulses; `docs/ENGINE.md` specifies range/default/mixing; `examples/physics_friction.ANVL` demonstrates behavior. The independent reviewer confirmed native tests for stopping, invalid values, zero friction, and geometric-mean mixing. Broader physics remains limited. Issue #8; commit `e1e3768`, reviewed at `83891c6`. |
| 312 | Add restitution configuration. | COMPLETE | runtime/anvil_runtime.c: body_restitution setter and contact solver. Current restitution API is per-body; material assets are not part of this item. Issue #8; commit `64a4101`. |
| 337 | Add static bodies. | COMPLETE | runtime/anvil_runtime.c: mass-zero static bodies and positive-mass dynamic bodies; docs/ENGINE.md. No kinematic body mode is implemented. Issue #8; commit `64a4101`. |
| 338 | Add dynamic bodies. | COMPLETE | runtime/anvil_runtime.c: mass-zero static bodies and positive-mass dynamic bodies; docs/ENGINE.md. No kinematic body mode is implemented. Issue #8; commit `64a4101`. |
| 350 | Document the physics solver and its limitations. | COMPLETE | docs/ENGINE.md: solver passes, contact shapes, limits, complexity, and unsupported behavior. Documentation describes the prototype, not a production rigid-body solver. Issue #8; commit `7de7d4a`. |
| 372 | Preserve CPU BVH as a supported backend. | COMPLETE | runtime/anvil_runtime.c: CPU BVH is the implemented ray backend; docs/ENGINE.md. GPU/DXR/Embree do not exist; only CPU BVH is available. Issue #5; commit `51deb5d`. |
| 376 | Add backend capability detection. | PARTIALLY IMPLEMENTED | runtime/anvil_runtime.c: ray_backend_available reports backend availability. Detection is limited to current compiled backend support; broader hardware/backend capability probing is absent. Issue #5; commit `51deb5d`. |
| 449 | Keep the existing automated tests, extension validation, and QA reports synchronized with every release. | PARTIALLY IMPLEMENTED | docs/QA_REPORT.md; tests/; vscode-extension/scripts/validate.js. This remains an ongoing release-process requirement; future releases must keep status synchronized. Issue #15; commit `f7c91b0`. |

## Audit policy

- `COMPLETE` means the item-specific behavior has source evidence, tests, documentation, and review; preserve any listed limits.
- `PARTIALLY IMPLEMENTED` means a working subset exists but one or more listed acceptance parts are missing.
- The counts summarize the 450 entries in issue #23, but unverified entries are not copied into this ledger. `NEEDS VERIFICATION` is a conservative status, not a claim that a feature is absent.
- Do not close issue #23 until all backlog requirements are genuinely delivered or explicitly resolved by the user.


Issue #48 is resolved. Strict UTF-8 parsing passes for both JSON status records; the latest reviewed snapshot `c102604` is recorded at 92/100, below the required 98. The current sprite candidate is pending independent review.
