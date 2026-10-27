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
