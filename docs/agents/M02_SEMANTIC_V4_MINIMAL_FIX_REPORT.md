# M02 semantic v4 — independent F1/F2/F3 minimal fix handoff

2026-11-05. Development FIX complete; PENDING INDEPENDENT RE-VERIFICATION.
Read /Users/sooeunkim/Documents/Codex/2026-11-05/task-4/M02_SEMANTIC_V4_INDEPENDENT_VERIFICATION.txt.
No actual TD-04 semantic content was parsed, compared or scored. Only its opaque
SHA256 was verified at the evaluation boundary as explicitly requested in F3.
No model job, model edits, OFFICIAL output or M06/M03 work. No PASS gate was created.

## F1 — complete field identity
backend/semantic_enrichment.py now stores field_identity containing selector, id,
name, type and label. INPUT compression requires exact identity, nonempty explicit
id/name plus selector, same interaction/session/instance/page/popup/action and raw
adjacency. Different name OR type prevents compression even with identical generic
selector/label. Missing stable identity also prevents compression. Generic rules only.
Regression: Contact/input.contact/id='', same-batch interaction, phone/tel vs
email/email retain distinct steps/event provenance; individually changing name and
type tested. Ambiguous no-id/no-name also stays separate. No actual compression
fired; counts did not change. Actual generated atoms additionally preserve the
complete field identity, and new serializer/rules version is semantic-2.

## F2 — strict business procedure comparison, target-only V1 removed
New dedicated backend/m02_semantic_comparator.py, stdlib-only, contract
ACTION_SCREEN_TARGET_ORDER_V2. It requires SAME action_type + SAME typed screen +
scoped target/declared alias, direct/eligible/RESOLVED output, same business process,
one-to-one and order-preserving deterministic alignment. No raw evidence fallback.
NFKC/casefold/Unicode whitespace normalization for target/human screen labels;
page_path preserves case/internal whitespace to avoid collapsing distinct URLs.
Target aliases are scoped by business process, action and typed screen. An alias
cannot bypass action/screen; conflicting same-context aliases block measurement.
GT step IDs are local to their business process, not forced globally unique.

GT representation MUST provide explicit action_type, positive step_order and typed
screen_context={kind,value}; kind page_path/page_title/menu_path/popup_title.
Target is explicit target_label or existing label; optional allowed_aliases are target
strings only. No action extraction from GT prose, guessed screen typing or GT-aware
business rules. Validate ALL requirements before alignment or metric computation.
Missing/ambiguous GT semantics => GT_SEMANTIC_SCHEMA_REQUIRED, score null.
Actual GT schema readiness is intentionally UNKNOWN until independent PASS authorizes
semantic access. Do not claim this task proves actual TD-04 has the required fields.
If it lacks them, report the schema limitation after authorized access, never fabricate
constraints or tune rules after seeing a score.

Scope adapter now assigns comparison_order by raw source position across ALL owned
fragments and preserves it in both final procedures and ownership/CSV ledger. Original
process-local step_order remains. Mixed is still ineligible and counted once. This
adds no GT-driven boundary/selection logic. Required-step IDs and statuses are also
included in post-PASS CSV output, verified on temporary synthetic GT only.

Negative regressions: INPUT/RESULT_CHECK; SAVE/CONFIRM despite alias; wrong screen;
case-sensitive wrong path; cross-action alias; raw auxiliary fallback; reversed order;
one generated cannot satisfy repeated requirements; mixed/unresolved cannot match.
Positive synthetic matching and local aliases/IDs covered. No actual score executed.

## F3 — freeze actual execution dependencies/model/GT boundary
Freeze + runtime verify now bind semantic comparator, evaluators.py utility dependency,
serializer/scope/candidate adapters, m02_candidate.py, run_storage.py, server.py,
backend/config.json, freeze script and contract. Missing mandatory dependencies fail.
Model manifest + every one of its 38 file_sha256 entries are hash-bound and checked
without inference. Model manifest remains
b9c69f7088f7d6abd5e0e21b569e69be50b099265bc8e9dd99eda07042bd0504;
no declared model file differs.
Source manifest is hash-bound. evaluation_boundary separately freezes td04_path,
opaque td04_sha256 and comparison contract. Replacing GT plus its wrapper manifest
cannot preserve approval. GT semantics are accessed only after matching independent
PASS; then the separately frozen GT digest is checked before parsing.
Synthetic tests demonstrate comparator/evaluators/run storage/model/source-manifest
tamper rejection. The old EXACT_GENERATED_TARGET_WITH_TD04_ALIASES_V1 contract cannot
open a gate even with the current hash. Old hash cannot approve the new manifest.

## FINAL frozen snapshot for re-verification
Path: evaluation_contracts/development/m02_serializer_v4/
manifest.json SHA256:
322ea5277b597e01068643a2e1667b6899b8c3e6b8f46730c79b1f17ce71d86a
business_steps.json: 15f7c51ed8291882e5c22594e54625d59913849c19e748d462ff3ed5c22eee61
scope.json: dc45441a2ccc4bc26b227475cb20cd6ca7dcc933a1e6a9ece23f5e710b228c1d
rules.json / rule hash: 4cbed85eb541306e2750c6a10f2344c0262004f5fd92c4587aa80e714503d29d
serializer version: business-process-serializer-4-semantic-2.
comparison contract: ACTION_SCREEN_TARGET_ORDER_V2.

FIX_REQUIRED a8bc... snapshot archived without overwriting in task workspace
m02_serializer_v4_FIX_REQUIRED_a8bc6fb5. Intermediate unapproved preverification
fix drafts also preserved as FIX_DRAFT_1c38de96 / FIX_DRAFT_c9d4d154.
No prior gate existed; no old approval reused. Use ONLY final 322ea... for verification.

## Unchanged scope/conservation limitations (not scores)
BU03 15; BU07 19; BU09 15; BU17 21; BU20 21 => 91 target steps.
178 total =91 target +73 established unrelated +14 UNASSIGNED. Mixed target0.
BU17 PM-008 two trailing steps remain included; BU03 excludes established BU02 atoms.
14 UNASSIGNED and 42 unclaimed raw event IDs remain disclosed; no ownership inferred.
All260 raw events and3 outcome evidence sidecars remain. Canonical HTTP39 records
GET30/POST8/PATCH1; all43 raw HTTP records retained. Target UNRESOLVED1 retained.
No semantic/ownership rules were changed to improve these counts or any score.

## Validation evidence
python3 -m unittest discover -s tests -v: 166 tests OK,17.866s.
node --test tests/test_frontend.cjs:24 mode/page DOM checks PASS.
Frontend test capture buffer increased16MiB because full evidence catalog exceeds
Node's1MiB default; product behavior unchanged by that harness-only fix.
Regenerated enrich twice and scope once using final frozen source inputs: byte-identical
business_steps.json/scope.json. No GT semantics accessed for regeneration.
Local HTTP GET catalog / POST M02 readiness / GET CSV all200. Readiness only:
DEV-M02-20261105T032839-f931bb10b8e4, NOT_CONFIGURED,score null,official_pass null.
CSV778820B contains generated provenance, comparison_order, scope/technical/raw rows.
Task artifacts: M02_FIXES_WEB_SMOKE.json, M02_FIXES_TESTS.txt, M02_FIXES_FRONTEND.txt.
No automatic approval review denial occurred. No interactive browser claim.

## Gate handoff — DO NOT self-approve
Independent verifier should reproduce F1/F2 synthetic counterexamples, all input/code/
model/boundary hashes, scope and deterministic outputs, and FINAL/GT isolation.
Only after independent PASS, create independent_verification.json with:
{
 "verdict":"PASS",
 "snapshot_manifest_sha256":"322ea5277b597e01068643a2e1667b6899b8c3e6b8f46730c79b1f17ce71d86a",
 "gt_leakage_check":"PASS",
 "scope_check":"PASS",
 "direct_comparison_contract":"ACTION_SCREEN_TARGET_ORDER_V2"
}
This file DOES NOT exist. Do not use V1 comparator/gate or archived draft hashes.
Actual GT semantic schema and score remain untested until this new PASS. If actual
schema is missing constraints, report GT_SEMANTIC_SCHEMA_REQUIRED. If a valid score
is below75%, analyze mismatches only; never tune model/serializer to score.
