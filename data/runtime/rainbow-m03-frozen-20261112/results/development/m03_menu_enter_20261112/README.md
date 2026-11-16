# M03 MENU_ENTER minimal improvement — DEVELOPMENT

- Frozen candidate ten unchanged. First remeasurement: **9/10, 90%, target >=80 met**. No further tuning.
- BU01 and BU12 now PASS via generic MENU_ENTER -> existing NAVIGATE, with unchanged source targets and provenance. No BU/menu/GT special cases.
- BU03 remains FAIL: projected orders [1,2,7,14,16], unsupported SELECT and unresolved steps omitted without renumbering. Mixed BU02/BU03 source and BU01/BU12 ambiguous end boundaries remain limitations, not repaired evidence.
- Production edit only backend/m03_real_generator.py: normalization and generator version. Existing target, resolution, event/node evidence and order validation preserved. Three synthetic tests added; no scenario/API schema changes.
- Real HTTP /api/m03/generate invoked once per candidate using current backend.server handler on temporary 127.0.0.1 ephemeral port. All HTTP200. Server stopped after batch; existing port8000 process untouched and may require later restart to load code.
- Existing central evaluate_scenarios and csv_evidence produce result/evidence. No integration-store submission or UI result equality claim: frozen candidate cohort is not registered. UI remains unconnected as requested. No browser clicks.
- before_hashes.json / after_hashes.json protect frozen config, snapshot, candidate, schema, evaluator, routes. Failure provenance retains source event/node IDs and all omitted steps. Original baseline is untouched.
- Independent Verification and final freeze are performed separately. This document does not claim independent PASS or official KTL acceptance.

## Regression completion
- Final full backend unittest: 469 tests PASS (46.564 s). Focused real generator: 9 PASS. Frontend synthetic contract suite PASS.
- Initial four failures were two inherited old generator version/hash assertions, updated only to the new approved generator version/hash. Historical diagnostic manifest preserved. Initial/final logs retained; no score or production logic changes followed the first 90% batch.
- Tests additionally changed: tests/test_integration_sandbox.py. Unrelated pre-existing working tree changes are not part of this task.
