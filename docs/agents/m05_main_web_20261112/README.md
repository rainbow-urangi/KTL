# M05 DEVELOPMENT main-web connection

Scope: actual backend.server on loopback port 8000, existing main frontend.
- Main M05 DEVELOPMENT now calls frozen prepare / cleaning adapter / validate_response / calculate_binary; no copied cleaning or F1 formula.
- Original 417 raw, locked20, candidate freeze/config/engine and old result/attempt claim unchanged. Separate UUID reproduction archive preserves complete new input and predictions.
- POST /api/evaluations/m05/run?mode=DEVELOPMENT runs real inference, not cached result. Source of truth is central server evaluator.
- New API result: TP7 FP0 FN3 TN10 Precision1 Recall.7 F1 .8235294117647058 PASS; target20 only, full417 context.
- Original baseline active config unchanged; bridge explicitly uses existing v2 frozen config.
- UI: dataset/config/hash, execution button/time, TP/FP/FN/TN, P/R/F1, target .7900, DEVELOPMENT PASS, evidence download.
- First reproduction completed inference and save but HTTP response failed while post-save validation read CSV BOM incorrectly. Preserved all artifacts; bridge UTF-8-sig read fixed, original measurement untouched. Retry API and download passed (see api_result.json/http_csv_verification.json).
- Browser NOT VERIFIED: CUA inventory empty; Native apps Sky Computer Use service startup request failed; iab Browser is not available. No browser click claimed. HTTP+DOM checks do not substitute real click.
- Engine known has_api limitation retained, not official-ready. No additional tuning.
- Modified main web integration sources were historically covered by M02 implementation inventory; M02 model/config/serializer/evaluator unchanged. Historical manifests not rewritten; new integration hashes tracked separately.

Regression: 443 Python unit tests PASS; 24 mode/page DOM rendering checks PASS.

Independent verification follow-up: overview DEVELOPMENT cards now use each server catalog dataset instead of stale current_site_dev_01. M05 overview dataset regression added; 24 mode/page DOM checks and immutable freeze verification PASS. No measurement or browser click performed for this text correction.
