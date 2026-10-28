# Anvil QA report

**Review date:** 2026-10-28
**Latest independent evaluation:** **68/100 - FAIL** on exact `be0d591a82578d397ee1bfb88c31fe99f4749637`.
**Current passing threshold:** 98/100. Historical 90-point passes do not pass the current requirement.
**Evaluator:** separate `semantic_full_review` agent, full 50-criterion review.

The full goal remains incomplete: direct no-C/no-Rust engine parity, selectable DXR/Embree, rich systems-language types, Forge formats and assembly/UEFI/OS outputs are still missing. The master backlog exists only in issue #23/comments; [capability matrix](COMPLETION_MATRIX.md) describes the current limits.

## Independent verification for this snapshot

- `python -m unittest discover -s tests -q`: **136 passed**, 117.892 seconds.
- Extension 0.1.11 grammar validation and VSIX CRC/source parity passed. Language ID `anvil`, extensions `.ANVL`/`.anvl`, grammar `vscode-extension/syntaxes/anvil.tmLanguage.json`. Installed 0.1.4 remains per preference; newer visible tokens are unverified.
- Python compileall, QA arithmetic, strict UTF-8 JSON and diff checks passed.
- Adversarial probes combine 128 statement blocks with 63 grouped/unary/user-call/abs levels; accepted inputs pass. Over-budget mixed expressions return controlled diagnostics. #64 configuration locations and #65 uncontrolled compiler recursion are verified fixed.
- Source includes and native function selection were verified in the preceding `edfbe86` review: native demo 3,072 bytes, native and C/MSVC demos print 20. The full regression suite includes those execution paths.
- Direct-backend window/input tests target only their generated windows. Coordinate coverage uses explicit test instrumentation; untouched OS coordinate dispatch remains unverified (#63). No CUA or fresh manual editor/sample inspection occurred. A later audit found the legacy C mouse harness called SetCursorPos during full suites; prior blanket no-global-input claims were too broad. #71 records this and removes that behavior in the current follow-up.

## Latest 50-criterion scoring — `be0d591`

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Language/compiler/runtime and direct target are identified. |
| 2 | Implicit requirements addressed | 1 | Runtime/input support is growing; most engine/Forge breadth remains unavailable (open). |
| 3 | Functionality matches intended goal | 1 | Language/native subset works; full engine missing and valid temporary-like names still miscompile (#72).
| 4 | Required deliverables present | 1 | Compiler, extension, tests and docs exist; native engine parity is missing (open). |
| 5 | No essential feature missing | 0 | GPU rendering, broader engine systems and Forge requirements remain absent (open). |
| 6 | Stated constraints respected | 1 | Native avoids C/Rust, but C is default; port remaining APIs before switching (open). |
| 7 | Ambiguity resolved logically | 2 | Direct machine-code/PE target follows user selection. |
| 8 | Behavior matches documentation | 1 | Current guide wording#58 is fixed, but documented identifier/string semantics fail (#72/#73).
| 9 | Important use cases supported | 1 | Interactive 2D input works; native 3D/assets/physics/networking remain missing (open). |
| 10 | Usable for intended purpose | 1 | Usable for a small native demo; complete engine workflows remain unavailable (open). |
| 11 | Core functionality works | 1 | Ordinary namespace/initialization fixes pass; valid temporary-like parameters still silently produce wrong values (#72).
| 12 | Secondary functionality works | 1 | Most engine primitives pass; quoted var/local text is falsely rejected as code references (#73).
| 13 | Primary workflows functional | 1 | Hosted subset builds work; Forge/plugin/assembly/UEFI/kernel primary workflows are absent (open). |
| 14 | Inputs validated | 1 | Runtime reservations fixed; valid names/string contents remain mishandled (#72/#73).
| 15 | Errors handled gracefully | 1 | Temporary-like local with a nonnumeric suffix leaks Python ValueError (#72).
| 16 | Edge cases covered | 2 | Tests cover signed/outside mouse coordinates, resize, capture, taps, wheel fractions, focus and draw-only scenes. |
| 17 | Invalid inputs controlled | 1 | Accepted temporary-like source identifiers can trigger an uncontrolled compiler exception (#72).
| 18 | Stable across repeated operations | 2 | Repeated calls/resources/input/includes and new per-call initialization regressions pass.
| 19 | No known critical defects | 1 | No runtime corruption reproduced, but valid-program silent miscompilation remains (#72).
| 20 | Components integrate | 1 | Ordinary variables integrate; source identifiers still alias internal scratch storage (#72).
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
| 31 | Automated tests provided | 2 | 136 Python tests and extension0.1.11 validation independently pass.
| 32 | Core tests covered | 1 | Nine differential cases improve coverage; internal-name collisions and quoted reference text escaped it (#72/#73).
| 33 | Failure scenarios tested | 2 | Invalid mouse arguments/keys and bitmap allocation-failure injection are covered. |
| 34 | Edge cases explicitly tested | 2 | Taps, repeats, simultaneous buttons, actual OS capture, wheel accumulation and draw-only behavior are tested. |
| 35 | Integration behavior tested | 1 | Coordinate test uses an explicit test-only WndProc wrapper; untouched OS-dispatch coverage is incomplete (#63, open). |
| 36 | Documented test commands work | 2 | Documented Python and extension validation commands run successfully. |
| 37 | Builds and compilation pass | 2 | 136tests, C/native probes, compileall and extension/package checks pass; extra valid-input failures separately tracked.
| 38 | Results recorded accurately | 2 | Exact baseline and unscored follow-up separated; prior cursor-movement claim and failed development run disclosed.
| 39 | Regression checks performed | 2 | Full suite and prior slow-draw/failure/resource regressions pass. |
| 40 | Verified against original goal | 0 | Only a prototype subset is verified; implement and verify full scope (open). |
| 41 | Installation instructions accurate | 2 | Python/native and Python/MSVC routes match independently exercised builds; extension installation documented. |
| 42 | Setup reproducible | 1 | Subset setup is reproducible; full engine setup is missing (open). |
| 43 | Usage understandable | 2 | Corrected compiler/migration guides identify actual support, usage and backend limits.
| 44 | Design decisions documented | 2 | Migration design and limits are documented. |
| 45 | Troubleshooting available | 2 | README, native diagnostic tables and include/depth troubleshooting provide actionable subset guidance.
| 46 | Opens in intended environment | 1 | CLI/editor automation works; complete native project/editor/runtime workflow (open). |
| 47 | Editor integration works | 1 | Grammar, corrected indentation/folding and VSIX parity pass; current newer installed-editor behavior remains unverified.
| 48 | Deliverables organized | 2 | Deliverables are organized and pushed. |
| 49 | Limitations disclosed | 2 | Native limitations are disclosed. |
| 50 | Practical for intended scope | 0 | Full game-engine/Forge scope remains incomplete (open). |
| | **Requirement fulfillment** | **11/20** | |
| | **Functionality and reliability** | **12/20** | |
| | **Code quality and architecture** | **14/20** | |
| | **Testing and verification** | **16/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **68/100** | Exact commit `be0d591`; FAIL against 98. |

### Deduction details and follow-up

- **#72 — scratch identity (3/8/11/14/15/17/19/20/32):** Source names beginning `_temporary_` alias internal slots; parameter7 returns0 and a nonnumeric suffix leaks ValueError. This breaks valid programs. Replace string-generated scratch names with private typed identities across arrays, calls, loops and math; add differential name/suffix cases. Current correction awaits independent verification.
- **#73 — quoted reference text (8/12/14/32):** `display text("var(ghost)")` and local-like text are falsely rejected as references. This blocks literal text/paths. Collect references outside quoted/escaped strings using shared lexical handling; preserve actual references and source metadata. Current correction awaits independent verification.
- **Scope (2–6/9–10/13/28/40/50):** Complete native engine, actual DXR/Embree, rich types, Forge/OS outputs and measured efficiency remain absent. Deliver full issue23 scope with executable acceptance evidence before default migration/completion.
- **Architecture (22/23/25/27/30):** Raw opcode/ABI duplication and semantic/frame/runtime coupling increase maintenance risk. Consolidate instruction/ABI helpers and validated lowering/storage interfaces.
- **Integration (35):** Instrumented/synchronized coordinate samples do not prove untouched OS pointer dispatch (#63). Gather independent integration evidence within input constraints.
- **Setup/editor (42/46/47):** Full project/engine/Forge/OS setup cannot be reproduced; newer installed-editor visuals remain unverified (#24). Implement missing workflows and respect installed0.1.4 preference.

The evaluator independently verified #58/#67–71 corrections, all63 public runtime reservations and a16-parameter conditional-local probe. #71 removes legacy desktop-pointer movement and the draw/update fixture race; historical no-global-input claims were corrected. A prior136-test development failure is retained in issue#71; the corrected full local run passed136 in116.325s before independent136/117.892s verification. Current tests contain no global pointer/keyboard injection calls. No CUA/manual editor inspection occurred. Current #72/#73 corrections pass139 local tests in126.156s and47 targeted tests, compileall, QA arithmetic, strictUTF8/review-vector parity and diff checks; they have no independent score yet.

## Review history

| Exact snapshot | Score / threshold | Evidence and changes |
|---|---|---|
| `5e80af327d1cedf9aafdc6af11a196702a866da5` | 68 / 98 — FAIL | 133tests; #66 verified, #67–69 found and #58 remained. Categories11/14/14/15/14. |
| `148363296d51de59e3b92db3bf768d19ad5d2ee2` | 71 / 98 — FAIL | 131 tests; #64/#65 verified; residual #66 and stale #58 found. Categories11/17/13/16/14. |
| `edfbe86252deb5af39504161f6e8571ae917fbb9` | 71 / 98 — FAIL | 125 tests; includes/function selection verified; #64 provenance and #65 recursion found. Categories 11/16/13/17/14. |
| `3270998384367be7b763cc605c0492208a72c988` | 72 / 98 — FAIL | 111 tests; #60 Wiki, #61 explicit-main arguments and #62 coordinate-test timing fixed; #63 remaining coverage gap. |
| `c10260483eab6b5adaadd261a66a92a9138b9ed8` | 92 / 98 — FAIL | Historical C-backed 77-test snapshot; UTF-8/status #48 fixed. It predates the direct-native/Forge/OS goal expansion. |
| `2a745bb9b455baffe9248f24d39970ea31146b23` | 90 / 90 — historical PASS | Earlier prototype evaluation; below today's 98 threshold and not proof of current full-goal completion. |

Earlier reports and their complete rubric tables remain available in Git history. Previous resolved defects include QA arithmetic #44, local-array recursion #21, near-plane overflow #47, native numeric diagnostics #49/#52–54, flicker #57, Wiki #60, entry arguments #61 and fixture race #62. Their resolutions do not close broader capability gaps.

## Bug tracking

All confirmed findings have detailed reproduction, impact and acceptance criteria in GitHub with `Codex Bugs`; user reports use `Romans21216 - Bugs`. Current compiler findings: [#72 temporary identities](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/72), [#73 quoted references](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/73). [#63 coordinate integration](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/63) and broader systems in#5–11/#14–15/#24 remain open. Complete backlog only in [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23).
