# M05 baseline adapter candidate (not frozen yet)

User-authorized existing deterministic cleaning rules, not a learned ML classifier.
No held-out dataset or F1 measurement was created. Original source and all M02
files remain unchanged. Independent verification must precede freeze.

## API and exact behavior

`python backend/m05_baseline_adapter.py --model evaluation_contracts/development/m05_baseline_adapter_candidate/rules.json`
reads `{"events":[{"id":"original UUID","features":{"case_id":"explicit sequence ID","activity":"existing standardized activity token","ts":"ISO timestamp or null"}}]}`
and emits predictions (id, KEEP/REMOVE, exact rule reason, predecessor ID).
Only these fields are accepted; GT/category/expected_label are rejected. Output
order and IDs are identical to input. Complete case context is required. Stable
sorting follows existing CSV adapter: valid timestamp then input index, invalid
or missing timestamps last. Filtering removes empty/exact/prefix tokens, then
RLE merges identical consecutive surviving activity tokens, separately by case.
No min_seq_len filtering or max_seq_len truncation is called: those discard model
sequences, not per-event cleaning judgments.

The original dataset.py is copied byte-for-byte and hash-checked. Selected AST
nodes are compiled unchanged, avoiding an unrelated torch dependency. The hash
covers the entire original file. Functions are not reimplemented.

## Functional DEVELOPMENT validation

`python scripts/validate_m05_baseline_adapter.py`
uses the existing CSV reader/generic_activity and explicit mapping
`task_id -> case_id`, `event_id -> source_event_pk`, `event_time -> ts`.
This mapping is a functional fixture, not evidence of held-out suitability or
an assertion that every prior model run used this mapping. Direct invocation of
original AI-model/dataset.py provides the comparison oracle. Each input event
has exactly one prediction; both programmatic and subprocess results match.
Prediction CSVs include source path/hash. Tests do not label semantic correctness.

## Coverage and limitations

- noise: empty activity; exact heartbeat API token; static/resources/favicon API
  prefixes only. Not a generic semantic noise classifier.
- duplicate: consecutive identical activity after drop filtering only, not all
  duplicate events and not nonconsecutive semantic duplicates.
- repeated_action: same limited RLE criterion, no separate category detector.
- irrelevant_action: no general task-relevance rule; some specific technical
  activity tokens are dropped, but this is not full category coverage.
- Reasons remain `empty_activity`, `drop_exact`, `drop_prefix`,
  `consecutive_same_activity`; these are not independent human category labels.

## Future collection, after independent PASS and freeze

Collect new raw session exports after the recorded freeze time; preserve source
CSVs/hashes, session/task boundaries, timestamp ordering, original event UUIDs,
and full surrounding sequence. Do not select from existing DEVELOPMENT data.
A human independently labels semantic KEEP/REMOVE and REMOVE categories without
seeing engine predictions. Keep 10/10 and recommended category mix as sampling
contract, not a way to cherry-pick rules known to pass. Retain ordinary meaningful
navigation/input/save events alongside naturally recorded technical background
and repeated events; do not synthesize successful measurements.

RLE needs context. The current 20-event evaluator passes only the 20 evaluated
rows. Therefore use complete selected case windows totaling 20 events, or obtain
approval for a context-preserving adapter/evaluator handoff before scoring an
arbitrary 20-event subset. Do not silently omit intervening KEEP rows or infer a
new adjacency. Resolve data availability and human labels before one-shot F1.

The candidate engine config is compatible with `m05_heldout.validate_engine` but
not installed as active `evaluation_contracts/m05_engine.json` until independent
verification and freeze. Existing held-out provenance gate stays BLOCKED.
