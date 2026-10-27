# Anvil autonomous development progress

This log records verified implementation batches and is reconciled with Git before each continuation. GitHub issue [#23](https://github.com/Romans21216/anvil-coding-LANGUAGE/issues/23) remains the user-maintained master backlog and source of truth.

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


## Batch 11 — resizable game window (item #144; candidate `2962455`)

- **Scope:** The native window is already resizable, but the old paint path always drew the 960×600 frame from the top-left, leaving clipping or unused space. The runtime now computes a centered 16:10 viewport, fills letterbox bars, and scales presentation without changing the internal resolution.
- **Regression coverage:** A native C harness checks the original 960×600 size, a wide 1200×600 client (120-pixel side bars), a tall 600×800 client (212-pixel top bar), a 1280×720 client, and invalid dimensions. All 73 Python tests pass; the runtime test module passes all 3 tests.
- **Documentation:** Engine and completion-matrix docs state the distinction between resizable presentation and fixed internal framebuffer.
- **Status:** Item #144 is IN PROGRESS pending independent review; all 73 tests pass locally. Latest independent score remains 92/100 on `5072597`, below the 98-point threshold.
