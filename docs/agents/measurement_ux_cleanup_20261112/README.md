# Measurement UX cleanup (2026-11-12)

## Scope
- Removed stored-result notices from all metric details and overview. Stored API results, files, evidence, and histories remain unchanged.
- M02 POST runs immediately. Only successful result display waits until 30 seconds from the explicit click, measured with performance.now(). The API is never delayed.
- Spinner + disabled run button + `측정 결과 확인 중...`; no inference claim. Result/evidence appear together after the display wait.
- Failures display immediately. Navigation/pagehide/BFCache invalidates pending work and cancels the display timer. M05/M06 do not wait.
- Frontend setting: `M02_RESULT_MIN_DISPLAY_DELAY_MS = 30000` in app.js; optional numeric `window.M02_RESULT_MIN_DISPLAY_DELAY_MS` override, including 0. Invalid overrides fall back to 30000. This is a presentation setting, not model configuration.

## Verification
- `node --check frontend/app.js`: PASS
- `node tests/test_frontend.cjs`: PASS (32 initial/legacy routes, current-run reset, stored-results hidden, explicit POST, error/race)
- `node tests/test_measurement_delay.cjs`: PASS (fake monotonic clock; immediate POST, 29999/30000 ms boundary, slow API elapsed-time subtraction, duplicate prevention, immediate errors, route/BFCache/stale responses, setting override, M05/M06 zero delay)
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`: 448 PASS. Synthetic/test code/API only, no actual M02 remeasurement.
- 1349 backend/data/model/contracts/result files match pre-change SHA-256. No score calculation or stored-result/evidence changes.
- Real browser button interactions are reserved for the user and were NOT performed.
- Independent review and final manual verification remain separate.

## Manual check
M02 entry is not-run; click -> spinner/disabled button without result or CSV; after at least 30 sec result and CSV appear. Refresh/reentry returns to not-run. Stored-history notice is absent. M05/M06 run normally without the M02 display delay.
