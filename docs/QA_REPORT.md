# Anvil QA report

**Review date:** 2026-10-28
**Latest independent evaluation:** **68/100 - FAIL** on exact `5e80af327d1cedf9aafdc6af11a196702a866da5`.
**Current passing threshold:** 98/100. Historical 90-point passes do not pass the current requirement.
**Evaluator:** separate `semantic_full_review` agent, full 50-criterion review.

The full goal remains incomplete: direct no-C/no-Rust engine parity, selectable DXR/Embree, rich systems-language types, Forge formats and assembly/UEFI/OS outputs are still missing. The master backlog exists only in issue #23/comments; [capability matrix](COMPLETION_MATRIX.md) describes the current limits.

## Independent verification for this snapshot

- `python -m unittest discover -s tests -q`: **133 passed**, 98.487 seconds.
- Extension 0.1.10 grammar validation and VSIX CRC/source parity passed. Language ID `anvil`, extensions `.ANVL`/`.anvl`, grammar `vscode-extension/syntaxes/anvil.tmLanguage.json`. Installed 0.1.4 remains per preference; newer visible tokens are unverified.
- Python compileall, QA arithmetic, strict UTF-8 JSON and diff checks passed.
- Adversarial probes combine 128 statement blocks with 63 grouped/unary/user-call/abs levels; accepted inputs pass. Over-budget mixed expressions return controlled diagnostics. #64 configuration locations and #65 uncontrolled compiler recursion are verified fixed.
- Source includes and native function selection were verified in the preceding `edfbe86` review: native demo 3,072 bytes, native and C/MSVC demos print 20. The full regression suite includes those execution paths.
- Direct-backend window/input tests target only their generated windows. Coordinate coverage uses explicit test instrumentation; untouched OS coordinate dispatch remains unverified (#63). No CUA or fresh manual editor/sample inspection occurred. A later audit found the legacy C mouse harness called SetCursorPos during full suites; prior blanket no-global-input claims were too broad. #71 records this and removes that behavior in the current follow-up.

## Latest 50-criterion scoring — `5e80af3`

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Language/compiler/runtime and direct target are identified. |
| 2 | Implicit requirements addressed | 1 | Runtime/input support is growing; most engine/Forge breadth remains unavailable (open). |
| 3 | Functionality matches intended goal | 1 | A custom language/native subset works, but full engine coverage and namespace correctness remain incomplete (#67).
| 4 | Required deliverables present | 1 | Compiler, extension, tests and docs exist; native engine parity is missing (open). |
| 5 | No essential feature missing | 0 | GPU rendering, broader engine systems and Forge requirements remain absent (open). |
| 6 | Stated constraints respected | 1 | Native avoids C/Rust, but C is default; port remaining APIs before switching (open). |
| 7 | Ambiguity resolved logically | 2 | Direct machine-code/PE target follows user selection. |
| 8 | Behavior matches documentation | 1 | Compiler/migration guides still contradict actual direct-backend support and latest review (#58).
| 9 | Important use cases supported | 1 | Interactive 2D input works; native 3D/assets/physics/networking remain missing (open). |
| 10 | Usable for intended purpose | 1 | Usable for a small native demo; complete engine workflows remain unavailable (open). |
| 11 | Core functionality works | 1 | Native global/local name overlap silently prints4 where C correctly prints9 (#67); fix storage resolution and differential conformance.
| 12 | Secondary functionality works | 2 | Mouse position, buttons, wheel, capture, focus/cancel and keyboard regressions pass generated-app tests. |
| 13 | Primary workflows functional | 1 | Hosted subset builds work; Forge/plugin/assembly/UEFI/kernel primary workflows are absent (open). |
| 14 | Inputs validated | 1 | Five public runtime names bypass reserved-name validation and reach C errors (#68); complete namespace ownership validation.
| 15 | Errors handled gracefully | 1 | Physical provenance #66 is fixed; #68 still exposes generated-C errors instead of source semantic diagnostics.
| 16 | Edge cases covered | 2 | Tests cover signed/outside mouse coordinates, resize, capture, taps, wheel fractions, focus and draw-only scenes. |
| 17 | Invalid inputs controlled | 2 | Both backends enforce expression and statement depth budgets; deep and mixed-depth probes return controlled diagnostics (#65 verified fixed).
| 18 | Stable across repeated operations | 2 | 133 independently passing tests cover repeated resource/input/include operations.
| 19 | No known critical defects | 1 | No crash/corruption reproduced, but silent numeric miscompilation remains (#67); resolve before release.
| 20 | Components integrate | 1 | Native frame/global storage disagrees with language/C semantics (#67); add cross-backend conformance.
| 21 | Logical project structure | 2 | Input emitter, window emitter, encoder, examples, tests and docs are separated. |
| 22 | Readable and consistently formatted | 1 | Raw x64 bytes are hard to maintain; add instruction abstractions and formatting (open). |
| 23 | Clear module responsibilities | 1 | Input has its own module; instruction encoding/state/platform behavior remain coupled (open). |
| 24 | Consistent descriptive naming | 2 | Names are consistent and descriptive. |
| 25 | Duplication minimized | 1 | ABI/instruction patterns repeat; consolidate encoder helpers (open). |
| 26 | Dependencies appropriate | 2 | Direct backend imports Windows APIs without a C/Rust shim. |
| 27 | Supports future extensions | 1 | Labels/fixups provide a base; complete runtime and backend interfaces (open). |
| 28 | No unfinished placeholders | 1 | Input handlers are real; native graphics still restricts scenes and opaque rectangle coverage (open). |
| 29 | Configuration understandable | 2 | Backend selection, TOML keys, source boundaries and limits are understandable; unsupported native manifests explicitly reject.
| 30 | Conventions followed | 1 | Win64/PE is exercised but manual; broaden ABI validation and abstractions (open). |
| 31 | Automated tests provided | 2 | 133 tests and extension grammar/package checks independently pass.
| 32 | Core tests covered | 1 | Valid global/local namespace overlap escaped numeric coverage (#67); add differential namespace cases.
| 33 | Failure scenarios tested | 2 | Invalid mouse arguments/keys and bitmap allocation-failure injection are covered. |
| 34 | Edge cases explicitly tested | 2 | Taps, repeats, simultaneous buttons, actual OS capture, wheel accumulation and draw-only behavior are tested. |
| 35 | Integration behavior tested | 1 | Coordinate test uses an explicit test-only WndProc wrapper; untouched OS-dispatch coverage is incomplete (#63, open). |
| 36 | Documented test commands work | 2 | Documented Python and extension validation commands run successfully. |
| 37 | Builds and compilation pass | 2 | 133 tests, extension/VSIX parity, compileall, UTF8 and diff checks pass; accepted-input failure #68 separately tracked.
| 38 | Results recorded accurately | 1 | Principal QA records are exact, but migration claims conflict with reviewed state (#58); finish synchronization.
| 39 | Regression checks performed | 2 | Full suite and prior slow-draw/failure/resource regressions pass. |
| 40 | Verified against original goal | 0 | Only a prototype subset is verified; implement and verify full scope (open). |
| 41 | Installation instructions accurate | 2 | Python/native and Python/MSVC routes match independently exercised builds; extension installation documented. |
| 42 | Setup reproducible | 1 | Subset setup is reproducible; full engine setup is missing (open). |
| 43 | Usage understandable | 1 | README/include guide are useful; compiler capability guidance contradicts implemented support (#58).
| 44 | Design decisions documented | 2 | Migration design and limits are documented. |
| 45 | Troubleshooting available | 2 | README, native diagnostic tables and include/depth troubleshooting provide actionable subset guidance.
| 46 | Opens in intended environment | 1 | CLI/editor automation works; complete native project/editor/runtime workflow (open). |
| 47 | Editor integration works | 1 | Grammar/package checks pass, but control-flow indentation fails (#69); newer visible editor verification remains absent.
| 48 | Deliverables organized | 2 | Deliverables are organized and pushed. |
| 49 | Limitations disclosed | 2 | Native limitations are disclosed. |
| 50 | Practical for intended scope | 0 | Full game-engine/Forge scope remains incomplete (open). |
| | **Requirement fulfillment** | **11/20** | |
| | **Functionality and reliability** | **14/20** | |
| | **Code quality and architecture** | **14/20** | |
| | **Testing and verification** | **15/20** | |
| | **Developer experience and delivery** | **14/20** | |
| | **Total** | **68/100** | Exact commit `5e80af3`; FAIL against 98. |

### Deduction details and follow-up

- **#67 — namespace correctness (3/11/19/20/32):** `var(x)` incorrectly resolves to same-name `local(x)` frame storage; native prints4 where C prints9. This silently changes valid results. Restrict var frame lookup to parameters and handle compound locals explicitly. Add differential read/write/loop/recursion/include tests. Local corrections await independent verification.
- **Development follow-up #71:** A 136-test local run failed the legacy C mouse coordinate assertion (-1 instead of480). The fixture relied on a draw between fixed updates and moved the desktop pointer. It now synchronizes synthetic window-local dispatch/sampling inside update, removes cursor movement and retains edge/viewport checks. Real pointer integration remains unverified. The failed run is retained as evidence. Three repeated fixture runs and the final136-test rerun (116.325s) passed; independent verification is pending.
- **Development follow-up #70:** Native scalar locals retained prior frame contents when conditional assignments were skipped (77 instead of specified70). The current follow-up zero-initializes scalar locals per invocation after preserving parameters and adds repeated/recursive/loop cases. This defect was discovered after the scored review; no independent score is assigned to its correction yet.
- **#68 — runtime symbol ownership (14/15):** Five public runtime names are absent from reservations; accepted functions fail downstream with MSVC C2371. Reserve the complete public namespace and test header parity plus source-located function/global/array failures. Corrections await independent review.
- **#58 — current guides (8/38/43):** Compiler and migration prose understates features and calls older work latest/pending. This misdirects usage and review interpretation. Update all public summaries, label historical logs and link current evidence instead of repeating live scores. Current correction awaits review.
- **#69 — indentation/folding (47):** Configuration rejects valid if/while/for headers despite passing token tests. Match real block syntax and add positive/negative configuration cases; package source changes while preserving installed0.1.4. New0.1.11 grammar/configuration and VSIX CRC/source parity pass; independent review is pending and no fresh visible-editor claim.
- **Scope (2–6/9–10/13/28/40/50):** Native full engine, actual DXR/Embree, rich types, Forge and OS workflows remain missing. Implement the complete issue23 scope with executable acceptance evidence before removing C/default dependency or claiming practical completion.
- **Architecture (22/23/25/27/30):** Raw opcode/ABI duplication and semantic/frame/runtime coupling increase maintenance and extension risk. Consolidate instruction/ABI helpers and shared validated storage/lowering contracts.
- **Integration (35):** Instrumented coordinate tests do not establish untouched OS dispatch (#63). Gather independent integration evidence within the user's input constraints.
- **Setup/editor (42/46/47):** Prototype setup works, but full native project/editor/Forge/OS workflows cannot be reproduced. Implement missing project support; installed0.1.4 leaves newer visible tokens unverified (#24).

The evaluator verified #66 physical provenance using eight extra CLI cases. All other findings remain open on this snapshot. Current source/package/documentation corrections receive no independent score until reviewed. No completion is claimed.

## Review history

| Exact snapshot | Score / threshold | Evidence and changes |
|---|---|---|
| `148363296d51de59e3b92db3bf768d19ad5d2ee2` | 71 / 98 — FAIL | 131 tests; #64/#65 verified; residual #66 and stale #58 found. Categories11/17/13/16/14. |
| `edfbe86252deb5af39504161f6e8571ae917fbb9` | 71 / 98 — FAIL | 125 tests; includes/function selection verified; #64 provenance and #65 recursion found. Categories 11/16/13/17/14. |
| `3270998384367be7b763cc605c0492208a72c988` | 72 / 98 — FAIL | 111 tests; #60 Wiki, #61 explicit-main arguments and #62 coordinate-test timing fixed; #63 remaining coverage gap. |
| `c10260483eab6b5adaadd261a66a92a9138b9ed8` | 92 / 98 — FAIL | Historical C-backed 77-test snapshot; UTF-8/status #48 fixed. It predates the direct-native/Forge/OS goal expansion. |
| `2a745bb9b455baffe9248f24d39970ea31146b23` | 90 / 90 — historical PASS | Earlier prototype evaluation; below today's 98 threshold and not proof of current full-goal completion. |

Earlier reports and their complete rubric tables remain available in Git history. Previous resolved defects include QA arithmetic #44, local-array recursion #21, near-plane overflow #47, native numeric diagnostics #49/#52–54, flicker #57, Wiki #60, entry arguments #61 and fixture race #62. Their resolutions do not close broader capability gaps.

## Bug tracking

All confirmed findings are tracked with detailed reproduction, impact and acceptance criteria under `Codex Bugs`; user reports use `Romans21216 - Bugs`. Current findings: [#67 namespace](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/67), [#68 reservation](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/68), [#69 indentation](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/69), [#58 metadata](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/58), [#63 coordinate coverage](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/63); #66 semantic provenance is independently resolved. Broader systems remain tracked in #5–11, #14–15, #24 and the canonical [#23 backlog](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23).
