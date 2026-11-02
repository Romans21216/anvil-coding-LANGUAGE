# Anvil QA report

## Current reviewed candidate

**Latest independent evaluation:** **79/100 - FAIL** against98 after record sync (raw77; criteria8 and38 restored to2).

Base f17498e709094573230c07c22de11278729e9858; source/test SHA256 fa614535072b589b80ce32146d44d91a046461c2fd7d26401f30f7c03f6affc2; runtime/build SHA256 fd0cb05bdc8b14824c6f8ca2bef5feef9f6c39f1bbb69b5f599498aee8919777; README/docs SHA256 adc351995a5ba3fbfe3c927963bbdb423e7366cbfa7fcc8c108cafeac3ae1fe5; all11-path SHA256 7ad64dd97eb0e90f9060fba1c2e0910513d651041ffba8a37ddf0bfa49aa2c70. Post-record-sync all11 hash: f4a8e4d7f5fe99c04cc37fe85bb93e60239f5632f1cee0793d6435498f50d548. Sorted UTF-8 difflib unified diff with three context lines; added physics file has empty base.

Source commit `028cfb2c72284b348a0c1282ba47bd01f69fe346` is published on origin/main; evaluation comment [#6585206519](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6585206519) posted (73 comments). Independent full suite250/255.521s; local full250/247.322s before a test-only literal update; focused authoring/build/module42/50.921s, six physics executable regressions6/13.093s, final literal case passes. Compileall/npm/QA/JSON/diff checks pass. VS Code0.1.4 unchanged. No runtime defect confirmed. Physics and networking are internal separate modules; packages and renderer/core separation remain incomplete.

## Latest 50-criterion scoring

79/100 — FAIL against98 after six-record sync (raw77; criteria8 and38 restored to2). Categories13/19/15/17/15.

Base f17498e709094573230c07c22de11278729e9858; source/test SHA256 fa614535072b589b80ce32146d44d91a046461c2fd7d26401f30f7c03f6affc2; runtime/build SHA256 fd0cb05bdc8b14824c6f8ca2bef5feef9f6c39f1bbb69b5f599498aee8919777; README/docs SHA256 adc351995a5ba3fbfe3c927963bbdb423e7366cbfa7fcc8c108cafeac3ae1fe5; all11 SHA256 7ad64dd97eb0e90f9060fba1c2e0910513d651041ffba8a37ddf0bfa49aa2c70. Post-record-sync all11 hash: f4a8e4d7f5fe99c04cc37fe85bb93e60239f5632f1cee0793d6435498f50d548. Sorted UTF-8 difflib unified diff with 3 context lines; added physics file base is empty.

The compiler selects separate networking and physics translation units only for reachable built-ins. This is internal modularity; package imports and renderer/core separation remain incomplete.

Independent full suite250/255.521s; local full250/247.322s before a test-only literal update. Focused authoring/build/module42/50.921s, six physics executable tests6/13.093s and final literal case passed. Compileall/npm/QA/JSON/diff checks passed. VS Code0.1.4 unchanged.

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|---:|---|
| 1 | requirements identified | 2 | current #23 and C-first reviewed |
| 2 | implicit requirements | 1 | portability/lifecycle incomplete |
| 3 | functionality | 1 | engine/Forge/OS incomplete |
| 4 | deliverables | 1 | broad deliverables absent |
| 5 | essential features | 0 | many requested systems absent |
| 6 | constraints | 2 | ANVL-C-MSVC-EXE preserved |
| 7 | ambiguity | 2 | backend boundaries clear |
| 8 | documentation parity | 2 | network module selection matches docs |
| 9 | use cases | 1 | major use cases unsupported |
| 10 | intended purpose | 1 | prototype only |
| 11 | core functionality | 2 | MSVC UDP host executable passed |
| 12 | secondary functionality | 2 | network integration tests pass |
| 13 | primary workflows | 1 | Forge/package/UEFI/kernel absent |
| 14 | input validation | 2 | markers/build arguments validated |
| 15 | error handling | 2 | network setup/receive pass |
| 16 | edge coverage | 2 | duplicate/unknown/text false positives covered |
| 17 | invalid inputs | 2 | unknown marker errors explicit |
| 18 | repeat stability | 2 | full suite passes locally |
| 19 | critical defects | 2 | no new runtime defect |
| 20 | integration | 2 | compiler/runtime integrate |
| 21 | project structure | 2 | files organized |
| 22 | formatting | 1 | formatting debt remains |
| 23 | module responsibilities | 1 | most runtime/compiler phases coupled |
| 24 | naming | 2 | names descriptive |
| 25 | duplication | 1 | binding/reference duplication |
| 26 | dependencies | 2 | Windows/MSVC deps tested |
| 27 | extensibility | 1 | registry internal; packages absent |
| 28 | unfinished scope | 1 | engine/target breadth incomplete |
| 29 | configuration | 2 | build config clear |
| 30 | conventions | 2 | C/Win32 fits |
| 31 | automated tests | 2 | 247 local and 15 independent focused tests |
| 32 | core tests | 2 | changed paths covered |
| 33 | failure tests | 2 | invalid/non-network/UDP covered |
| 34 | edge tests | 2 | duplicate/text false positives covered |
| 35 | integration tests | 1 | #63 remains open |
| 36 | test commands | 2 | QA/npm/compile/JSON/diff checks pass |
| 37 | builds | 2 | MSVC UDP executable passes |
| 38 | results recorded | 2 | criterion38 restored by record sync |
| 39 | regressions | 2 | local and focused regressions pass |
| 40 | full goal | 0 | full acceptance incomplete |
| 41 | installation | 2 | instructions match |
| 42 | reproducibility | 1 | platform/package setup incomplete |
| 43 | usage | 2 | C-first/reuse documented |
| 44 | design documentation | 2 | boundaries documented |
| 45 | troubleshooting | 2 | troubleshooting exists |
| 46 | editor workflow | 1 | editor/project workflows incomplete |
| 47 | editor integration | 1 | installed0.1.4 preserved; new visible verification absent |
| 48 | organization | 2 | files organized |
| 49 | limitations | 2 | limitations disclosed |
| 50 | practical scope | 0 | full goal remains unverified |
| | **Requirement fulfillment** | **13/20** | |
| | **Functionality and reliability** | **19/20** | |
| | **Code quality and architecture** | **15/20** | |
| | **Testing and verification** | **17/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **79/100** | FAIL against98 |

### Deduction details and follow-up

Networking is separately compiled only when reachable. User-facing package resolution, other runtime module boundaries, broad engine/language, DXR/Embree, Forge, UEFI/OS, cross-platform, editor and measured performance requirements remain incomplete. Full inventory: GitHub issue #23.

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


## Historical review identity — project memory-budget candidate (superseded)

Base `87e23d6943028222619f9febe0ed970e8d1a7ed7`; source/test SHA256 `57b0392fa1a325a23fda8d1aa202e7299b141e92d390b1cc518cc0b0ad22db5c`; implementation SHA256 `24ad1dc17364afc5c94eb80ae8dcd8fbfafa8113f5a579c3a7c39683cd6954ac`; all16 changed paths at review SHA256 `caa73ca775bfd3ecca4aa1ef57e5c522cf39ae6d89b37d7333249ceedc514615`. Full suite passed233 tests independently in253.611s and locally in269.749s. Categories13/19/15/17/15; score79/100 after record sync. `[memory]` limits apply to C/native builds and nested includes; native allocation diagnostics report the declaring module path and line. #90 was fixed, independently verified, and closed after publication; issues #87–#89 are also closed. #123 remains partial because runtime subsystems and packages are not selectively linked. The full goal remains incomplete.

Latest evaluation comment: https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6583162339

Historical record-only recheck for the project-memory-budget candidate: PASS at that time. Its 233-test evidence, 69-comment issue count, and #90 state do not describe the current candidate.

Historical publication record for the superseded project-memory-budget candidate: commit `b4e8a20ee511388123f4982001ac997c6c720e4f`; issue #90 closed; issue #23 evaluation comment #6583162339. This does not describe the current networking-module candidate.
