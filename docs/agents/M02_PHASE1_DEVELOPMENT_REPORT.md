# M02 Phase 1 DEVELOPMENT implementation report

2026-11-03 · **READY_FOR_VERIFICATION — Phase 1 incomplete / actual score NOT MEASURED**.
Independent Verification Task has not run. Neither product PASS nor official trial PASS.

## Implemented

- TD-04 DEVELOPMENT contract transcribes the supplied starred GT PDF, BU03/07/09/17/20, arrow-separated 27 required procedures; each has process/business-unit ID, business name, required ID, screen context, order, empty allowed-alias array. No invented aliases. `evaluation_contracts/development/m02_td04_v1.json` is not OFFICIAL. Status DIRECT_MAPPING_UNRESOLVED.
- Persisted v1.2.1 maps copied byte-for-byte into `data/development/current_site_unseen_validation_v1/m02_frozen_output/`. Every original model, every canonical occurrence, every unpaired map including login preamble is retained: 21 maps / 137 graph nodes / 176 canonical occurrences. No new inference or process generation. The 185 instance steps differ from 176 canonical map occurrences because the existing engine selects one medoid instance per map; this policy predates GT evaluation.
- `backend/m02_candidate.py` serializes direct typed action/page/target/method/endpoint fields into comparison keys, retaining repeats and stable occurrence IDs. Serializer accepts no GT content. Raw source evidence supports identity lookup only, never direct answer counts. TD-04 is loaded after serialization. No model module is invoked and no GT is passed to a model.
- Evaluation-only raw-save-anchor process identity: BU03→PM-020, BU07→PM-010, BU09→PM-019, BU17→PM-007, BU20→PM-002; all unpaired maps remain present. BU17 trailing PM-008 remains unpaired, not discarded. No GT similarity/best-instance selection. Each anchor is verified to have exactly one process-map owner before scoring. BU03's map contains schedule lookup as well as registration; no extraction of its favorable subsection.
- Additive `dataset_id=v1_2_1_unseen_m02_development` query selection to existing DEVELOPMENT M02 POST; no request body, arbitrary path, or command accepted. Existing requests retain behavior. Candidate unavailable/hash error cannot fall back to legacy. Existing REFERENCE/OFFICIAL behavior untouched.
- Existing M02 page offers candidate/legacy input selection, run, five-BU table, target75%, result/hash/manifest and evidence CSV download. Current candidate catalog explicitly shows the comparison blocker. No research dashboard. A future validated direct mapping contract can use existing one-to-one evaluator and generate actual per-BU/aggregate values without changing frozen model artifacts.

## Actual DEVELOPMENT outcome — no fabricated score

| BU | Generated canonical steps | Required steps | Accuracy | Completeness | Score |
|---|---:|---:|---|---|---|
| BU03 | 22 | 5 | Not measured | Not measured | Not measured |
| BU07 | 13 | 6 | Not measured | Not measured | Not measured |
| BU09 | 13 | 6 | Not measured | Not measured | Not measured |
| BU17 | 15 | 5 | Not measured | Not measured | Not measured |
| BU20 | 17 | 5 | Not measured | Not measured | Not measured |

Aggregate M02 score=null; threshold_met=null; official_pass=null. Neither ≥75% nor <75% is established. No model improvement is authorized or started. Boundary F1, 20-execution segmentation and unrelated ambiguous boundaries were not used as criteria or blockers.

Exact blocker: there is no validated direct equivalence mapping between the model's technical signatures and the source PDF's semantic procedures. For example, `selection|/mypage/work/daily|dialog_control||` cannot independently distinguish 저장, 확인 or 종료; `input|...|input_control||` cannot distinguish date/week/content. Raw input label/node evidence cannot silently supply those answers under FINAL p.7 item7. No requirement is imposed that the model itself must emit a particular `direct_label` field: typed keys are supported, but their correspondence must be defined before a numeric business-procedure score. An absent mapping is not a measured zero.

The original PDF supplies 27 steps, but does not specify semantic aliases for these technical signatures. A reviewable decision is needed on direct typed-signature equivalence and procedure granularity; do not tune labels/aliases by score. If no objective equivalence exists for a specific procedure, retain that fact rather than equating an arbitrary generic click to it. A subsequent adapter may implement an approved deterministic mapping without retraining. Do not re-collect GT5 or treat all five executions as lacking raw evidence.

Granularity warning (not an actual score): under one-to-one matching and all176 canonical occurrences denominator, even matching every one of27 requirements has a mathematical ceiling `100*sqrt(27/176)` = 39.167473%. This illustrates the coarse TD-04 vs technical-map granularity issue; it does not authorize dropping maps, selecting GT-only denominators, semantic compression, changing FINAL or changing the model. Resolve the comparison contract explicitly before interpreting this as a model-performance failure.

## Evidence and tests

- Latest real HTTP run: `DEV-M02-20261103T063438-db4cbe826f39`, status NOT_CONFIGURED, no numeric score. Page/API catalog/input selection/run/CSV endpoint tested over localhost. `web_check.json` verifies HTTP workflow.
- Repository evidence: `results/development/DEV-M02-20261103T063438-db4cbe826f39/evidence.csv`; 208 rows = 5 summaries +27 GT rows +176 generated rows. Generated technical fields/IDs are downloadable. Match/unmatched/missing and scores are **NOT_EVALUATED/null**, not success/zero. It is a blocked-run evidence CSV, not a scored performance evidence CSV.
- CSV SHA256 `e05d7daae2299db25a5b2e8b945b112aa669f8bce96a93e98285a7ce9df8a893`. Full independent CSV row/model/GT count and copied-original equality checks in `/Users/sooeunkim/Documents/Codex/2026-11-03/task-9/phase1/independent_csv_hash_audit.json`. This audit is a separate script, **not** the required separate Verification Task.
- Required regression: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`, 114 tests OK in socket-allowed environment. Initial sandbox112 run had6 localhost bind PermissionErrors, subsequently passed with socket access; later2 tests added. Frontend24 mode/page DOM checks and integration sandbox checks passed. New six tests use synthetic fixtures, not KTL evidence.
- Every v1.2.1 manifest-listed file hash verifies. Copied process_models/process_nodes equal pre-existing source hashes. V6.2/data-reference tracked diff empty. No model/training/runtime/inference/cluster/threshold changes, OFFICIAL data, final freeze, commit or push.
- Reproduce blocked run: start `python3 -m backend.server`; visit `/metrics/m02?mode=DEVELOPMENT`, select Frozen v1.2.1, run; or POST `/api/evaluations/m02/run?mode=DEVELOPMENT&dataset_id=v1_2_1_unseen_m02_development`. Package remains fully local/repository-backed.

## Handoff

Request independent verification of FINAL p.6–7, 27-step transcription, procedure granularity, direct-vs-auxiliary distinction, immutable copy hashes, all176 denominator and identity-anchor policy, API compatibility, null-score safeguard, HTTP/CSV, and tests. Verify whether typed fields permit an objective direct contract without user interpretation; do not accept an overly restrictive label-only requirement. If an objective mapping is possible, a Development Fix Task may implement it and reverify. Otherwise obtain the exact unresolved mapping decision. Phase2/M06 and Phase3/M03 remain unstarted until the user receives the M02 result/blocker. M05 official contract stays blocked on KTL quantity conflict; M01 is not a blocker.
