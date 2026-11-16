# M05 evidence-based timestamp resolution

## Result and scope

The full-context evaluator can validate a timezone-naive export without rewriting the export or the frozen engine input. This is a validation/provenance change, not a cleaning, normalization, label or scoring change. Actual held-out prediction was not run. No full-context approval, target lock, held-out bundle or score was created.

- Added `backend/m05_timestamp_evidence.py`.
- Integrated it into `backend/m05_full_context.py` before collection and session/task time checks.
- Added `tests/test_m05_timestamp_evidence.py`.
- Updated the full-context implementation note and evidence CSV template.
- Raw provenance and label schema remain unchanged. Additional output provenance: `validated_event_timestamp_utc`, `timestamp_resolution_method`, `timestamp_evidence_sha256`.

## Gate contract

An existing explicit-offset `event_time` works without a policy within the lossless timestamp format below. When a policy is present, an aware raw timestamp must also have the offset and wall time of the declared exporter timezone at that instant; agreement with a UTC payload alone does not excuse a contradictory exporter timezone. A bare `collection.timezone` never authorizes a naive export.

For a naive export, the existing byte-hashed `collection.clock_evidence` JSON must include `timestamp_policy`. Its exact raw bindings, in collection file order, contain only each raw reference's `path` and `sha256` (not row count/mapping). The policy's timezone must match `collection.timezone`. Use an IANA region, `UTC`, or fixed `+HH:MM`/`-HH:MM`, not an abbreviation such as `KST` or `CST`.

Example shape, with placeholder references that must be replaced by real verified evidence:

```json
{
  "dataset_id": "dataset-id",
  "findings": "Source-backed clock/export findings, independently reviewed before approval",
  "timestamp_policy": {
    "schema_version": "m05-timestamp-evidence-v1",
    "timestamp_column": "event_time",
    "timezone": "Asia/Seoul",
    "raw_files": [{"path": "data/held_out/m05/dataset-id/raw/events.csv", "sha256": "actual-file-hash"}],
    "payload_sources": [{
      "column": "locators_json",
      "event_id_path": ["event_context", "event_id"],
      "session_id_path": ["session", "page_session_id"],
      "timestamps": [
        {"path": ["event_context", "event_time"], "format": "iso8601"},
        {"path": ["analysis", "event_ts_ms"], "format": "unix_ms"}
      ]
    }]
  }
}
```

The example's field paths are data, not hard-coded collector logic. Other JSON columns and object paths are supported. `iso8601` requires an explicit offset. Raw and payload timestamps use calendar dates and complete seconds: `YYYY-MM-DD[T or space]HH:MM:SS`, optional decimal point/comma and 1–6 fractional digits, with `Z` or `±HH:MM` for an aware timestamp. Explicit offset hours must be below 24 and minutes below 60; invalid offsets are rejected rather than normalized by Python. A decimal comma is converted to a decimal point only in the validation-local string so Python 3.10 and 3.12 agree, while the original raw/engine value remains untouched. Naive raw timestamps omit only that timezone suffix. Excess fractional digits are rejected before Python parsing, even if zero, so Python version-dependent truncation cannot silently lose precision. Basic/week-date forms, abbreviated times and fractional/seconds-resolution timezone offsets are deliberately unsupported. `unix_s`, `unix_ms`, and `unix_us` are explicit Unix-epoch units; units are never guessed. Source JSON numeric precision is preserved through Decimal parsing. Epoch coefficient/exponent digits are then converted directly to integer microseconds without any Decimal-context arithmetic, rounding, tolerance or sub-microsecond truncation. All declared timestamp sources are mandatory and must describe exactly the same instant. The policy must enumerate every authoritative event-time representation in the export; independent source review must check that it did not omit conflicting fields. Server receive time is not event time and must not be substituted for it.

Every payload is tied to the raw event ID and session ID. For a naive export, the bound UTC instant converted into the policy timezone must exactly reproduce the CSV wall time, including date and subsecond precision. The authoritative UTC resolves a DST fold when present. A nonexistent wall time cannot round-trip and is rejected.

## Alternative: explicit exporter-timezone authority

When event-time UTC/epoch payload evidence is absent, `timestamp_policy.timezone_authority` may reference a separate byte-hashed JSON artifact inside the same held-out bundle. It must contain:

- `schema_version: m05-export-timezone-authority-v1`.
- `dataset_id`, `collector_id`, and `collector_version` matching collection.
- Exact ordered `raw_files` path/hash bindings, `timestamp_column: event_time`, and matching `timezone`.
- Nonempty `authority`, `reviewer`, and `findings`, plus timezone-aware `recorded_at_utc`.
- A nonempty `source_artifacts` list of path/hash references to original exporter configuration or other authoritative records inside the bundle. Every source is checked for path confinement and byte hash.

This is a documentary evidence route, not automatic certification that the supplied narrative is true. The existing independent full-context reviewer must verify that the source artifacts actually establish the exporter timezone for these exact files and collector. Self-attestation or an unrelated configuration does not satisfy that review. Both payload and authority may be supplied; missing/conflicting payloads are not ignored in favor of authority. Without UTC evidence, ambiguous DST folds and nonexistent local times fail closed.

## Invariants and verification

- Raw rows/bytes, source order, `event_time`, and frozen normalized `features.ts` are untouched. Evidence never enters the model payload.
- All post-freeze, collection, session and task time-bound checks use resolved UTC. This also fixes the old session/task reparse of naive raw strings.
- Raw, clock, collection, authority, source-artifact and approval bindings are revalidated by the existing full-context pipeline before/after inference. Labels, history, target lock, independent approval and single-attempt gates remain in force.
- No fallback to host timezone, mtime, nearest time, rounding, tolerated offset, or synthetic/rewritten raw exists.
- Fail-closed coverage includes missing evidence, payload ID mismatch, UTC/epoch conflict, CSV/UTC conflict, missing declared fields, invalid/duplicate-key JSON, unknown/ambiguous timezone, authority identity/hash/path mismatch, invalid epoch precision, collection/session/task bounds, and pre-adapter/pre-score blocking.

Tests:

```sh
python3 -B -m unittest discover -s tests -p 'test_m05_timestamp_evidence.py' -v
python3 -B -m unittest discover -s tests -v
```

- Focused synthetic tests: **35 passed on Python 3.10.5 and 35 passed on Python 3.12.6** (`focused_tests.log`, `focused_tests_python312.log`).
- Required full Python regression: **415 passed** (`full_regression.log`).
- Frozen validator: **PASS**. Before/after raw/frozen hashes: **25/25 unchanged**, including all 17 frozen artifacts, active config, freeze JSON and six supplied raw CSVs (`integrity_before.json`, `validation.json`).
- Read-only timestamp diagnostics: 203/203 events in raw_01 and 147/147 in raw_02 have matching event/session identity, UTC/epoch agreement, exact Asia/Seoul wall-time agreement, and post-freeze instants. No predictions or GT labels were used. This diagnostic is not collection authority or evaluation approval.
- raw_02 event range: `2026-11-11T12:36:45.064Z` through `2026-11-11T12:38:29.307Z`.

Independent review found boundary defects in the initial implementation: an aware exporter-zone conflict, Decimal-context rounding of tiny fractions, Python 3.12 ISO sub-microsecond truncation, Python normalization of malformed explicit offsets, and version-dependent decimal-comma handling. All were corrected and covered by new regressions; the counts and artifact manifest here refer to the corrected implementation.

Independent verification is a separate step. This implementation report does not claim its own independent approval or actual M05 readiness.
