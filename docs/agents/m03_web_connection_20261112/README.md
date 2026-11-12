# M03 web execution connection — READY FOR MANUAL WEB VERIFICATION

## Scope
- Only M03 web transport, active catalog and M03 presentation were added.
- `backend/m03_main_web.py` reads the unchanged frozen final ten, invokes `backend.m03_integration.generate` with REAL once per BU, and calls the unchanged `evaluate_scenarios`.
- No browser clicks were performed. Actual UI acceptance remains with the user.
- No generator, MENU_ENTER rule, evaluator/schema, GT, process map, model/config, BU03 ordering or M02/M05/M06 behavior was changed.

## Request / persisted evidence
- Explicit POST `/api/evaluations/m03/run?mode=DEVELOPMENT&dataset_id=m03_final_10_frozen_20261112` runs the batch. Existing `/api/m03/generate` request/response contract remains unchanged.
- GET `/api/measurement` verifies readiness only. It never generates/evaluates. Legacy stored data are preserved, never used as the current result.
- Each explicit run has a unique immutable run directory with `result.json`, `run_manifest.json`, `evidence.csv`, `received_payload.json` (all ten generated scenarios).
- UI result, per-BU verdicts, and CSV come from the central evaluator. No frontend scoring.
- Current-run state is page-local; reload, navigation, history and BFCache reset it. The evidence link appears only after explicit successful execution.

## Actual code/API validation
- Main localhost API run: `DEV-M03-20261112T083848-c882d6a3a2d6`.
- Ten scenarios generated: 9 PASS, 1 FAIL (BU03), success rate 90%, target 80%, threshold met. `official_pass` remains null.
- All ten scenario response objects equal the corresponding frozen `m03_menu_enter_20261112/BUxx-api.json` response objects exactly.
- CSV has ten rows, nine success=True. API/CSV/disk result match. Evidence SHA-256: `4a1bc41e8b1ebe54d8cf34f01f8887472b65c3006603be3bf805e12b71782e65`.
- Full Python regression: 473 tests PASS (`regression.log`).
- Node synthetic frontend: 32 routes plus M02/M03/M05/M06 explicit execution, current-run reset, errors, duplicate guard and stale response tests PASS.
- Separate M02 delay synthetic regression PASS; M05/M06 speed unaffected.

## Freeze integrity / authorized transport exception
Historical `docs/agents/m03_development_freeze_20261112/freeze_manifest.json` is unchanged. Of 43 historical hashes, all 42 non-transport artifacts are unchanged. `backend/server.py` differs only by three M03 batch dispatch lines; its original bytes are `server_before.py.txt`. The old whole-tree verifier intentionally reports this transport difference, not a generator/config drift. `verification.json` records new transport hashes, unchanged-core count, original freeze identity, and exact reproduced results. The bridge verifies the original manifest and all 42 core artifacts before and after every run. The run manifest records the historical freeze hash plus actual current server transport hash separately; it does not falsely label the old server hash as current input.

## Source limitations retained
BU01/BU12 source completion boundaries remain ambiguous. BU03 workflow mixes BU02/BU03 events; no slicing, renaming or ordering repair occurred. These limitations remain visible on the input panel and per-run source metadata. The development PASS is not a claim of KTL official acceptance.

## User manual check
Open `http://127.0.0.1:8000/metrics/m03`: initial `미실행`, fixed ten BU list, explicit M03 execution, 90% and BU03 failure, CSV, refresh/reentry reset. The assistant has not clicked any browser button.
