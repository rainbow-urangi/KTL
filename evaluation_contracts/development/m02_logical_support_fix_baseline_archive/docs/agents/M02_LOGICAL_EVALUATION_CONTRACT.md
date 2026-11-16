# M02 logical evaluation contract v1 — precomparison, DEVELOPMENT

Authority: FINAL pp6–7, user-confirmed business-procedure unit and five-target scope,
authoritative original workflow text, independent audit
M02_BLOCKED_MEASUREMENT_GT_REVIEW_VERIFICATION.txt. Physical typed screen identifiers
on every GT step are a former V2 implementation choice, NOT a FINAL requirement.
This contract corrects that evaluation-boundary condition; no model, serializer,
generated step, ownership, required procedure or approved original GT is changed.

## Inputs / invariants
Frozen final canonical generated action_type,target_field_label/target,menu,page,
order and eligibility only; original TD-04 ID,label,menu/screen name,order,aliases;
GT-only compiled logical role sidecar. Never raw events, node/evidence sidecars,
HTTP outcomes, source-field labels as alternative matching answers, scores or best
instances. Source provenance is retained in CSV but never promoted to a match.
All scoped generated steps remain denominator, including mixed once/ineligible and
UNRESOLVED. All original GT procedures remain required. One-to-one ordered alignment;
no grouping/compression/deletion/step regeneration or source-specific exceptions.

## Logical context, physical constraints
Each original menu_screen_name is the logical business workflow context, not a claim
of physical equality at every subprocedure. A candidate must assert that context in
its FINAL menu leaf, or if menu is absent, its exact final page title/name. There is
no URL-slug translation, substring route inference, arbitrary inherited previous page
or context wildcard. An explicit different menu is incompatible; missing comparable
context is unknown. If it could affect an otherwise compatible unmatched procedure,
comparison is INCOMPARABLE/null, not a manufactured zero score.
Any explicit source action_type remains binding; a conflict with inferred logical
intent requires clarification and blocks rather than overriding that action.
Physical path/title/menu/popup constraints are enforced only when authoritatively
present in source GT. Missing physical constraints alone do not invalidate TD-04.
URL path equality preserves case. Popup constraint can use only a final popup action's
explicit target; no raw popup evidence lookup. Wrong declared physical screen remains
a negative case even with a correct logical menu.

## Source-only logical roles and sufficient direct conditions
These are EVALUATION roles, not additions to serializer action taxonomy.
- ENTER_CONTEXT: first named menu/context in source flow. Direct final PAGE_ENTER or
  MENU_ENTER must assert the named context. SELECT of a similarly named content item
  alone is not promoted into entry. Physical navigation mechanism need not be specified.
- INITIATE_REGISTRATION: source 등록 before input/save. Direct REGISTER of declared
  registration target, with no INPUT since previous final write and an INPUT before
  the next write in the same explicit final logical context. This expresses starting
  registration, NOT a guessed popup-open or completed write. No phase wildcard.
- COMMIT_REGISTRATION: source 등록 after input. Direct REGISTER of declared target
  after INPUT since previous final write. Initiation cannot satisfy commit and vice
  versa. Unknown phase on a potentially matching step is incomparable, not zero.
- SELECT_OBJECT: direct SELECT of the whole source named object. A numeric control
  click alone does not become date/week selection by raw evidence or assumed aliases.
- INPUT_INFORMATION: source is one logical named information-entry procedure. One
  direct INPUT must explicitly assert the WHOLE source information object. Exact
  object semantics derive symmetrically by removing only the action suffix 입력/input
  from GT and final target. Qualifiers and all object words remain. A phone/name/email
  field is not the whole client-information procedure; multiple fields cannot be
  unioned into one match or used for multiple numerator entries. This assesses map
  procedure meaning, NOT value correctness/all mandatory form fields. The source does
  not enumerate such fields; none are invented. If a future authoritative definition
  requires explicit field coverage, that changes the evaluation contract and must be
  separately fixed/frozen before comparison, not inferred from generated fields.
- SAVE_INFORMATION: direct SAVE of declared save target under logical context;
  no submit/HTTP2xx/passive message substitution.
- INSPECT_COMPLETION: direct RESULT_CHECK expressing source 완료 확인 under
  declared logical context after a final write. CONFIRM acknowledgement and passive
  success messages are different and do not automatically match. No check is created.
- END_WORKFLOW: original 종료 is a logical end whose physical realization is not
  exhaustively defined. A sufficient direct proof is the final business step being
  SELECT or CONFIRM explicitly targeting the source end command/declared alias in
  the same logical context. INPUT/SAVE/REGISTER/UNRESOLVED with that text do not match.
  Position alone or arbitrary POPUP_CLOSE never proves end. If no sufficient direct
  end proof exists, the source does not let us reject other realizations as failures:
  return END_REALIZATION_UNSPECIFIED, entire metric null, keep requirement/denominator.
  A future authoritative direct_end_definition={kind:EXPLICIT_END_CONTROL} can make
  the explicit-control definition exhaustive; none is invented for current source.

Completion and termination are logical map procedures; no statement of successful
execution/real window closure is inferred. Sufficient direct conditions do not claim
that source requires an actual control named 종료; other realizations remain unknown.
This conditional end handling is intentional substantive uncertainty, not a hidden
physical-schema demand or an END taxonomy repair. Four current end requirements stay
disclosed as conditional. Do not turn them into missing/zero without valid semantics.

## Targets / aliases / order
Preserve original27IDs,labels,order,menu names and aliases verbatim. Only symmetric
input/selection action-suffix parsing forms logical objects; no added synonyms,
business-specific dictionaries, substring similarity, embeddings or output-derived
aliases. Other targets use original declared text/aliases exactly. Alias scope is
business process + logical role + context; conflicting same-scope aliases block.
Action-compatible intent, context, target and order are jointly necessary; never
label-only. Registration phase uses final action/order only and is generic, computed
without GT labels or scores. Alignment maximizes compatible ordered one-to-one
matches with deterministic ties retaining earlier final generated candidates. It
never chooses a process instance/map or changes source/generated units.

## Unknowns and gate
Unknown GT role, missing logical name, inconsistent provenance, unknown potential
context/phase/completion scope, or unmatched conditional end => incomparable/null.
Known different action/target/menu/declared physical screen is incompatible, not a
wildcard. UNRESOLVED/mixed stay ineligible and denominator. No missing evidence is
converted into a guessed success or fabricated zero. Source body does not define
all physical realization details; uncertainty is reported with procedure IDs.

Freeze ORIGINAL unchanged generated artifacts + generation/model inputs, this logical
contract, GT-only role compiler, logical comparator/adapter, all executing local
utilities/router/storage/server/config, source GT + opaque hashes, source-text/Library
provenance. Preserve old V2 snapshot, dependencies and blocked run. New manifest+new
independent PASS for LOGICAL_BUSINESS_PROCEDURE_V1 required. Old V2 PASS cannot open
this path. No actual alignment/score before new independent PASS; synthetic tests
only. Post-PASS actual incomparability remains null and must be reported, not tuned.
