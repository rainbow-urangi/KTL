# M02 semantic serializer v4.2 — DEVELOPMENT precomparison contract

Authority: FINAL pp6–7 and the user's KTL-confirmed interpretation, semantic
enrichment authorization and explicit execution ownership policy. Frozen v1.2.1,
V6.2 and historical serializer outputs are immutable. No score informs these rules.

## Generation and boundaries
Pure generation accepts frozen maps/nodes/canonical occurrences plus allowlisted
raw evidence. TD-04 semantics, aliases, BU/execution labels and scores NEVER enter
semantic classification, splitting or compression. Scope is strictly postgeneration.
Every raw UI source event is restored as an atom. Different field identity cannot
merge. INPUT compression requires consecutive raw events, same explicit interaction,
session, instance, action, page, popup and complete field identity: selector, id,
name, type and label. At least explicit id/name plus selector is required. Missing
identity stays separate. Identical selector/label is insufficient when name/type
changes. Save and confirmation are never merged. UNRESOLVED steps remain retained.

Generic taxonomy: PAGE_ENTER, MENU_ENTER, QUERY, VIEW, DETAIL_OPEN, SELECT, INPUT,
SAVE, REGISTER, UPDATE, CONFIRM, RESULT_CHECK, POPUP_OPEN, POPUP_CLOSE, UNRESOLVED.
Fixed generic exact verb lexicon plus typed direct action, no business dictionaries.
Input values cannot supply field labels. Source event/node/occurrence provenance,
field identity, split_from, evidence and rule IDs remain generated output.
HTTP stays evidence only, methods/status/raw+normalized paths retained, no fallback
causality promotion. Explicit unique interaction outcomes attach as evidence only;
no passive success message creates a completion procedure. All sidecars retained.

## Execution scope
Explicit manifest start/end event anchors and session only. Missing end is not
inferred; remaining unknowns stay UNASSIGNED. Single execution owns a step; all
split-map fragments included. Multiple BU owners => CROSS_EXECUTION_MIXED; relevant
mixed counted globally once, never matching eligible and never per-BU duplicates.
Scope never splits/repairs a step. Established unrelated BU steps excluded with
ledger; UNASSIGNED separately disclosed. Target BU lists exist only in evaluation.
Postscope procedures receive comparison_order from raw source position across all
fragments of that execution. Original step_order within process remains preserved.

## ACTION_SCREEN_TARGET_ORDER_V2 (supersedes target-only V1)
The dedicated self-contained comparator reads ONLY final generated action_type,
target_field_label, one typed screen field, resolution/matching eligibility and
comparison_order/step_order. It never scans raw evidence, field-label sidecars or
node evidence for alternate answers. Procedure must be direct + eligible + RESOLVED.

GT evaluation representation MUST explicitly supply, for each required procedure:
- id and positive unique step_order;
- action_type, exactly one generic taxonomy value (UNRESOLVED cannot match);
- screen_context = {kind, value}, nonempty; kind is page_path, page_title, menu_path
  or popup_title;
- target_label, or existing label treated only as the declared complete target;
- allowed_aliases: optional list of nonempty target strings scoped to this required
  action + typed screen + procedure, NEVER global action/screen aliases.

Generated screen value is respectively menu_page, page_title,
menu.selected_path_text/path_text, or popup.target_popup.title/active_popup_title.
No URL-to-screen-name inference, action extraction from prose, substring matching,
embedding match or business-specific dictionary is allowed. Menu/screen free text
alone is not silently interpreted as a typed screen. NFKC/casefold/whitespace
normalization applies to target and human screen labels; page_path preserves case
and internal whitespace with only edge whitespace stripped. Action matches exactly.
A target alias cannot bypass action/screen constraints. Ambiguous aliases shared by
different canonical targets within the same action/screen block measurement.

All GT schema validated BEFORE any alignment/metrics. Missing/ambiguous GT semantic
fields => GT_SEMANTIC_SCHEMA_REQUIRED, score null, no guess or zero score.
Do not infer missing GT action/screen from raw or generated output, and do not edit
TD-04 after looking at scores. Whether actual TD-04 contains these fields may only
be checked after independent PASS authorizes semantic access. No claim of actual
schema completeness is made in this precomparison task.

Matching is deterministic order-preserving one-to-one alignment within the same BU;
all generated procedures remain denominator, including unresolved/mixed unmatched.
No best-instance/map selection. LCS compatibility uses action + typed screen + target
simultaneously. Tie policy retains earlier generated candidate. Repeated procedure
requirements require repeated compatible generated steps. Per-BU counts omit shared
mixed steps; aggregate denominator adds relevant mixed exactly once.

## Freeze and independent gate
Freeze generation inputs, rules, outputs, scope, this contract, dedicated comparator,
evaluators.py utility dependency, candidate adapters, server/run storage/config,
freeze script and frozen model manifest + EVERY manifest-declared model file hash.
Verify all bindings at runtime without model execution. Freeze the GT-source manifest
and TD-04 path/opaque SHA256 separately under evaluation_boundary. Opaque hashing
reads no GT semantics and never passes GT bytes to generation.
Any input/code/model/GT-boundary change invalidates the approved manifest hash. The
old target-only contract cannot open the V2 gate even if its hash is otherwise valid.
Independent PASS must name ACTION_SCREEN_TARGET_ORDER_V2 and the NEW snapshot hash.
Without it return null metrics/NOT_EVALUATED provenance CSV before any GT semantic IO.
