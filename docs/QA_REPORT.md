# Anvil QA report

**Review date:** 2026-10-28
**Latest independent evaluation:** **71/100 - FAIL** on exact `148363296d51de59e3b92db3bf768d19ad5d2ee2`.
**Current passing threshold:** 98/100. Historical 90-point passes do not pass the current requirement.
**Evaluator:** separate `include_full_review` agent, full 50-criterion review.

The full goal remains incomplete: direct no-C/no-Rust engine parity, selectable DXR/Embree, rich systems-language types, Forge formats and assembly/UEFI/OS outputs are still missing. The master backlog exists only in issue #23/comments; [capability matrix](COMPLETION_MATRIX.md) describes the current limits.

## Independent verification for this snapshot

- `python -m unittest discover -s tests -q`: **131 passed**, 90.231 seconds.
- Extension 0.1.10 grammar validation and VSIX CRC/source parity passed. Language ID `anvil`, extensions `.ANVL`/`.anvl`, grammar `vscode-extension/syntaxes/anvil.tmLanguage.json`. Installed 0.1.4 remains per preference; newer visible tokens are unverified.
- Python compileall, QA arithmetic, strict UTF-8 JSON and diff checks passed.
- Adversarial probes combine 128 statement blocks with 63 grouped/unary/user-call/abs levels; accepted inputs pass. Over-budget mixed expressions return controlled diagnostics. #64 configuration locations and #65 uncontrolled compiler recursion are verified fixed.
- Source includes and native function selection were verified in the preceding `edfbe86` review: native demo 3,072 bytes, native and C/MSVC demos print 20. The full regression suite includes those execution paths.
- Native window/input tests target only their generated windows. Coordinate coverage uses explicit test instrumentation; untouched OS coordinate dispatch remains unverified (#63). No CUA/global input or fresh manual editor/sample inspection occurred.

## Latest 50-criterion scoring — `1483632`

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Language/compiler/runtime and direct target are identified. |
| 2 | Implicit requirements addressed | 1 | Runtime/input support is growing; most engine/Forge breadth remains unavailable (open). |
| 3 | Functionality matches intended goal | 1 | Keyboard and mouse native 2D rectangles work; complete engine coverage remains missing (open). |
| 4 | Required deliverables present | 1 | Compiler, extension, tests and docs exist; native engine parity is missing (open). |
| 5 | No essential feature missing | 0 | GPU rendering, broader engine systems and Forge requirements remain absent (open). |
| 6 | Stated constraints respected | 1 | Native avoids C/Rust, but C is default; port remaining APIs before switching (open). |
| 7 | Ambiguity resolved logically | 2 | Direct machine-code/PE target follows user selection. |
| 8 | Behavior matches documentation | 1 | Stale C-only capability claims and pending/latest review wording were reproduced in status documents (#58 reopened). Current rewrite awaits independent verification.
| 9 | Important use cases supported | 1 | Interactive 2D input works; native 3D/assets/physics/networking remain missing (open). |
| 10 | Usable for intended purpose | 1 | Usable for a small native demo; complete engine workflows remain unavailable (open). |
| 11 | Core functionality works | 1 | Buffered windows, fixed updates and keyboard state work; complete native engine core remains partial (open). |
| 12 | Secondary functionality works | 2 | Mouse position, buttons, wheel, capture, focus/cancel and keyboard regressions pass generated-app tests. |
| 13 | Primary workflows functional | 1 | Hosted subset builds work; Forge/plugin/assembly/UEFI/kernel primary workflows are absent (open). |
| 14 | Inputs validated | 2 | Entry arguments use ordinary validated lowering; math/RNG/noise domains and button/key inputs are checked. |
| 15 | Errors handled gracefully | 1 | Included local-array/parameter conflict names the entry file instead of the library declaration (#66); current correction awaits independent review.
| 16 | Edge cases covered | 2 | Tests cover signed/outside mouse coordinates, resize, capture, taps, wheel fractions, focus and draw-only scenes. |
| 17 | Invalid inputs controlled | 2 | Both backends enforce expression and statement depth budgets; deep and mixed-depth probes return controlled diagnostics (#65 verified fixed).
| 18 | Stable across repeated operations | 2 | 131 independently passing tests cover repeated resource/input/include operations.
| 19 | No known critical defects | 2 | No critical runtime corruption reproduced; P2 semantic provenance #66 is tracked.
| 20 | Components integrate | 2 | Cross-file recursion, native selection, graphical init and C/native demos independently pass. |
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
| 31 | Automated tests provided | 2 | 131 Python tests and extension grammar/package checks independently pass.
| 32 | Core tests covered | 2 | Generated-app globals are inspected after window-local messages. |
| 33 | Failure scenarios tested | 2 | Invalid mouse arguments/keys and bitmap allocation-failure injection are covered. |
| 34 | Edge cases explicitly tested | 2 | Taps, repeats, simultaneous buttons, actual OS capture, wheel accumulation and draw-only behavior are tested. |
| 35 | Integration behavior tested | 1 | Coordinate test uses an explicit test-only WndProc wrapper; untouched OS-dispatch coverage is incomplete (#63, open). |
| 36 | Documented test commands work | 2 | Documented Python and extension validation commands run successfully. |
| 37 | Builds and compilation pass | 2 | 131 tests, extension/VSIX parity, compileall, UTF-8 and diff checks pass.
| 38 | Results recorded accurately | 1 | Completion/status documents retain stale capability and review claims (#58); rewrite and synchronized records await independent review.
| 39 | Regression checks performed | 2 | Full suite and prior slow-draw/failure/resource regressions pass. |
| 40 | Verified against original goal | 0 | Only a prototype subset is verified; implement and verify full scope (open). |
| 41 | Installation instructions accurate | 2 | Python/native and Python/MSVC routes match independently exercised builds; extension installation documented. |
| 42 | Setup reproducible | 1 | Subset setup is reproducible; full engine setup is missing (open). |
| 43 | Usage understandable | 2 | README/include/migration guides provide executable commands and explicit limits. |
| 44 | Design decisions documented | 2 | Migration design and limits are documented. |
| 45 | Troubleshooting available | 1 | Basic guidance exists; new include/depth/target diagnostics need fuller troubleshooting (open). |
| 46 | Opens in intended environment | 1 | CLI/editor automation works; complete native project/editor/runtime workflow (open). |
| 47 | Editor integration works | 1 | Grammar checks pass; current installed package is 0.1.4, fresh visual check absent (open). |
| 48 | Deliverables organized | 2 | Deliverables are organized and pushed. |
| 49 | Limitations disclosed | 2 | Native limitations are disclosed. |
| 50 | Practical for intended scope | 0 | Full game-engine/Forge scope remains incomplete (open). |
| | **Requirement fulfillment** | **11/20** | |
| | **Functionality and reliability** | **17/20** | |
| | **Code quality and architecture** | **13/20** | |
| | **Testing and verification** | **16/20** | |
| | **Developer experience and delivery** | **14/20** | |
| | **Total** | **71/100** | Exact commit `1483632`; FAIL against 98. |

### Deduction details and follow-up

- **#66 — included semantic diagnostics (criteria 8/15):** A parameter/local-array conflict in `lib.ANVL:2` reports the entry filename. This misdirects debugging. Use the declaration's physical source/line, add both-backend CLI regressions and independently verify. Local correction is in progress; the score remains tied to the reviewed snapshot.
- **#58 — capability/review metadata (criteria 8/38):** Completion/status documents say C-only output and identify old work as latest or pending. This misstates delivered behavior and verification. Rewrite current capability summaries, retain exact review identifiers in evaluation records and verify parity. The current rewrite awaits review.
- **Scope (2–6, 9–11, 13, 28, 40, 50):** Native runtime and whole-engine/Forge/OS workflows are incomplete. Existing examples cannot satisfy these use cases. Implement the remaining issue #23 requirements with executable acceptance evidence; do not switch the default before native parity.
- **Architecture (22, 23, 25, 27, 30):** Raw byte encoding, repeated ABI sequences and platform/state coupling increase maintenance and extension risk. Consolidate instruction/ABI abstractions and runtime/backend interfaces with regression evidence.
- **Configuration/setup/tooling (29, 42, 45–47):** Native manifests and full project/editor workflows remain absent. Basic troubleshooting exists, but target/include/depth guidance needs expansion. Implement project parity and document/test setup. Installed editor 0.1.4 leaves newer visible highlighting unverified (#24).
- **Integration (35):** The coordinate test's explicit WndProc wrapper checks the handler and query behavior but cannot prove untouched end-to-end dispatch. Add independent dispatch evidence within the user's input constraints (#63).

Every deduction remains open except the specific independently resolved findings. No final release/completion is claimed. Issue #23 was checked after the critic run; no new user requirement was found. Current local #66/#58 changes have no independent score yet.

## Review history

| Exact snapshot | Score / threshold | Evidence and changes |
|---|---|---|
| `edfbe86252deb5af39504161f6e8571ae917fbb9` | 71 / 98 — FAIL | 125 tests; includes/function selection verified; #64 provenance and #65 recursion found. Categories 11/16/13/17/14. |
| `3270998384367be7b763cc605c0492208a72c988` | 72 / 98 — FAIL | 111 tests; #60 Wiki, #61 explicit-main arguments and #62 coordinate-test timing fixed; #63 remaining coverage gap. |
| `c10260483eab6b5adaadd261a66a92a9138b9ed8` | 92 / 98 — FAIL | Historical C-backed 77-test snapshot; UTF-8/status #48 fixed. It predates the direct-native/Forge/OS goal expansion. |
| `2a745bb9b455baffe9248f24d39970ea31146b23` | 90 / 90 — historical PASS | Earlier prototype evaluation; below today's 98 threshold and not proof of current full-goal completion. |

Earlier reports and their complete rubric tables remain available in Git history. Previous resolved defects include QA arithmetic #44, local-array recursion #21, near-plane overflow #47, native numeric diagnostics #49/#52–54, flicker #57, Wiki #60, entry arguments #61 and fixture race #62. Their resolutions do not close broader capability gaps.

## Bug tracking

All confirmed findings are tracked with detailed reproduction, impact and acceptance criteria under `Codex Bugs`; user reports use `Romans21216 - Bugs`. Current findings: [#58 metadata](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/58), [#63 coordinate coverage](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/63), [#66 semantic provenance](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/66). Broader systems remain tracked in #5–11, #14–15, #24 and the canonical [#23 backlog](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23).
