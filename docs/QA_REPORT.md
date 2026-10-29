# Anvil QA report

**Review date:** 2026-10-29
**Latest independent evaluation:** **76/100 - FAIL** on exact `b76fc02a1f6ea9ab24f7af004e8a0981ba249252`.
**Current passing threshold:** 98/100. Historical scores do not establish current full-goal completion.
**Evaluator:** separate `project_full_review` agent, full 50-criterion review.

The full native engine, selectable DXR/Embree, rich systems-language types, Forge formats, assembly/UEFI/OS targets and measured optimization remain incomplete. The complete inventory remains exclusively in issue #23/comments.

## Independent verification for this snapshot

- `python -m unittest discover -s tests -q`: **194 passed**, 281.445 seconds, original session without restart.
- Extension0.1.12 grammar/VSIX CRC and source parity, compileall, QA arithmetic, strict UTF-8 JSON and diff checks passed. Installed0.1.4 preserved; newer visible editor tokens remain unverified.
- 194 tests independently passed in 281.445s without restart; npm0.1.12/VSIX CRC and source parity, compileall, QA arithmetic, strict UTF-8 JSON and diff checks passed.
- Former #81 supplementary Cyrillic/Japanese/emoji physical source path now compiles on both backends and reports exact raw UTF-8 path/physical line4 with exit2. Shared C byte literals cover all path/allocation/project-title metadata. Byte-exact controls/NUL/DEL/emoji/hex-digit-followers and supplementary-title compilation pass; no C ANSI-window Unicode display claim.
- Additional independent MSVC encoder harness reproduced1164 Unicode scalars as4105 exact UTF-8 bytes, including all ASCII controls/NUL/DEL/quotes/backslashes,1000 randomized scalars and digit-following escapes.
- Former #82 helper calls and private array reads/writes are rejected at original source lines before either backend. All source node identifiers are checked before generated binding, with quoted/comment text unchanged. Alias/private state/helper closure/recursion/init-once/project/limits and preceding runtime regressions pass.
- No new defect confirmed. Full50 review re-read #23 body/52comments after tests and #80 optimization requirements separately. Prior #79 stays verified fixed; installed0.1.4 preserved and untouched coordinate integration gap #63 remains.
- Test interactions remain window-local; untouched OS coordinate dispatch gap #63 remains disclosed. No fresh CUA/editor verification or installation.

## Latest 50-criterion scoring — `b76fc02`

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Full #23 scope, approved selective syntax and separate #80 optimization request identified. |
| 2 | Implicit requirements addressed | 1 | Complete resource, portability and runtime workflows missing; implement remaining systems (#6/#11/#23, open). |
| 3 | Functionality matches intended goal | 1 | Native2D improves; complete engine/Forge/OS functionality absent (#5-11/#23, open). |
| 4 | Required deliverables present | 1 | Compiler/runtime subset, examples, extension and tests exist; full native engine/systems deliverables absent (#11/#23, open). |
| 5 | No essential feature missing | 0 | Native3D/assets/audio/physics/networking, actual DXR/Embree, rich types and Forge/OS targets missing (#5-11/#23, open). |
| 6 | Stated constraints respected | 1 | Native emits direct machine code without C/Rust; broader engine/default still uses C/MSVC. Complete migration (#11, open). |
| 7 | Ambiguity resolved logically | 2 | Canonical modules, file-local aliases/exports, initializer ordering and whole-file coexistence explicitly defined. |
| 8 | Behavior matches documentation | 2 | Selective imports/privacy, Unicode metadata, initialization and existing runtime behavior match independently exercised contracts; #81/#82 verified fixed. |
| 9 | Important use cases supported | 1 | Native2D shapes/text/alpha/projects work; major engine and Forge/OS workflows absent (#5-11/#23, open). |
| 10 | Usable for intended purpose | 1 | Useful prototype; deliver complete engine/systems acceptance applications (#11/#15/#23, open). |
| 11 | Core functionality works | 1 | Implemented numeric/native2D subset passes; complete native engine core partial (#11, open). |
| 12 | Secondary functionality works | 2 | Supplementary UTF-8 path diagnostics now pass both native and C; prior rendering/procedural/array/resource regressions pass. |
| 13 | Primary workflows functional | 1 | Source/project builds work; Forge/package/assembly/UEFI/kernel workflows absent (#11/#23, open). |
| 14 | Inputs validated | 2 | All unbound source references reject compiler-private identities; file/root/arity/budget/domain/configuration inputs exercised. #82 fixed. |
| 15 | Errors handled gracefully | 2 | Allocation/null-bits/budget/active-flush failures exit2; best-effort teardown disclosed. |
| 16 | Edge cases covered | 2 | Alias conflicts, nested/recursive imports, expanded limits, initialization and existing runtime boundaries exercised. |
| 17 | Invalid inputs controlled | 2 | Invalid source/domain/configuration and new injected resource failures remain controlled. |
| 18 | Stable across repeated operations | 2 | Canonical module state/initializer reuse and previous window/resource/input/array regressions pass. |
| 19 | No known critical defects | 2 | No corruption, ABI regression, stale pixel pointer or lifetime defect reproduced. |
| 20 | Components integrate | 2 | Scoped bindings integrate with both backends, private state/helpers, source diagnostics and native projects; #81/#82 verified fixed. |
| 21 | Logical project structure | 2 | ProgramLoader separates bounded graph resolution and scoped binding from syntax/backend emission. |
| 22 | Readable and consistently formatted | 1 | Extensive raw instruction/platform emission remains, including packed SSE2. Expand named helpers (#23, open). |
| 23 | Clear module responsibilities | 1 | Surface ownership improves separation; native expression parsing/validation/emission remain coupled. Add validated IR (#11/#23, open). |
| 24 | Consistent descriptive naming | 2 | Scope, canonical module, alias, dependency queue and bound-symbol names are descriptive. |
| 25 | Duplication minimized | 1 | Integer/scalar addressing now share encoding; expression parser/precedence duplication remains. Share validated lowering (#23, open). |
| 26 | Dependencies appropriate | 2 | Bounded local resolution needs no network/package dependency; native adds no C/Rust shim. |
| 27 | Supports future extensions | 1 | Private pixel surface strengthens the base; typed IR/target/linking/platform interfaces incomplete (#11/#23, open). |
| 28 | No unfinished placeholders | 1 | Surface/blending paths are real; required engine/target breadth remains unsupported (#5-11/#23, open). |
| 29 | Configuration understandable | 2 | Selectors, qualifiers, aliases, root boundaries, graph limits and initialization restrictions documented. |
| 30 | Conventions followed | 1 | Pixel/nonvolatile/stack/integer-addressing conventions verified; richer systems/foreign/object interfaces absent (#11/#23, open). |
| 31 | Automated tests provided | 2 | 194 tests and extension0.1.12 grammar/package validation independently pass. |
| 32 | Core tests covered | 2 | Implemented subset covered by actual native/C execution, supplementary path/byte-literal checks and private call/array access rejection. |
| 33 | Failure scenarios tested | 2 | Missing exports/qualifiers, arity, cycles, boundaries and runtime errors explicitly exercised. |
| 34 | Edge cases explicitly tested | 2 | Same-basename aliases, private helpers/state, recursion, initialization once, quoted syntax and limits tested. |
| 35 | Integration behavior tested | 1 | GDI/CPU integration passes; untouched OS mouse-coordinate dispatch remains unverified (#63, open). |
| 36 | Documented test commands work | 2 | Documented unittest/npm/QA commands execute successfully. |
| 37 | Builds and compilation pass | 2 | 194 tests, native/C executables, compileall and extension0.1.12 package checks pass. |
| 38 | Results recorded accurately | 2 | Exact b76fc02/76/194 evidence recorded; local checks, previous71 review and historical snapshots distinguished. |
| 39 | Regression checks performed | 2 | Original194-test suite completed on immutable source without restart, including previous rendering/input/resource regressions. |
| 40 | Verified against original goal | 0 | Complete engine/Forge/OS acceptance unavailable; implement and verify full scope (#5-11/#14-15/#23, open). |
| 41 | Installation instructions accurate | 2 | Python/native and MSVC routes match executable checks; extension installation documented. |
| 42 | Setup reproducible | 1 | Prototype subset reproducible; full engine/Forge/OS setup absent (#11/#23, open). |
| 43 | Usage understandable | 2 | Selective/whole-file behavior, alias syntax, private state and examples are documented. |
| 44 | Design decisions documented | 2 | Canonical state, file-local exports, helper closure, graph/source budgets and compatibility are explained. |
| 45 | Troubleshooting available | 2 | Native/compiler/include guides provide domain limits and actionable diagnostics. |
| 46 | Opens in intended environment | 1 | CLI/runtime/static extension validate; full editor/project/runtime workflow incomplete (#11/#23, open). |
| 47 | Editor integration works | 1 | Extension0.1.12 grammar/VSIX pass; newer visible-editor behavior/advanced tooling unverified. Preserve installed0.1.4 (#24/#23). |
| 48 | Deliverables organized | 2 | Loader, syntax helpers, examples, tests, extension and documentation organized. |
| 49 | Limitations disclosed | 2 | Remaining engine/package/linking/OS/optimization/tooling gaps disclosed; #81/#82 resolved with independent evidence. |
| 50 | Practical for intended scope | 0 | Full intended engine/Forge/OS product incomplete; deliver remaining systems and acceptance projects (#5-11/#14-15/#23, open). |
| | **Requirement fulfillment** | **12/20** | |
| | **Functionality and reliability** | **18/20** | |
| | **Code quality and architecture** | **14/20** | |
| | **Testing and verification** | **17/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **76/100** | Exact commit `b76fc02`; FAIL against98. |

### Deduction details and follow-up

Full independent review of b76fc02:76/100 FAIL against98, categories12/18/14/17/15;194 tests passed in 281.445s. Selective imports, qualified calls, private helpers/state and aliases verified; #81 supplementary C UTF-8 metadata and #82 private source-reference bypass independently fixed. Full native engine/Forge/OS/types/targets/actual ray backends/benchmarks/tooling and #63 remain incomplete. Goal stays active.

Full scope deductions remain covered by #5–11/#14–15/#23/#24 and #63. Missing systems must be implemented and independently exercised; a green subset suite alone does not establish completion.

## Review history

| Exact snapshot | Score / threshold | Evidence and changes |
|---|---|---|
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
