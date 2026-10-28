# Anvil QA report

**Review date:** 2026-10-28
**Latest independent evaluation:** **76/100 - FAIL** on exact `ecdf68109fd5932d8ae572a8f16446194e93b935`.
**Current passing threshold:** 98/100. Historical 90-point passes do not pass the current requirement.
**Evaluator:** separate `project_full_review` agent, full 50-criterion review.

The full goal remains incomplete: direct no-C/no-Rust engine parity, selectable DXR/Embree, rich systems-language types, Forge formats and assembly/UEFI/OS outputs are still missing. The master backlog exists only in issue #23/comments; [capability matrix](COMPLETION_MATRIX.md) describes the current limits.

## Independent verification for this snapshot

- `python -m unittest discover -s tests -q`: **162 passed**, 139.160 seconds.
- Extension 0.1.11 grammar validation and VSIX CRC/source parity passed. Language ID `anvil`, extensions `.ANVL`/`.anvl`, grammar `vscode-extension/syntaxes/anvil.tmLanguage.json`. Installed 0.1.4 remains per preference; newer visible tokens are unverified.
- Python compileall, QA arithmetic, strict UTF-8 JSON and diff checks passed.
- Adversarial probes combine 128 statement blocks with 63 grouped/unary/user-call/abs levels; accepted inputs pass. Over-budget mixed expressions return controlled diagnostics. #64 configuration locations and #65 uncontrolled compiler recursion are verified fixed.
- Source includes and native function selection were verified in the preceding `edfbe86` review: native demo 3,072 bytes, native and C/MSVC demos print 20. The full regression suite includes those execution paths.
- Direct-backend window/input tests target only their generated windows. Coordinate coverage uses explicit test instrumentation; untouched OS coordinate dispatch remains unverified (#63). No CUA or fresh manual editor/sample inspection occurred. A later audit found the legacy C mouse harness called SetCursorPos during full suites; prior blanket no-global-input claims were too broad. #71 records this and removes that behavior in the current follow-up.

## Latest 50-criterion scoring — `ecdf681`

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Language/compiler/runtime and direct target are identified. |
| 2 | Implicit requirements addressed | 1 | Runtime/input support is growing; most engine/Forge breadth remains unavailable (open). |
| 3 | Functionality matches intended goal | 1 | Custom language/native subset works; complete engine/Forge/OS functionality remains absent. |
| 4 | Required deliverables present | 1 | Compiler, extension, tests and docs exist; native engine parity is missing (open). |
| 5 | No essential feature missing | 0 | GPU rendering, broader engine systems and Forge requirements remain absent (open). |
| 6 | Stated constraints respected | 1 | Native avoids C/Rust, but C is default; port remaining APIs before switching (open). |
| 7 | Ambiguity resolved logically | 2 | Direct machine-code/PE target follows user selection. |
| 8 | Behavior matches documentation | 2 | Semantic ray composition and native project settings match documented supported contracts; #77 independently fixed. |
| 9 | Important use cases supported | 1 | Interactive 2D input works; native 3D/assets/physics/networking remain missing (open). |
| 10 | Usable for intended purpose | 1 | Usable for a small native demo; complete engine workflows remain unavailable (open). |
| 11 | Core functionality works | 1 | Numeric/namespace/local/scratch/formatter cases pass; complete native engine core remains partial. |
| 12 | Secondary functionality works | 2 | Actual compiled ray/text order, input/procedural/resource primitives pass. |
| 13 | Primary workflows functional | 1 | Hosted subset builds work; Forge/plugin/assembly/UEFI/kernel primary workflows are absent (open). |
| 14 | Inputs validated | 2 | #78 independently verified fixed:64 control-entry cases reject cleanly with manifest diagnostics and no artifacts. |
| 15 | Errors handled gracefully | 2 | #78 independently verified fixed:64 control-entry cases reject cleanly with manifest diagnostics and no artifacts. |
| 16 | Edge cases covered | 2 | Tests cover signed/outside mouse coordinates, resize, capture, taps, wheel fractions, focus and draw-only scenes. |
| 17 | Invalid inputs controlled | 2 | #78 independently verified fixed:64 control-entry cases reject cleanly with manifest diagnostics and no artifacts. |
| 18 | Stable across repeated operations | 2 | Repeated maximum arrays, recursive unwind/reuse and GUI callback allocations pass. |
| 19 | No known critical defects | 2 | No critical corruption or numeric miscompilation reproduced; no new confirmed finding in latest review. |
| 20 | Components integrate | 2 | Includes, project settings/native runtime and semantic ray/HUD order integrate in executable tests. |
| 21 | Logical project structure | 2 | NativeArrays owns allocation/lifetime emission; compiler, window/input and encoder responsibilities are separated. |
| 22 | Readable and consistently formatted | 1 | Raw x64 bytes are hard to maintain; add instruction abstractions and formatting (open). |
| 23 | Clear module responsibilities | 1 | Input has its own module; instruction encoding/state/platform behavior remain coupled (open). |
| 24 | Consistent descriptive naming | 2 | Names are consistent and descriptive. |
| 25 | Duplication minimized | 1 | ABI/instruction patterns repeat; consolidate encoder helpers (open). |
| 26 | Dependencies appropriate | 2 | Direct heap/window imports require no C/Rust shim; unused array functions omit heap imports. |
| 27 | Supports future extensions | 1 | Labels/fixups/demand loading and array module provide a base; complete runtime/target interfaces (open). |
| 28 | No unfinished placeholders | 1 | Input handlers are real; native graphics still restricts scenes and opaque rectangle coverage (open). |
| 29 | Configuration understandable | 2 | Backend/TOML/include/title and1–240Hz settings are organized and documented. |
| 30 | Conventions followed | 1 | Win64/PE is exercised but manual; broaden ABI validation and abstractions (open). |
| 31 | Automated tests provided | 2 | 162 tests and extension0.1.11 validation independently pass. |
| 32 | Core tests covered | 2 | Numeric/differential/include/runtime and compiled semantic ray-order regressions cover implemented core. |
| 33 | Failure scenarios tested | 2 | Invalid mouse arguments/keys and bitmap allocation-failure injection are covered. |
| 34 | Edge cases explicitly tested | 2 | Taps, repeats, simultaneous buttons, actual OS capture, wheel accumulation and draw-only behavior are tested. |
| 35 | Integration behavior tested | 1 | Coordinate test uses an explicit test-only WndProc wrapper; untouched OS-dispatch coverage is incomplete (#63, open). |
| 36 | Documented test commands work | 2 | Documented Python and extension validation commands run successfully. |
| 37 | Builds and compilation pass | 2 | 162 tests include C/native execution; compileall/extension/VSIX/UTF8/diff pass. |
| 38 | Results recorded accurately | 2 | Exact ecdf681 / 76 / 162 evidence agrees across records; historical input-test limitations disclosed. |
| 39 | Regression checks performed | 2 | Full suite and prior slow-draw/failure/resource regressions pass. |
| 40 | Verified against original goal | 0 | Only a prototype subset is verified; implement and verify full scope (open). |
| 41 | Installation instructions accurate | 2 | Python/native and Python/MSVC routes match independently exercised builds; extension installation documented. |
| 42 | Setup reproducible | 1 | Subset setup is reproducible; full engine setup is missing (open). |
| 43 | Usage understandable | 2 | Corrected compiler/migration guides identify actual support, usage and backend limits. |
| 44 | Design decisions documented | 2 | Migration design and limits are documented. |
| 45 | Troubleshooting available | 2 | README, native diagnostic tables and include/depth troubleshooting provide actionable subset guidance. |
| 46 | Opens in intended environment | 1 | CLI/runtime/static extension validate; full editor workflows and fresh visible verification remain incomplete. |
| 47 | Editor integration works | 1 | Grammar, corrected indentation/folding and VSIX parity pass; current newer installed-editor behavior remains unverified. |
| 48 | Deliverables organized | 2 | Deliverables are organized and pushed. |
| 49 | Limitations disclosed | 2 | Native limitations are disclosed. |
| 50 | Practical for intended scope | 0 | Full game-engine/Forge scope remains incomplete (open). |
| | **Requirement fulfillment** | **12/20** | |
| | **Functionality and reliability** | **18/20** | |
| | **Code quality and architecture** | **14/20** | |
| | **Testing and verification** | **17/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **76/100** | Exact commit `ecdf681`; FAIL against 98. |

### Deduction details and follow-up

- **#78 RESOLVED:** All64 independent control-character entry cases pass on both backends; diagnostics name the manifest and no traceback/artifact leaks. No new confirmed finding.
- **Scope (2–6/9–10/13/28/40/50):** Complete native engine, actual DXR/Embree, rich types, Forge/OS outputs and measured efficiency remain absent. Deliver full issue23 scope with executable acceptance evidence before default migration/completion.
- **Architecture (22/23/25/27/30):** Numeric transport/addressing duplication is reduced. Raw opcodes remain across runtime/platform emitters, and expressions.py/native_codegen.py duplicate expression parsing/precedence. Add validated shared lowering/IR and broader systems ABI/interfaces; existing #11/#23 compiler items track these gaps.
- **Integration (35):** Instrumented/synchronized coordinate samples do not prove untouched OS pointer dispatch (#63). Gather independent integration evidence within input constraints.
- **Setup/editor (42/46/47):** Full project/engine/Forge/OS setup cannot be reproduced; newer installed-editor visuals remain unverified (#24). Implement missing workflows and respect installed0.1.4 preference.

The full ecdf681 review independently verifies shared numeric ABI transport and scalar addressing. All 162 tests passed in 139.160s, including 2048 executed addressing combinations and independent callee checks. An extra executable probe combines a live outer temporary, 15 nested side-effect arguments, 200 locals and an 8192-element heap array, returning 1063.25. Another 512 signed-disp32 endpoint encodings were checked without executing invalid addresses. No new defect was confirmed. Score remains 76 because broader parsing/IR duplication, platform/runtime encoding, systems ABI and full-scope gaps remain. Next: validated lowering/IR and native rendering parity. Installed 0.1.4 preserved; #63 remains unverified. The evaluator re-read issue #23 and its 41 comments after the suite.

## Review history

| Exact snapshot | Score / threshold | Evidence and changes |
|---|---|---|
| `2f7cd743ba37101c87a0daa5d1c9c017d9ab5dc2` |76 /98 FAIL|158 tests in 145.917s; native local arrays independently verified; no new finding.|
| `2b4e5e8d84bb0695af92eadd3740a4a84a6410dd` |76 /98 FAIL|151tests142.480s; #78 verified; no new finding.|
| `1570abdd429683759f31066f04e5982ec10de386` |73 /98 FAIL|150tests152.822s; #77/projects verified; #78 found.|
| `86681061c3e6d564b315dd571be4958202ac295d` |72 /98 FAIL|146tests125.935s; #74–76 verified; #77 found.|
| `c8b01e70dccfe777b490f5eec2d469b6e1c50800` | 69 / 98 — FAIL | 139tests; #72/#73 verified; #74/#75 found. Categories11/13/14/16/15. |
| `be0d591a82578d397ee1bfb88c31fe99f4749637` | 68 / 98 — FAIL | 136tests; #58/#67–71 verified; #72/#73 found. Categories11/12/14/16/15. |
| `5e80af327d1cedf9aafdc6af11a196702a866da5` | 68 / 98 — FAIL | 133tests; #66 verified, #67–69 found and #58 remained. Categories11/14/14/15/14. |
| `148363296d51de59e3b92db3bf768d19ad5d2ee2` | 71 / 98 — FAIL | 131 tests; #64/#65 verified; residual #66 and stale #58 found. Categories11/17/13/16/14. |
| `edfbe86252deb5af39504161f6e8571ae917fbb9` | 71 / 98 — FAIL | 125 tests; includes/function selection verified; #64 provenance and #65 recursion found. Categories 11/16/13/17/14. |
| `3270998384367be7b763cc605c0492208a72c988` | 72 / 98 — FAIL | 111 tests; #60 Wiki, #61 explicit-main arguments and #62 coordinate-test timing fixed; #63 remaining coverage gap. |
| `c10260483eab6b5adaadd261a66a92a9138b9ed8` | 92 / 98 — FAIL | Historical C-backed 77-test snapshot; UTF-8/status #48 fixed. It predates the direct-native/Forge/OS goal expansion. |
| `2a745bb9b455baffe9248f24d39970ea31146b23` | 90 / 90 — historical PASS | Earlier prototype evaluation; below today's 98 threshold and not proof of current full-goal completion. |

Earlier reports and their complete rubric tables remain available in Git history. Previous resolved defects include QA arithmetic #44, local-array recursion #21, near-plane overflow #47, native numeric diagnostics #49/#52–54, flicker #57, Wiki #60, entry arguments #61 and fixture race #62. Their resolutions do not close broader capability gaps.

## Bug tracking

All confirmed findings have detailed reproduction, impact and acceptance criteria in GitHub with `Codex Bugs`; user reports use `Romans21216 - Bugs`. No new confirmed defect in the latest review; #78 is independently resolved. [#63 coordinate integration](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/63) and broader systems in#5–11/#14–15/#24 remain open. Complete backlog only in [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23).

Focused independent record-only check of0b13a46 passed: all50 vectors,76/100 categories, exact2b4e5e8 and151/142.480s evidence agree; current native project/settings docs and ancillary fields match. No rescore or implementation change.

Record-only check3fe3e57 found stale total-row source and local-array rollout wording (#58). Those lines are corrected in this follow-up; all main score vectors and158/145.917s evidence passed. Source76 score unchanged.

Focused independent record recheckfbf6143 passes after #58 corrections: total-row source2f7cd74 and native local-array rollout agree with all four50-score vectors,76/100 and158/145.917s evidence. No rescore or implementation change.

Focused independent record-only recheck of 91b06cd: PASS. All six current records, all 50 scores and both candidate_validation objects agree on exact source ecdf681, 76/100, categories 12/18/14/17/15 and 162 tests in 139.160s. Historical 2f7cd74/158 evidence remains identified as history. No implementation change or rescore.

Unscored follow-up: native Anvil-written circle/line kernels implemented; local 168-test suite passed in 155.565s plus targeted pixels/limits/lifetime/selection and CLI sample checks. Awaiting separate FULL50 review. Latest independent ecdf681/76/162 evidence above remains unchanged until that review.
