# Anvil implementation status

The full 450-item list is maintained only in the body and comments of GitHub issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23). This compact ledger records evidence only for items already audited or in progress; it does not duplicate the full item list. `IMPLEMENTATION_STATUS.json` holds the same audited subset as structured data.

Updated 2026-10-27 from independent code review of exact commit `ed08f43ca0d9beb5440f18fade48faf556694b1f`; the latest evaluation is 89/100, below the required 98/100 bar. The critic confirmed the 64-test result and fixes for issues #32/#33; issue #34's historical test-count mismatch is corrected and closed. The latest documentation review of `c648ccb` found that the criterion score arithmetic and Markdown status summary needed synchronization; issues #35/#36 track those corrections.

## Status counts

- COMPLETE: 12
- PARTIALLY IMPLEMENTED: 3
- NOT IMPLEMENTED: 0
- BLOCKED: 0
- NEEDS VERIFICATION: 435
- IN PROGRESS: 0

## Audited current items

| # | Item | Status | Evidence and remaining work |
|---:|---|---|---|
| 46 | Add short-circuit Boolean evaluation. | COMPLETE | `compiler/anvil.py` maps `and`/`or` to C `&&`/`||`; the native side-effect test confirms false `and` / true `or` skip calls while true `and` / false `or` execute them. The independent reviewer confirmed behavior on `83cf626` (57 tests passed). The overall QA score was 89/100 due to unrelated stale count text in the QA report; see issue #28. |
| 47 | Add explicit overflow behavior. | COMPLETE | `anvil_check_number` guards arithmetic and all numeric built-in results, including `receive()`. Native cases cover arithmetic, comparison, invalid math, accumulation, loop-step overflow, end-to-end NaN/finite UDP datagrams, and no-socket receive behavior. The full suite passes (61 tests); extension and static checks pass; independent review of `15439b5` confirmed the behavior. Issues #30 and #31 are resolved and closed. Overall QA remains below 98/100. |
| 48 | Add division-by-zero diagnostics. | COMPLETE | `compiler/anvil.py` lowers `/` through `anvil_divide`; `runtime/anvil_runtime.c` reports path/line and exits 2 on zero (including negative zero). Native tests cover zero diagnostic and regular division; the independent reviewer confirmed the behavior on commit `12b4e55` (90/100 PASS). Runtime detection only; no compile-time constant analysis. |
| 49 | Add language feature versioning. | COMPLETE | Optional leading `language version 1` declaration; unversioned files keep version 1 behavior. Independent review `ed08f43` verified all 64 tests and the 5,000-digit source-located diagnostic. Issues #32/#33 are fixed and closed. Only version 1 is implemented. |
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
