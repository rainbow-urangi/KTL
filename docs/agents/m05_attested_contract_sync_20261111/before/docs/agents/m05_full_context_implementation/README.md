# M05 full-context implementation (DEVELOPMENT only)

Implementation supports full raw inference followed by scoring **only twenty independently locked targets**. It does not establish that a new real dataset, independent labels, or a valid held-out approval exists. No real new raw inference or F1 measurement was run while implementing this change.

The 2026-11-11 user decision keeps exactly KEEP10/REMOVE10 and removes all per-category quotas. Each REMOVE has one objectively raw-supported category from duplicate, noise, repeated_action, or irrelevant_action; a category may occur zero to ten times. KEEP10 has no category. remove_category is evidence/explanatory metadata, independently labeled before prediction; binary REMOVE vs KEEP determines confusion, regardless of engine reason/category alignment. Targets or labels must never be changed after viewing predictions. Earlier preparation and audit snapshots remain historical records, not current category requirements.

## Entry points

- `backend/m05_full_context.py`: validation, full-sequence orchestration, target-only central scoring, immutable run artifacts.
- `backend/m05_readiness_web.py`: isolated loopback web at port 8768; `/validate` never runs prediction or returns F1; `/measure` validates again before the one batch.
- `backend/m05_full_context_csv.py`: evidence-only independent confusion/P/R/F1 recalculation.
- `scripts/recalculate_m05_full_context_csv.py RUN_DIRECTORY`: read-only snapshot, ID join, provenance, artifact hashes and independent CSV/result reconciliation.
- `tests/test_m05_full_context.py`: temporary synthetic 300-row fixtures only, including context-sensitive prediction and real frozen adapter subprocess on synthetic bytes.

Existing `backend/m05_heldout.py`, `backend/evaluators.py`, frozen adapter/rules/normalization, engine config, M02/main server/frontend, original source data and freeze records are not modified. The central frozen `calculate` receives only the selected twenty rows after full prediction validation. No max-length/min-length CSVCaseAdapter path runs.

## Required bundle schema

All artifact references are `{ "path": "repository-relative/path", "sha256": "64-character sha256" }`. Hashes are byte hashes unless specifically described as canonical JSON digests. Repository-contained symlinks are resolved and checked; held-out artifacts must stay in the separated dataset directory.

`data/held_out/m05/<dataset_id>/manifest.json`:

- `schema_version`: `m05-full-context-v1`
- `dataset_id`: exact directory name
- `used_for_training: false`, `used_for_development: false`
- artifact references: `collection`, `target_labels`, `target_selection`, `label_lock`, `prediction_access_audit`
- `provenance`: `reviewer`, timezone-aware `reviewed_at_utc`, `complete_history_attested: true`, nonempty `training_inventories`, `development_inventories`, `audit_evidence` lists of artifact references.

### Collection and full sequence

Collection JSON binds `dataset_id`, `scope: COMPLETE_SESSIONS_AND_TASKS`, timezone-aware `collection_started_at_utc`/`collection_ended_at_utc`, `collector_id`, `collector_version`, `timezone`, `completion_reason`, integer `event_count`, ordered `raw_files`, `sessions`, `tasks`, `clock_evidence`, and `export_evidence`. All collection and event times must be after the pinned engine freeze and not in the future. Clock/export evidence are JSON records with the matching dataset ID and substantive findings, independently reviewed below. File mtime is never evidence.

Each ordered raw file reference adds `row_count` and `column_mapping`. Files must be CSV under `<dataset>/raw/`; all CSVs there must be declared. Raw CSV required columns: `event_id,task_id,session_id,event_time`. Frozen normalization maps `case_id=task_id`, `source_event_pk=event_id`, `ts=event_time`, plus identity mappings of other existing `STANDARD_FIELDS` columns. Every row is retained in file-list/CSV-record order. `event_time` with an explicit UTC offset remains supported. A timezone-naive export requires a hash-bound timestamp policy in clock evidence: event/session-bound UTC or epoch payload fields must agree with the CSV wall time in the declared exporter timezone, or a separately bound exporter-timezone authority and its hashed source artifacts are required. No host timezone, file mtime, bare collection timezone, or row rewrite is accepted. See [timestamp evidence contract](../m05_timestamp_evidence_20261111/README.md). The evidence-only UTC value is used for collection/session/task boundary checks, while raw bytes and frozen `features.ts` stay unchanged.

The exact original `read_standard_rows`, activity derivation, normalization and sort functions are compiled unchanged from hash-pinned source AST definitions. No GT/category influences features. Case normalization collisions across sessions or different raw case IDs are BLOCKED. The engine receives only `{events: [{id, features: {case_id, activity, ts}}]}`.

Session JSON contains `sessions`, task JSON contains `tasks`. Each entry has exact ordered `event_ids`, `source_session_id`, `complete: true`, `completion_evidence`, timezone-aware `started_at_utc` and `ended_at_utc`; task entries additionally have `source_case_id`. Inventories must cover every full raw row with matching boundaries and no omitted/duplicate group.

`raw_sequence_sha256` is the canonical JSON digest of the ordered `collection.raw_files` list. Canonical JSON is UTF-8, sorted keys, `ensure_ascii=false`, compact separators `(',', ':')`. `normalized_input_sha256` digests the complete `{events: ...}` payload.

### Historical separation

Each history JSON has `scope` (`training` or `development`), nonempty CSV `source_files`, and `events` containing exact `{event_id, feature_sha256}` entries. Historical CSVs are normalized with the same frozen normalizer. The recorded inventory must reproduce every source row, and neither event ID nor normalized feature fingerprint may overlap **any full-context input row**. No automatic content-overlap relaxation occurs. History sources cannot be held-out files.

Each provenance audit has matching `raw_sequence_sha256`, complete `inventory_sha256` list, `method: SOURCE_HISTORY_RECONCILIATION`, `coverage_complete: true`, and substantive `findings`. These declarations and inventories are insufficient without an independent registry approval that explicitly reviews source-history completeness.

### Targets and independent labels

`target_labels` is CSV with exactly the header in `backend/m05_full_context.py::LABEL_FIELDS` (the preparation `target_labels.template.csv` has this same schema). Exactly twenty unique IDs must join to full raw rows. `held_out` is the exact CSV string `true`, not Python truthiness. Provenance columns, zero-based full sequence index and one-based CSV **record** number must match byte-hashed raw sources. KEEP10/REMOVE10 is mandatory. REMOVE category must be one of the four allowed metadata values; there is no category quota or requirement to cover all four types. KEEP category must be empty. Label rationale, labeler and timezone-aware labeling time are mandatory; labeling must follow full collection completion.

Selection JSON: ordered `event_ids` matching CSV order, `raw_sequence_sha256`, and a substantive `selection_principle`.

Lock JSON: `target_labels_sha256`, `target_selection_sha256`, `raw_sequence_sha256`, `normalized_input_sha256`, `locked_at_utc`, `prediction_blind: true`, `labeler`. Lock must follow all labels and full collection completion. Declaration alone does not establish blindness.

Prediction access audit JSON: matching `label_lock_sha256`, `raw_sequence_sha256`, `coverage_complete: true`, `prediction_runs: []`, `prediction_views: []`, `method: EXECUTION_AND_ACCESS_LOG_RECONCILIATION`, `findings`, independent `reviewer`, `reviewed_until_utc`, nonempty `source_logs` references. Each log JSON binds raw digest, `entries: []`, and `coverage_started_at_utc` through `coverage_ended_at_utc`, spanning collection start through label lock. An independent human must substantiate that this really covers the collector/export and prediction/access history. Generated assertions are not real collection or independence evidence.

### Independent approval, separately maintained

`evaluation_contracts/m05_full_context_approvals.json` must already contain an `approvals` entry:

- `status: PASS`
- `binding`: exact `manifest_sha256` (canonical manifest digest), `raw_sequence_sha256`, `normalized_input_sha256`, and pinned `engine_freeze_sha256`
- `reviewer`: neither labeler nor provenance preparer
- `reviewed_at_utc`: after lock and no later than current time
- `evidence_review: SOURCE_COMPLETENESS_POST_FREEZE_HISTORY_AND_BLIND_LABEL_LOCK`

The evaluator never creates, updates, infers or approves this registry. A manifest editing itself or a `prediction_blind=true` flag cannot open the gate. Approval must be genuine independently performed review, not an implementation test record. File hashes bind bytes, not human truth, so independent review of collection completeness and access-log coverage is an explicit trust boundary.

## Execution and outputs

Freeze SHA-256 is pinned to `23fde29b22c23976ccf02760f58b2c2490f3e5b054c385193fc7c463f5f00d10`; all original immutable hashes, active config and exact executable argv are validated before inference. A durable attempt claim keyed by normalized full input identity is created before running. Failed, timed-out or uncertain runs are retained and never silently rerun. Changing labels or approval metadata does not reopen an exposed input.

Full prediction IDs must exactly match the full input IDs, with valid binary labels, original case/activity/index, and removal provenance. Target IDs are joined only afterward. Full context stays in `full_predictions.json` and never enters the CSV denominator.

Each run lives under `results/development/m05_full_context/<binding-digest>/`. It preserves `attempt.json`, `engine_input.json`, `validated_manifest.json`, `normalization_provenance.json`, `locked_target_snapshot.json`, `full_predictions.json`, target-only `evidence.csv`, `result.json`, and `run_manifest.json`. Failure writes `blocked.json`, no successful result. No source data is overwritten. Successful files are byte-hashed by the run manifest, and sources are revalidated before and after inference.

REMOVE is positive: TP/FP/FN/TN sum to twenty; TP+FN=10; TN+FP=10. P=TP/(TP+FP), R=TP/(TP+FN), F1=2TP/(2TP+FP+FN); zero denominator means zero. PASS compares unrounded F1 >=0.79. All results remain DEVELOPMENT, `official_pass=null`. Category/engine-reason disagreement does not alter binary scoring.

Run-specific CSV/manifest downloads recheck artifact hashes, target/full prediction joins and independent CSV recalculation. No generic stale `/evidence.csv` is served. Browser errors/validation failure clear result links. Persistent claims also block repeated clicks and reopening an already attempted dataset.

## Reproduction and limits

Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_m05*py' -v`, then repository-required `python3 -m unittest discover -s tests -v`. Tests create and delete synthetic fixtures in temporary directories; their fabricated approval/log records are never real evidence or retained under `data/held_out`.

Run the read-only independent checker on a future completed authorized run with `python3 scripts/recalculate_m05_full_context_csv.py <run_directory>`.

This implementation does not execute against a real new raw bundle, create real target labels, or claim a measured F1. Actual collector provenance, independent label locking/approval, real browser measurement and real CSV evidence remain pending until valid inputs and authorization exist.
