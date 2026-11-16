# M02 main web execution connection

Status: Development code/API validation PASS; independent verification pending; actual browser clicks owned by user.

## Scope
Only M02 execution wiring and M02 result presentation changed. No M03 behavior or evaluator, model, GT, input dataset, serializer, matching, thresholds or formulas changed.

The POST endpoint is `/api/evaluations/m02/run?mode=DEVELOPMENT&dataset_id=m02_recovery_data_05_exact_five`.
The active catalog exposes it without running evaluation. Current-run state remains page-local; initial entry/refresh/history/reentry show unexecuted. Only successful explicit POST supplies result and CSV links.

## Existing evaluator reused
`m02_baseline_77_29_preserved/snapshot/.../web_ready/server.py::measure` is executed unchanged with snapshot imports in an isolated Python subprocess. It re-evaluates frozen process maps, not model inference. UI discloses this scope.
The snapshot omitted the historical routing-only `m02_recovery_rules_v1/manifest.json`. A hash-pinned original copy is added only to a disposable workspace containing a byte-copy of the snapshot. Snapshot/raw/baseline are not modified. The first API test failed closed on that missing manifest; no result was persisted. After minimal transport repair the API passed.

## Verified result
Accuracy 64.51612903225806%; Completeness 92.5925925925926%; Final Score 77.28981596002805%; PASS (target75%).
31 generated, 20 direct matches, 25/27 GT satisfied.
Run: DEV-M02-20261112T063000-70d56362b4e9.
Run-specific downloaded CSV exactly matches the frozen evidence bytes, SHA-256 `105f5ab3fff0f21013d9923828df4d4e2f18919ff593659a8800a2313361240d`.
CSV counts independently recalculate API metrics. Per-BU generated steps, matching evidence and missing GT are included.

## Tests and preservation
- 448 unittest regression PASS on final product code.
- Synthetic DOM 32 route/legacy-query cases and M02/M05/M06 explicit POST/reset/navigation/repeated-submit/stale-response/error handling PASS.
- Actual loopback HTTP POST and run-specific CSV/result GET PASS (no browser clicks).
- `before.json` and `protected_comparison.json` cover original artifact hashes. Existing changes are only authorized main-web files plus latest-M02 index update.
- Previous latest result is still byte-identical at `results/development/DEV-M02-20261108T104041-57f01a6e5b9d/result.json`.
- Existing raw, GT, frozen model/config, preserved baseline, M03, and previous run artifacts unchanged.

Remaining: independent verification; load updated backend for user's manual M02 browser check. No browser verification is claimed.
