# M05 category quota removal, 2026-11-11

The DEVELOPMENT contract requires exactly 20 targets: KEEP10 and REMOVE10. REMOVE category is independently justified evidence metadata from duplicate/noise/repeated_action/irrelevant_action, without a category quota or four-type coverage requirement. The score remains binary REMOVE/KEEP F1. Targets or labels must not be changed from predictions.

The validator and independent CSV checker validate category membership only. Web copy, the user20 contract and active documents are synchronized. Existing blind-label locks, raw provenance, history separation, freeze hashes, approval gate, one-shot execution, exact 20/10/10 counts, KEEP-empty category and binary scoring remain enforced.

## Verification

- M05 tests: 76 PASS, covering single-category and uneven distributions, invalid categories, independent CSV/F1 consistency and one-shot protection.
- Full Python regression: 419 PASS.
- Frontend syntax and 24 DOM checks: PASS.
- Protected files: 705 unchanged by SHA-256, including frozen engine/adapter/normalization, weights, M02 snapshots and raw01/raw02.
- All 19 expected frozen artifact/config/candidate hashes match. validate_freeze passed.
- Separate independent review remains pending. This report is not approval for a real evaluation bundle.

No real held-out raw prediction, target-label selection/lock, engine tuning or F1 measurement was performed. Temporary synthetic fixtures and fabricated test approvals were never retained as real evidence. Earlier audit records are unchanged.

verification.json records exact hashes and check results. before_integrity.json and before/ preserve the baseline. implementation.patch contains the nine-file scoped diff. Focused and full regression logs are alongside this report.
