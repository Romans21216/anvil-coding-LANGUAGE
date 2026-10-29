# Anvil QA report

**Review date:** 2026-10-29
**Latest independent evaluation:** **71/100 - FAIL** on exact `957ee124402e0ba773971aaee24c48c8b277929a`.
**Current passing threshold:** 98/100. Historical scores do not establish current full-goal completion.
**Evaluator:** separate `project_full_review` agent, full 50-criterion review.

The full native engine, selectable DXR/Embree, rich systems-language types, Forge formats, assembly/UEFI/OS targets and measured optimization remain incomplete. The complete inventory remains exclusively in issue #23/comments.

## Independent verification for this snapshot

- `python -m unittest discover -s tests -q`: **192 passed**, 323.089 seconds, original session without restart.
- Extension0.1.12 grammar/VSIX CRC and source parity, compileall, QA arithmetic, strict UTF-8 JSON and diff checks passed. Installed0.1.4 preserved; newer visible editor tokens remain unverified.
- 192 tests independently passed in323.089s without restart; npm0.1.12/VSIX CRC and source parity, compileall, QA arithmetic, strict UTF-8 JSON and diff checks passed.
- Alias/state/helper isolation, recursion, dependency closure, initialization once, project roots and graph budgets pass provided tests. Extra BMP Cyrillic/Japanese diagnostics pass both backends; supplementary filename succeeds natively but MSVC fails C3850 on JSON surrogate escapes (#81).
- Extra private-helper probe executes73 on both backends; private-array mutation executes42 natively, bypassing exports through generated names (#82). Both findings are filed with Codex Bugs and detailed acceptance criteria. Evaluator re-read #23 body/51comments after suite and #80 separately; installed0.1.4 and #63 gap preserved.
- Test interactions remain window-local; untouched OS coordinate dispatch gap #63 remains disclosed. No fresh CUA/editor verification or installation.

## Latest 50-criterion scoring — `957ee12`

| # | Criterion | Score | Evidence, deduction, and status |
|---:|---|:---:|---|
| 1 | Explicit requirements identified | 2 | Full #23 scope, approved selective syntax and separate #80 optimization request identified. |
| 2 | Implicit requirements addressed | 1 | Complete resource, portability and runtime workflows missing; implement remaining systems (#6/#11/#23, open). |
| 3 | Functionality matches intended goal | 1 | Native2D improves; complete engine/Forge/OS functionality absent (#5-11/#23, open). |
| 4 | Required deliverables present | 1 | Compiler/runtime subset, examples, extension and tests exist; full native engine/systems deliverables absent (#11/#23, open). |
| 5 | No essential feature missing | 0 | Native3D/assets/audio/physics/networking, actual DXR/Embree, rich types and Forge/OS targets missing (#5-11/#23, open). |
| 6 | Stated constraints respected | 1 | Native emits direct machine code without C/Rust; broader engine/default still uses C/MSVC. Complete migration (#11, open). |
| 7 | Ambiguity resolved logically | 2 | Canonical modules, file-local aliases/exports, initializer ordering and whole-file coexistence explicitly defined. |
| 8 | Behavior matches documentation | 1 | Private helper/state and supplementary-Unicode path guarantees fail in #81/#82. Correct C literals and source-reference validation; open. |
| 9 | Important use cases supported | 1 | Native2D shapes/text/alpha/projects work; major engine and Forge/OS workflows absent (#5-11/#23, open). |
| 10 | Usable for intended purpose | 1 | Useful prototype; deliver complete engine/systems acceptance applications (#11/#15/#23, open). |
| 11 | Core functionality works | 1 | Implemented numeric/native2D subset passes; complete native engine core partial (#11, open). |
| 12 | Secondary functionality works | 1 | BMP Unicode diagnostics improve, but supplementary source paths break C compilation. Fix shared C UTF-8 literals; #81 open. |
| 13 | Primary workflows functional | 1 | Source/project builds work; Forge/package/assembly/UEFI/kernel workflows absent (#11/#23, open). |
| 14 | Inputs validated | 1 | Source can reference generated private function/array identities. Validate every source reference before binding; #82 open. |
| 15 | Errors handled gracefully | 2 | Allocation/null-bits/budget/active-flush failures exit2; best-effort teardown disclosed. |
| 16 | Edge cases covered | 2 | Alias conflicts, nested/recursive imports, expanded limits, initialization and existing runtime boundaries exercised. |
| 17 | Invalid inputs controlled | 2 | Invalid source/domain/configuration and new injected resource failures remain controlled. |
| 18 | Stable across repeated operations | 2 | Canonical module state/initializer reuse and previous window/resource/input/array regressions pass. |
| 19 | No known critical defects | 2 | No corruption, ABI regression, stale pixel pointer or lifetime defect reproduced. |
| 20 | Components integrate | 1 | Scoped binding allows private-reference bypass; C/native supplementary-path parity incomplete. Correct #81/#82; open. |
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
| 31 | Automated tests provided | 2 | 192 tests and extension0.1.12 grammar/package validation independently pass. |
| 32 | Core tests covered | 1 | Provided suite misses private-reference forms and supplementary C literal paths. Add #81/#82 regressions; open. |
| 33 | Failure scenarios tested | 2 | Missing exports/qualifiers, arity, cycles, boundaries and runtime errors explicitly exercised. |
| 34 | Edge cases explicitly tested | 2 | Same-basename aliases, private helpers/state, recursion, initialization once, quoted syntax and limits tested. |
| 35 | Integration behavior tested | 1 | GDI/CPU integration passes; untouched OS mouse-coordinate dispatch remains unverified (#63, open). |
| 36 | Documented test commands work | 2 | Documented unittest/npm/QA commands execute successfully. |
| 37 | Builds and compilation pass | 2 | 192 provided tests, actual native/C executables, compileall and package checks pass; supplementary path failure is deducted under12. |
| 38 | Results recorded accurately | 2 | Exact957ee12/71/192/323.089 evidence recorded; earlier independent/local evidence remains distinguished. |
| 39 | Regression checks performed | 2 | Original192-test suite completed on immutable source without restart, including previous rendering/input/resource regressions. |
| 40 | Verified against original goal | 0 | Complete engine/Forge/OS acceptance unavailable; implement and verify full scope (#5-11/#14-15/#23, open). |
| 41 | Installation instructions accurate | 2 | Python/native and MSVC routes match executable checks; extension installation documented. |
| 42 | Setup reproducible | 1 | Prototype subset reproducible; full engine/Forge/OS setup absent (#11/#23, open). |
| 43 | Usage understandable | 2 | Selective/whole-file behavior, alias syntax, private state and examples are documented. |
| 44 | Design decisions documented | 2 | Canonical state, file-local exports, helper closure, graph/source budgets and compatibility are explained. |
| 45 | Troubleshooting available | 2 | Native/compiler/include guides provide domain limits and actionable diagnostics. |
| 46 | Opens in intended environment | 1 | CLI/runtime/static extension validate; full editor/project/runtime workflow incomplete (#11/#23, open). |
| 47 | Editor integration works | 1 | Extension0.1.12 grammar/VSIX pass; newer visible-editor behavior/advanced tooling unverified. Preserve installed0.1.4 (#24/#23). |
| 48 | Deliverables organized | 2 | Loader, syntax helpers, examples, tests, extension and documentation organized. |
| 49 | Limitations disclosed | 2 | Package/linking/runtime/optimization gaps disclosed; confirmed #81/#82 are open and tracked. |
| 50 | Practical for intended scope | 0 | Full intended engine/Forge/OS product incomplete; deliver remaining systems and acceptance projects (#5-11/#14-15/#23, open). |
| | **Requirement fulfillment** | **11/20** | |
| | **Functionality and reliability** | **15/20** | |
| | **Code quality and architecture** | **14/20** | |
| | **Testing and verification** | **16/20** | |
| | **Developer experience and delivery** | **15/20** | |
| | **Total** | **71/100** | Exact commit `957ee12`; FAIL against98. |

### Deduction details and follow-up

Full independent review of957ee12:71/100 FAIL against98, categories11/15/14/16/15;192 tests passed in323.089s. Selective imports implemented, but #81 supplementary-Unicode C literal encoding and #82 private function/array reference bypass remain open. Full engine/Forge/OS/targets/types/backends/benchmarks/tooling and #63 remain incomplete. Goal stays active.

Full scope deductions remain covered by #5–11/#14–15/#23/#24 and #63. Missing systems must be implemented and independently exercised; a green subset suite alone does not establish completion.

## Review history

| Exact snapshot | Score / threshold | Evidence and changes |
|---|---|---|
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

#81 remains OPEN: /utf-8 fixes BMP encoding, but supplementary paths emit invalid C surrogate universal escapes. #82 OPEN: source references to compiler-private function/array names bypass selective exports/state isolation. Both have detailed reproduction, impact and acceptance criteria under Codex Bugs. Prior #79 remains verified fixed; #63 and broad #5–11/#14–15/#24 remain open. Complete inventory only in [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23).
