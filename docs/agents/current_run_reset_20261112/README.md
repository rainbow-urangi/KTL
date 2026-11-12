# Current-run state reset

Status: READY FOR MANUAL VERIFICATION (not browser verified).

Only frontend presentation/state and test code changed. No evaluator, model, config, dataset, stored result or evidence modifications. Protected before/after snapshot and report attached.

Current result starts empty, takes only a successful completed POST response for the same metric, and resets across document reload, navigation and BFCache. Stored catalog results are not rendered as current results. Starting another run clears the previous current result; failures leave no score/evidence. Late replies after navigation are ignored. No local/session storage used.

M02/M03 execution was already unavailable and remains unavailable. No invented button or recomputation. All metrics share the reset behavior.

M05/M06 synthetic VM handler checks are NOT actual browser clicks or real measurements. User handles manual run/reload/leave/return verification. Existing M05 0.8235294117647058 remains stored, unchanged.

Validation: `node --check frontend/app.js`; `node tests/test_frontend.cjs`; `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_measurement_ui -v`. Targeted checks, not full Python regression (no backend/evaluator change).
