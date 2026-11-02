# Anvil QA report

**Review date:** 2026-11-02
**Latest independent evaluation:** **79/100 - FAIL** on base `87e23d6943028222619f9febe0ed970e8d1a7ed7`, source/test diff SHA256 `57b0392fa1a325a23fda8d1aa202e7299b141e92d390b1cc518cc0b0ad22db5c`, implementation diff SHA256 `24ad1dc17364afc5c94eb80ae8dcd8fbfafa8113f5a579c3a7c39683cd6954ac`. The independent full50 review scored78 while criterion38 still referenced the previous candidate; syncing this 233-test candidate restores criterion38 to2. The independent six-record parity recheck passed.
**Current passing threshold:** 98/100. Historical scores do not establish current full-goal completion.
**Evaluator:** separate `final_review` agent; the independent full50 review is complete and the six-record parity recheck passed.

The generated-C/MSVC path is the required compiler workflow; direct-native parity is optional. The full engine, selectable DXR/Embree, rich types, Forge formats, assembly/UEFI/OS targets and measured optimization remain incomplete. The complete inventory remains exclusively in issue #23/comments.

## Independent verification for this snapshot

- Base `87e23d6943028222619f9febe0ed970e8d1a7ed7`; source/test SHA256 `57b0392fa1a325a23fda8d1aa202e7299b141e92d390b1cc518cc0b0ad22db5c`; implementation SHA256 `24ad1dc17364afc5c94eb80ae8dcd8fbfafa8113f5a579c3a7c39683cd6954ac`; all16 changed paths at review SHA256 `caa73ca775bfd3ecca4aa1ef57e5c522cf39ae6d89b37d7333249ceedc514615`. Hashes use sorted paths and concatenated `difflib.unified_diff` output with three context lines.
- `python -m unittest discover -s tests -q`: **233 passed in253.611s** in the independent review; local run passed233 in269.749s. Three targeted C recursion, imported-native recursion and maximum-budget tests passed in2.147s. Independent compileall, VS Code extension0.1.13 validation, QA arithmetic, strict UTF-8 JSON and `git diff --check` passed. Installed VS Code0.1.4 remains unchanged.
- C function elimination starts from explicit top-level calls, or `main` when no explicit call statements exist; graphical programs start at `draw`/`update`. Transitive ordinary calls, callback dispatch targets and engine helpers remain. All function bodies are still validated.
- C generation omits unreachable Anvil functions and global scalar/array declarations unused by top-level initialization and emitted functions. Reachable writes and expression evaluation remain. A 200,000-element dead global array was omitted from generated C, while a compiled executable still printed5. A selectively imported function retained its live module storage and removed storage reachable only through an uncalled imported function. Callback targets and version1/version2 local shadowing probes also passed.
- Issue #90 was filed under Codex Bugs for the native local-array failure location. The fix reports the earliest declaration line and declaring source path, including imported modules; independent regressions assert the library path and line2. Issue #90 was fixed, independently verified, and closed after commit publication. Items #80/#81 now have partial per-project memory-budget support.
- Issues #88/#89 remain fixed. Item #123 remains partial: unreachable functions and unused global scalar/array declarations are pruned, but runtime subsystems/package features are not selectively linked.
- Reviewer reread current issue #23 and comments after tests. No new implementation defect remains. Direct-native parity remains optional; #63 integration evidence remains open.
- Synchronizing records restores criterion38 from1 to2 and the score to79/100. Independent six-record parity confirmation passed. The complete goal remains below98.

## Latest 50-criterion scoring — base `87e23d6943028222619f9febe0ed970e8d1a7ed7` plus source/test diff `57b0392f`

**79/100 — FAIL against98.** Categories: requirements13/20; functionality/reliability19/20; architecture15/20; verification17/20; delivery15/20.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Full current #23 scope and the C-first update were read. |
| 2 | Implicit requirements addressed | 1 | Portability, full resources and production lifecycle remain incomplete. |
| 3 | Functionality matches intended goal | 1 | Working language subset; full engine, Forge and OS scope is incomplete. |
| 4 | Required deliverables present | 1 | Compiler/runtime/docs/VSIX exist; broad engine and systems deliverables remain absent. |
| 5 | No essential feature missing | 0 | Rich types, audio, GPU/DXR/Embree, broader assets/physics/networking and Forge/OS remain absent or partial. |
| 6 | Stated constraints respected | 2 | Inspectible C→MSVC→EXE is the required path; no silent backend change. |
| 7 | Ambiguity resolved logically | 2 | Version 1 compatibility, version 2 scope and optional native limits are explicit. |
| 8 | Behavior matches documentation | 2 | Compiler docs match generated behavior: reachable functions and unused global scalar/array storage are pruned after validation; startup calls, callbacks, and transitive dependencies remain. |
| 9 | Important use cases supported | 1 | Major engine and Forge/OS workflows remain unsupported. |
| 10 | Usable for intended purpose | 1 | Useful prototype; full production purpose remains incomplete. |
| 11 | Core functionality works | 2 | Primary C build, function/storage reachability, selected imports, and implemented runtime subset pass executable probes. |
| 12 | Secondary functionality works | 2 | Ordinary and callback compositions pass default/release probes, including side effects, nested calls, recursion, and display lowering. |
| 13 | Primary workflows functional | 1 | Forge/package/assembly/UEFI/kernel workflows remain absent. |
| 14 | Inputs validated | 2 | Invalid references, roots, arity, budgets and domains are checked. |
| 15 | Errors handled gracefully | 2 | Runtime/compile failures produce controlled diagnostics; a mocked MSVC launcher failure also cleans its owned helper directory. |
| 16 | Edge cases covered | 2 | Unicode, numeric, bounds, allocation, clipping and lifetime regressions pass. |
| 17 | Invalid inputs controlled | 2 | Malformed inputs and unsupported features are rejected in tested paths. |
| 18 | Stable across repeated operations | 2 | Runtime resource, repeated-operation and recursion tests pass. |
| 19 | No known critical defects | 2 | No current implementation defect was confirmed; #83–#90 are fixed and independently verified. Issue #90 closure follows commit publication. |
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
| 31 | Automated tests provided | 2 | 233 tests passed independently in253.611s and locally in269.749s; extension0.1.13 checks pass. |
| 32 | Core tests covered | 2 | Implemented behavior is covered by executable C/native tests. |
| 33 | Failure scenarios tested | 2 | Missing exports, arity, cycles, boundaries and runtime errors are exercised. |
| 34 | Edge cases explicitly tested | 2 | Aliases, private helpers/state, recursion, initialization, text and limits are tested. |
| 35 | Integration behavior tested | 1 | OS mouse-coordinate dispatch coverage #63 remains open. |
| 36 | Documented test commands work | 2 | Documented unittest/npm/QA commands execute successfully. |
| 37 | Builds and compilation pass | 2 | C/MSVC executable builds, compileall and package checks pass. |
| 38 | Results recorded accurately | 2 | Exact source/test/implementation hashes, both 233-test runs and all50 criterion scores are synchronized; independent record-parity recheck passed. |
| 39 | Regression checks performed | 2 | Full233-test runs passed independently and locally; C/native memory bounds, recursive exhaustion and imported-source diagnostics are covered. |
| 40 | Verified against original goal | 0 | Full engine/Forge/OS acceptance remains incomplete; passing subsets do not prove completion. |
| 41 | Installation instructions accurate | 2 | Current C/MSVC and extension instructions are accurate. |
| 42 | Setup reproducible | 1 | Full target/platform/package setup remains incomplete. |
| 43 | Usage understandable | 2 | C-first build, metadata, v2 variables, callback usage and source-order function arguments are documented. |
| 44 | Design decisions documented | 2 | Compatibility and feature boundaries are described. |
| 45 | Troubleshooting available | 2 | Compiler/include/runtime guides include limits and diagnostics. |
| 46 | Opens in intended environment | 1 | Full editor/project/runtime workflows remain incomplete. |
| 47 | Editor integration works | 1 | VSIX grammar passes; newer visible-editor verification and advanced tools remain incomplete; preserve0.1.4. |
| 48 | Deliverables organized | 2 | Source, examples, tests, package and docs are organized; function reachability is explicit and build intermediates are cleaned. |
| 49 | Limitations disclosed | 2 | Engine, Forge/OS, acceleration and optimization gaps are disclosed. |
| 50 | Practical for intended scope | 0 | Full engine/Forge/OS and measured-efficiency deliverables remain absent. |
| | **Requirement fulfillment** | **13/20** | |
| | **Functionality and reliability** | **19/20** | |
| | **Code quality and architecture** | **15/20** | |
| | **Testing and verification** | **17/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **79/100** | Base `87e23d69` plus source/test diff `57b0392f`; FAIL against98. |

### Deduction details and follow-up

Issues #83–#88 are fixed and independently verified. Ordinary named-function calls now capture each argument in ordered compiler temporaries before invocation. The normal C build now keeps C, objects, and MSVC helper files in owned temporary directories; explicit C emission/preservation flags remain available. The new executable tests cover the original expected12/actual21 case in default/release, function-body and top-level contexts, v1/v2 sources, and generated-name conflicts. Independent probes additionally verify nested ordinary calls, recursive frame preservation (21034), seven display call groups/14 evaluations, and display temporary collision diagnostics. Existing callback handle mutation and unset-callback tests pass. The #88 entry-root and #89 graphical-startup defects were fixed and independently verified. The new storage pass prunes declarations only; it preserves all writes and expression evaluation. No new implementation defect was confirmed.

Other deductions remain open: complete #23 engine/media/networking/runtime/tooling/Forge/OS outputs; actual selectable DXR/Embree; platform/resource workflows and benchmark evidence; untouched #63 integration coverage; editor build/debug/navigation; expression IR and centralized structured binding; normalize new parser/codegen formatting. Direct-native parity is optional under the updated C-first direction.

The numeric score is an exact snapshot result. The C-first implementation is not complete; continue toward98 and verify the entire required goal, not only the existing suite.

## Review history

| Exact snapshot | Score / threshold | Evidence and changes |
|---|---|---|
| Base `87e23d69` plus source/test diff `57b0392f…` |79 /98 FAIL|233 tests passed locally in269.749s and independently in253.611s; project memory budgets and imported native diagnostics reviewed; criterion38 restored after record sync; independent six-record parity recheck passed.|
| Base `7b0e921d` plus code/test diff `e61e6091…` |79 /98 FAIL|227 tests passed locally in293.538s and independently in254.117s; global storage, selective-import, callback, and local-shadowing probes passed; historical parity audit passed.|
| Base `7b0e921d` plus code/test diff `24dbf3ea…` |79 /98 FAIL|224 tests passed in both local250.318s and independent257.990s runs; #89 graphical startup and C DCE roots verified; score79 after record synchronization and independent parity recheck passed.|
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

Base `87e23d6943028222619f9febe0ed970e8d1a7ed7`; source/test SHA256 `57b0392fa1a325a23fda8d1aa202e7299b141e92d390b1cc518cc0b0ad22db5c`; implementation SHA256 `24ad1dc17364afc5c94eb80ae8dcd8fbfafa8113f5a579c3a7c39683cd6954ac`; all16 changed paths at review SHA256 `caa73ca775bfd3ecca4aa1ef57e5c522cf39ae6d89b37d7333249ceedc514615`. Full suite passed233 tests independently in253.611s and locally in269.749s. Categories13/19/15/17/15; score79/100 after record sync. `[memory]` limits apply to C/native builds and nested includes; native allocation diagnostics report the declaring module path and line. #90 was fixed, independently verified, and closed after publication; issues #87–#89 are also closed. #123 remains partial because runtime subsystems and packages are not selectively linked. The full goal remains incomplete.

Latest evaluation comment: https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6583162339

Independent six-record record-only recheck: PASS. All six current records agree on candidate base/hash identity, score79/100, criterion vector/category subtotals, 233 local/independent test results and timings, 3 focused tests, issue #23 comment count69 before this update, and issue #90 fixed-but-open status. No source change, test rerun, or rescore.

Publication record: reviewed candidate pushed to `main` as `b4e8a20ee511388123f4982001ac997c6c720e4f`; issue #90 closed with exact reproduction and passing test evidence; issue #23 evaluation comment https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6583162339 posted (70 comments after publication). Score remains79/100; no rescore.
