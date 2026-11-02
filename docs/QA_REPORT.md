# Anvil QA report

**Review date:** 2026-11-02
**Latest independent evaluation:** **79/100 - FAIL** on base `57101e5e517cbc533b94fa394dc0c9e7d419851f`, source/test diff SHA256 `3f4b3b491c43b75a502ab76a46e785d6bd0716cc913de964896e268f8a7a63fc`, non-test implementation diff SHA256 `17d6c2242467e1f97a964247e258b96962685002bc97682c5687f79b97f328f7`, and original eight-path reviewed diff SHA256 `e7fe4e704c5693071deace3724f62dee1b9cb28d29dc8e8dba65f736c8866ee4`. The post-record-sync eight-path worktree hash is `96150fc7c167fce8cc33abf4fade221d76f1a341d9c532444ca093b39ebab363`; that hash includes the evaluation summary edit in `COMPLETION_MATRIX.md` and does not change the reviewed code/test hash. Full50 independent review initially scored78/100 because criterion38 records still identified the previous candidate; syncing the six records restores criterion38 and the score to79. Categories13/19/15/17/15. Independent six-record record-only parity recheck: PASS.
**Evaluation comment:** https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6583971959 (issue #23 now has71 comments). Candidate source commit `18ec564a53b79dc7577e804f78bf6a5cebeff7d1` is published to origin/main.
**Current passing threshold:** 98/100. Historical scores and passing subsets do not establish full-goal completion.
**Evaluator:** separate `final_review` agent. It ran9 targeted build/code-generation tests, all passing; `compileall`, QA arithmetic and diff checks passed. The 240-test full-suite result (310.826s) is the local exact-candidate run; the reviewer did not repeat that long run.

## Reviewed candidate and verification

- Reviewed base `57101e5e517cbc533b94fa394dc0c9e7d419851f` plus the eight-file implementation/documentation batch. Sorted-path UTF-8 `difflib.unified_diff` with three context lines: compiler/test SHA256 `3f4b3b491c43b75a502ab76a46e785d6bd0716cc913de964896e268f8a7a63fc`; non-test implementation SHA256 `17d6c2242467e1f97a964247e258b96962685002bc97682c5687f79b97f328f7`; original eight-path reviewed SHA256 `e7fe4e704c5693071deace3724f62dee1b9cb28d29dc8e8dba65f736c8866ee4` (post-sync eight-path hash is recorded in the summary header).
- Local: `python -m unittest discover -s tests -q` passed **240 tests in310.826s**. `python -m compileall -q compiler tests scripts`, `python scripts/validate_qa_report.py`, strict UTF-8 JSON parsing and `git diff --check` passed.
- Independent reviewer: **9 targeted tests passed**; paired MSVC release executables both printed `23`. Without synthetic legacy runtime roots, size was142,848 bytes versus143,360 bytes (512-byte reduction). This is one sample and gives no broad CPU, memory or size claim.
- No new confirmed defect. The former helper collision finding is fixed in the current source: the MSVC helper lives in its owned object temporary directory, and a sentinel preservation test passes. Installed VS Code0.1.4 remains unchanged.
- This batch enables release COMDAT/linker pruning and removes unconditional engine/network roots for console programs. Runtime sources remain monolithic; feature packages, broad engine/runtime systems, Forge, OS/UEFI work, DXR/Embree, and measured efficiency remain incomplete. Full requirement inventory stays only in [GitHub issue #23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23).

## Latest 50-criterion scoring — base `57101e5e517cbc533b94fa394dc0c9e7d419851f` plus compiler/test diff `3f4b3b491c43b75a502ab76a46e785d6bd0716cc913de964896e268f8a7a63fc`

**79/100 — FAIL against98 after record synchronization** (independent raw score78 before criterion38 synchronization).

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Current #23 requirements and C-first direction were reviewed. |
| 2 | Implicit requirements addressed | 1 | Portability and full resource lifecycle remain incomplete. |
| 3 | Functionality matches intended goal | 1 | Implemented language works; complete engine and Forge/OS scope do not. |
| 4 | Required deliverables present | 1 | Compiler, runtime, docs and extension exist; broad deliverables remain. |
| 5 | No essential feature missing | 0 | Rich types, audio, GPU/DXR/Embree, broad assets/physics/networking, Forge/OS are absent or partial. |
| 6 | Stated constraints respected | 2 | Required .ANVL-to-C-to-MSVC-to-EXE path remains intact. |
| 7 | Ambiguity resolved logically | 2 | Compatibility and backend boundaries are documented. |
| 8 | Behavior matches documentation | 2 | Release linker GC and conditional engine/network roots match docs. |
| 9 | Important use cases supported | 1 | Major engine and Forge/OS use cases remain unsupported. |
| 10 | Usable for intended purpose | 1 | Useful prototype, not the full intended product. |
| 11 | Core functionality works | 2 | Targeted executable/build probes and paired output probe pass. |
| 12 | Secondary functionality works | 2 | Root selection and linker options have focused regressions. |
| 13 | Primary workflows functional | 1 | Forge, package, assembly, UEFI and kernel workflows remain absent. |
| 14 | Inputs validated | 2 | Tested compiler/build inputs are validated. |
| 15 | Errors handled gracefully | 2 | Helper cleanup and unrelated sentinel-file preservation are tested. |
| 16 | Edge cases covered | 2 | Focused linker/root cases pass. |
| 17 | Invalid inputs controlled | 2 | Invalid and unsupported input handling remains tested. |
| 18 | Stable across repeated operations | 2 | No repeated-operation issue was found in the changed path. |
| 19 | No known critical defects | 2 | No new critical defect confirmed; helper collision fix is present. |
| 20 | Components integrate | 2 | Compiler, C output, linker settings and tests integrate for this behavior. |
| 21 | Logical project structure | 2 | Compiler/build responsibilities remain understandable. |
| 22 | Readable and consistently formatted | 1 | Dense and inconsistent formatting remains a maintenance cost. |
| 23 | Clear module responsibilities | 1 | Parsing, validation and emission remain coupled; validated IR is absent. |
| 24 | Consistent descriptive naming | 2 | Names are generally descriptive. |
| 25 | Duplication minimized | 1 | Textual rewrites and repeated reference handling remain. |
| 26 | Dependencies appropriate | 2 | Current build dependencies fit the Windows/MSVC target. |
| 27 | Supports future extensions | 1 | Platform abstraction and package/object boundaries remain limited. |
| 28 | No unfinished placeholders | 1 | Required engine and target breadth remains unfinished. |
| 29 | Configuration understandable | 2 | Current build configuration is understandable. |
| 30 | Conventions followed | 2 | C/Win32 conventions fit this implementation. |
| 31 | Automated tests provided | 2 | 240 full-suite tests pass on the candidate; reviewer ran 9 focused tests. |
| 32 | Core tests covered | 2 | Changed linker and code-generation paths have regressions. |
| 33 | Failure scenarios tested | 2 | Build failure cleanup and root selection have focused coverage. |
| 34 | Edge cases explicitly tested | 2 | Release/debug separation and string false-positive cases are tested. |
| 35 | Integration behavior tested | 1 | OS mouse-coordinate dispatch integration gap #63 remains open. |
| 36 | Documented test commands work | 2 | QA arithmetic, compileall and diff checks pass. |
| 37 | Builds and compilation pass | 2 | MSVC release probe succeeded with matching program output. |
| 38 | Results recorded accurately | 2 | Independent review initially scored1 while records described the previous candidate; record sync restores2. |
| 39 | Regression checks performed | 2 | Full local suite plus reviewer targeted checks pass. |
| 40 | Verified against original goal | 0 | Complete engine/Forge/OS acceptance remains incomplete. |
| 41 | Installation instructions accurate | 2 | Current installation instructions remain accurate. |
| 42 | Setup reproducible | 1 | Platform and package setup is still incomplete. |
| 43 | Usage understandable | 2 | C-first workflow is clear. |
| 44 | Design decisions documented | 2 | Current design boundaries are documented. |
| 45 | Troubleshooting available | 2 | Troubleshooting and compiler/build documentation exist. |
| 46 | Opens in intended environment | 1 | Full editor, project and runtime workflows remain incomplete. |
| 47 | Editor integration works | 1 | Extension validation exists; newer visible verification is incomplete and installed0.1.4 stays unchanged. |
| 48 | Deliverables organized | 2 | Files are organized; helper intermediates are isolated and cleaned. |
| 49 | Limitations disclosed | 2 | Major limitations are disclosed. |
| 50 | Practical for intended scope | 0 | Full engine and Forge/OS objective remains unverified. |
| | **Requirement fulfillment** | **13/20** | |
| | **Functionality and reliability** | **19/20** | |
| | **Code quality and architecture** | **15/20** | |
| | **Testing and verification** | **17/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **79/100** | Base `57101e5e517cbc533b94fa394dc0c9e7d419851f` plus source/test diff `3f4b3b491c43b75a502ab76a46e785d6bd0716cc913de964896e268f8a7a63fc`; FAIL against98. Independent pre-sync score78; criterion38 is restored after six-record synchronization. |

### Deduction details and follow-up

The current change improves release executable reachability and size by removing unnecessary generated roots and enabling linker garbage collection. Its measured saving is512 bytes in the paired sample only. The overall implementation still needs modular feature packages and automatic dependency handling; broader language, engine, rendering backends, media/audio, physics/networking, Forge formats, system/UEFI/OS workflows, benchmark evidence, and editor workflows remain substantial work. Item #63 integration evidence remains open. Direct-native parity is optional under the current C-first direction. The full goal remains below98 and active.

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
