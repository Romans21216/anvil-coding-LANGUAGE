# Anvil QA Report

**Verification date:** 2026-10-27  
**Source format:** `.ANVL`  
**Independent evaluation:** 94/100, PASS (threshold: 90/100)

## Scope and implementation status

Anvil is an early, Windows-focused game language and native runtime prototype. It accepts simple BASIC/Lua-inspired `.ANVL` programs, validates them, emits ordinary C, and uses the verified MSVC backend to create an `.exe`. The runtime includes a software 2D/3D renderer, keyboard camera movement/look and FOV control, a fixed-step loop, seeded random/noise helpers, numeric UDP for LAN experiments, and the built-in `ray_sphere(x,y,z,radius)` function. Ray spheres are traced per pixel using a CPU BVH for closest-hit and hard-shadow queries, diffuse lighting, and specular highlights. The BVH supports up to 32 ray spheres in one trace batch. It is not a general-purpose or production-ready engine: assets, audio, physics, portability, and a Rust backend are not implemented.

The `.ANVL` suffix is the user's explicit choice and is registered by the compiler documentation, examples, project manifest, and VS Code extension. The suffix also appears in an unrelated metadata serialization format; this project does not claim that it is globally unique.

## Verification results

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -v` | PASS — 26 tests, including projected-sphere bounds coverage |
| `npm test` from `vscode-extension` | PASS — manifest/config validated; TextMate grammar loaded; representative token scopes matched |
| Build `game.ANVLproj` with MSVC | PASS — produced `build/qa_final_recheck.exe`; sample includes camera settings and two ray-traced spheres |
| Build `examples/numeric_demo.ANVL` with MSVC | PASS — produced `build/final_numeric.exe` |
| Run numeric demo executable | PASS — printed `17` |
| Native runtime integration test | PASS — verified four 10 Hz update callbacks, 0.1-second delta, queued Space key edge delivered to update, and clean shutdown |
| VS Code package | PASS — `vscode-extension/anvil-language-support-0.1.0.vsix` packaged; grammar test verifies built-in `ray_sphere` highlighting |
| VS Code workspace verification | PASS — opened `examples/first_world.ANVL`; installed Anvil extension was visible, syntax colors appeared, and the status bar showed language mode **Anvil** |
| Runtime display check | PASS — built sample displayed the regular 3D primitives and both ray-traced spheres in the native game window |

The runtime integration test caught and led to removal of an invalid second free of the pixel buffer owned by `CreateDIBSection`. The projected-sphere regression now compiles the production bounds helper and checks dense sphere-surface samples at multiple offsets and depths.

A follow-up verification on 2026-10-27 reran `python -m unittest discover -s tests -v` (26 passed, including the projected-sphere bounds regression), `npm test` in `vscode-extension` (passed), and a fresh MSVC manifest build to `build/qa_final_recheck.exe` (passed).

## Independent 50-criterion evaluation

The separate reviewer first scored the implementation at 93/100, then corrected an arithmetic inconsistency and rechecked the code after this report was added. The final independent result is **94/100 (PASS)**. The corrected assessment gives full credit for criterion 25 (no unused helper/import evidence) and criterion 38 (this report durably records the results). The table below reflects the corrected scores and deductions.

| # | Criterion | Score | Evidence / deduction |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Compiler, runtime, examples, docs, and extension address stated requirements. |
| 2 | Implicit requirements addressed | 1 | Practical engine features such as assets, audio, physics, and portability remain outside scope. |
| 3 | Functionality matches intended goal | 1 | 2D/3D software-rendered prototype and numeric UDP partially satisfy the broad full-engine goal. |
| 4 | Required deliverables present | 2 | Compiler, runtime, examples, manifest, documentation, extension, and package are present. |
| 5 | No essential feature missing | 2 | Requested core areas have working examples or implementations: rendering, camera control, BVH ray tracing, RNG/noise, multiplayer primitive, and EXE compilation. |
| 6 | Stated constraints respected | 2 | `.ANVL` is the user's clarified and confirmed source extension. |
| 7 | Ambiguity resolved logically | 2 | Manifest, Windows target, and C backend decisions are documented. |
| 8 | Behavior matches documentation | 2 | Main documented compiler/runtime behavior matches implementation. |
| 9 | Important use cases supported | 2 | Direct builds, manifest builds, rendering, networking samples, and numeric sample are supported. |
| 10 | Usable for intended purpose | 2 | Useful within documented Windows prototype scope. |
| 11 | Core functionality works | 2 | Compiler, runtime, camera commands, BVH ray-traced spheres, and native builds work. |
| 12 | Secondary functionality works | 2 | Fixed-step callbacks and queued key-edge input are covered by a native integration test. |
| 13 | Primary workflows functional | 2 | Direct-source and manifest build paths work. |
| 14 | Inputs validated | 2 | Expressions, types, arity, symbols, manifest fields, paths, rates, and ports are validated. |
| 15 | Errors handled gracefully | 2 | Invalid syntax and malformed manifests produce controlled diagnostics. |
| 16 | Edge cases covered | 2 | Test suite includes fixed-step/key-edge timing and invalid input cases. |
| 17 | Invalid input controlled | 2 | Invalid source, manifests, paths, rates, and ports are rejected with diagnostics. |
| 18 | Stability across repeated operations | 2 | Full tests/build workflows pass; seeded RNG/noise repeatability is tested. |
| 19 | No critical defects known | 2 | Key-edge handling and DIB cleanup defects are fixed; runtime probe shuts down cleanly. |
| 20 | Components integrate | 2 | Compiler, project manifest, native runtime, and networking examples integrate. |
| 21 | Logical project structure | 2 | Compiler, runtime, examples, docs, tests, and extension are organized separately. |
| 22 | Readable and consistently formatted | 1 | Some compiler sections remain compressed and would benefit from formatting cleanup. |
| 23 | Clear module responsibilities | 1 | Parsing, validation, C generation, and build orchestration are concentrated in one compiler file. |
| 24 | Consistent descriptive naming | 2 | Anvil naming is consistent across source, runtime, docs, and extension. |
| 25 | Duplication minimized | 2 | Reviewer’s follow-up scan found no evidence of unused helpers or imports. |
| 26 | Appropriate dependencies | 2 | Dependencies and MSVC build path are documented and appropriate. |
| 27 | Supports reasonable extensions | 1 | One C backend and Windows runtime constrain future backend/platform growth. |
| 28 | No unfinished placeholders | 2 | No misleading placeholder features; unsupported scope is disclosed. |
| 29 | Understandable configuration | 2 | Manifest settings are explicit, validated, and unsupported keys are rejected. |
| 30 | Framework conventions followed | 2 | Python, C, TOML, and VS Code conventions are followed. |
| 31 | Automated tests provided | 2 | 25 automated tests pass. |
| 32 | Core tests covered | 2 | Compiler, generated code, numeric behavior, manifest, runtime linking, network, and native runtime are covered. |
| 33 | Failure scenarios tested | 2 | Malformed source/manifests, unsupported settings, and escaping paths are covered. |
| 34 | Edge cases explicitly tested | 2 | Runtime test exercises a queued key press between fixed updates. |
| 35 | Integration behavior tested | 2 | Native runtime integration test builds and executes a real windowed program. |
| 36 | Documented test commands work | 2 | Python unittest and extension npm commands both pass. |
| 37 | Builds and compilation pass | 2 | MSVC release builds pass for manifest game and numeric demo; runtime probe also builds. |
| 38 | Results recorded accurately | 2 | This report records reproducible test and build commands, outcomes, and integration evidence. |
| 39 | Regression checks after fixes | 2 | Full suite passed after runtime cleanup and language/extension updates. |
| 40 | Verified against original goal | 1 | Runtime is verified, but the broad engine vision remains a prototype. |
| 41 | Installation instructions accurate | 2 | Setup/build instructions match the current Python, MSVC, and extension workflows. |
| 42 | Setup reproducible | 2 | Python, Visual Studio Build Tools, and extension dependencies are documented. |
| 43 | Usage understandable | 2 | Language and build examples are understandable. |
| 44 | Design decisions documented | 2 | Manifest schema, fixed timestep, compiler backend, and engine limits are explained. |
| 45 | Troubleshooting guidance | 2 | README includes troubleshooting guidance. |
| 46 | Opens in intended environment | 2 | Anvil project is open in VS Code with `.ANVL` sample selected and mode Anvil shown. |
| 47 | Editor integration works | 2 | VS Code grammar checks pass for the `ray_sphere` built-in; installed package syntax colors render in workspace. |
| 48 | Deliverables organized | 2 | Source, runtime, docs, examples, tests, and extension are under the AnvilEngine project. |
| 49 | Limitations and assumptions disclosed | 2 | Windows/MSVC, prototype feature limits, backend status, and suffix collision are documented. |
| 50 | Practical for stated scope | 2 | Usable for the documented prototype and sample workflows. |

### Evaluator category subtotals

| Category | Score |
|---|---:|
| Requirement fulfillment | 18/20 |
| Functionality and reliability | 20/20 |
| Code quality and architecture | 17/20 |
| Testing and verification | 19/20 |
| Developer experience and delivery | 20/20 |
| **Total** | **94/100 — PASS** |

The corrected criterion scores sum to 94. The remaining deductions are limited to prototype feature scope, compressed compiler formatting, compiler responsibilities concentrated in one file, and future backend/platform extensibility.

## Remaining improvements

1. Extend the engine beyond this prototype with assets, audio, physics, and additional platform/backend support.
2. Split compiler parsing, validation, C generation, and build orchestration into maintainable modules; normalize formatting and remove unused code.
3. Consider a more globally unique file suffix only if the user changes the explicit `.ANVL` choice.



