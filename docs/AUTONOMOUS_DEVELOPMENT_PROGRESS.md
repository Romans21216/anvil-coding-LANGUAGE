# Anvil autonomous development progress

This is a historical batch log. Each entry describes the state at that batch, including then-pending findings and then-latest reviews. For current capability and verification state, use [QA_REPORT.md](QA_REPORT.md), [capability matrix](COMPLETION_MATRIX.md) and [structured state](CODEX_AUTONOMOUS_STATE.json). GitHub issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23) remains the user-maintained master backlog and source of truth.

## Batch 1 — configurable Coulomb friction

- **Features:** Added `body_friction(handle, coefficient)` to the 2D circle/axis-aligned-box solver. Coefficients are finite values from 0 to 1; bodies default to 0.5; pair values combine by geometric mean; tangent impulses clamp against normal impulse.
- **Backlog:** #311 is partially implemented pending separate zero-friction and mixed-coefficient tests. #303 and #302 were already implemented and verified in prior reviewed commits.
- **Files:** runtime C/API header, compiler built-in tables, physics docs and wiki, friction example, VS Code grammar/docs/validation, native integration test, VSIX 0.1.7.
- **Tests:** `python -m unittest discover -s tests -q` — 53 passed; `npm test --prefix vscode-extension` — passed; `python -m py_compile compiler/anvil.py tests/test_compiler.py` — passed; MSVC release build of `examples/physics_friction.ANVL` — passed; `git diff --check` — passed. Interactive window not launched.
- **Independent review:** Commit `f7c91b01ec0b4f91e2cf26c0ea08e95a5669c860`, 87/100 — FAIL. Findings: completion/evaluation docs had stale friction and QA snapshot, extension 0.1.7 not visually verified, and separate zero/mixed coefficient tests recommended. See issues [#24](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/24), [#26](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/26), and [#27](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/27).
- **Documentation:** API and engine guides were updated in the implementation commit. QA/evaluation/completion docs are now synchronized in the follow-up working tree; issue #27 remains open pending independent verification.
- **Commit/push:** `f7c91b01ec0b4f91e2cf26c0ea08e95a5669c860`, pushed to `origin/main`.
- **GitHub issues:** #8 and #15 updated to the latest review; #24 tracks unverified extension visuals; #26 tracks missing friction edge-case tests; #27 tracks stale evaluation records from the reviewed commit. Issue #23 was checked after the critic and left unchanged.
- **Remaining blockers:** VS Code 0.1.7 visual verification is deferred by user preference (0.1.4 stays installed). Full game-engine goal remains incomplete.
- **Next batch:** Add deterministic regression tests for zero friction and different per-body coefficients, then rerun review and synchronize reports.

## Batch 2 — friction edge-case tests and tracking synchronization

- **Features:** Added native integration coverage for frictionless contacts and geometric-mean combination of different per-body coefficients. Updated QA/evaluation/completion docs to reflect the reviewed friction feature and its limits. Added a 450-item evidence inventory, cumulative progress log, and resumable state file from the unchanged master backlog.
- **Backlog:** Item #311 is COMPLETE after independent review of the friction implementation and edge cases. Items #302/#303 remain complete; no other backlog item was promoted without source/test review.
- **Files:** `tests/test_compiler.py`, `docs/QA_REPORT.md`, `docs/ANVIL_EVALUATION.txt`, `docs/COMPLETION_MATRIX.md`, `README.md`, `docs/IMPLEMENTATION_STATUS.json`, `docs/IMPLEMENTATION_STATUS.md`, `docs/AUTONOMOUS_DEVELOPMENT_PROGRESS.md`, and `docs/CODEX_AUTONOMOUS_STATE.json`.
- **Tests:** Targeted zero/mixed friction case passed. Full follow-up: 54 Python tests passed; VS Code extension validation passed; Python compilation passed; native MSVC friction sample build passed; `git diff --check` passed; status JSON parses and contains all 450 backlog entries.
- **Independent review:** Exact commit `83891c6fe801659e350defa2e080b30fb914963b` scored **90/100 — PASS** (16/20, 20/20, 17/20, 19/20, 18/20). Reviewer ran 54 tests, extension validation, py_compile, MSVC friction sample build, diff check, and confirmed 450 unique sequential status entries. The older 87 score remains historical for exact commit `f7c91b0`.
- **GitHub issues:** #26 (friction edge tests) and #27 (stale evaluation records) are resolved after independent verification. #8 and #15 reflect current implementation and the 90-point review. Issue #23 was checked after the critic and left unchanged.
- **Commit/push:** `e1e3768` (`test(physics): cover friction edge cases and sync tracking`) and `83891c6` (resumable state), pushed to `origin/main`.
- **Remaining blockers:** Visual verification of VSIX 0.1.7 remains deferred by user preference; 0.1.4 stays installed.
- **Next batch:** Investigate backlog item #48 (division-by-zero diagnostics), implement source-located behavior and tests, then run the critic and sync reports/issues.

## Batch 3 — source-located division-by-zero diagnostics

- **Features:** Compiler lowering for `/` now calls the runtime `anvil_divide` helper. A zero denominator, including negative zero, prints the source path and line and exits with code 2; normal floating-point division is preserved.
- **Backlog:** #48 is COMPLETE. The inventory records the source and native-test evidence, with runtime-only detection as a limitation.
- **Files:** `compiler/anvil.py`, `runtime/anvil_runtime.c`, `runtime/anvil_runtime.h`, compiler tests, language/compiler/wiki docs, and implementation status inventory.
- **Tests:** `python -m unittest tests.test_compiler -v` — 54 passed (including source-located zero division and regular division); `npm test` in `vscode-extension` — passed; `python -m compileall -q compiler tests` — passed; `git diff --check` — passed.
- **Review:** Exact commit `12b4e55b142d0fd48cccddfc6d6f67eefed16710` scored **90/100 — PASS** (16/20, 20/20, 17/20, 19/20, 18/20). The independent reviewer ran 56 tests, extension validation, Python compile, MSVC release build/run (`numeric_demo` output `17`), diff check, and confirmed all 450 sequential status entries. No defect was found in the division diagnostic. The evaluation documents now record this score.
- **Commit/push:** `12b4e55` (`feat(compiler): report division by zero locations`) pushed to `origin/main`.
- **GitHub issues:** After review, issue #23 was checked; it remains open and unchanged (updated `2026-10-27T19:17:01Z`). It was not modified. No Codex Bugs issue was needed because the critic found no new product bug.
- **Remaining limitations:** This is a runtime check; it does not statically prove a denominator is zero. DXR and Embree remain unavailable, and this work does not change renderer behavior.
- **Next batch:** Continue by selecting the next small, verified item from issue #23; preserve the user's 0.1.4 VS Code installation preference.

## Batch 4 — short-circuit logical evaluation

- **Features:** Audited backlog item #46. `and` and `or` already lower to C `&&` and `||`, which short-circuit. Added a native regression test proving skipped side-effecting calls are not run and required right-side calls do run; clarified this behavior in the language guide and wiki.
- **Backlog:** #46 is COMPLETE after native behavior tests and independent verification.
- **Files:** `tests/test_compiler.py`, `docs/LANGUAGE.md`, `docs/Wiki/Language-Reference.md`, implementation-status inventory, progress log, and resumable state.
- **Tests:** Targeted MSVC compile/run regression passed (1 test); `python -m unittest discover -s tests -q` — 57 passed; `npm test --prefix vscode-extension` — passed; `python -m compileall -q compiler tests` — passed; `git diff --check` — passed.
- **Review:** Exact implementation commit `83cf626b0a5ab370d5a6da476ea47bbc2a9f728a` passed short-circuit behavior review; it scored 89/100 - FAIL due the stale QA test count (issue #28, now closed after re-review). The documentation follow-up `71b818b20c3ae012ba33cec846f8a208220b7991` also scored 89/100 - FAIL (16/20, 20/20, 17/20, 18/20, 18/20): the critic found `ANVIL_EVALUATION.txt` still described item #46 as pending review. This second finding is tracked in issue #29. Both reviews ran 57 tests, extension validation, Python compilation, native MSVC sample build/run, and diff check; reviewers confirmed the full list resides only in issue #23 and its comment. No code defect was found. The latest docs-only review of `2a745bb9b455baffe9248f24d39970ea31146b23` scored 90/100 and confirmed both documentation findings are fixed (issues #28 and #29 closed); it passed under the previous 90-point bar.
- **Commit/push:** `83cf626` (`test(language): verify short-circuit evaluation`) pushed to `origin/main`.
- **GitHub issues:** The full 450-item list was copied verbatim from issue #23 into issue comment [#issuecomment-6451810775](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23#issuecomment-6451810775). The repository no longer mirrors that full list; it keeps only audited work/status evidence. The stale QA count was filed as issue [#28](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/28) with the `Codex Bugs` label. Issue #23 remains the only home for the complete item list.
- **Limitations:** Current short-circuit behavior is provided by the C backend; this adds coverage but does not introduce a backend-independent intermediate representation.
- **Next batch:** Continue implementing high-value engine capabilities from issue #23 to address the current evaluator deductions and reach the new 98/100 passing threshold.

## Evaluation threshold update — 2026-10-27

- The user raised the required passing score to **98/100** after review of `2a745bb`.
- That review's 90/100 was marked PASS under the then-current 90-point threshold, but it is below the new bar. Historical scores and their original pass/fail labels remain unchanged.
- Future critic results must be compared with 98/100. Continue engineering against verified evaluator deductions and issue #23's source list.

## Batch 5 — explicit numeric overflow behavior (implementation complete; evaluation follow-up in progress)

- **Features:** Backlog item #47 now rejects numeric expressions that produce NaN or infinity. `anvil_check_number` reports the `.ANVL` source path and line and exits with code 2; arithmetic intermediates are checked before comparisons. Division by zero retains its distinct diagnostic.
- **Backlog:** #47 is COMPLETE after independent behavior review; the overall project still fails the new 98/100 QA threshold.
- **Files:** `compiler/anvil.py`, runtime C API/implementation, compiler tests, language/compiler/wiki docs, and the compact audited status ledger.
- **Tests:** Native regression coverage passes for direct multiplication overflow, overflow inside a comparison, invalid `sqrt(-1)`, local add/sub accumulation, `for` step overflow, a UDP NaN datagram, finite UDP value, and no-socket receive. `python -m unittest discover -s tests -q` — 61 passed; `npm test --prefix vscode-extension` — passed; `python -m compileall -q compiler tests` — passed; JSON validation and `git diff --check` — passed.
- **Review:** Candidate `8ae53c4daaed0d2160262aa24a2a0d5178235a96` scored **85/100 — FAIL**. Reviews of `bcbf221` and `c5d7d40` each scored **89/100 — FAIL** and identified status contradictions, both now corrected. Latest review of exact commit `15439b54cd6e2b7a8165866d6054141f466f1b3e` scored **90/100 — FAIL** against 98; it confirmed the workflow records are consistent and found no current defect. Issues [#30](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/30) and [#31](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/31) are closed.
- **Commit/push:** Numeric behavior fix is in `6c52b959dc3d5d13d174e37e57006f63d4cda951`; progress/state QA follow-up `15439b5` is pushed and independently verified. The overall score remains below 98/100.
- **Limitations:** Anvil currently uses doubles; this detects non-finite outcomes but does not detect all finite precision loss or introduce integer overflow semantics.
- **Next batch:** Continue directly from issue #23 item #49 (language feature versioning), then rerun the evaluation against 98/100.

## Batch 6 — language feature versioning (implementation, superseded by review follow-up)

- **Features:** Backlog item #49 adds an optional leading `language version 1` declaration. Existing unversioned files keep version 1 behavior. Malformed, repeated, late, and unsupported declarations report the source path and line.
- **Backlog:** #49 is COMPLETE after independent review of `ed08f43`; only language version 1 is implemented.
- **Files:** `compiler/anvil.py`, compiler regression tests, language/compiler/wiki docs, and the compact implementation ledger.
- **Tests:** `python -m unittest discover -s tests -q` — 64 passed; `npm test --prefix vscode-extension` — passed; `python -m compileall -q compiler tests` — passed; JSON summary totals 450 items with 15 audited entries; `git diff --check` — passed.
- **Review:** Exact commit `ed08f43ca0d9beb5440f18fade48faf556694b1f` scored 89/100 below the 98-point bar and independently verified item #49. Issues #32 and #33 were fixed and closed; QA count issue #34 is being corrected in Batch 8.
- **Commit/push:** Item #49 implementation is pushed in `d5191d4ba2c7744b1b6207086abf0d8e05320afc`; its full validation passed. The state-record correction is in pushed commit `2dd1d8ee4d9a2d30669ba5198a9de153bc9b01a2`. Review of that exact snapshot scored 85/100 and found an oversized-version diagnostic failure and this stale sentence, now tracked in issues [#32](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/32) and [#33](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/33).
- **Next batch:** Correct test-count evidence in QA_REPORT.md and obtain a fresh review.

## Batch 7 — version diagnostics and QA-state corrections (complete)

- **Findings:** Independent review of `2dd1d8ee4d9a2d30669ba5198a9de153bc9b01a2` scored **85/100 — FAIL** and reported two issues, both labeled `Codex Bugs`: [#32](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/32) (5,000-digit version declarations raised uncaught `ValueError`) and [#33](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/33) (stale “being committed” progress wording).
- **Fixes:** Version parsing now compares decimal text without unbounded integer conversion; long unsupported versions receive a bounded source-located diagnostic. Added a 5,000-digit regression test. Corrected the progress sentence to distinguish pushed commit state from pending review.
- **Tests:** `python -m unittest discover -s tests -q` — 64 passed; `npm test --prefix vscode-extension` — passed; `python -m compileall -q compiler tests` — passed; both status JSON files parse and the backlog summary totals 450; `git diff --check` — passed.
- **Commit/push:** Fixes and QA synchronization were committed and pushed in `f7372a6805d3324f91eb362d9f3e64f501c4090b`.
- **Review:** Exact commit `ed08f43ca0d9beb5440f18fade48faf556694b1f` scored **89/100 — FAIL** against 98. The critic reran 64 tests, verified the oversized-version diagnostic, confirmed the progress wording fix, and closed issues #32 and #33. It also found a mismatch between historical test counts in QA rubric rows 31 and 39; tracked in [#34](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/34).
- **Next batch:** Sync QA counts for issue #34, obtain fresh review, then continue issue #23 item #50.

## Batch 8 — synchronize QA review counts (complete)

- **Finding:** Review `ed08f43` identified stale test totals in QA rows 31/39; review `c648ccb` confirmed those were fixed and found rubric arithmetic and Markdown/JSON status drift. Issues #34–#36 record those findings; all three are now closed after review `727d349`.
- **Fix:** Rows 31/39 distinguish 63 tests on `2dd1d8e` and 64 on `ed08f43`; criteria 8, 14, 15, and 17 are scored 2 to align verified behavior and sum to 89; the Markdown ledger now matches JSON (12 complete, 0 in progress; review `ed08f43`, score 89).
- **Tracking:** Issues #35 and #36 are labeled `Codex Bugs`; both are fixed and closed after independent confirmation.
- **Review:** Exact documentation commit `702d8792d4270a75c0db67b2300fc03da3409240` scored 89/100. The critic verified rubric arithmetic, Markdown/JSON status counts, JSON validity, and the 450-item backlog invariant; no new defect was found. The overall score is below the user's 98/100 threshold.
- **Next batch:** Continue from issue #23 item #50 (formal language specification); address the remaining engine breadth, compiler architecture, and editor-verification deductions.

## Batch 9 — formal language specification (in progress)

- **Backlog:** Issue #23 item #50 is being implemented as a normative specification of the language currently accepted by the compiler. The full backlog remains only in issue #23.
- **Deliverable:** `docs/LANGUAGE_SPEC.md` documents UTF-8 line syntax, language versioning, declarations, scope, arrays, control flow, expression precedence/evaluation, built-ins, rendering statements, runtime limits/errors, compilation, and a complete example. README, guide, and wiki now link to it.
- **Scope:** The document states current Windows/MSVC and CPU renderer/BVH limitations; it does not present roadmap capabilities as implemented.
- **Review:** The compiler accepted the documented conformance example and emitted C. Independent conformance check against `compiler/anvil.py` and `runtime/anvil_runtime.c` is pending. Do not mark #50 complete or change the latest QA score until reviewed.
- **QA:** Latest critic at this point was 89/100 — FAIL against 98. The new document had not yet received a fresh critic review.
- **Next:** Validate and correct the specification, obtain an independent review of the exact candidate commit, then update the evaluation and ledger with that result.

### Independent review follow-up — commit `3cd390c`

- **Score:** 84/100 — FAIL against the required 98/100. Category scores: requirements 15/20, functionality/reliability 16/20, architecture 17/20, testing 19/20, developer experience/delivery 17/20.
- **Checks:** Critic reran 64 Python tests, VS Code extension validation, Python compilation, status JSON/Markdown counts, and an MSVC release build/run of the conformance sample (output `6`). It verified issue #23's 450 sequential backlog entries.
- **Findings:** Unicode decimal digits reach invalid generated C; display text grammar omits required coordinates; display suffix ordering conflicts with implementation; camera grammar promises unsupported expressions; the accepted `null` cleanup statement is omitted; trailing whitespace makes the commit diff check fail. Tracked precisely in `Codex Bugs` issues #37–#42.
- **Evaluation:** Updated `QA_REPORT.md`, `ANVIL_EVALUATION.txt`, both state ledgers, and this progress log immediately after the critic run. The score remains below 98. Fix all six findings and rerun the critic.

### Finding corrections — candidate `b8213aa` for fresh review

- **#37:** Numeric/version/array/port/display-integer token patterns now use ASCII `[0-9]`. Added a regression proving Arabic-Indic `١` returns a line diagnostic and emits no C. Also bounded huge array-size text before integer conversion and added a 5,000-digit array-size regression.
- **#38–#41:** Updated the normative EBNF and semantic rules for mandatory text location, legacy display integer placement, whitespace-free camera coordinates, and accepted no-op `set var(name) = null`. Also included the text-number compatibility form.
- **#42:** Removed the spec's trailing spaces; `git diff --check` now passes.
- **Validation:** 66 Python tests pass; `npm test --prefix vscode-extension` and `python -m compileall -q compiler tests` pass. MSVC release builds pass for `examples/numeric_demo.ANVL` (run output `17`) and `examples/first_world.ANVL`. Manual negatives confirm unpositioned text and spaced camera expressions are rejected with source diagnostics; `git diff --check` passes.
- **Review state:** Findings #37–#42 remain open until an independent critic reviews the exact fix commit. Latest critic is still 84/100; do not record a higher score until a new review runs.

### Independent review follow-up — commit `0abba63`

- **Score:** 88/100 — FAIL against the required 98/100. Category scores: requirements 15/20, functionality/reliability 20/20, architecture 17/20, testing 19/20, delivery 17/20.
- **Checks:** Critic confirmed 66 tests, extension validation, Python compilation, MSVC numeric/conformance builds (outputs `17` and `6`), starter-world release build, clean diff, matching status records, and 450 unique issue #23 entries.
- **Resolved:** Critic confirmed fixes #37–#42; added resolution comments and closed all six issues.
- **New finding:** Duplicate `-l(x,y)` modifiers are permitted by `display_tail` in the spec but rejected by `emit_display`. Tracked in [issue #43](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/43), labeled `Codex Bugs`.
- **Evaluation:** Updated QA report, full text evaluation, JSON/Markdown status ledgers, and this log immediately after the critic. Latest score remains below 98; fix #43 and re-review.

### Issue #43 correction candidate

- **Change:** The normative spec now states that a display command may contain at most one `-l(x,y)` and one `-rotate(x,y,z)`. Repeated RGB modifiers are documented as accepted with the first color taking effect, matching the current parser.
- **Regression:** Added a compiler test asserting a repeated text-location modifier fails with a source-line diagnostic before C generation.
- **Validation:** `python -m unittest discover -s tests -q` — 67 passed; extension validation, Python compileall, and `git diff --check` pass.
- **Review state:** Issue #43 remains open. Latest official score is still 88/100 until a new critic reviews the exact correction commit.


### Critic follow-up — exact commit `65c15bf`

- **Threshold:** The user's current pass requirement is **98/100**. The review score of **89/100 is FAIL**.
- **Verification:** The independent critic ran 67 Python tests, VS Code extension validation, Python compilation, and `git diff --check`; all passed. It confirmed the issue #43 language-spec correction.
- **Completion:** Item #50 is marked COMPLETE after the critic verified the specification matches the current compiler. Issues #37–#43 are resolved.
- **Finding:** QA rubric arithmetic was stale: the previous narrative reported 88 while displayed rows summed to 84. Tracked in [issue #44](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/44), labeled `Codex Bugs`.
- **Evaluation sync:** Updated this progress log, QA report, full evaluation, Markdown/JSON implementation ledgers, and autonomous state to exact reviewed commit `65c15bf002c1bad268aec2bd68e7b184fd110c33`. Latest category totals: 16/20, 20/20, 17/20, 18/20, 18/20 (89/100). This synchronization commit needs a fresh critic review; 98 remains unmet.


### QA follow-up critic — exact commit `ff8428d`

- **Score:** 89/100 — FAIL against the user's 98/100 requirement. Categories: 16/20, 20/20, 17/20, 18/20, 18/20.
- **Confirmed:** All 50 criterion rows total 89; the category subtotals match; the implementation inventory totals 450 (13 complete, 3 partial, 434 needing verification, 0 in progress).
- **Findings:** QA_REPORT.md still labeled the current candidate as 64 tests instead of 67, described closed issue #43 as open, and had no committed arithmetic validator. Criterion 38 remained 1/2. Issue [#44](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/44) remains open and labeled `Codex Bugs`.
- **Follow-up prepared:** Corrected the stale lines and added `scripts/validate_qa_report.py`, documented in README. The script checks all 50 criteria, five category subtotals, and total against the current evaluation score. Its first run exposed a parser-pattern issue; that was corrected, and it now reports 50 criteria = 89/100 with matching category subtotals. A fresh critic review is pending.


### QA arithmetic validator critic — exact commit `0c75929`

- **Score:** 89/100 — FAIL against 98. Categories: 16/20, 20/20, 17/20, 18/20, 18/20. Criterion 38 remains 1/2.
- **Confirmed:** The 50 criterion rows and categories sum to 89; status ledgers agree at 450 items; the validator accepts the current rubric and rejects a malformed subtotal.
- **Finding:** `scripts/validate_qa_report.py` uses a score pattern that excludes valid `0` scores. The critic proved a valid rubric with a zero-scored criterion and matching 98 total is rejected. Tracked in open [issue #44](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/44), labeled `Codex Bugs`.
- **Evaluation:** Updated the QA report, full evaluation, implementation ledgers, autonomous state, and this log immediately after the review. Fix the parser and add a zero-score regression before asking for another review.


### Issue #44 zero-score correction candidate

- **Fix:** The QA validator now accepts criterion scores from 0 through 2 and provides `--report` for testing alternate report fixtures.
- **Regression:** Added `tests/test_qa_report.py` cases for a consistent rubric containing a 0-point criterion (total 87) and rejection of a mismatched category subtotal.
- **Validation:** Targeted QA tests pass (2); full Python suite passes (69); QA validator, Python compilation, extension validation, and `git diff --check` pass.
- **Review state:** This was the candidate before the `7c1385c` review. The critic confirmed the zero-score fix and regression; issue #44 is resolved and closed.


### QA arithmetic validator review — exact commit `7c1385c`

- **Fresh score:** 90/100 — FAIL against 98. Categories: 16/20, 20/20, 17/20, 19/20, 18/20. Criterion 38 rises to 2/2; the prior QA record score remains 89 for its exact snapshot.
- **Verification:** 69 Python tests, npm extension validation, Python compileall, QA arithmetic validator, valid-zero and malformed-subtotal fixtures, and `git diff --check HEAD^ HEAD` all pass. JSON/Markdown counts agree at 450.
- **Resolution:** The critic confirmed the validator and zero-score regression. Issue [#44](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/44) is closed.
- **Evaluation:** Updated all current evaluation and status records immediately after the critic. The 98-point pass requirement remains unmet.


## Batch 10 — compiler phase separation candidate

- **Scope:** Issue #12 and backlog items #101–#104. The 1,018-line compiler entry module was decomposed into common model/configuration, lexer helpers, syntax parser, semantic validator, expression parser/lowering, C backend, build driver, and CLI orchestrator. `compiler/anvil.py` remains a compatibility facade and CLI.
- **Behavior preservation:** Generated C for `numeric_demo`, `functions`, `arrays`, `loops`, `local_arrays`, `first_world`, `ray_backends`, `network_counter`, and `network_client` is byte-identical to the pre-refactor compiler at `854d36c`.
- **Phase tests:** Added tests for parse→semantic→codegen, semantic rejection of an unresolved variable before generation, and compatibility-facade exports.
- **Validation:** Full Python suite: 72 passed; extension validation passed; compileall, Black check, QA arithmetic validation, and diff check passed.
- **Review state:** Items #101–#104 are marked IN PROGRESS pending independent review of the exact committed candidate. The last scored review remains 90/100 — FAIL against 98; no score change is claimed before review.


## Batch 10 review — compiler phases independently verified

- **Exact review commit:** `96b71fedca97facaff60f2c3b8362f16c64b8b9d`.
- **Fresh score:** **91/100 — FAIL** against the user's 98/100 passing threshold. Categories: requirements 16/20, functionality/reliability 20/20, architecture 18/20, testing 19/20, delivery 18/20. Criterion 23 improved from 1 to 2 after the reviewer confirmed separated compiler phases.
- **Independent verification:** 72 Python tests, extension validation, compileall, QA validator, and diff check passed. Both CLI help paths work; all 21 previously exposed facade definitions remain available; generated C is byte-identical for 12 examples versus baseline `854d36c`. JSON and Markdown status agree on 20 audited rows and a 450-item total.
- **Backlog status:** Items #101–#104 are COMPLETE. Counts are 17 complete, 3 partial, 0 in progress, and 430 needing verification.
- **Remaining issues:** Issue #12 remains open because long lines remain and Black was unavailable to the reviewer. Other deductions are incomplete engine breadth, Windows/MSVC and C-only limits, and unverified newer VS Code highlighting; the latter follows the user's choice to keep 0.1.4 installed. No new functional bug was reproduced.
- **Evaluation sync:** QA report, plain-text evaluation, status ledgers, and autonomous state were updated immediately after this critic run.


### Batch 10 formatting follow-up candidate

- **Candidate:** `3f77eee7bf23d70ae97e7f1968851882dd0d923e` wraps source lines in the five compiler modules cited by review `96b71fe`; generated C strings are split only as adjacent literals, preserving emitted bytes.
- **Local verification:** 72 tests passed; Black 26.10.1 default 88-column check passed; no lines exceed 88 columns in the five cited modules; compileall, QA arithmetic, and diff check passed; 12 examples produce byte-identical generated C versus `854d36c`.
- **Review:** Independently evaluated as exact commit `5072597`; fresh score 92/100, FAIL against 98.


### Formatting review — exact commit `5072597`

- **Fresh score:** **92/100 — FAIL** against the 98/100 threshold. Categories: requirements 16/20, functionality 20/20, architecture 19/20, testing 19/20, delivery 18/20. Criterion 22 improved to 2/2; criterion 23 remains 2/2.
- **Independent checks:** 72 Python tests, extension validation, compileall, QA arithmetic, diff check, both CLI help forms, all 21 legacy facade exports, and 12/12 generated-C parity comparisons passed. Black 26.10.1 default-style check passed and the cited modules are all at most 88 columns.
- **Inventory:** 20 audited rows; 430 needing verification, 3 partial, 17 complete, 0 in progress (450 total).
- **Resolution:** Issue #12 acceptance is met; compiler modules, formatting, phase tests, docs, and compatibility have independent evidence. Issue #12 is closed. The critic also found `current_active_item: 22` ambiguous beside completed backlog item 104 and zero in-progress backlog rows. This was filed as [issue #45](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/45), labeled `Codex Bugs`; the sync clears the active backlog item and records rubric criterion 22 in `last_reviewed_rubric_criterion`. Issue #45 is resolved and closed.
- **Remaining score deductions:** engine scope, Windows/MSVC and C-only limits, and unverified new-token highlighting because extension 0.1.4 remains installed per user preference.


## Batch 11 — resizable game window (canonical item #172; candidate `2962455`)

- **Scope:** Canonical item #172 in issue #23 comment 6451810775 is “Add dynamic window resizing.” The native window is already resizable, but the old paint path always drew the 960×600 frame from the top-left, leaving clipping or unused space. The runtime now computes a centered 16:10 viewport, fills letterbox bars, and scales presentation without changing the internal resolution.
- **Regression coverage:** A native C harness checks the original 960×600 size, a wide 1200×600 client (120-pixel side bars), a tall 600×800 client (212-pixel top bar), a 1280×720 client, and invalid dimensions. All 73 Python tests pass; the runtime test module passes all 3 tests.
- **Documentation:** Engine and completion-matrix docs state the distinction between resizable presentation and fixed internal framebuffer.
- **Status:** Canonical item #172 is IN PROGRESS pending independent review; all 73 tests pass locally. Item #144 is compiler version reporting and remains unverified. Latest independent score is 91/100 on `bc4db99`, below the 98-point threshold.


### Review finding — canonical backlog mapping correction

- **Exact reviewed commit:** `bc4db99368b3af2953e49adc4e4cbd8f5706bb4e`. **Score:** 91/100 — FAIL against 98. Categories: requirements 16/20, functionality 20/20, architecture 19/20, testing 18/20, delivery 18/20.
- The latest full-list comment on issue #23 (`6451810775`) defines #144 as compiler version reporting and #172 as dynamic window resizing. The candidate had incorrectly recorded the feature as #144. This reduced criterion 38 from 2 to 1; issue #46 (`Codex Bugs`) records the finding.
- The runtime viewport implementation passed the 73-test suite and 3 native runtime tests. Review inspected geometry and paint handling but did not visually launch a resized window. No code defect was reproduced.
- The status and QA records are being corrected to canonical #172; fresh review is required before treating criterion 38 as restored.


### Fresh critic result — corrected resize tracking candidate `f12c0ac`

- **Exact reviewed commit:** `f12c0ac42f3d1f7b74fc78b9c37fa9ae4e8c1de`.
- **Score:** **92/100 — FAIL** against the current **98/100** passing requirement. Categories: requirements 16/20, functionality/reliability 20/20, architecture 19/20, testing/verification 19/20, delivery 18/20.
- **Change from the prior review:** Criterion 38 rises from 1/2 to 2/2 after the critic confirmed item #172 is dynamic window resizing and #144 remains unverified compiler version reporting. The 91/100 `bc4db99` score remains historical.
- **Independent checks:** 73 Python tests, VS Code extension validation, compileall, QA arithmetic, and `git diff --check` passed. The 21 audited rows sum to the 450-item backlog. The critic did not visually inspect a resized game window.
- **Issue tracking:** Issue #46's canonical-number correction has now been independently verified, documented with evidence, and closed. The 98-point goal remains unmet by 6 points. The fresh result was added to issue #23 without duplicating its 450-item list.


## Batch 12 — robust near-plane clipping (canonical item #185)

- **Implementation:** pushed commit `cfce40701ac24f7fb64a0f194d7e32d5e25e2d52`. Camera-space triangles are clipped into valid polygons; grid segments are clipped to retain the visible segment; rasterized spheres now intersect camera rays and draw a flat cap where clipped by the near plane. Triangle raster bounds are clamped before integer conversion to avoid huge projected coordinates overflowing screen bounds.
- **Regression coverage:** native MSVC tests cover segments entirely behind and crossing the near plane, triangles with zero/one/two hidden vertices and boundary vertices, spheres crossing the near plane, spheres behind it, and missed rays. All **74 Python tests** pass; extension validation, compileall, QA rubric arithmetic, and diff check pass.
- **Status:** item #185 is IN PROGRESS; the current audited ledger has 22 rows (428 needing verification, 3 partial, 17 complete, 2 in progress = 450). Far/side frustum clipping remains. This candidate has not yet received a fresh critic score; the latest reviewed result remains 92/100 — FAIL against 98.


### Critic review — synchronized item #185 candidate `4bc8bc3`

- **Exact reviewed commit:** `4bc8bc3c5d01c59622d7af1237b6021d5903e13f`.
- **Fresh score:** **90/100 — FAIL** against the current **98/100** threshold. Categories: 16/20 requirements, 20/20 functionality, 19/20 architecture, 17/20 testing, 18/20 delivery.
- **Finding 1 — issue #47, numerical clipping overflow:** an MSVC probe called `anvil_clip_segment_near` with finite endpoints `(-1e308, 0, 0.01)` and `(1e308, 0, 0.4)` at near depth `0.08`; it returned visible with `x=INFINITY`. The reviewer did not reproduce a full-window crash. This reduced criterion 34 to 1/2.
- **Finding 2 — issue #47, stale candidate test count:** `docs/IMPLEMENTATION_STATUS.json` said 73 tests while the candidate passed 74 and the other QA records stated 74. This reduced criterion 38 to 1/2.
- **Independent checks:** 74 Python tests, extension validation, compileall, QA arithmetic, and diff check passed. The ledger has 22 audited rows and `428 + 3 + 17 + 2 = 450`. No live visual behavior was inspected.
- **Correction:** commit `15ac43a8033557859db509ecca2fa8c88a13d7b7` adds stable interpolation and screen-line clipping with extreme-value regression cases. The candidate JSON test count is corrected to 74. All 74 Python tests, extension validation, compileall, QA arithmetic, JSON parsing, and diff check pass. The 90-point result remains attached to exact commit `4bc8bc3`; a fresh review of `15ac43a` is required.


### Fresh critic result — corrected item #185 snapshot `eec0608`

- **Exact reviewed commit:** `eec0608dd6f252090b50fda1027eba14c6af1292`.
- **Score:** **92/100 — FAIL** against 98. Categories: requirements 16/20, functionality 20/20, architecture 19/20, testing 19/20, delivery 18/20. Criteria 34 and 38 returned to 2/2 after verifying finite extreme-coordinate clipping and the consistent 74-test count.
- **Independent checks:** 74 Python tests, all 4 native runtime tests, npm extension validation, compileall, QA arithmetic, JSON/status counts, and diff check passed. Ledger: 22 audited rows; `428 + 3 + 17 + 2 = 450`.
- **Issue #47:** the critic verified the earlier segment overflow case, extreme triangle clipping, and ±1e308 screen-line clipping. Both tracked findings are resolved; issue #47 is closed with evidence.
- **Remaining evaluation gap:** no live window was launched to visually inspect resizing or near-plane clipping. Remaining partial rubric criteria are 2, 3, 5, 9, 27, 40, 47, and 50. The required 98-point bar remains unmet.

### Mouse-input batch — canonical backlog items #391–394

- Added `mouse_x()`, `mouse_y()`, `mouse_pressed(button)`, `mouse_held(button)`, and `mouse_wheel()` built-ins across the C runtime, compiler, and VS Code grammar.
- Pointer coordinates map through the live centered aspect-preserving viewport to 960×600 virtual pixels; points in letterbox bars return `-1`. Button-down edges and wheel detents are available through one fixed update, and held-button state clears on release or focus loss.
- Added `examples/mouse_input.ANVL`, language/spec/engine/wiki documentation, extension token checks, and native integration coverage for resized coordinates, letterbox rejection, click edges, button release, and wheel reset.
- The candidate is not yet independently reviewed; the last verified score remains 92/100 — FAIL against 98. Items #391–394 are recorded as IN PROGRESS until full verification and independent review.


### Fresh critic result — mouse input candidate `d757c79`

- **Exact commit reviewed:** `d757c797751f40eee47fd518c3cf6dd3a3ae790c`.
- **Result:** **91/100 — FAIL** against the current required pass score **98/100**. Categories: requirements 16/20; functionality/reliability 20/20; architecture 19/20; testing/verification 18/20; developer experience/delivery 18/20. Criterion vector 1–50: `2,1,1,2,1,2,2,2,1,2 / 2,2,2,2,2,2,2,2,2,2 / 2,2,2,2,2,2,1,2,2,2 / 2,2,2,2,2,2,2,1,2,1 / 2,2,2,2,2,2,1,2,2,1`.
- **Finding (criterion 38, P2):** both `docs/IMPLEMENTATION_STATUS.json` and `docs/CODEX_AUTONOMOUS_STATE.json` contain CP1252 bytes and fail strict UTF-8 JSON parsing. Permissive decoding also shows candidate SHA `ddf8c6f...` and pending/uncommitted status despite reviewed HEAD `d757c79...`. This is a report-integrity defect; no mouse code bug was reproduced.
- **Verification:** 77 Python tests, npm extension test, Python compileall, QA arithmetic validator invocation, and exact-commit diff check passed. Mouse integration tested viewport mapping after resize, letterbox rejection, left/right/middle press/held/release, and wheel capture/reset. The QA validator still printed the previous 92/100 rubric before synchronization. No live mouse window was visually inspected.
- **Next:** serialize both JSON files explicitly as UTF-8, correct candidate/review references, keep the 98 threshold, and re-review the corrected snapshot.


### Fresh critic result — corrected report snapshot `c102604`

- **Exact commit reviewed:** `c10260483eab6b5adaadd261a66a92a9138b9ed8`.
- **Result:** **92/100 — FAIL** against the current 98/100 pass requirement. Categories: requirements 16/20; functionality/reliability 20/20; architecture 19/20; testing/verification 19/20; delivery 18/20. The full 50-item vector is unchanged from the prior `d757c79` review except criterion 38 is restored to 2/2.
- **Verification:** strict UTF-8 parsing, status parity (26 audited; `424 + 3 + 21 + 2 = 450`; #391–394 COMPLETE), 77 Python tests, extension validation, compileall, QA arithmetic, and diff-check pass on the exact candidate. Mouse synthetic native tests pass for resize mapping, letterbox exclusion, all three button edges/held/release states, and wheel input.
- **Finding status:** issue #48's JSON encoding and stale-review metadata defect is fixed and closed. The previous d757c79 result remains 91/100; corrected c102604 scores 92/100. No code defect was found. No live mouse-enabled window was visually inspected.
- **Remaining partial criteria:** 2, 3, 5, 9, 27, 40, 47, and 50. Continue work toward 98; this result is six points below passing.


## Batch 13 — bounded BMP image and sprite resources (source candidate `9d9bf90`)

- Added `image_load`, `image_width`, `image_height`, `image_destroy`, `image_draw`, and `image_draw_scaled` built-ins. The runtime accepts uncompressed 24-bit and 32-bit BMP images, handles padded rows and top-down files, applies bounds on dimensions/pixels/total memory, clips drawing, supports alpha, and frees resources on release or shutdown. Generation-checked numeric handles prevent a stale handle from aliasing a reused image slot.
- Added a bundled sprite and `examples/image_sprite.ANVL`, API/compiler docs, formal language-spec entries, wiki notes, and VS Code grammar/sample validation (package 0.1.9; not installed over the user's 0.1.4).
- Native runtime regression covers 24-bit and top-down 32-bit files, malformed/oversized inputs, dimension queries, clipped/scaled/native drawing, destruction, reload and stale-handle rejection. `python -m unittest discover -s tests -q` passed 79 tests; MSVC release build of the example, npm extension validation, compileall, QA arithmetic and diff check pass.
- Canonical issue #23 status: #201 PARTIALLY IMPLEMENTED (BMP only), #202 IN PROGRESS pending independent review, #209 IN PROGRESS pending independent review, #212 PARTIALLY IMPLEMENTED (scaling present, rotation missing).
- Latest independent score remains **92/100 — FAIL against 98** on `c102604`; review of the sprite source candidate is pending.

## Batch 14 — cross-backend number and text-slice parity (C8 findings)

- Closed the eight open C8 findings from the strict Part 8 review with executed C/native comparisons rather than source inspection alone.
- C8-1: the native `mid` helper clamps `start` and `count` in the double domain before converting to int64, and `right` clamps then truncates the count, so huge and fractional arguments match the C runtime (`mid("abcdef",1e300,2)` is empty, `right("abcdef",1.9)` is `f` on both).
- C8-2: both parsers keep nine significant fraction digits and skip the rest; a six-value cross-backend probe is identical.
- C8-3: the two test oracles that still encoded prefix parsing were corrected, a cross-backend parity test was added, and `LANGUAGE_SPEC.md` now states the whole-text rule explicitly.
- C8-4/C8-8: the native parser accumulates the integer mantissa in double like C, stops consuming exponent digits at C's 1000 boundary, and both backends read a magnitude outside the finite binary64 range as 0.
- C8-5: `chr(0)` is documented as empty text because Anvil text is zero-terminated, with matching tests on both backends.
- C8-6: the build-cache key now hashes every top-level runtime `.c`/`.h` file and the compiler's size/mtime, with a key-version tag retiring old entries.
- C8-7: `anvil_noise` rejects non-finite and out-of-range coordinates before any float-to-int conversion, using the native `[-2147483648, 2147483647)` interval; `fbm` inherits the per-octave check.
- Files: `compiler/native_codegen.py`, `compiler/cli.py`, `runtime/anvil_runtime.c`, `docs/LANGUAGE_SPEC.md`, `README.md`, and the number/mid/chr/noise/cache test files.
- Tests: `tests/test_number.py` 19 passed; the targeted cross-backend batch `test_number`, `test_number_format`, `test_text_functions`, `test_chrorrd`, `test_mid`, `test_noise_bounds`, `test_build_cache`, `test_native_x64` 97 passed.
- Commits: `fdb6344` (C8-1/C8-3/C8-5), `214e200` (C8-7), `40bf89d` (C8-6), `e6513b4` (C8-2/C8-4/C8-8), `7545c4c` (README).

## Batch 15 — build safety and bounded inputs (8.10, 8.15)

- **Atomic output:** `build_c` links to `<name>.partial.exe` and only replaces the requested output after the toolchain succeeds, so a failing `cl`/`cc` cannot leave a truncated program behind. A failing-toolchain test keeps the previous bytes.
- **Cache bypass:** `--no-cache` skips the cached lookup, forces a real build and stores nothing, leaving existing entries usable. Documented in the CLI table.
- **Bounded entry source:** the entry file is stat'ed and refused above the 4 MiB include budget before it is read, so a mistaken huge path cannot be loaded into memory.
- **Bounded call depth (C backend):** generated functions call `anvil_frame_enter`/`anvil_frame_leave`; a chain that grows the C stack past 512 KiB stops with `Anvil call depth exceeded the 512 KiB stack budget` and exit 2. 200000-deep non-tail recursion previously died with no output and now reports the diagnostic; 100-deep recursion still returns 5050.
- **Files:** `compiler/build.py`, `compiler/cli.py`, `compiler/codegen.py`, `compiler/common.py`, `runtime/anvil_runtime.c`, `runtime/anvil_runtime.h`, `docs/COMPILER.md`, `docs/INCLUDES.md`, `docs/LANGUAGE_SPEC.md`, and four new test files.
- **Tests:** full suite on `0b0130d` 646 passed, 1 skipped, 1 xfailed; targeted batch after the recursion change 128 passed.
- **Commits:** `dd40769`, `0b0130d`, `a24a071`, `6f0f3e8`.
- **Native guard:** the same 512 KiB budget now applies to the native backend through an inline `anvil_frame_enter` helper with a writable .data base slot; 20000-deep recursion reports the diagnostic instead of dying silently. Tests cover both backends.

## Batch 16 — packaging with dry run and manifest (8.14)

- **Command:** `--package <dir>` copies the built program and every asset into the target folder and writes `anvil-package.json`; `--package-dry-run` prints the same manifest and validates inputs without touching the filesystem.
- **Assets:** the project manifest gained an optional `[assets] files = [...]` list, merged with literal `image_load("...")`/`sound_load("...")` paths found in the program's sources. Paths outside the project folder are rejected; every missing asset is listed and fails the package step with exit 1.
- **Manifest:** format, name, target, backend, compiler identity (SHA-256 of `cl`, language version for native), used builtins, program size/hash, per-asset path/size/hash and a checksums map. No timestamps, so identical inputs produce identical bytes.
- **Files:** `compiler/package.py` (new), `compiler/cli.py`, `docs/COMPILER.md`, `tests/test_package.py`.
- **Tests:** `tests/test_package.py` 5 passed; with the cache and compiler suites 80 passed.
- **Commit:** `79d8af3`.

## Batch 17 — lifecycle commands run/clean/doctor/new (8.14)

- **`--run`:** builds, then runs the program and returns its exit code, so edit → build → run is one command. A failing program propagates its status (division by zero returns 2); combining it with `--check`, `--emit-c` or `--package` is rejected.
- **`--clean`:** removes only what the toolchain writes beside a project — `*.generated.c`, `*_obj`, `*.partial.exe`, `*.build.cmd` and `.anvil-cache` — and keeps sources and the executable.
- **`--doctor`:** prints Python version/path, platform, the discovered C compiler, native-backend readiness and the three runtime files, without needing a source file.
- **`--new <dir>`:** scaffolds `main.ANVL`, `game.ANVLproj` and `README.md` in an empty folder and refuses a non-empty one.
- **Files:** `compiler/commands.py` (new), `compiler/cli.py`, `docs/COMPILER.md`, `tests/test_commands.py`.
- **Tests:** 7 passed. Manual: `--new` then `--run` printed `Hello from Anvil`; `--clean` removed 3 artifacts and kept `main.exe`.
- **Commit:** `75a4805`.
- **Remaining from the 8.14 command list:** `test` and `format` are still unimplemented.

## Batch 18 — format command (8.14)

- **`--format`:** normalises line endings, trailing whitespace, runs of blank lines, the final newline and block indentation. Because Anvil ignores indentation, the formatter only touches whitespace and never rewrites a token; `else` dedents then re-indents, and repeated runs are idempotent.
- **`--format-check`:** exits 1 when a file would change, so CI can require formatted sources.
- **Safety evidence:** every file under `examples/` was copied, formatted and re-checked; all still compiled (`fail=0`). A unit test formats a copy of `first_world.ANVL` and asserts `--check` still reports ok.
- **Files:** `compiler/formatting.py` (new), `compiler/commands.py`, `compiler/cli.py`, `docs/COMPILER.md`, `tests/test_format.py`.
- **Tests:** 6 passed.
- **Commit:** `5967fdb`.
- **Remaining from the 8.14 command list:** `test` only.

## Batch 19 — project test runner (8.14)

- **`--test`:** compiles and runs every `tests/**/*.ANVL` case with the selected backend into a temporary output directory, running each case from its own folder so relative includes and assets resolve. A case passes when the built program exits 0.
- **Reporting:** `PASS name` per case, `FAIL name (exit N)` plus the captured build/run output, then a `N passed, M failed` summary; exit 1 if any case fails or the project has no `tests/` folder or no cases.
- **Files:** `compiler/commands.py`, `compiler/cli.py`, `docs/COMPILER.md`, `tests/test_commands.py`.
- **Tests:** 10 passed. Manual: one passing plus one failing case reported `1 passed, 1 failed` and exit 1; removing the failing case gave exit 0.
- **Commit:** `44dcd1b`.
- **Command surface:** `new`, `run`, `build`, `test`, `format`, `clean`, `doctor` and `package` now all exist, completing the 8.14 command list for this checkout.

## Batch 20 — measured backend capability matrix (8.16)

- **Tool:** `tools/capability_matrix.py` compiles and runs fourteen feature cases on the C and native backends. A case counts as `runs` only when the build succeeds and the program's output matches the expected text exactly; other statuses are `rejected`, `runtime-error`, `wrong-output`, `build-error`, `timeout` or `skipped`.
- **Result:** 12 of 14 cases run identically. `image-load` and `physics-body` are C-only and both report their existing located diagnostics (`... is not available in the native x64 backend yet; build with --backend c`).
- **Reproducibility:** temporary directories are stripped from the notes, so repeated runs produce identical bytes; `--check` exits 1 when the committed document is stale, and a test enforces it.
- **Files:** `tools/capability_matrix.py` (new), `docs/CAPABILITY_MATRIX.md` (generated), `tests/test_capability_matrix.py`, `docs/COMPILER.md`.
- **Commit:** `1afefc5`.

## Batch 21 — testing and coverage labels (8.15)

- **`docs/TESTING.md`:** records the exact environment (Windows 11 10.0.26200, Python 3.13.15, MSVC 14.51.36231, Git Bash from the repo root), the commands for the full, headless and per-area suites, and the tooling checks (`--test`, `--format-check`, `tools/capability_matrix.py --check`, `npm test`).
- **Coverage labels:** every test module is classified as headless or interactive. Interactive means a generated PE creates a real window and is driven by bounded messages to its own process id (`test_native_keyboard`, `test_native_mouse`, `test_native_window`, `test_native_procedural`, and the graphical `test_includes` cases).
- **Tolerances:** 960×600 fixed framebuffer with letterboxing, fixed-step updates (1–240 Hz, default 60), explicit state timeouts rather than sleeps, exact byte/value comparisons, and no performance claims from these tests.
- **Gaps recorded:** Windows-only runs, grammar-only extension validation, no manual visual claim.
- **Accuracy check:** all 91 test modules named in the page exist.
- **Files:** `docs/TESTING.md` (new), `README.md`.
- **Commit:** `8997af2`.

## Batch 22 — network fuzzing and prompt output (8.14/8.15)

- **Runtime hardening:** `anvil_net_receive` ignores datagrams whose length is not one double and 8-byte payloads that are NaN or infinite, keeping the previous value. A malformed packet can no longer poison comparisons or stop the program.
- **Fuzz test:** `tests/test_net_fuzz.py` hosts a real program, sends empty/1/4/7/9/16-byte datagrams and NaN/+inf/-inf bit patterns, then one valid 2.5, and asserts the program exits 0 with only 2.5 accepted and no `nan`/`inf` output.
- **Found while testing:** `say` output was block-buffered when stdout was a pipe, so a running program looked silent until exit. Generated C now calls `fflush(stdout)` after each `say` line; `tests/test_output_flush.py` reads the first line while the program is still sleeping.
- **Contract update:** the old UDP NaN test expected exit 2 with a located non-finite error; it now floods NaN and asserts survival plus acceptance of a later finite value. `docs/LANGUAGE_SPEC.md` and `docs/MULTIPLAYER.md` record the payload rules.
- **Tests:** 70 passed across `test_compiler`, `test_net_fuzz` and `test_output_flush`.
- **Commits:** `031bfb0`, plus the test-contract commit.

## Batch 23 — Part 8 evidence ledger (8.16)

- **`docs/PART8_EVIDENCE.md`:** maps sections 8.8–8.17 to verified behaviour, the exact commits and test files, and the remaining gap for each. Status is honest: 8.8/8.10 verified, 8.9 verified for existing resources, 8.11/8.13/8.14/8.15 partial, 8.12 browser not implemented, 8.17 new-user trial not performed.
- **Checked before claiming:** local-array and recursion budgets are covered by `tests/test_compiler.py` and `tests/test_recursion_budget.py`; image caps are documented and enforced but only missing-file diagnostics are tested (recorded as a gap); the 3D sample is marked interactive rather than automated.
- **Index:** 17 commits from the C8 parity work through the network fuzz and per-line flush.
- **Files:** `docs/PART8_EVIDENCE.md` (new), `README.md`.
- **Commit:** `27be76d`.

## Batch 24 — image limit diagnostics (8.9/8.10)

- **Specific rejections:** `image_load` used one generic message for every failure. Each check now returns early with the reason: width or height over 8,192 (naming the value), pixel count over 16,777,216, the remaining 128 MiB budget in MiB, a file shorter than its declared rows, or an allocation failure.
- **Tests:** `tests/test_image_limits.py` covers the width, height, pixel-count and short-file messages plus an 8,192-pixel-wide image that still loads; `tests/test_image_error.py` still passes unchanged. 8 passed.
- **Docs:** `ENGINE.md` and `LANGUAGE_SPEC.md` describe the named reasons; `TESTING.md` lists the new module.
- **Commit:** `e4de27d`.

## Batch 25 — build-cache completeness (C8-9, C8-10)

- **Reproduced both findings** with `.scratch/repro_c89_c810.py` before changing code: a 4096-byte compiler replaced by different 4096-byte code with the original `st_mtime_ns` restored produced the identical cache key, and rewriting the `link.exe` beside the compiler also left the key unchanged.
- **C8-9 fix:** `_compiler_identity` hashes the compiler's bytes instead of path/size/mtime.
- **C8-10 fix:** the key now includes `link.exe` bytes from the compiler's own toolset folder, the installed Windows SDK `Include`/`Lib` version directories, and `WindowsSDKVersion` when present. `CACHE_KEY_VERSION` is `anvil-cache-v3`, so pre-fix entries are never reused.
- **Tests:** `test_same_size_same_time_compiler_replacement_changes_the_key`, `test_a_changed_linker_beside_the_compiler_changes_the_key`, `test_an_unchanged_linker_keeps_the_key` — red before the fix, green after; 12 passed with `test_build_atomic`.
- **Measured cost:** cold C build 1.67 s, cached hit 0.22 s (was 0.13 s) with the real MSVC toolset, so hashing ~4.6 MB of tools costs about 0.09 s.
- **Known gap recorded in `docs/COMPILER.md`:** libraries passed through `build_c(libraries=...)` are still not part of the key.
- **Commit:** `d1e56b9`.

## Batch 26 — typo inside an unused function (8.10/8.8)

- **Gap found by probing include diagnostics:** an unknown call inside a function that is never called compiled clean (`main.ANVL: ok`), because uncalled functions are pruned before lowering and the project's documented boundary only checks emitted code. Include spans themselves are correct: the same error in a *called* helper reports `lib/util.ANVL:5` with a caret.
- **Fix:** `compiler/lints.py::unknown_calls_in_unused_functions` warns `unused function 'helper' calls unknown function 'helo'; did you mean 'hello'?`, reusing the suggestion helper. It joins the existing warning list, so `--deny-warnings` exits 1. Entry file only, matching the unused-function warning's shared-include policy.
- **Pre-flight:** all 36 examples parsed; zero would warn.
- **Tests:** `test_a_typo_in_an_uncalled_function_is_reported` was red first, then green; 50 passed across `test_lints`, `test_suggestions`, `test_dead_branches`, `test_refusals`, `test_unused_imports`. CLI verified: warning with caret, `--deny-warnings` rc 1.
- **Commit:** `a896281`.

## Batch 27 — always-on-top and fullscreen (8.11/8.14)

- **`window_on_top(on)`**: sets or clears `WS_EX_TOPMOST` so the game floats over other programs, or goes behind them again when clicked away.
- **`window_fullscreen(on)`**: saves the window style and rectangle, switches to borderless `WS_POPUP` on the current monitor, and restores the exact previous style and rectangle on `0`. Both return 1 on success and 0 without a window, usable as statements or expressions.
- **Native backend:** reports a source-located "not available in the native x64 backend yet" diagnostic instead of ignoring the call.
- **Tests:** `tests/test_window_flags.py` drives a real window and inspects live Win32 state after each phase — `WS_EX_TOPMOST` present/absent, `WS_POPUP` plus rectangle equal to the monitor, then the original rectangle restored. 110 passed with includes, compiler, capability matrix and native x64.
- **Also:** `examples/window_controls.ANVL` (F/T toggles), spec and engine docs, native migration note, VS Code grammar and `npm test`.
- **Commit:** `25ac3ab`.

## Batch 28 — SDK contents and environment script identity (C8-11, C8-12)

- **C8-12 reproduced first:** a same-size `VsDevCmd.bat` replacement with the original `st_mtime_ns` restored produced the identical environment cache path.
- **C8-12 fix:** the cache file name is now a SHA-256 of `VsDevCmd.bat` and `vcvarsall.bat` contents plus the arch, so stale environments cannot be revived.
- **C8-11 fix:** `_sdk_fingerprint` hashes every file under the newest SDK version's `Include` and `Lib` trees by path, size and mtime. Measured 40 ms cold and 10 ms warm, against 531 ms for a stat-per-file walk, because `os.scandir` supplies the metadata.
- **Residual window:** a build still trusts the newest version directory by name; if two SDKs were installed out of order the newest name wins, which matches VsDevCmd's usual selection.
- **Tests:** header edit, library edit, unchanged control, newer version directory and missing SDK; same-size script replacement, changed nested script, unchanged script. 27 passed.
- **Cost after the change:** cold build 451 ms (was 413 ms), cache hit 53 ms (was 41 ms).
- **Commit:** `a4eafbc`.

## Batch 29 — window flags, first-hour workflow and a green checkpoint

- **Suite:** 742 passed, 1 skipped, 1 xfailed in 190 s on `fab2030` (was 646 passed in 618 s before this work stream; the 3.3x speedup comes from the cached toolset environment).
- **Window controls:** `window_on_top` / `window_fullscreen` with live Win32 state assertions, including repeated toggles that must not re-save the fullscreen geometry.
- **Diagnostics:** closest-name suggestions, stable codes for ten errors, `--explain CODE`, `--diagnostics editor` with `file:line:column`.
- **Build loop:** compiler/linker/SDK/environment identity all content-based; `--timings` shows parse+generate ~3 ms against a ~450 ms cold build.
- **First hour:** `tests/test_first_hour.py` runs the documented scaffold → check → build → run → format → package → doctor → explain path.
- **Open roadmap items are features, not defects:** browser target (no WASM toolchain in this environment), glTF/animation, audio, records. All audit findings C8-1..C8-12 are closed.

## Batch 30 — C8-11 header half: hash the headers the build consumed

- **Reproduced first:** on a synthetic SDK tree, replacing `windows.h` and `kernel32.lib` with different same-size contents and restoring their `st_mtime_ns` left `_sdk_fingerprint` at the identical `3a845389c0b0d552`. A size-changing edit did change it, which is why the committed tests missed the case.
- **Whole-tree byte hashing rejected by measurement:** 1,167 MB under `Include\10.0.26100.0` plus `Lib\10.0.26100.0` costs 5,867 ms, more than a cold build, so it cannot sit on a cache hit.
- **Fix:** `build_c(..., deps_path=...)` passes `cl /sourceDependencies<file>`; `store_build` copies the JSON beside the cache entry as `<base-key>.deps.json`, and `cached_build` folds a SHA-256 of those headers' **bytes** into the key. Missing or unreadable sidecars fall back to the metadata key, so old caches still work and repair on the next real build.
- **Measured cost:** `examples/first_world.ANVL` consumes 120 distinct headers (5.45 MB); digesting them costs 9-10 ms, and `/sourceDependencies` adds no measurable compile time (315 ms with and without the flag; the dependency list was identical across runs).
- **Tests:** same-size/same-mtime replacement changes the key; unchanged headers keep it; missing, unreadable and deleted-dependency cases. `tests/test_build_cache.py` 20 passed; with build-atomic, toolchain-env, timings and compiler suites 85 passed. End to end the second build printed `(reused build cache)` and wrote a 147-entry sidecar.
- **Still open:** the library half. Default `.lib` files are resolved by the linker, not named on the command line, so a same-size replacement of one is still invisible to the key.

## Batch 31 — C8-11 library half: hash the libraries the linker resolved

- **Problem:** default `.lib` files are chosen by `#pragma comment(lib, …)` inside SDK headers, so they appear on neither the command line nor the header dependency list. A same-size, same-mtime replacement of a static library could still return a stale executable.
- **Capture:** `build_c(..., libs_path=...)` adds `/link /VERBOSE` and parses the `Searching <path>.lib:` lines the linker prints, writing `<base-key>.libs.json` beside the cache entry. On failure the captured output is echoed to stderr before the build error propagates.
- **Keying:** `_library_digest` folds a SHA-256 over each resolved library's path and bytes into the cache key, independent of the header sidecar; either list may be missing and its half falls back to the metadata key.
- **Measured:** a real build resolves nine libraries totalling 62 MB; digesting them costs about 36 ms, taking a `first_world` cache hit from ~145 ms to 169-177 ms against a 315 ms cold build. sha256 was the fastest option here (blake2b was 1.6x slower).
- **Verified end to end:** second build printed `(reused build cache)`; folded key `3b0ba6cd…` equals the cached executable's name; `.libs.json` lists 9 libraries.
- **Tests:** same-size/same-mtime library replacement changes the key, missing library list falls back, `/VERBOSE` parsing keeps only files that exist. `tests/test_build_cache.py` 24 passed.
- **Closes:** C8-11 entirely — headers (Batch 30) and libraries (this batch).

## Batch 32 — audio: bounded WAV playback (8.14)

- **Builtins:** `sound_load(path)`, `sound_error()`, `sound_play(handle)`, `sound_play_loop(handle)`, `sound_stop(voice)`, `sound_stop_all()`, `sound_volume(voice,v)`, `sound_pan(voice,p)`, `sound_pitch(voice,r)`, `sound_active()`, `sound_destroy(handle)`.
- **Format and limits:** uncompressed PCM WAV, mono or stereo, 8- or 16-bit, 8,000–192,000 Hz; converted once at load to 48 kHz stereo 16-bit. 16 sound slots, 8 voices, 8 MiB decoded per sound, 48 MiB total. Every rejection sets a readable `sound_error()` (open failure, bad RIFF, non-PCM, channel/bit-depth/rate limits, per-sound or total budget, truncated data).
- **Device and threading:** `waveOut` opened lazily on first play, mixed on one worker thread into three 10 ms buffers (~30 ms latency). A missing or lost device falls back to silence with an error instead of crashing; audio is released on window teardown and through `atexit` for console-only programs.
- **Backends:** C backend only; `--backend native` raises the standard located "not available in the native x64 backend yet" diagnostic.
- **Tests:** load errors for missing/empty path, non-WAV, 24-bit, 3 channels, low rate and the per-sound budget; play/volume/pan/pitch clamps; bounded voices (8 then "all voices are busy"); looping across its source length; destroy stops voices and frees the slot. `tests/test_audio.py` 10 passed.
- **Also:** `examples/audio_demo.ANVL` with `examples/assets/anvil_tone.wav`, spec table and grammar, evidence ledger, testing doc.

## Batch 33 — saves: typed key/value storage (8.14)

- **Builtins:** `save_number(slot,v)`, `load_number(slot)`, `save_text(slot,text)`, `load_text(slot)`, `save_exists(slot)`, `save_delete(slot)`, `save_error()`.
- **Storage:** one value per slot in `%LOCALAPPDATA%\Anvil\<project>` (project name comes from the source or manifest, sanitised to `[A-Za-z0-9._-]`); `ANVIL_SAVE_DIR` overrides the root for hosts and tests.
- **Safety:** slot names are 1–64 bytes from the same safe set, must not start with a dot and must not contain `..`, so a save cannot escape its folder. Files carry an `ANVSAVE1` magic plus a type byte; reading text as a number (or the reverse) returns 0/empty with a named error instead of reinterpreting bytes. Writes go to a temp file and `MoveFileExA(..., MOVEFILE_REPLACE_EXISTING)` swaps it in atomically.
- **Limits:** 255-byte text values, non-finite numbers rejected on read, missing slot is a normal first run (0/empty, empty error).
- **Tests:** round trip, cross-run persistence, missing slot, type mismatch in both directions, delete, traversal/oversized/invalid slots, 255-byte boundary and the default `%LOCALAPPDATA%` root. `tests/test_saves.py` 9 passed.
- **Also:** `examples/save_demo.ANVL`, spec table and grammar, engine/language docs, evidence ledger, testing doc.
- **Fixed en route:** the `number("...")` lint matched the `number(` inside `load_number(`, warning about every non-numeric save slot; the matcher now requires a name boundary, with a regression test.

## Batch 34 — compile-time and size budgets are enforced (8.15)

- **Published budgets:** `tools/bench_budgets.json` now records, per benchmark case and backend, a time ceiling and an executable-size ceiling plus the measured median they came from. Budgets are 3x the measured time and 1.25x the measured size, which absorbs scheduler noise without hiding a real regression.
- **Enforcement:** `python tools/bench_anvil.py --check` exits 1 and prints every exceeded budget; `--write-budgets` re-measures the current machine and rewrites the file, so re-baselining is a command rather than an edit.
- **Tests:** `tests/test_perf_thresholds.py` covers the budget file (every case and backend present, all ceilings positive), runs the four cases against the published budgets (fails on any regression), and feeds a deliberately impossible budget through the checker to prove it is not vacuous. 3 passed in 2.1 s.
- **Measured baseline on this machine:** tiny C 0.397 s / 144,384 B; texty 0.411 s / 151,040 B; big 0.424 s / 154,624 B; big_trim 0.397 s / 144,384 B; native 0.001-0.005 s and 3-27 KB. Published ceilings: C 1.18-1.25 s and 180-193 KB; native 3-14 ms and 3.8-33 KB.

## Batch 35 — sprite tint, flip and rotation (8.14)

- **Builtins:** `image_draw_rotated(handle,cx,cy,degrees,scale)` draws centred, rotated clockwise and uniformly scaled; `image_tint(handle,r,g,b)` multiplies the sprite's colours (0-255 per channel, 255 = unchanged); `image_flip(handle,x,y)` mirrors it. Tint and flip are per-image state applied by every draw path and reset on destroy.
- **Implementation:** the scaled path samples the source with the flip applied and shades through the tint before alpha-blending; the rotated path inverse-transforms each destination pixel around the centre and samples nearest-neighbour, matching the existing scaled draw's filtering.
- **Tests:** `tests/test_sprite_draw.py` draws a 2x2 quadrant BMP, resizes the window until the client is exactly 960x600 (so the framebuffer maps 1:1), and reads the presented pixels with GetPixel. It asserts the four plain quadrants, the horizontal flip, a 128-grey tint, and the 90-degree clockwise arrangement (top-left blue, top-right red, bottom-left white, bottom-right green). 1 passed in 2.8 s.
- **Also:** `examples/sprite_transform_demo.ANVL`, spec table and grammar, evidence ledger, testing doc.

## Batch 36 — atlas-region drawing (8.14)

- **Builtin:** `image_draw_region(handle,sx,sy,sw,sh,dx,dy,dw,dh)` copies a source rectangle (a sprite-sheet cell) into a destination rectangle with the existing nearest-neighbour scaling, tint and flip; flip mirrors inside the cell. A source rect outside the image returns 0 and draws nothing, so a wrong atlas layout is visible instead of silently clamped.
- **Tests:** the second case in `tests/test_sprite_draw.py` loads a 4x4 four-quadrant BMP, draws each 2x2 cell into a 4x4 destination and checks the centre pixel, mirrors the top half (red|green becomes green|red) and asserts an out-of-range region returns 0 and leaves the frame untouched. 2 passed in 6.1 s.
- **Editor:** the TextMate grammar and `validate.js` now list the sprite, sound and save builtins (they had lagged behind the runtime); `npm test` passes.
- **Docs:** language spec row and grammar, evidence ledger, testing doc.

## Batch 37 — 2D camera (8.14)

- **API:** `camera2d(pan_x,pan_y,zoom)` sets a world→screen transform `screen = (world - pan) * zoom` used by rect, circle, line, text position and every sprite draw path. The identity default keeps existing programs unchanged; zoom is clamped to 0.05–20, and a non-finite or non-positive zoom returns 0 and leaves the camera alone. `mouse_x`/`mouse_y` invert the transform, so pointer coordinates are world coordinates. Text moves with the camera but keeps its pixel size because there is no scalable font yet; 3D drawing is untouched.
- **Tests:** `tests/test_camera2d.py` draws a world-space rect and samples the window at the identity position, after a (50,50) pan, after 2× zoom, after a rejected zero-zoom call and after reset. 1 passed.
- **Harness fix:** two window-reading tests in the same run interfered — the second window could be occluded, and `GetPixel` on a window DC then reads the covering window. `WindowReader.force_client_size` now raises its window with `HWND_TOPMOST`, which made the three window tests pass together.
- **Docs:** language spec row and grammar, editor grammar/validator, evidence ledger, testing doc.

## Batch 38 — scalable text under the camera (8.14)

- **Runtime:** `anvil_text` now sizes its font as `20 * camera2d_zoom` (clamped to 6–720 px), so world-space labels grow and shrink with the camera instead of staying a fixed pixel size. The default camera still renders the original 20 px.
- **Harness:** `WindowReader.bounding_box` first read pixels one at a time with GetPixel, which took seconds per scan and made timing-sensitive tests read stale frames. It now grabs the rectangle in one BitBlt through a DIB section (`grab`), so a scan is milliseconds.
- **Test:** `tests/test_text_zoom.py` holds identity, 2x zoom and reset frames for 2.5 s each and measures the bounding box of the glyphs; 2x must be at least 1.6x wider and taller and moved right, and reset must return to the original box. 1 passed; the three window suites together 4 passed in 17.1 s.
- **Docs:** language spec camera row, evidence ledger, testing doc.

## Batch 39 — runtime frame benchmarks with enforced budgets (8.15)

- **Builtins:** `frame_tick()`, `frame_render()` and `frame_present()` return the last frame's update, draw and presentation times in seconds; the main loop records them with QueryPerformanceCounter around each phase. This is the first way for a program to see real per-frame work instead of the fixed 60 Hz `delta()`.
- **Harness:** `tools/bench_runtime.py` builds four ordinary Anvil scenes (idle 2D, 2D overdraw with 1,200 rects and 120 circles, 40 text lines, 20 cubes plus a plane), skips 30 warm-up frames, buckets 120 frame totals at 0.25 ms resolution (no runtime sort), prints p50/p95/worst and compares against `runtime` budgets in `tools/bench_budgets.json`. `--write-budgets` re-measures (2.5x headroom); `--check` exits 1 on a miss.
- **Measured here:** idle 0.38 ms, overdraw 3.88 ms, text 1.12 ms, cubes 2.88 ms p50.
- **Test:** `tests/test_runtime_budget.py` runs `--check` and asserts the scene list matches the budgets file; 2 passed in 13 s.
- **Docs:** language spec clock row, evidence ledger, testing doc.

## Batch 40 — atlas packing tool (8.14)

- **Tool:** `tools/pack_atlas.py` reads uncompressed 24/32-bit BMPs, orders them by height/width/name, packs them on shelves with an optional gutter, writes a 32-bit BGRA sheet and a sorted, timestamp-free `anvil-atlas-1` JSON manifest. Sprite names come from file stems and duplicates are refused; an image wider than the sheet is refused with its width in the message.
- **Bug caught by the test:** the width guard unpacked the sprite tuple with the fields in the wrong position, so it compared heights and allowed a 5 px image into a 4 px sheet. `pack()` now indexes the width field directly.
- **Tests:** `tests/test_atlas_pack.py` packs three solid sprites, reads the sheet back and checks every cell pixel against the manifest rectangle, verifies rectangles do not overlap with padding, requires byte-identical sheet and JSON across runs, and covers the duplicate-name and oversized-image errors; 4 passed.
- **Docs:** `docs/ATLAS.md` documents the workflow, options, manifest and `image_draw_region` usage.

## Batch 41 — audio mixer groups (8.14)

- **Runtime:** every loaded sound carries a group (1..3, default 1). Three group gains plus a master gain (group 0) multiply into the mixer, with mute tracked separately so a muted group keeps its volume. `sound_group(handle,group)`, `sound_group_volume(group,v)` (0..1), `sound_group_mute(group,on)`, `sound_group_gain(group)` (effective, 0 while muted) and `sound_group_stop(group)` (0 stops all) are exposed.
- **Compatibility:** the default group is 1 and its gain is 1.0, so existing programs mix exactly as before.
- **Tests:** `tests/test_audio_groups.py` covers assignment, invalid groups and fractional groups, gain clamping, master gain and mute, and stop isolation with two looping voices in groups 1 and 2 plus a stop-all; 3 passed. Playback cases skip when the machine has no audio device.
- **Docs:** language spec audio row, evidence ledger, testing doc.

## Batch 42 — compile-time glTF import (8.13)

- **Compiler:** `compiler/gltf.py` reads `.gltf` at build time, resolves external `.bin` or base64 data-URI buffers, walks the node hierarchy (matrix or TRS, 64 levels), converts triangles/strips/fans, averages `COLOR_0` or uses the material `baseColorFactor`, and enforces a 200,000-triangle budget. `model_draw` is lowered to a static `double` array plus `anvil_mesh_draw`.
- **Runtime:** `anvil_mesh_draw` scales/rotates/translates each triangle, flat-shades it with the scene light and rasterises through the same near-plane clip and depth buffer as `cube`.
- **Diagnostics:** missing, malformed, oversized or unsupported models stop the build at the call site with the resolved path; a `model_draw` in an included module is rejected with a clear message instead of emitting a definition after its use.
- **Bug caught while building:** the index bounds check compared primitive-local corners rather than resolved indices, so a valid quad was rejected as out of range; the loader now maps corners through the index accessor first.
- **Tests:** `tests/test_gltf_model.py` covers the loader (quad → two triangles, translation, missing/broken files), the located compile error, a rendered quad whose centre matches the computed flat-shade value (169,0,0), and depth ordering with a nearer blue quad. 6 passed; the rendered frame was also inspected as an image.
- **Docs:** language spec row, `docs/MODELS.md`, README link, evidence ledger, testing doc.

## Batch 43 — GLB container support (8.13)

- **Loader:** `compiler/gltf.py` now reads `.glb` as well as `.gltf`: it validates the 12-byte header (magic, version 2, declared length), walks the chunks, decodes the JSON chunk, keeps the BIN chunk as buffer 0 for buffers without a `uri`, and skips unknown chunk types per the spec. Truncated chunks, a missing JSON chunk and a wrong version or magic are named errors.
- **Tests:** `tests/test_gltf_model.py` builds a GLB fixture holding the same quad and asserts its triangles are identical to the `.gltf` version, rejects a header-only GLB, and renders the GLB quad with the same expected centre pixel. 9 passed.
- **Docs:** `docs/MODELS.md` table and unsupported list, language spec row, evidence ledger, testing doc.

## Batch 44 — streaming music (8.14)

- **Runtime:** one music track is streamed from disk instead of decoded into memory. `music_load` parses RIFF chunks, records the data offset/length and validates PCM 8/16-bit mono/stereo 8k-192k. The mixer keeps an 8192-frame (~170 ms) staging buffer, refills it from the file and linearly resamples to 48 kHz; the track stops at EOF unless looping, and `music_stop` rewinds.
- **API:** `music_load`, `music_play`, `music_play_loop`, `music_stop`, `music_playing`, `music_volume` (0-1, scaled by the master group), `music_position`, `music_length` and `music_error`.
- **Tests:** `tests/test_music.py` covers length/volume/clamps, five named load failures (missing, non-WAV, 3 channels, 24-bit, empty data), a playing track that reports position and rewinds on stop, a short track that finishes itself, and a looping track that keeps playing with a wrapping position. 4 passed.
- **Fix along the way:** `say` rejected `music_error()` until the text-returning builtin was added to the codegen text-expression list (it already existed in the expression layer's set).
- **Docs:** language spec row, evidence ledger, testing doc.

## Batch 45 — particle system (8.14/8.15)

- **Runtime:** a fixed 4,096-particle pool with `particle_emit(x,y,vx,vy,life,size,r,g,b)`, `particle_count`, `particle_clear` and `particle_gravity`. Particles advance every fixed update by velocity plus constant gravity, expire on their lifetime, and are drawn after the program's draw pass as squares fading from alpha 255 to 0. World-space, so the 2D camera applies.
- **Bounds:** emit returns 0 when the pool is full or an argument is non-finite/`life <= 0`/`size <= 0`; window teardown empties the pool.
- **Tests:** `tests/test_particles.py` covers argument rejection, filling all 4,096 slots and the next emit failing, clear returning the live count, a fresh particle reading nearly solid red, a mid-life faded value and a black frame after expiry. 3 passed.
- **Benchmark:** `particles_2d` joins `tools/bench_runtime.py` (about 2,400 live particles at p50 0.88 ms), and its budget is enforced with the others.
- **Bug caught:** the runtime header lacked the new prototypes, so generated C used implicit declarations and `particle_clear` returned garbage; the prototypes were added after the `anvil_rect` block.
- **Docs:** language spec row, evidence ledger, testing doc, `examples/particles_demo.ANVL` (screenshot inspected: orange fountain over the floor band).

## Batch 46 — bounding-sphere culling for models (8.13)

- **Compiler:** `bounds_of` computes a centre and radius from the baked triangles and emits them as part of the `anvil_mesh_draw` call, so culling costs no runtime bounds pass.
- **Runtime:** each model's sphere is scaled, rotated and translated, then tested against the near plane and the projected viewport. Entirely-behind or entirely-outside models are skipped before any triangle work, returning 0. `mesh_culled()`/`mesh_drawn()` expose per-frame counts and `mesh_culling(on)` toggles the test.
- **Measured:** 20 off-screen models of 2,048 triangles each (40,960 triangles) cost 3.83 ms/frame with culling off and 0.20 ms with it on — 18.9x less render time for that scene. A single 2-triangle quad only gained 1.11x, so the win scales with triangle count, as expected.
- **Tests:** `tests/test_gltf_model.py` now asserts a behind-camera model reports 1 culled / 0 drawn, a visible one 0 / 1, and that `mesh_culling(0)` forces the behind-camera model to draw. 10 passed.
- **Docs:** language spec model row, `docs/MODELS.md` culling section, evidence ledger, testing doc.

## Batch 47 — overhead shadows (8.13)

- **Runtime:** `shadow(on)` makes `cube` and `model_draw` draw a copy of their geometry flattened onto a horizontal plane at `shadow_height(y)`, in black at `shadow_alpha(a)` (default 150), before the object. Drawn through the same depth buffer, so objects occlude their own shadows correctly.
- **Camera:** added `camera_angle(yaw,pitch)` so a program can look down programmatically (pitch clamped to ±89). Until now only the arrow keys could pitch the camera, which made ground-plane behaviour untestable.
- **Tests:** `tests/test_shadows.py` sets a tilted camera and samples a pixel where the shadow must land: a horizontal quad at y=2 casting onto y=0 (darkens, then returns to background when `shadow_height(1)` moves it), and a cube at y=1 casting below itself. 2 passed. The demo frame was inspected as an image: two cubes on a grid plane with dark shadows beneath.
- **Docs:** language spec rows for the 3D camera and shadows, evidence ledger, testing doc, `examples/shadows_demo.ANVL`.

## Batch 48 — IMA ADPCM WAV support (8.14)

- **Decoder:** a shared IMA ADPCM block decoder (89-entry step table, 16-entry index table) for WAV format tag 0x0011, mono or stereo, blocks up to 4,096 bytes.
- **Sounds:** `sound_load` decodes every block to 16-bit, then reuses the existing 48 kHz resampler; a decode larger than 64 MiB is refused. Validation now allows PCM 8/16-bit and ADPCM 4-bit with distinct messages.
- **Music:** `music_load` accepts ADPCM and the streaming reader decodes one block at a time into a small buffer, so memory stays flat; length and looping use block counts.
- **Queries:** added `sound_duration(handle)` and `sound_rms(handle)` so imported audio can be checked without playing it.
- **Bugs fixed:** the music parser still rejected every non-PCM format (`if (format != 1) return 0`), and `frame_bytes` became 0 for 4-bit audio, dividing by zero (0xC0000094) when the stream started.
- **Tests:** `tests/test_wav_adpcm.py` covers decoding and playing a compressed sound, streaming ADPCM music with the right length and position, decoded RMS within 600 of the PCM reference, and the 4-bit rejection messages for both loaders. 4 passed.

## Batch 49 — WebAssembly console target (8.12 first slice)

- **Backend:** `--backend wasm` reuses the C code generation with a freestanding runtime (`runtime/anvil_wasm.c` + `anvil_wasm.h`), links with clang 23.1.4 and wasm-ld, and writes both the `.wasm` and a host `.html` page that wires `env.write` to a `<pre>`.
- **Runtime:** implemented `printf`/`putchar`/`strlen`/`memcpy`/`memset`/`strcmp`, a 1 MiB bump allocator, number formatting, string helpers (`str_set`, `str_cat`, `text_mid`, `text_upper`, `text_to_number`), array bounds checks and frame-depth checks; math builtins lower to wasm instructions via `__builtin_*`.
- **Subset enforcement:** `scene`/`display`/`engine` statements and builtins outside the allowed list are refused with a source-located error before linking, instead of failing at link time with an undefined symbol.
- **Host:** `tools/wasm_host.mjs` runs a module under Node and is used by `--run`.
- **Tests:** `tests/test_wasm.py` covers hello output, strings/arrays/loops/function calls, `--check`, the generated host page, and both refusals (graphics at line 1, `time()` at line 2). 5 passed.
- **Docs:** `docs/WASM.md`, backend list, README link, evidence ledger, testing doc.

## Batch 50 — canvas 2D in the wasm target (8.12)

- **Runtime:** the wasm runtime now forwards `clear`, `rect`, `circle`, `line` and `text` to host imports and stores the `update`/`draw` callbacks; `anvil_run` returns immediately and the exported `anvil_frame(delta)` runs one update, clear, draw and `present`. Strings cross the boundary as `(ptr, len)` and the host decodes UTF-8 from memory.
- **Host page:** generated `.html` now contains a 960×600 canvas with a 2D context, real drawing for each primitive, and a `requestAnimationFrame` loop calling `anvil_frame`.
- **Node host:** `--record` captures the draw-command stream as JSON so tests can assert order and arguments without a browser.
- **Validation:** `scene 2d` and `display rect/circle/line/text` are allowed; `scene 3d`, `camera`, `engine` and other shapes are refused with their line number.
- **Tests:** `tests/test_wasm.py` adds the canvas command stream (clear, rect, circle, line, text, present with exact arguments), the host page contents, and the new refusals. 8 passed.
- **Visual check:** the generated page was served over HTTP and opened in Chromium; the canvas showed the red rectangle and yellow "hi" text, and sampled pixels matched the scene colours.

## Batch 51 — wasm input and time (8.12)

- **Runtime:** keyboard/mouse state with one-frame pressed edges, `time()`/`delta()` driven by the host's frame delta (clamped 0-250 ms), and exported setters `anvil_key`, `anvil_mouse`, `anvil_mouse_button` and `anvil_wheel`. Key codes match the C runtime (A-Z 65-90, Space 32, Enter 13, Escape 27, arrows 37-40); mouse buttons are left/right/middle.
- **Host page:** window keydown/keyup listeners (with `KeyA` mapping and arrow/space scroll suppression), canvas-relative mousemove, mouse buttons and wheel; `window.anvil` exposes the instance so frames can be stepped deterministically.
- **Node host:** `--input JSON` drives a script of `key`/`mouse`/`button`/`wheel`/`frame` steps for tests.
- **Tests:** `tests/test_wasm.py` adds exact output for pressed/held edges, mouse coordinates and per-frame delta, time accumulation across frames, and the host page's input listeners. 11 passed.
- **Visual check:** a colour-flag program was served and opened in Chromium; stepping frames showed blue when idle, red while `A` was held, and blue again on release, both through the exported API and through real DOM `KeyboardEvent`s.

## Batch 52 — wasm math and random (8.12)

- **Runtime:** `sin`/`cos` implemented without libm by reducing the angle to [-pi, pi] (nearest-turn) and summing the Taylor series to n=9; `rnd(low, high)` uses the same xorshift64 multiplier/algorithm as the C runtime and keeps its inclusive integer range and swap-if-reversed behavior, seeded with a fixed constant so runs are reproducible.
- **Why:** clang lowers `sin`/`cos` to libcalls in wasm (there is no trig instruction), so the freestanding shim has to provide them under the libm names the C generator already emits.
- **Tests:** `tests/test_wasm.py` runs a ten-value trig program and pins results that match `cl.exe`'s libm byte-for-byte, including `sin(1e6)`; a 500-draw loop asserts `rnd(0,9)` never leaves its range and `rnd(4,4)` is the fixed point. 13 passed.
- **Cross-check:** the same source compiled with the C backend and with the wasm backend produced identical ten-line output (`diff` empty).

## Batch 53 — wasm saves over localStorage (8.12)

- **Runtime:** the six save builtins plus `save_error` now work in wasm. Values are a type byte plus payload: numbers as 16 hex digits of the IEEE-754 bit pattern (exact round trip), text as UTF-8 (255-byte limit). Slot validation, project-name sanitizing, "not a readable Anvil save", type-mismatch and non-finite messages all match the C runtime word for word.
- **Hosts:** the page maps `save_read`/`save_write`/`save_delete` onto `localStorage` keys of the form `anvil:<project>/<slot>`; the Node host uses a Map, optionally persisted through `ANVIL_SAVE_FILE`.
- **Tests:** `tests/test_wasm.py` covers the round trip and every error name, two separate Node runs sharing one JSON file, invalid slots and oversized text. 16 passed.
- **Visual check:** a program that saves "seen" on its first frame was served in Chromium. With cleared storage, frame 1 drew green and `localStorage` then held `2yes`; after a reload, frame 1 drew blue, so the page really reads the persisted slot.

## Batch 54 — wasm text helpers (8.12)

- **Runtime:** `lower`, `trim`, `left`, `right`, `char`, `contains`, `starts_with` and `ends_with` are implemented in the freestanding shim with the C runtime's exact clamping: counts truncate toward zero, values at or above the length clamp to the whole string, negative/NaN counts give empty text, and `char` returns empty text for an out-of-range index.
- **Tests:** `tests/test_wasm.py` builds the same source for wasm and for the C backend and asserts both outputs are equal, with the expected 15 lines pinned (`left("abc", 99)` is `abc`, `right("abc", -1)` is empty, `left("abcdef", 1.9)` is `a`, `char("hello", 9)` is empty). 17 passed.

## Batch 55 — compile and runtime memory capture (8.15)

- **Tool:** `tools/bench_memory.py` samples the working set of the compiler's whole process tree (Python plus `cl.exe`) every 20 ms during a cold build, records the generated C and executable sizes, then samples each scene's working set every 50 ms while it runs. `--check` enforces `tools/mem_budgets.json`; `--write-budgets` re-baselines it with 2.5x headroom and floors (200 MB compile, 60 MB runtime).
- **Measured here:** compile peak 111.6-113.3 MB for all five scenes; generated C 10.9 KB (idle) to 15.0 KB (3D); executables 187-206 KB; runtime peak 17.2-17.3 MB for every scene, which is dominated by fixed process overhead rather than scene content — recorded honestly instead of inferred.
- **Tests:** `tests/test_memory_budget.py` runs one scene, asserts the metrics are present and sane, checks the budget file covers all five scenes, and enforces the gate through `--check`. 3 passed.
- **Gap:** VRAM and input latency are still not instrumented; allocation counts per resource are not exposed.

## Batch 56 — noise, fBm and characters in wasm (8.12)

- **Runtime:** `noise`/`fbm` ported with the C runtime's hash table, gradient table, fade curve and 0.7 scale, including the coordinate-range check that writes `Anvil noise coordinate range error` and traps. `ord`/`chr` match the C semantics: `ord("")` is 0, `chr(0)` is empty text, and an out-of-range `chr` writes `Anvil chr out of range` and stops with a non-zero exit.
- **Hosts:** both hosts now route `write(2, ...)` to stderr (the generated C already used fd 2), so the C and wasm failure paths report through the same channel.
- **Tests:** `tests/test_wasm.py` compares a 13-line noise/fBm/ord/chr program across C and wasm byte for byte (including negative and fractional coordinates) and asserts the `chr(300)` failure message, empty stdout and non-zero exit. 19 passed.

## Batch 57 — input-latency capture (8.15)

- **Tool:** `tools/bench_input.py` builds a program that prints `time()` once for clock calibration and again whenever `pressed(A)` fires, finds the window by process id, posts `WM_KEYDOWN`/`WM_KEYUP` through `PostMessageW`, and reports p50/p95/worst over N presses and R runs. The program clock is calibrated against the harness before any sleep, which matters: reading the calibration line after a delay charged the wait to every sample and produced 328 ms "latency".
- **Measured:** p50 25.5-29.4 ms, p95 43.3-51.6 ms, worst 51.6 ms over 20 presses x 3 runs on this machine. That is between one and two 60 Hz frames, which matches the loop's structure (message pump, then fixed-step accumulator).
- **Negative result kept honest:** replacing the frame `Sleep` with `MsgWaitForMultipleObjectsEx` so the loop wakes on input was measured A/B and was *worse* (p50 28.4 vs 25.5, p95 53.4 vs 43.3), so the runtime change was reverted rather than shipped on intuition.
- **Tests:** `tests/test_input_latency.py` measures 8 presses, checks the report shape and ordering, and enforces `tools/input_budgets.json` through `--check`. 3 passed.

## Batch 58 — resource accounting builtins (8.15)

- **Builtins:** `memory_images()`, `memory_audio()`, `memory_video()` and `memory_total()` report the bytes held by each class. Images use the runtime's existing 128 MiB budget counter and fall as images are destroyed; audio uses the existing 48 MiB decoded counter; video is the fixed 960x600x4 backbuffer (2,304,000 bytes).
- **Why:** 8.15 asked for allocation and VRAM capture, and the runtime already tracked these numbers internally for its budgets but never exposed them, so a game or a benchmark could not see them.
- **Tests:** `tests/test_memory_builtins.py` loads an 8x8 and a 4x4 BMP and a 100-frame 8 kHz WAV, then asserts the exact sequence 0, 256, 320, 1, 64, 1, 0 for images, 2,304,000 for video, and 2,400 bytes for the decoded mono-to-48k-stereo sound, back to 0 after destroy.
- **Wiring:** builtin arity and C names, the usage list, the TextMate grammar and the editor validator all know the four names; `npm test --prefix vscode-extension` passes.

## Batch 59 — baked sprites in wasm (8.12)

- **Why bake:** the browser cannot read a file synchronously, and `image_load` in the C runtime is synchronous. The wasm backend now decodes every literal `image_load("...")` BMP while compiling (24/32-bit, 8,192 px per side, 4 MiB total) and emits it as a C array plus a registration table; the runtime looks the path up in that table.
- **Runtime:** 32 image slots with generational handles, `image_width/height/destroy/error`, and drawing forwarded to a host `image_draw` import with destination rectangle, angle, tint and flip. A computed path cannot be baked and returns 0 with an `image_error()` that says so; a missing literal file is a located build error.
- **Hosts:** the page converts ARGB pixels once per image into an offscreen canvas with tint applied and draws scaled/flipped/rotated with smoothing disabled; the Node host records the draw plus an FNV checksum of the pixels.
- **Verified:** a 2x2 BMP (red/green/blue/white) scaled to 200x200 and drawn 1:1 was sampled in Chromium — quadrants read (253,1,1), (1,255,1), (1,1,255), (255,255,255) and the 1:1 pixels read exactly red and green. `tests/test_wasm.py` asserts the recorded draw geometry, tint/flip fields, the exact pixel checksum, the missing-file build error and the computed-path runtime message. 22 passed.

## Batch 60 — atlas regions and 8-bit BMPs in wasm (8.12)

- **Runtime:** `image_draw_region` forwards a source cell to a host `image_region` import; the rectangle must lie fully inside the image or the call returns 0 and draws nothing, matching the C runtime. The baker now also decodes 8-bit palette BMPs (palette at 14+header size, `colorsUsed` or 256 entries, top-down and bottom-up).
- **Hosts:** the page's tint conversion moved into a cached `tintedSurface(pointer,w,h,r,g,b)` keyed by pointer and tint, shared by `image_draw` and `image_region`; regions draw with `drawImage(source, sx,sy,sw,sh, dx,dy,dw,dh)` inside the flip transform. The Node host records region geometry and the pixel checksum.
- **Verified:** in Chromium, cell (0,0) of a 2x2 quad drew red at its destination, cell (1,0) drew green, an out-of-bounds cell drew nothing, and an 8-bit palette BMP drew exactly (200,100,50). `tests/test_wasm.py` asserts the recorded region rectangles, that the invalid cell produces no op, the palette image's checksum, and the existing sprite cases. 23 passed.

## Batch 61 — Web Audio in wasm (8.12)

- **Bake:** literal `sound_load("...")` WAVs are decoded at build time (PCM mono/stereo, 8/16-bit, 8,000-192,000 Hz, 8 MiB budget) and emitted as int16 samples at their original rate; the page builds an `AudioBuffer` at that rate and lets the browser resample instead of converting twice.
- **Runtime:** 16 generational sound slots, `sound_load`/`sound_error`/`sound_play`/`sound_stop`/`sound_stop_all`/`sound_volume`/`sound_active`/`sound_destroy`, with host imports for the playback verbs. Pan, pitch, loop, groups and streaming music are not implemented in wasm yet.
- **Gestures:** browsers suspend audio until a user gesture; the page resumes the context on `keydown`/`pointerdown`, and `window.anvilAudio()` exposes `{active, voices, state, sampleRate}`.
- **Verified:** the Node host records each play with frames, channels, rate, volume and peak sample (800 frames, mono, 8 kHz, peak 12000). In Chromium the context stayed `suspended` before a trusted click and moved to `running` after one, with the voice ending cleanly. `tests/test_wasm.py` asserts the recorded play, volume and stop ops, the exact stdout sequence, a located missing-file error and a compressed-WAV refusal. 26 passed.

## Batch 62 — wasm audio: loop, pan, pitch, duration (8.12)

- **API:** `sound_play_loop`, `sound_pan`, `sound_pitch` and `sound_duration` join the wasm audio set. Pan clamps to -1..1 and pitch to 0.25-4 with the same return-the-applied-value contract as the C runtime; duration is `frames / rate` from the baked source.
- **Hosts:** the page routes each voice through a gain node and a stereo panner, sets `source.loop` for looping plays, and applies pan/pitch to the live nodes; the Node host records the loop flag and the pan/pitch calls.
- **Verified:** a program reports duration 0.1 s, loop voice 1, pan(`2`)->1, pitch(`9`)->4, pan(-0.5), pitch(0.5) and stop; the Node recorder matches those ops. In Chromium a looping 0.1 s tone stayed active at 0.5 s and 2.0 s with the context `running`, so it really loops rather than holding a finished source. `tests/test_wasm.py` asserts both; 27 passed.

## Batch 63 — wasm mixer groups (8.12)

- **API:** `sound_group`, `sound_group_volume`, `sound_group_mute`, `sound_group_gain` and `sound_group_stop` now exist in the wasm target with the C runtime's contract: groups 1-3 plus master 0, gain clamped 0-1, mute separate from volume, `group_gain` reads 0 while muted, and `group_stop(0)` stops everything while `group_stop(1..3)` returns how many voices it stopped.
- **Hosts:** the page builds four gain nodes lazily (each group into the master, master into the destination) and initialises them from the stored volumes and mute flags, because a program can set a group volume before any audio context exists; the first `sound_play` used to lose it. The Node host tracks each voice's group and answers `group_stop` with the count.
- **Verified:** a program reports group 2, an invalid group 9 -> 0, master volume 0.5, mute -> gain 0, unmute -> gain 1, two plays in group 2 and `group_stop(2)` -> 2 with `sound_active()` 0; the recorder shows both plays carrying group 2. In Chromium `window.anvilAudio().groups` reported `[1, 1, 0.25, 1]` after setting group 2 to 0.25 before playback, which is the bug this batch fixed. 28 wasm tests passed.

## Batch 64 — 3D scenes in wasm (8.12)

- **Runtime:** `scene 3d`, `camera perspective`, `camera fov`, `camera_angle` and `display cube/plane/sphere` now work in the wasm target. Points are rotated, translated, transformed with the C runtime's camera basis (yaw/pitch, right/up/forward) and projected with the same 480/324 centre and focal formula, so a camera that frames a scene on the desktop frames it the same way in the browser.
- **Shading:** each face's normal is dotted with a fixed directional light and scaled into 0.45-1.0 brightness, which is why the cube's top and front read differently instead of flattening into one silhouette.
- **Host:** triangles are collected per frame and painted far-to-near on the 2D canvas at `present()`; the Node host records a summary (count and bounding box). Two bugs were fixed getting here: the `image_region` import attribute was left above the new `triangle` declaration, so triangle calls were routed into the image reader (a `Uint32Array` offset crash), and the C signatures needed the trailing alpha argument the generator emits.
- **Verified:** a cube-plus-plane scene emits 14 triangles with a bounding box wider than the canvas (the 14-unit floor at 5 units away), a sphere emits 320 (10 rings x 16 segments x 2). Chromium renders the blue cube on the grey floor with visibly different face shades; sampled pixels showed (61,114,177) on the cube and (29,41,56) on the floor. `tests/test_wasm.py` asserts both summaries; 30 passed.

## Batch 65 — baked glTF models in wasm (8.12)

- **Runtime:** `model_draw` and the mesh counters now exist in the wasm target. The compiler already bakes glTF triangles into the module for the C backend (12 doubles per triangle: three positions plus RGB), so the runtime only has to scale, rotate, translate, compute a face normal, flat-shade and submit each triangle through the 3D path built in Batch 64. `mesh_drawn()` reports the triangles submitted in the frame; `mesh_culled()` is 0 and `mesh_culling(on)` only echoes, because there is no bounding-sphere test yet, and the docs say so.
- **Verified:** a 2x2 glTF quad at distance 6 emits exactly 2 triangles spanning 393-567 x 237-411, which is the projection of a 2-unit quad at focal 520; translating it to x = -2 shifts the bounding box left. In Chromium the quad renders shaded (177, 0, 0) against the (10, 12, 18) clear colour, with the diagonal seam between its two triangles visible in the screenshot. `tests/test_wasm.py` asserts both triangle summaries; 32 passed.

## Batch 66 — wasm shadows and model culling (8.12)

- **Shadows:** `shadow(on)`, `shadow_height(y)` and `shadow_alpha(a)` now work in the 3D path. A cube contributes one shadow quad (its bottom face) and a model contributes its triangles, all flattened onto the ground plane in black at that alpha.
- **Layering:** the first version made the shadow invisible because the host's painter sort ordered by depth only, and the big floor triangles averaged nearer than the shadow and painted over it. Triangles now carry a layer (0 geometry, 1 shadow) and sort by layer first, so shadows always land on top of the floor — and never on top of the cube, because the layer split is explicit rather than a depth bias.
- **Culling:** `model_draw` skips a model whose bounding sphere is entirely behind the near plane or outside the screen, and `mesh_culled()` reports it; `mesh_culling(on)` toggles it.
- **Two geometry bugs found by looking at pixels:** the shadow used a *side* face of the cube rather than the bottom face, so all three vertices shared a z and projected to a line (a single faint pixel row); and with a level camera a ground plane is edge-on, which made early checks look broken until the camera was pitched down with `camera_angle(0,-22)`.
- **Verified:** a cube with a 300 alpha request clamps to 255 and submits 14 triangles (12 cube + 2 shadow); a model with shadows submits 4 (2 + 2); a model at x = 40 reports `mesh_culled()` 1 and submits nothing. In Chromium the pitched-down scene shows the dark shadow quad on the floor beside the floating cube. `tests/test_wasm.py` asserts all three; 35 passed.

## Batch 67 — music in wasm (8.12)

- **Why baked:** the desktop `music_load` streams from disk, but a browser cannot read a file synchronously and the music API is synchronous. The wasm build decodes the one literal `music_load("...")` track at compile time (PCM mono/stereo, 8/16-bit, 8,000-192,000 Hz, 16 MiB budget) and bakes it into the module. This is honest par with the API, not with the streaming behaviour, and the docs say so.
- **Runtime:** `music_load`, `music_play`, `music_play_loop`, `music_stop`, `music_playing`, `music_volume`, `music_position`, `music_length` and `music_error`. Position comes from the host audio clock and wraps on a looping track; a computed path reports the bake limit through `music_error()`.
- **Hosts:** the page plays the track through an `AudioBufferSourceNode` into a gain node feeding mixer group 1, so `sound_group_volume(1, ...)` affects music too. `window.anvilAudio().music` exposes playing/position. The Node host records the music ops.
- **Verified:** a 0.2-second track reports `1, 0.2, 1, 1, 0.5, 0` for load/length/play/playing/volume/position, and the recorder shows `["music_play", 1600, 1, 8000, 1, 1]`. In Chromium the music reports playing with the position advancing (0.42 s then 0.92 s) once the context is unlocked by a click. `tests/test_wasm.py` also covers a missing file and a computed path; 38 passed.

## Batch 68 — wasm source-mapped traps (8.12)

- **Why:** a wasm trap surfaces as `RuntimeError: unreachable` plus `wasm-function[17]`, which tells a beginner nothing. The compiler now writes `program.map.json` beside the module and embeds the same table in the host page, mapping each generated function (`anvil_update`) to its Anvil name and declaration line.
- **Hosts:** both the page and the Node host walk the JS stack, pick the first frame the map knows, and report `Anvil runtime error in fn(update) at line 4: RuntimeError: unreachable`. Runtime-helper frames fall through to the raw stack.
- **Honest limit:** this is function-level. It says which function trapped and where that function starts, not the exact statement — the generated C has no per-statement debug info yet.
- **Verified:** a program that calls `chr(300)` from `fn(update)` produces the map entries `anvil_update -> {update, 4}` and `anvil_draw -> {draw, 10}`, and running it under Node exits non-zero with both the `Anvil chr out of range` message and the mapped location. In the page, `describeError` maps a synthetic `anvil_update` frame to "fn(update) at line 4" and leaves an unmapped `anvil_text_chr` frame alone. `tests/test_wasm.py` asserts the map file, the page contents and the Node message; 39 passed.

## Batch 69 — capability matrix covers wasm (8.16)

- **Tool:** `tools/capability_matrix.py` now builds and runs every case on the wasm backend as well, adding a third column and a summary that counts all-three, C+native and C+wasm coverage. Build rejections report the first real compiler error line rather than the "wasm build failed:" header.
- **Two real gaps found by measuring:** `lists` failed to link because `anvil_list_get` existed in the C runtime but not in the wasm shim, and `math-builtins` failed because `min`/`max` lower to `fmin`/`fmax` libcalls and the shim had no declarations. Both are fixed; the list error message reproduces the C runtime's `path:line: list index N is outside 0..M` text.
- **Result:** 12 of 14 cases now run on all three backends; 13 of 14 run on C and wasm, with only `physics-body` refused in wasm (physics is not part of the browser subset). `image-load` runs in wasm thanks to the baked-image support, while native still refuses it.

## Batch 70 — asset memory scene (8.15)

- **Tool:** `tools/bench_memory.py` gained an `assets` scene: eight generated 64x64 BMPs and two 0.25 s 8 kHz WAVs are loaded, the program prints `memory_images()`, `memory_audio()` and `memory_video()`, waits 0.3 s so the sampler sees the peak, destroys one image and one sound and prints both counters again.
- **Measured:** images 131,072 B (8 x 64 x 64 x 4), audio 576,000 B (two mono 8 kHz clips resampled to 48 kHz stereo), video 2,304,000 B; runtime peak 5.2 MB with the assets live, against 1.9 MB without the wait — the wait is what makes the peak visible, which is worth knowing when reading the number.
- **Budgets:** `tools/mem_budgets.json` now records exact byte budgets for the asset counters alongside the per-scene RSS budgets, and `--check` fails if a load leaks or a size changes.
- **Tests:** `tests/test_memory_budget.py` asserts the exact image and video bytes, a positive audio count, and that destroying one image and one sound reduces each counter. 4 passed.

## Batch 71 — 2D physics in wasm (8.12)

- **Port, not reimplementation:** the wasm runtime now carries the C runtime's 2D solver — circle and axis-aligned box bodies, the same contact tests, four solver iterations, -9.81 default gravity, restitution/friction bounds, the same generational handle encoding and the same 1,000,000-unit coordinate and speed clamps. Reimplementing it would have meant two solvers drifting apart.
- **Shim additions:** `isfinite` (bit-free comparison form) and `hypot` (sqrt of the sum of squares) were the only missing pieces; `uint64_t`/`uint32_t` uses became plain unsigned types and `UINT32_MAX` a literal.
- **Verified:** a circle dropped from y = 10 onto a static box at 180 fixed steps comes to rest at y = 1.000 with vy = 0 and 99 contact reports on both backends, byte for byte. The capability matrix now reports all 14 cases running on C and wasm (12 on all three, because native still refuses `image-load` and `physics-body`). `tests/test_wasm.py` asserts the parity program against the C build; 40 passed.

## Batch 72 — WebGL depth buffer in the wasm 3D path (8.12)

- **Renderer:** 3D triangles are now drawn with WebGL into an offscreen 960x600 canvas and blitted onto the visible canvas at `present()`. The shader maps camera depth onto clip-space z and a real depth buffer resolves every pixel, so submission order stops mattering and intersecting geometry is correct instead of approximated by a sort.
- **Scene handshake:** the runtime now calls a `scene_mode` host import when `anvil_set_scene3d` runs, so the page knows whether to use the depth renderer or the 2D path. Shadows (layer 1) draw after geometry with the depth test disabled so they stay on top of the floor without covering the object.
- **Fallbacks:** the Node host has no WebGL and keeps the painter path, and a page opened with `?painter=1` forces it. `?nosort=1` skips the far-to-near sort, which is how the depth test was demonstrated.
- **Bug found while verifying:** the first projection inverted z (nearer mapped to the far plane), so the depth test kept the *farther* cube. After flipping `z = depth/500*2 - 1`, a near-red/far-green pair reads red in WebGL, green with an unsorted painter and red with a sorted painter — exactly the expected three-way result, sampled in Chromium.
- **Tests:** a scene-mode handshake test asserts the page carries the renderer and the Node recorder shows `["scene_mode", 1]`; the 2D canvas test filters that hint out. 41 wasm tests passed.

## Batch 73 — resource lifetime stress (8.15)

- **Test:** `tests/test_resource_stress.py` runs the same program on C and wasm: 200 cycles of image load/destroy and sound load/destroy, 300 body create/destroy, 100 particle emits, then 100 save/delete cycles. It asserts the peak image bytes are exactly one image (256 B), that image and audio counters return to 0, that physics capacity and particle counts behave, and that the deleted save no longer exists.
- **Three wasm bugs found by running it:** the memory builtins (`memory_images`, `memory_audio`, `memory_video`, `memory_total`) did not exist in the wasm backend at all; `particle_clear` and the whole particle API were missing; and `sound_destroy` never subtracted its bytes, so `memory_audio` climbed by 1,600 B per load (a real leak in the accounting, exactly the class of bug the test exists for).
- **Fixes:** the wasm runtime now accounts image bytes per slot, counts audio in the same 48 kHz stereo 16-bit units the C runtime reports (9,600 B for the 0.05 s probe clip on both backends), implements the 4,096-particle pool with emit/count/clear/gravity and fading squares drawn after the program pass, and exposes the four memory counters.
- **Verified:** C and wasm now print identical sequences for the load/destroy probe; the stress test passes on both. The wasm handle numbers differ from C (stride-based) but handles are opaque, so the test does not compare them.

## Batch 74 — indexed BMPs and image_pixel (8.12)

- **4-bit and 8-bit BMPs** now load on both backends. The C loader accepts `BI_RGB` at 4/8 bpp, reads the palette (clamped to the bit depth, rejecting palettes that overlap the pixel data) and unpacks nibble or byte indices with rows padded to 4 bytes; the wasm baker does the same so a palette sprite looks identical in the browser.
- **New builtin `image_pixel(handle, x, y)`** returns the `0xAARRGGBB` colour or 0 outside the image. It exists because indexed-BMP correctness is otherwise only testable through a window; it is also useful for hit-testing and palette checks. It needed a prototype in `anvil_runtime.h` — without one the generated C took the return as `int`, which silently turned 0xFF0000FF into -16776961 and made the out-of-bounds read garbage.
- **Tests:** `tests/test_bmp_palette.py` writes a 2x2 4-bit BMP (four-colour palette) and an 8-bit BMP (three colours), loads both, and asserts every pixel plus the `image_width`/`image_height`/out-of-bounds values on C and wasm. The first run "failed" only because the test's own colour constants were mislabelled and it assumed top-down rows; the loader was right, and both backends now agree byte for byte.

## Batch 75 — visual smoke run (8.15)

- **Tool:** `tools/visual_smoke.py` builds and runs the visual examples (sprite transforms, particles, physics boxes, first world), captures each 960x600 client area through the existing Win32 grabber, writes a PNG into `docs/screenshots/`, and reports distinct colours and the fraction of pixels that differ from the dominant background. `--check` compares those numbers with `tools/visual_budgets.json` and exits 1 on a blank or regressed frame; `--write-budgets` re-baselines.
- **What it caught immediately:** the sprite demo's headline "large copy rotates" was drawn at scale 0.5 on a 32x32 asset — a 16-pixel speck in a 960x600 window. Nothing failed; nobody had looked. It is now scale 6 and fills the frame.
- **Second finding:** the examples load assets through repository-root-relative paths, so `--run` from anywhere else silently draws nothing (image_load returns 0). The tool runs from the root and the checklist records the caveat; an asset-root fallback is the general fix.
- **Human part stays human:** `docs/VISUAL_CHECKLIST.md` lists what to look at per shot — text crispness, sprite rotation edges, resting contact, sphere shading — because a colour count cannot judge those.
- **Test:** `tests/test_visual_smoke.py` runs the tool on one example and asserts the PNG header says 960x600 and the frame is not blank.

## Batch 76 — textured cubes (8.13)

- **Feature:** `display cube(x, y, z, size) -texture(handle)` maps a loaded BMP across every face with 0..1 coordinates per face. The modifier parses like `-rotate`/`-l`, the generated C brackets the draw with `anvil_texture(handle)` / `anvil_texture(0)`, and the runtime samples in the existing barycentric rasteriser so the depth buffer, near-plane clipping and lighting path are unchanged.
- **Two bugs on the way:** the texture modifier was matched inside string literals, so `display text("... -texture(handle)")` tried to evaluate `handle` — fixed by masking quoted text before scanning modifiers; and the sampler's first version interpolated UVs linearly, which compressed the checker towards the horizon on angled faces, so it now interpolates u/z and 1/z and divides (perspective-correct).
- **Verification:** `tests/test_texture3d.py` draws a 4x4 four-colour BMP on a cube, captures the window and classifies each quadrant by dominant channel, and asserts the wasm backend refuses `-texture` with a line-numbered message rather than linking an undefined symbol. 2 passed.
- **Known limit:** nearest-neighbour sampling with no mip chain, so a fine checker seen edge-on moirés. Written down in `docs/LANGUAGE.md` instead of pretending otherwise.
- **Demo:** `examples/textured_cube.ANVL` plus `examples/assets/checker.bmp`, added to the visual smoke cases.

Animated scenes made the visual gate flaky at exact budgets (particles 22.8% against a 22.9% baseline), so the gate now allows 15% drift below the recorded baseline.


## Batch 77 — window presentation and flicker (user report)

- **Report:** "there is a flickering issue that is not as properly fixed". The earlier QA #57 flicker fix only handled `WM_ERASEBKGND`; the frame still went out through `InvalidateRect` + `UpdateWindow`, so every frame re-entered `WM_PAINT`, filled the window DC black and then re-scaled the image into it.
- **Fix, in three parts:** the paint handler now composes into a cached memory DC and blits once (`BitBlt`) instead of painting the window directly; the frame loop presents straight to the window DC with `anvil_present_window()` instead of forcing a repaint per frame, leaving `WM_PAINT` for occlusion and resize; and `DwmFlush()` at the top of the frame paces the loop to the compositor so a blit cannot land mid-composition and tear a moving scene. The flush sits before the phase timers so `frame_present()` still reports blit cost, not the wait.
- **Measured:** 40 resize cycles sampling the client centre found 0 frames with any black in both the old and the new build — the capture path cannot see the transient, so the flicker evidence is the code path (a full-window black fill on the window DC every frame) rather than a reproduced frame. Said plainly because a test that cannot fail is not evidence.
- **Tests:** `tests/test_flicker.py` asserts a static full-window rectangle covers over 90% of every sampled frame with under 2% black; runtime budgets still pass with the compositor pacing.

## Batch 78 — buffer(on) toggle

- **Builtin:** `buffer(on)` switches the window's double buffer and returns the previous state, so `say buffer(0)` reports `1` the first time. It starts on. `buffer(0)` presents straight to the window DC; `buffer(1)` composes in the cached memory DC and blits once.
- **Why a toggle rather than always-on:** the flag makes the difference visible and measurable (and lets a machine with an expensive copy turn it off), and it gives the flicker fix a name a program can control instead of hidden behaviour.
- **Wasm:** the call is accepted and only records the preference, because the browser composites the canvas for us.
- **Tests:** `tests/test_buffer_toggle.py` reads the previous-state values back from the save store (`1, 1, 0, 0` for on/off/off/on), captures the window with buffering on and off, and asserts the full-window rectangle is still drawn. Grammar and language docs updated; 876 passed, 1 xfailed.

## Batch 79 — true double buffering

- **Change:** the window now owns two DIB framebuffers. The program draws into the back one while the front one is displayed; `anvil_present_window` publishes the finished frame and swaps, then re-selects the new back buffer into the memory DC so GDI text lands in the right surface. `buffer(0)` keeps single-buffer drawing, and `WM_PAINT` paints from `anvil_display_pixels`, never from a buffer that is being drawn.
- **Why it matters:** the earlier version composed one buffer and copied it to the screen. That removed the black flash, but the displayed pixels were still the same memory the next frame was about to overwrite. With two buffers the visible image is immutable until the swap, which is the definition the user asked for: the buffer holds the next frame, so nothing is ever seen half-drawn.
- **Verified:** the sprite demo shows text, both sprites and the rotated copy with no stale or missing regions; two captures 350 ms apart differ in 3,924 pixels, so the swap is live rather than a frozen first frame. `tests/test_flicker.py`, `test_buffer_toggle.py` and `test_sprite_batch.py` pass (5 tests).

## Batch 80 — text wrapping and measurement (8.14)

- **`display text("...") -l(x, y) -wrap(width)`** breaks a caption at measured word boundaries: lines are filled with whole words while `GetTextExtentPoint32A` says the line fits, then advanced by 1.35x the glyph height. A single word wider than the limit is drawn anyway instead of vanishing, and a non-positive or non-finite width falls back to an unwrapped draw.
- **`text_width("...")`** returns the pixel width of a string in the current font, so a panel or underline can be sized to the text instead of guessed. Both share the font helper the renderer already used, so measurement and drawing cannot drift apart.
- **Bug on the way:** the first refactor cut the body off `anvil_text` while extracting the font helper — the LSP caught `undeclared identifier 'height'` immediately, which is exactly the kind of edit a compile-only check would have caught later and with a worse message.
- **Tests:** `tests/test_text_wrap.py` renders a 62-character caption at `-wrap(300)`, counts ink in the first two line bands (both must contain text), reads `text_width` back from the save store and asserts a plausible 380-620 px range, and checks the wasm refusal. `examples/text_wrap_demo.ANVL` shows the panel fit and a half-width bar.

## Batch 81 — per-allocation load sites and `memory_report()` (8.15)

- **Builtin:** `memory_report()` prints every live image and sound as one row — index, `WxH` or frame count, bytes, the Anvil `file:line` that allocated it, and the asset path — then a `live allocations: N (X image bytes, Y audio bytes)` total. It returns the live count so a program can log a warning above a threshold instead of only reading a byte total.
- **How the site is captured:** `image_load()` and `sound_load()` carry the source location as extra C arguments (`anvil_image_load_site(path, "file", line)`); the compiler rewrites the call when the builtin is parsed, so no runtime stack walk is needed and no debug symbols are required in a release build. The C runtime keeps a site per image slot and per sound slot and clears it when the resource is destroyed.
- **Wasm:** the browser bakes literal loads at compile time and has no call site to name, so the shim defines the `_site` wrappers as pass-throughs (the shared C generator emits the same call) and the compiler refuses `memory_report()` with a located message.
- **A real wasm bug found on the way:** the wasm shim never defined `anvil_str_from_number`, so any program that joined a number to text (`"w " & image_width(h)`) failed to compile on wasm with `call to undeclared function`. Implemented beside `anvil_str_cat`, matching the C runtime's formatting.
- **Tests:** `tests/test_memory_report.py` builds a headless `fn(main)` program, asserts the image row names `report.ANVL:3`, the sound row `report.ANVL:4`, the exact 256/2400-byte counts, the `live allocations: 2` total and the drop to 1 after `image_destroy`, and checks the wasm refusal. Grammar and language spec updated; VS Code validation passes.

## Batch 82 — tilemaps (8.14)

- **Builtins:** `tilemap_new(image, tile_w, tile_h, columns, rows)` returns a generational handle for a grid of cells that name tiles in a tileset image; `tilemap_free`, `tilemap_columns`, `tilemap_rows`, `tilemap_tiles`, `tilemap_set`, `tilemap_get`, `tilemap_fill`, `tilemap_area`, `tilemap_draw` and `tilemap_error` complete the set. Tile `t` maps to `(t % tiles_per_row, t / tiles_per_row)` in the sheet, and tile `-1` is empty so a cell can be cleared without a placeholder tile.
- **Bounds:** 16 live maps, 1..128 cells per side, tile size a whole number of pixels no larger than the sheet. Cells are `malloc`ed per map, so an unused slot costs nothing, and the map handle is generation-encoded so a stale handle after `tilemap_free` is rejected.
- **Drawing:** every non-empty cell is drawn through the atlas-region path, so tint, flip, the 2D camera and sprite batching all apply; cells that cannot touch the framebuffer after the camera are skipped before any pixel work. A valid call returns 1 even when every cell is empty or off-screen, matching `image_draw`.
- **Wasm:** the whole family is refused with a line-numbered "not available" message.
- **Verification:** `tests/test_tilemap.py` covers the headless API (counts, fill/area clipping, set/get bounds, `-1` clears, stale handles, invalid tiles, invalid sizes) and a pixel test that draws a 3x2 map at 4x, captures the frame with `frame_capture()` and reads the four cell colours, the fill colour, both sides of a cell boundary and a pixel outside the grid. `examples/tilemap_demo.ANVL` paints a 20x12 island and is now a visual-smoke case with a recorded baseline (45 colours, 52.1% content).

## Batch 83 — tilemap collision (8.14)

- **Builtins:** `tilemap_solid(map, tile, on)` marks a tile index solid and `tilemap_is_solid(map, tile)` reads it back; `tilemap_cell(map, x, y, scale)` returns the tile under a world point; `tilemap_collide(map, x, y, w, h, scale)` tests a world rectangle against solid cells.
- **Storage:** the solid flags are a bitset over tile indices, allocated the first time a map marks one, so maps that never collide cost nothing; it is freed with the map. The empty tile `-1` and indices outside the sheet are rejected, and a sheet with over 1,000,000 tiles refuses solid markup rather than allocating an unbounded table.
- **Placement contract:** collision uses the same rule as `tilemap_draw(map, 0, 0, scale)` — cells are `tile_w*scale` wide with the map anchored at the origin — so the world coordinates a game passes to drawing are the ones it passes to collision. A rectangle that lands entirely outside the grid returns 0, and a zero-size rectangle or zero scale returns 0.
- **Tests:** `tests/test_tilemap.py` gains a headless collision program asserting the exact 24-value sequence: marking, clearing, rejecting `-1` and out-of-sheet tiles, cell lookups on and off the grid, a hit, two misses, a zero-size rectangle, a zero scale, and a stale handle after `tilemap_free`. A second test checks the wasm refusal names `tilemap_collide` on line 3.

## Batch 84 — animated tiles (8.14)

- **Builtins:** `tilemap_animate(map, tile, frames, fps)` makes a tile cycle through `frames` consecutive indices at `fps` frames per second; `tilemap_frame(map, tile)` reports the index currently drawn. `frames` must fit the tile's row of the sheet (1 disables), `fps` must be positive and finite, and the empty tile or an out-of-sheet index is rejected.
- **Row wrapping:** frames advance left to right inside the base tile's row and wrap at the row end, so an animation can never bleed into the row below — a 4-wide sheet animating its last tile shows tile `base-3`, not a tile from the next row.
- **Render-time substitution:** the cell keeps its base tile, so `tilemap_get`, `tilemap_cell`, solid flags and `tilemap_collide` all keep answering with the base. That keeps collision stable while the art moves, which is the property a platformer needs. The frame tables are allocated on first use and freed with the map, like the solid bitset.
- **Demo:** the tileset gained a fifth row holding two adjacent water frames (tiles 16 and 17); `examples/tilemap_demo.ANVL` fills with tile 16 and animates it at 0.8 fps. The captured frame was inspected by eye and the visual baseline moved to 48 colours / 59.2% content (three consecutive captures agreed exactly, because the 1 s settle always lands in frame 0).
- **Tests:** `tests/test_tilemap.py` adds a headless bounds/disabling/`tilemap_frame` sequence and a pixel test that draws a 1x1 map whose tile animates white→red once per second, samples frame 5 (white, base tile) and frame 75 (red, wrapped frame) so the drawn tile provably follows the clock.

## Batch 85 — parallax layers (8.14)

- **Builtin:** `parallax(factor)` scales how much of the 2D camera pan the following draws follow: 1 is the world layer, 0.35 scrolls a backdrop slower, 0 pins a layer (HUD, caption, sky) to the screen. It clamps to 0–4, leaves the value alone for a non-finite argument, and returns the previous factor so a draw can restore what it found. Zoom and the mouse mapping are unaffected.
- **Implementation:** the factor multiplies the camera pan inside `anvil_camera2d_point`, the single helper every 2D draw path already used, so rects, circles, lines, text, sprites, particles and tilemaps all honour it without touching each path.
- **A demo bug the feature exposed:** with the camera panning, the full-window clear and the caption were drawn at factor 1 and slid left, leaving an uncovered strip on the right and a clipped caption. Both are now drawn at factor 0, which is the correct HUD behaviour and also the cleanest way to show what factor 0 means.
- **Tests:** `tests/test_parallax.py` asserts the clamp/previous-value sequence (`1, 0.5, 4, 4, 0`) and pans the camera 100 px with two identical rectangles at factors 1 and 0.5, reading the captured frame to prove the world layer lands at x=0, the half-speed layer at x=50 and nothing is drawn beyond. `examples/parallax_demo.ANVL` scrolls a 64x12 animated sea at 0.35 behind a 16x10 island at 1.0; its captured frame was inspected by eye and the visual baseline is 42 colours / 59.1% content.

## Batch 86 — larger tile worlds with viewport-scaled drawing (8.14)

- **Limit raised:** a tilemap may now be up to 512x512 cells per side (was 128x128), so a 512-cell world with 16 px tiles spans 8,192 pixels. Cells are still allocated per map, so a map costs 1 MiB at the new maximum and nothing when unused.
- **Draw cost now follows the viewport, not the map:** `tilemap_draw` derives the visible cell range from the camera pan (scaled by the parallax factor), the zoom and the placement, clamps it to the grid in the double domain before casting (a wild pan cannot overflow `int`), and walks only those cells. The per-cell camera transform and cull test are gone.
- **Measured:** a new `tilemap_large` runtime scene builds a 512x512 map with a 4x4 patch at the origin and a 40x40 patch off-screen and draws it once per frame. Walking every cell cost 0.38 ms p50 / 0.38 ms p95 of scene work; the visible-range walk costs 0.12 ms p50 / 0.12 ms p95 on the same build, a 3.2x reduction that no longer grows with the map. The scene is recorded in `tools/bench_budgets.json` (measured 0.12 ms, budget floor 0.5 ms p50 / 2.0 ms p95).
- **Tests:** `tests/test_tilemap.py` adds a 512-accepted/513-rejected bounds test with a set/get at cell (511,511), and a pixel test that fills a 512x512 map with empty cells, places green at (0,0) and blue at (400,400), captures the near frame, pans the camera 25,600 px (8 px tiles at 8x) and captures again — the far cell only appears because the range follows the camera.
- **Also corrected:** `docs/PART8_EVIDENCE.md` still asserted "no batching" in the 8.14 row; 2D sprite batching has existed since `sprite_batch`, so the row now says 2D batching exists and 3D batching does not.
