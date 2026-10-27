# Anvil QA Report

**Review date:** 2026-10-27  
**Source format:** `.ANVL`  
**Latest completed independent evaluation:** **86/100 — FAIL** (requested threshold: 90/100; review preceded the new `while` feature)

## Scope

Anvil is an early Windows-focused language and game-runtime prototype. The compiler validates BASIC/Lua-inspired `.ANVL` programs, emits C, and invokes MSVC to create a native `.exe`. The runtime has a fixed-size software 2D/3D renderer, keyboard camera controls, fixed-step updates, seeded random/noise functions, a minimal numeric UDP API, and built-in `ray_sphere(x,y,z,radius)`. Ray spheres use CPU BVH traversal, diffuse/specular lighting, and hard-shadow queries; the documented per-batch limit is 32. This is not a production engine. Assets, audio, physics, cross-platform support, a Rust backend, RTX/DXR, and Embree remain unimplemented.

The `.ANVL` suffix was chosen by the user. Functions support numeric parameters, numeric return values, recursion, and function-local numeric state. `while` loops are implemented; `for` loops, arrays, user-defined structures, and modules/imports are not implemented.

## Verification

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -q` | PASS — 32 tests (including `while` execution and missing-condition diagnostics) |
| `npm test --prefix vscode-extension` | PASS — extension manifest/config and TextMate token scopes |
| Build `game.ANVLproj` with MSVC | PASS — reviewer built `build/audit_360_game.exe` |
| Build and run `examples/functions.ANVL` | PASS — reviewer built executable; it printed `13` |
| Native runtime integration | PASS — fixed-step updates, delta, queued Space key edge, and clean shutdown covered |
| Projected sphere bounds regression | PASS — compiled production projection helper sampled sphere surfaces at centered, off-axis, and near-camera positions |
| VS Code package | PASS — VSIX package exists and extension grammar checks pass |
| VS Code extension installation | PASS — installed VSIX with VS Code 1.143.1; `code --list-extensions --show-versions` reports `anvil-engine.anvil-language-support@0.1.0` |
| VS Code language mode and visible sample highlighting | NOT VISUALLY VERIFIED in this review |
| Live game window visual inspection | NOT PERFORMED in the latest independent review |

Earlier display and editor evidence in prior reports is historical, not part of the latest independent review. Current test/build results demonstrate a working prototype path, not production readiness or measured performance.

## Independent 50-criterion review

The latest completed full independent reviewer scored the project **86/100**, below the 90-point acceptance threshold, before the `while` feature was added. A focused follow-up review passed loop parsing, nesting, and code generation; it did not rescore the full 50-criterion rubric. The rubric below is retained as the previous full review.

| Criteria | Scores |
|---|---|
| 1–10: Requirement fulfillment | 2, 1, 1, 2, 1, 2, 2, 1, 1, 2 (**15/20**) |
| 11–20: Functionality and reliability | 2, 2, 2, 2, 2, 2, 2, 2, 2, 2 (**20/20**) |
| 21–30: Code quality and architecture | 2, 1, 1, 2, 2, 2, 1, 2, 2, 2 (**17/20**) |
| 31–40: Testing and verification | 2, 2, 2, 2, 2, 2, 2, 0, 2, 1 (**17/20**) |
| 41–50: Developer experience and delivery | 2, 2, 2, 2, 2, 1, 1, 2, 2, 1 (**17/20**) |
| **Total** | **86/100 — FAIL** |

Main deductions: the full engine backlog is substantially incomplete; compiler responsibilities and formatting are concentrated in one file; visible editor language mode was not verified; and evaluation documents had become stale and contradictory. Criterion 38 scored zero because the prior QA report had inaccurate test counts and a superseded score. Both confirmed documentation issues have since been corrected and closed. The Python suite now passes 32 tests, and this report records the added loop feature. VS Code installation was confirmed after the prior full review.

## Bug tracking

The reviewer filed [issue #1](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/1), **Codex Bugs: evaluation documents contradict current compiler and test results**, and [issue #2](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/2), **Codex Bugs: compiler guide says while loops are unsupported**. Both carried the `Codex Bugs` label and were closed after the reports were corrected. Missing roadmap features are not classified as bugs.

## Next priorities

1. Continue implementing the user's improvement backlog in small, tested increments.
2. Split parser, validation, C generation, and build orchestration into modules.
3. Visually verify the installed extension's language mode and sample highlighting in an editor session.
4. Expand renderer features and add pixel-level visual regression checks.
5. Improve networking reliability and portability before treating it as multiplayer infrastructure.
6. Add benchmarks before claiming high or “hyper-efficient” performance.

