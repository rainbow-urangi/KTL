# M02 DEVELOPMENT — authorized post-PASS measurement attempt

2026-11-05. Actual measurement outcome: BLOCKED / GT_SEMANTIC_SCHEMA_REQUIRED.
Implementation verification PASS is valid; a numeric performance result was NOT
produced. This is neither a score of0 nor an M02<75/model failure finding.

## Authority and unchanged artifacts
Confirmed independent gate verdict PASS for snapshot manifest
322ea5277b597e01068643a2e1667b6899b8c3e6b8f46730c79b1f17ce71d86a,
contract ACTION_SCREEN_TARGET_ORDER_V2. Independent report SHA256 matches gate.
Gate explicitly permits subsequent actual GT schema access and comparison, and says
schema incompleteness must return null rather than guessed mappings.

Post-PASS actual TD-04 was parsed for the first time in this workflow. Opaque SHA256
19922ea39a42c756e9f951cee85ce5b4c6dae0db2d0d31591ad2a2ef636d6578 matches frozen boundary.
No source code, rules, GT, model or frozen output was modified in this measurement
attempt. Full input/output hash audit has zero mismatches; all38 frozen model file
hashes remain bound/unchanged. Model manifest remains b9c69f7088f7d6abd5e0e21b569e69be50b099265bc8e9dd99eda07042bd0504.
No training/inference, OFFICIAL output, M06/M03 or score-driven changes occurred.

An initial assess attempt rejected the predictions.json provenance check before GT
access. An immediate complete byte-hash audit found no mismatches; subsequent assess
and HTTP execution passed all integrity checks consistently. Cause of that initial
transient check failure is not established; no result from that failed attempt was
used and no hash/artifact was replaced to bypass it.

## Actual GT schema findings
All27 required procedures provide label, menu_screen_name, step_order and aliases.
All27 lack BOTH explicit action_type and typed screen_context={kind,value} required
by the independently approved strict contract. Existing free-text menu_screen_name
was NOT silently interpreted as a page_path/page_title/menu_path/popup_title.
No action was guessed from prose, raw events or generated output.

The comparator validates the complete GT schema before alignment/statistics, so no
required procedure was matched, classified as missing, or converted to zero. Here
"matched not measured" differs from "matched count0"; required27 is not missing27.

| BU | Generated | GT required | Matched | Unmatched generated | Missing required | Accuracy | Completeness | Score |
|---|---:|---:|---|---|---|---|---|---|
| BU03 |15|5|not measured|not measured|not measured|not measured|not measured|not measured|
| BU07 |19|6|not measured|not measured|not measured|not measured|not measured|not measured|
| BU09 |15|6|not measured|not measured|not measured|not measured|not measured|not measured|
| BU17 |21|5|not measured|not measured|not measured|not measured|not measured|not measured|
| BU20 |21|5|not measured|not measured|not measured|not measured|not measured|not measured|
| TOTAL |91|27|not measured|not measured|not measured|not measured|not measured|not measured|

Required counts are independently audited schema row counts. The blocked web result
leaves required_count null rather than pretending comparison ran. Schema audit files
separately supply the verified27/5/6/6/5/5 counts above. No matches or metrics were
computed by the audit.

## Scope/conservation disclosures
Target denominator91; all generated178=91target+73 established unrelated+14UNASSIGNED.
Mixed target0. BU17 includes trailing PM-0082. Target UNRESOLVED1 stays denominator.
14UNASSIGNED and42 unclaimed raw IDs remain coverage limitations, not silently
claimed unrelated. All260 raw events retained. Canonical HTTP39, all43 raw HTTP
preserved;3 outcome sidecars remain evidence-only. No score-dependent filtering.

## Persisted actual DEVELOPMENT execution / web / CSV
Run ID DEV-M02-20261105T033528-40ac71704a1e.
status NOT_CONFIGURED; details.comparison_status GT_SEMANTIC_SCHEMA_REQUIRED;
score/threshold_met/official_pass null. Target75 remains displayed.
Input v1_2_1_unseen_m02_development; model workflow_candidate_v1_2_1;
serializer business-process-serializer-4-semantic-2;
rule hash4cbed85eb541306e2750c6a10f2344c0262004f5fd92c4587aa80e714503d29d.

Local HTTP verification:
GET /api/evaluations?mode=DEVELOPMENT ->200, denominator91 and schema blocker.
POST /api/evaluations/m02/run?mode=DEVELOPMENT&dataset_id=v1_2_1_unseen_m02_development
->200 with persisted blocked/null result above.
GET /api/evaluations/m02/runs/DEV-M02-20261105T033528-40ac71704a1e/evidence.csv
->200;778820bytes; correct evidence attachment route.
CSV SHA256 e6602afb572861982faec5ddebb3922b9099d132bdfbf8b39ce4329c1c852884.
CSV477rows=178generated+39technical+260raw;178generated statuses NOT_EVALUATED.
91generated rows flagged in_m02_denominator=True and all have comparison_order.
Source event/node IDs, field identity, rule and evidence remain downloadable.
This CSV is BLOCKED measurement provenance, not numerical performance evidence.
No required/match/aggregate-calculation rows are fabricated for the failed schema.

Frontend24 mode/page DOM checks PASS after actual blocked run. No interactive browser
or numeric score visual verification claimed. Backend code unchanged since166-test
independently verified suite; full frozen input hashes still match.

Saved run files:
results/development/DEV-M02-20261105T033528-40ac71704a1e/result.json
results/development/DEV-M02-20261105T033528-40ac71704a1e/evidence.csv
results/development/DEV-M02-20261105T033528-40ac71704a1e/run_manifest.json

Task workspace supporting artifacts:
M02_ACTUAL_RUN.json — exact persisted result/API output.
M02_GT_SCHEMA_AUDIT.csv / .json —27 required schema checks without invented semantics.
M02_ACTUAL_RUN_INTEGRITY.json — all hashes, gate/report binding and CSV audit.
M02_ACTUAL_HTTP.txt / M02_ACTUAL_FRONTEND.txt — HTTP and DOM evidence.

## Minimum necessary next action (NOT performed)
Provide an evaluation-only authoritative semantic declaration for the27 GT procedures:
1. Explicit action_type from frozen generic taxonomy, based only on TD-04/source
   business-procedure definitions, never generated/raw/match/score answers.
2. Explicit typed screen_context.kind/value identifying the intended declared screen.
   Resolve any naming/identifier ambiguity from the authoritative screen/menu spec,
   not by choosing a value that fits generated output.
Preserve original IDs, procedure text, order and declared aliases. Do not change
serializer/model or invent GT constraints from output. A versioned evaluation-only
GT schema extension or sidecar must preserve the original source and provenance.
Any new schema/boundary source changes require a new frozen evaluation manifest and
independent gate approval BEFORE remeasurement. No such declaration was authored here.

Current75% criterion is UNDETERMINED. No mismatch-performance analysis or model
improvement recommendation is valid without comparable GT. Keep v1.2.1 + enrichment
+ serializer fixed. Parent should independently verify this blocked measurement and
schema audit before deciding the authorized schema work. M06/M03 remain stopped.
