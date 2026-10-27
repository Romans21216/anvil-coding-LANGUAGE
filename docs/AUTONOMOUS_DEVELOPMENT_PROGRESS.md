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

## Batch 6 — language feature versioning (in progress)

- **Features:** Backlog item #49 adds an optional leading `language version 1` declaration. Existing unversioned files keep version 1 behavior. Malformed, repeated, late, and unsupported declarations report the source path and line.
- **Backlog:** #49 is IN PROGRESS pending independent review; only language version 1 is implemented.
- **Files:** `compiler/anvil.py`, compiler regression tests, language/compiler/wiki docs, and the compact implementation ledger.
- **Tests:** `python -m unittest discover -s tests -q` — 63 passed; `npm test --prefix vscode-extension` — passed; `python -m compileall -q compiler tests` — passed; JSON summary totals 450 items with 15 audited entries; `git diff --check` — passed.
- **Review:** The last overall review is `15439b54cd6e2b7a8165866d6054141f466f1b3e`, 90/100 below the new 98-point bar. Item #49's independent review is pending.
- **Commit/push:** Item #49 implementation is pushed in `d5191d4ba2c7744b1b6207086abf0d8e05320afc`; its full validation passes. A small state-record correction is being committed before requesting review of the exact final snapshot.
- **Next batch:** Complete review for item #49, update the evaluation, then continue addressing deductions toward 98/100.
