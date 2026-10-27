# Anvil implementation status

This is an initial evidence inventory for all 450 entries mirrored from GitHub issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23). The issue remains the user-maintained source of truth; it was not modified. Items without an audited implementation are marked NEEDS VERIFICATION rather than guessed complete or missing. See `IMPLEMENTATION_STATUS.json` for evidence, tests, limitations, acceptance checks, priority, linked issue, and commit per item.

Generated 2026-10-27 against independently reviewed commit `83891c6fe801659e350defa2e080b30fb914963b` on `main`.

## Status counts

- COMPLETE: 8
- PARTIALLY IMPLEMENTED: 3
- NOT IMPLEMENTED: 0
- BLOCKED: 0
- NEEDS VERIFICATION: 439
- IN PROGRESS: 0

## Audited current items

| # | Item | Status | Evidence and remaining work |
|---:|---|---|---|
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
- `NEEDS VERIFICATION` is the conservative initial status until source/test evidence is explicitly audited. It is not a claim that the feature is absent.
- Do not close issue #23 until all backlog requirements are genuinely delivered or explicitly resolved by the user.
