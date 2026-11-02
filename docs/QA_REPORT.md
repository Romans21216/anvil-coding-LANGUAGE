# Anvil QA report

**Review date:** 2026-11-02
**Latest independent evaluation:** **78/100 - FAIL** on base `0e2126ecf01f1815bffef33a7d270f7cf2f3da50`, source/test diff SHA256 `ddf56f5fe30c6caf138e9fcb7716f0d1e60c84a5e4cd73d92a9f2ecf4036c5d9`, reviewed complete diff SHA256 `8498be7b670f7f676dbc0e90942535eb68e6efcbc3228cddaa0d95a13ed7bc70`. The review covered the build-cleanup source/test snapshot; this report update is documentation synchronization.
**Current passing threshold:** 98/100. Historical scores do not establish current full-goal completion.
**Evaluator:** separate `final_review` agent, full 50-criterion review.

The generated-C/MSVC path is the required compiler workflow; direct-native parity is optional. The full engine, selectable DXR/Embree, rich types, Forge formats, assembly/UEFI/OS targets and measured optimization remain incomplete. The complete inventory remains exclusively in issue #23/comments.

## Independent verification for this snapshot

- Exact review source: base `0e2126ecf01f1815bffef33a7d270f7cf2f3da50`, source/test diff SHA256 `ddf56f5fe30c6caf138e9fcb7716f0d1e60c84a5e4cd73d92a9f2ecf4036c5d9`, reviewed complete diff SHA256 `8498be7b670f7f676dbc0e90942535eb68e6efcbc3228cddaa0d95a13ed7bc70`; changed-file hashes are recorded in both structured status JSON documents.
- `python -m unittest discover -s tests -q`: **216 passed** in **242.910 seconds**, exit0. The run covers default temporary C/object/helper cleanup and explicit C preservation.
- `npm test --prefix vscode-extension`, compileall, QA rubric arithmetic, strict UTF-8 parsing of both structured records, and `git diff --check` passed. Installed VS Code0.1.4 remained unchanged; source/package0.1.13 was checked.
- The C build now removes generated C by default; `--generated-c PATH` preserves it and `--emit-c PATH` emits C without linking. End-to-end tests build and run a program that prints23, verify no sibling generated C/object directory remains, and preserve a pre-existing caller-owned `.build.cmd` sentinel.
- An independent failure-path probe confirmed a mocked compiler-launch failure cleans temporary helpers while preserving the sentinel. Issue #87's ownership defect is fixed and closed after this independent verification.
- The reviewer reread issue #23 and its63 comments after testing, including the new C/assembly UEFI-kernel, Anvil-authored OS interface, and modular optional-feature clarification. No new defect was found. Direct-native parity remains optional under the C-first direction.
- Issues #79 and #81–#87 are verified fixed; #63 remains an integration evidence gap. No extension was installed and no global input was used.

## Latest 50-criterion scoring — base `0e2126ec` plus source/test diff `ddf56f5f`

**78/100 — FAIL against98.** Categories: requirements13/20; functionality/reliability18/20; architecture15/20; verification17/20; delivery15/20.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Full current #23 scope and the C-first update were read. |
| 2 | Implicit requirements addressed | 1 | Portability, full resources and production lifecycle remain incomplete. |
| 3 | Functionality matches intended goal | 1 | Working language subset; full engine, Forge and OS scope is incomplete. |
| 4 | Required deliverables present | 1 | Compiler/runtime/docs/VSIX exist; broad engine and systems deliverables remain absent. |
| 5 | No essential feature missing | 0 | Rich types, audio, GPU/DXR/Embree, broader assets/physics/networking and Forge/OS remain absent or partial. |
| 6 | Stated constraints respected | 2 | Inspectible C→MSVC→EXE is the required path; no silent backend change. |
| 7 | Ambiguity resolved logically | 2 | Version 1 compatibility, version 2 scope and optional native limits are explicit. |
| 8 | Behavior matches documentation | 2 | #83–#87 corrected; ordinary call argument order, callback handle capture, nested calls, build-artifact ownership, and documented exactly-once/cleanup semantics are independently verified. |
| 9 | Important use cases supported | 1 | Major engine and Forge/OS workflows remain unsupported. |
| 10 | Usable for intended purpose | 1 | Useful prototype; full production purpose remains incomplete. |
| 11 | Core functionality works | 1 | Primary C build and implemented language/runtime subset pass. |
| 12 | Secondary functionality works | 2 | Ordinary and callback compositions pass default/release probes, including side effects, nested calls, recursion, and display lowering. |
| 13 | Primary workflows functional | 1 | Forge/package/assembly/UEFI/kernel workflows remain absent. |
| 14 | Inputs validated | 2 | Invalid references, roots, arity, budgets and domains are checked. |
| 15 | Errors handled gracefully | 2 | Runtime/compile failures produce controlled diagnostics; a mocked MSVC launcher failure also cleans its owned helper directory. |
| 16 | Edge cases covered | 2 | Unicode, numeric, bounds, allocation, clipping and lifetime regressions pass. |
| 17 | Invalid inputs controlled | 2 | Malformed inputs and unsupported features are rejected in tested paths. |
| 18 | Stable across repeated operations | 2 | Runtime resource, repeated-operation and recursion tests pass. |
| 19 | No known critical defects | 2 | No confirmed critical defect remains; issues #83–#87 are fixed and independently verified. |
| 20 | Components integrate | 2 | Ordinary and callback calls use ordered lowering; generated temporary declarations, display composition, recursion and collision diagnostics pass. |
| 21 | Logical project structure | 2 | Compiler phase and runtime modules have clear responsibilities. |
| 22 | Readable and consistently formatted | 1 | Dense one-line and inconsistent formatting in new parser/codegen changes hinders maintenance. |
| 23 | Clear module responsibilities | 1 | Expression parsing, validation and emission remain coupled; add validated IR. |
| 24 | Consistent descriptive naming | 2 | Names generally communicate compiler and runtime roles. |
| 25 | Duplication minimized | 1 | Overlapping textual rewrites show duplicated reference handling; centralize structured binding. |
| 26 | Dependencies appropriate | 2 | Python/MSVC/Windows and extension dependencies are configured and verified. |
| 27 | Supports future extensions | 1 | Typed IR, object/package boundaries and platform abstraction remain incomplete. |
| 28 | No unfinished placeholders | 1 | Required engine and target breadth remains unsupported. |
| 29 | Configuration understandable | 2 | Selectors, qualifiers, aliases and project boundaries are explicit. |
| 30 | Conventions followed | 2 | C/Win32 workflow matches current conventions; broader system interfaces remain absent. |
| 31 | Automated tests provided | 2 | 216 tests and extension0.1.13 checks pass. |
| 32 | Core tests covered | 2 | Implemented behavior is covered by executable C/native tests. |
| 33 | Failure scenarios tested | 2 | Missing exports, arity, cycles, boundaries and runtime errors are exercised. |
| 34 | Edge cases explicitly tested | 2 | Aliases, private helpers/state, recursion, initialization, text and limits are tested. |
| 35 | Integration behavior tested | 1 | OS mouse-coordinate dispatch coverage #63 remains open. |
| 36 | Documented test commands work | 2 | Documented unittest/npm/QA commands execute successfully. |
| 37 | Builds and compilation pass | 2 | C/MSVC executable builds, compileall and package checks pass. |
| 38 | Results recorded accurately | 2 | Exact source, score, test timing, previous baseline and current finding are distinguished. |
| 39 | Regression checks performed | 2 | Full216-test run completed on the immutable reviewed source. |
| 40 | Verified against original goal | 0 | Full engine/Forge/OS acceptance remains incomplete; passing subsets do not prove completion. |
| 41 | Installation instructions accurate | 2 | Current C/MSVC and extension instructions are accurate. |
| 42 | Setup reproducible | 1 | Full target/platform/package setup remains incomplete. |
| 43 | Usage understandable | 2 | C-first build, metadata, v2 variables, callback usage and source-order function arguments are documented. |
| 44 | Design decisions documented | 2 | Compatibility and feature boundaries are described. |
| 45 | Troubleshooting available | 2 | Compiler/include/runtime guides include limits and diagnostics. |
| 46 | Opens in intended environment | 1 | Full editor/project/runtime workflows remain incomplete. |
| 47 | Editor integration works | 1 | VSIX grammar passes; newer visible-editor verification and advanced tools remain incomplete; preserve0.1.4. |
| 48 | Deliverables organized | 2 | Source, examples, tests, package and docs are organized; default C/object/helper intermediates are removed, with explicit C preservation options. |
| 49 | Limitations disclosed | 2 | Engine, Forge/OS, acceleration and optimization gaps are disclosed. |
| 50 | Practical for intended scope | 0 | Full engine/Forge/OS and measured-efficiency deliverables remain absent. |
| | **Requirement fulfillment** | **13/20** | |
| | **Functionality and reliability** | **18/20** | |
| | **Code quality and architecture** | **15/20** | |
| | **Testing and verification** | **17/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **78/100** | Base `0e2126ec` plus source/test diff `ddf56f5f`; FAIL against98. |

### Deduction details and follow-up

Issues #83–#87 are fixed and independently verified. Ordinary named-function calls now capture each argument in ordered compiler temporaries before invocation. The normal C build now keeps C, objects, and MSVC helper files in owned temporary directories; explicit C emission/preservation flags remain available. The new executable tests cover the original expected12/actual21 case in default/release, function-body and top-level contexts, v1/v2 sources, and generated-name conflicts. Independent probes additionally verify nested ordinary calls, recursive frame preservation (21034), seven display call groups/14 evaluations, and display temporary collision diagnostics. Existing callback handle mutation and unset-callback tests pass. No new defect was confirmed.

Other deductions remain open: complete #23 engine/media/networking/runtime/tooling/Forge/OS outputs; actual selectable DXR/Embree; platform/resource workflows and benchmark evidence; untouched #63 integration coverage; editor build/debug/navigation; expression IR and centralized structured binding; normalize new parser/codegen formatting. Direct-native parity is optional under the updated C-first direction.

The numeric score is an exact snapshot result. The C-first implementation is not complete; continue toward98 and verify the entire required goal, not only the existing suite.

## Review history

| Exact snapshot | Score / threshold | Evidence and changes |
|---|---|---|
| Base `0e2126ec` plus source/test diff `ddf56f5f…` |78 /98 FAIL|216 tests in242.910s; default build cleanup and explicit C preservation verified; #87 fixed/closed; no new finding.|
| Base `6e8d3651` plus source/test diff `8f158a13…` |78 /98 FAIL|213 tests in227.671s; #86 ordinary argument-order issue verified fixed; no new finding.|
| Base `6e8d3651` plus source/test diff `8f158a13…` |78 /98 FAIL|213 tests in227.671s; #86 fixed; no new finding.|
| Base `6852275d` plus source/test diff `301855e2…` |78 /98 FAIL|210 tests in219.067s; #83–#85 fixed; no new finding.|
| Base `6852275d` plus source/test diff `87f9eb7f…` |75 /98 FAIL|208 tests in215.487s; #83/#84 fixed; #85 was confirmed and later fixed.|
| Base `6852275d` plus diff `9ec495ff…` |75 /98 FAIL|206 tests in216.413s; #83 fixed; #84 confirmed; historical snapshot.|
| `c06744a5585d7e84ece07fc8347fb32df9897e27` |75 /98 FAIL|203 tests in223.038s; historical review; #83 discovered.|
| `b76fc02a1f6ea9ab24f7af004e8a0981ba249252` |76 /98 FAIL|194 tests in 281.445s; selective imports reviewed. #81/#82 independently verified fixed; no new finding; full goal remains incomplete.|
| `957ee124402e0ba773971aaee24c48c8b277929a` |71 /98 FAIL|192 tests in 323.089s; selective imports reviewed. #81 residual and #82 private-reference bypass confirmed; both open.|
| `68ff824b53cae9952fbfbce7fd27d29ac4bfc7f2` |76 /98 FAIL|175 tests in218.389s; native literal Unicode text verified; no new finding.|
| `139f9241a7af1c3a137d0f6408fab0bfb5141662` |76 /98 FAIL|169 tests in165.552s; both #79 failures verified fixed with110 extra full-frame guard cases.|
| `b0e02422d6447b5f6f289797e7211a9870aff26d` |73 /98 FAIL|169 tests in203.685s; original #79 hang fixed, residual negative-tangent membership found.|
| `f11240c19d708718d8b94bae5f3b3764df435f88` |73 /98 FAIL|168 tests in176.154s; native circles/lines verified; original #79 C stall discovered.|
| `ecdf68109fd5932d8ae572a8f16446194e93b935` |76 /98 FAIL|162 tests in139.160s; numeric ABI/addressing independently verified; no new finding.|
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

Focused record-only check at ba78d22 found one stale ancillary extension field in IMPLEMENTATION_STATUS.md: source0.1.11 instead of0.1.12 (#58). Corrected here; all50 scores, categories, exactb76fc02/76/194/281.445 evidence and remaining records passed. No source change or rescore; focused recheck passed at b752f41.

#81 and #82 independently VERIFIED FIXED on b76fc02: supplementary UTF-8 metadata compiles/reports correctly, and source cannot name private generated functions/arrays. Prior #79 stays verified fixed. #63 and broader #5–11/#14–15/#24/#23/#80 capability/verification gaps remain open. Confirmed findings retain detailed reproduction, impact and acceptance under Codex Bugs; user reports use Romans21216 - Bugs. Complete inventory only in [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23).

Focused independent record-only recheck at b752f41: PASS. All six current records, ancillary fields, all50 scores and both candidate_validation objects agree on reviewed source b76fc02,76/100,categories12/18/14/17/15 and194 tests281.445s. Source extension0.1.12/installed0.1.4 and historical71/192/323.089 evidence are distinguished; follow-ups null. #58 correction verified. No source change, new test run or rescore.


## Latest independent review identity

Base `0e2126ecf01f1815bffef33a7d270f7cf2f3da50`; source/test diff SHA256 `ddf56f5fe30c6caf138e9fcb7716f0d1e60c84a5e4cd73d92a9f2ecf4036c5d9`; reviewed complete diff SHA256 `8498be7b670f7f676dbc0e90942535eb68e6efcbc3228cddaa0d95a13ed7bc70`. Full suite passed216 tests in242.910s. Categories13/18/15/17/15; FAIL against98. Issue #87's temporary helper ownership fix is independently verified and closed; no new defect. The full C-first evaluation remains incomplete against issue #23.

Evaluation comment: https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6580462677
