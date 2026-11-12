# KTL common measurement UI

User-authorized UI/routing cleanup only. Current existing measurements retain internal provenance and mode; no official acceptance is asserted.

- Main view: `/metrics/m01` through `/metrics/m07`, no mode selection. Old query strings no longer change the displayed configuration.
- GET `/api/measurement` reads current stored metadata without Service.catalog or M02 assess.
- M02: saved exact-five recovery05 cohort, existing result/CSV bytes only. No new measurement or model verification.
- M03: saved current semantics candidate cohort result/CSV only; final ten-business-unit selection and batch run remain separate work.
- M05 and M06: buttons route to existing evaluator endpoints, unchanged.
- M01/M04/M07: no feature expansion; external result state only.
- Evidence files remain original; UI does not compute metrics or verdicts.
- M05 existing CSV recheck: TP7 FP0 FN3 TN10, Precision1 Recall0.7 F1=0.8235294117647058. No new prediction was executed.
- 1316 pre-existing backend/data/config/model/result files hashed before and after: only backend/server.py changed for read-only routing. All other protected files unchanged.
- JavaScript syntax and 32 route/legacy-query presentations plus synthetic request/error/repeated-submit checks PASS. These dispatch mock handlers only, not browser buttons.
- Full unittest suite 445 PASS.
- No browser clicks performed, per user. User retains actual UI button validation.

## Changed files
frontend/app.js, frontend/index.html, backend/measurement_ui.py, backend/server.py, tests/test_frontend.cjs, tests/test_measurement_ui.py.

## Independent verification
Separate Verification Task must inspect final hashes and tests. M02/M03 are explicitly saved-result views, not falsely enabled batch measurement buttons.
