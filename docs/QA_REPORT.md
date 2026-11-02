# Anvil QA report

## Current reviewed candidate

**Latest independent evaluation:** **79/100 after record synchronization — FAIL against 98** (raw independent score 78; criterion 38 restored after sync). Categories: requirements 13/20, functionality/reliability 19/20, architecture 15/20, testing/verification 17/20, delivery 15/20.

**Reviewed candidate:** `9d69a44e563373e5085fb30445c29312ec793ed3` (base `513b1d02de3b599070d04324a8d3460300e40241`). Independent reviewer found no reproducible defect. Full binary Git diff SHA256: `0c365af6b748171406d69b554485e8013eb1cc3c9c6f2edb6e1cf8baba614651`; all-text unified diff SHA256: `f66d13c0eec7cc08a00281116e8ce7d3e831bb78763502a293067516d219e654`; compiler/runtime/tests unified diff SHA256: `9ff18d6826b7b907558789a1de8f5505f6b4618cdbd393aa3b29e207d8d36ebd`; documentation unified diff SHA256: `02273fa646348096ac1abdd91ef3fb44fad3e99a2a0e382c008648f3cbe2f7a1`. Hashes use sorted paths and Python `difflib.unified_diff` with three context lines.

- Local full suite: **266 tests passed in 366.905s**.
- Independent full suite on the exact candidate: **266 tests passed in 416.764s**. Four focused image selection/runtime tests passed independently in 5.239s. Compileall, extension npm validation, QA validator after synchronization, strict UTF-8 JSON and `git diff --check` passed.
- The C build now compiles BMP image decoding/drawing as `runtime/anvil_image.c` only when reachable image built-ins are used. Image resources release through runtime shutdown hooks. No new defect was confirmed.
- Full requirements remain in GitHub issue #23. User-facing packages, broad engine/language features, actual DXR/Embree, Forge/media, OS/UEFI, portability, editor workflows and measured performance remain incomplete. Goal remains active.

### Latest 50-criterion scoring

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|---:|---|
| 1 | requirements identified | 2 | requirements reviewed against the project objective and issue #23 |
| 2 | implicit requirements | 1 | portability and lifecycle work remain incomplete |
| 3 | functionality | 1 | implemented subset is useful; broad engine and Forge scope remains |
| 4 | deliverables | 1 | compiler, runtime, extension, docs and tests exist; many requested systems remain absent |
| 5 | essential features | 0 | essential language, engine and target capabilities are still missing |
| 6 | constraints | 2 | documented C/MSVC default and optional direct-native path are respected |
| 7 | ambiguity | 2 | backend boundaries and image API behavior are documented |
| 8 | documentation parity | 2 | reachable selection, image cleanup and documented image limits match implementation |
| 9 | use cases | 1 | small-game workflows work; many listed use cases remain unsupported |
| 10 | intended purpose | 1 | early prototype, not yet a practical general game engine |
| 11 | core functionality | 2 | image loading, drawing and cleanup passed a native runtime harness |
| 12 | secondary functionality | 2 | reachable and unreachable image calls select expected runtime modules |
| 13 | primary workflows | 1 | build/use works; package, Forge and OS workflows remain absent |
| 14 | input validation | 2 | BMP dimensions, format, pixel count, row stride and memory use are bounded |
| 15 | error handling | 2 | allocation/load failure paths return safely; shutdown cleanup was exercised |
| 16 | edge coverage | 2 | tests cover top-down images, invalid/oversized images, clipping, stale handles and shutdown |
| 17 | invalid inputs | 2 | invalid image cases fail without uncontrolled termination |
| 18 | repeat stability | 2 | full suite and repeated runtime tests passed |
| 19 | critical defects | 2 | no critical defect reproduced in this change |
| 20 | integration | 2 | compiler markers, module selection, C build and runtime cleanup integrate in tests |
| 21 | project structure | 2 | image runtime is separated into a dedicated source module |
| 22 | formatting | 1 | formatting debt remains in the wider codebase |
| 23 | module responsibilities | 1 | image/network/physics modules are separate; renderer and remaining runtime stay coupled in core |
| 24 | naming | 2 | module and shutdown-hook names are descriptive and consistent |
| 25 | duplication | 1 | compiler/runtime knowledge and pixel-blending logic remain duplicated in places |
| 26 | dependencies | 2 | module adds no external dependency; existing Windows runtime requirements are explicit |
| 27 | extensibility | 1 | registry selection is internal; user-facing packages/plugins remain unfinished |
| 28 | unfinished scope | 1 | direct-native image support and broader runtime modularity remain unfinished |
| 29 | configuration | 2 | module selection is explicit and tied to generated markers |
| 30 | conventions | 2 | code follows existing C and Windows runtime conventions |
| 31 | automated tests | 2 | relevant automated tests are present and passed |
| 32 | core tests | 2 | image parsing, module selection and cleanup are tested |
| 33 | failure tests | 2 | invalid images and allocation/load failures are covered |
| 34 | edge tests | 2 | image bounds, clipping, top-down BMPs, alpha and stale handles are tested |
| 35 | integration tests | 1 | image integration is covered; unrelated OS-dispatch gap #63 remains |
| 36 | test commands | 2 | documented unittest, extension and QA commands ran |
| 37 | builds | 2 | full suite and MSVC-backed runtime image test passed |
| 38 | results recorded | 2 | raw review assigned 1; exact candidate evidence is synchronized here, restoring this point |
| 39 | regressions | 2 | full regression suite passed after the refactor |
| 40 | full goal | 0 | full objective remains incomplete |
| 41 | installation | 2 | build/setup instructions match implementation |
| 42 | reproducibility | 1 | runtime and image module remain Windows-specific |
| 43 | usage | 2 | language and build usage are documented |
| 44 | design documentation | 2 | module selection, image limits and cleanup behavior are documented |
| 45 | troubleshooting | 2 | troubleshooting guidance exists |
| 46 | editor workflow | 1 | VS Code workflow exists; broader editor/project workflows remain incomplete |
| 47 | editor integration | 1 | extension validation passes; installed 0.1.4 preserved, newer package not visually verified |
| 48 | organization | 2 | source, runtime, tests and docs are organized |
| 49 | limitations | 2 | native image limitations and remaining engine scope are disclosed |
| 50 | practical scope | 0 | deliverable is not yet suitable for the full production-quality goal |
| | **Requirement fulfillment** | **13/20** | |
| | **Functionality and reliability** | **19/20** | |
| | **Code quality and architecture** | **15/20** | |
| | **Testing and verification** | **17/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **79/100** | FAIL against 98 |

### Deduction details and follow-up

The raw independent result was 78/100 because criterion 38 was 1 while the records still described the previous candidate. Exact candidate identity, hashes, complete 50-score vector and local/independent test evidence are synchronized here, restoring criterion 38 to 2 and the score to 79. The overall goal remains substantially incomplete; see issue #23 for the complete requirements.

## Review history

| `de68679f1f05a3a5db7b5eadbf20989e43321a76` |79 /98 FAIL|Registry-driven runtime-module trigger patterns; 253 tests local285.750s and independent283.720s; raw78, criterion38 restored to79; no defect; evaluation comment6585531493.|

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


## Historical review identity — project memory-budget candidate (superseded)

Base `87e23d6943028222619f9febe0ed970e8d1a7ed7`; source/test SHA256 `57b0392fa1a325a23fda8d1aa202e7299b141e92d390b1cc518cc0b0ad22db5c`; implementation SHA256 `24ad1dc17364afc5c94eb80ae8dcd8fbfafa8113f5a579c3a7c39683cd6954ac`; all16 changed paths at review SHA256 `caa73ca775bfd3ecca4aa1ef57e5c522cf39ae6d89b37d7333249ceedc514615`. Full suite passed233 tests independently in253.611s and locally in269.749s. Categories13/19/15/17/15; score79/100 after record sync. `[memory]` limits apply to C/native builds and nested includes; native allocation diagnostics report the declaring module path and line. #90 was fixed, independently verified, and closed after publication; issues #87–#89 are also closed. #123 remains partial because runtime subsystems and packages are not selectively linked. The full goal remains incomplete.

Latest evaluation comment: https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6583162339

Historical record-only recheck for the project-memory-budget candidate: PASS at that time. Its 233-test evidence, 69-comment issue count, and #90 state do not describe the current candidate.

Historical publication record for the superseded project-memory-budget candidate: commit `b4e8a20ee511388123f4982001ac997c6c720e4f`; issue #90 closed; issue #23 evaluation comment #6583162339. This does not describe the current networking-module candidate.
