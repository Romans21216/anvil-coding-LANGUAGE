# Anvil implementation status

The full 450-item list is maintained only in the body and comments of GitHub issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23). This compact ledger records evidence only for items already audited or in progress; it does not duplicate the full item list. `IMPLEMENTATION_STATUS.json` holds the same audited subset as structured data.

Updated 2026-10-27 from independently reviewed implementation commit `83cf626b0a5ab370d5a6da476ea47bbc2a9f728a`. Item #46 is complete; the overall review's stale QA test-count finding remains tracked in issue #28.

## Status counts

- COMPLETE: 10
- PARTIALLY IMPLEMENTED: 3
- NOT IMPLEMENTED: 0
- BLOCKED: 0
- NEEDS VERIFICATION: 437
- IN PROGRESS: 0

## Audited current items

| # | Item | Status | Evidence and remaining work |
|---:|---|---|---|
| 46 | Add short-circuit Boolean evaluation. | COMPLETE | `compiler/anvil.py` maps `and`/`or` to C `&&`/`||`; the native side-effect test confirms false `and` / true `or` skip calls while true `and` / false `or` execute them. The independent reviewer confirmed behavior on `83cf626` (57 tests passed). The overall QA score was 89/100 due to unrelated stale count text in the QA report; see issue #28. |
| 48 | Add division-by-zero diagnostics. | COMPLETE | `compiler/anvil.py` lowers `/` through `anvil_divide`; `runtime/anvil_runtime.c` reports path/line and exits 2 on zero (including negative zero). Native tests cover zero diagnostic and regular division; the independent reviewer confirmed the behavior on commit `12b4e55` (90/100 PASS). Runtime detection only; no compile-time constant analysis. |
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
