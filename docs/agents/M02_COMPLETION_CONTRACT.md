# M02 common normal-completion contract, 2026-11-05

Authority: explicit user clarification delivered to this task via parent delegation. TD-04 종료 means normally completed business state, not a separate click/navigation. For registration/writing: execute write -> normal processing -> visible UI reflected/completed state. Examples include success message, resulting data/list/detail reflection, explicit UI outcome, or automatically closed popup after completed save. An acknowledgement, X close, menu navigation or page exit is not an extra required step unless TD-04 explicitly requires it. Separate 완료 확인 means UI completion display, not mandatory click.

Current deployment route/menu sources must NOT define historical data meaning. Only collection-time raw provenance is admitted. The user clarification is an evaluation interpretation, not GT input to generator/model.

## Minimal implementation

Pure `m02_completion_semantics.extend` accepts only a prior GT-independent serializer snapshot/raw ledger. No GT/process labels/matches/scores are accepted. All prior generated IDs/fields/evidence remain; chronological step_order is updated after inserting genuine raw UI observations. No model inference/retraining, input compression or original artifact overwrite occurs. One previously unclaimed raw UI outcome produces at most one new canonical RESULT_CHECK state, with its own source event ID (source node IDs empty if no model node exists). This is observed state serialization, not copying a write node or synthesizing a user action. All raw evidence remains preserved.

Supported proof is deliberately narrow: explicit affirmative past-tense success message, explicit source_interaction_id to exactly one same-session raw write interaction, same full raw page path, after write, no intervening pending INPUT/write/unresolved action. A generic failure/negation/future/question filter rejects non-success. Current parser supports Korean 저장/등록/수정/처리 and English saved/created/registered/updated success grammar. No application object names, endpoint dictionaries, BU/event exceptions or current UI mappings are used.

HTTP 2xx, GET requery, close or proximity alone is never direct completion. Existing HTTP related_strategy=recent_action_fallback is not upgraded. No general DOM-data identity diff/auto-close causality schema is available, so these user-allowed proof classes remain unresolved unless separately explicit; no guessed success.

Comparator reads the new frozen canonical observation and verifies referenced prior direct eligible completed write in the current execution/operation. REGISTER INITIATE is not a completed write. Exact target label is not required for state requirements: the explicit state observation supplies meaning, with independent logical context and action/eligibility checks. One-to-one ordered alignment remains: one raw success/state cannot match both 完了確認 and 終了 by duplication, and no extra click step is introduced. Missing or unaligned completion proof remains incomparable, not zero. Existing explicit-end-control declarations remain supported only when authoritatively supplied.

URL/location_path menu leaves are technical namespace, yielding UNKNOWN against human GT menus, never automatic conflict/translation. Same full raw page can establish support operation membership only within one proven execution; it cannot itself establish GT menu identity. No context registry learned from GT or current deployed UI. Human menu conflicts remain conflicts. Model/serializer inputs have no GT exposure; GT-only sidecar authoring is separate evaluation code.

## Freeze and gate

New snapshot m02_logical_evaluation_v2_completion stores new serialization/scope, generic rules, original unmodified TD-04 roles, user interpretation, all executing dependencies, model/source bindings and outputs. Old snapshots/results remain preserved. An old independent PASS cannot authorize this manifest. No actual GT comparison until a new independent PASS binds to the exact manifest hash. Synthetic counterexamples only may exercise comparison before that gate.

## Disclosed limitations for independent verification

A raw causal success message is sufficient normal-processing/UI proof; no acknowledgement is needed. Unsupported endpoint/list/auto-close interpretations remain unproven. One-to-one may leave overlapping state requirements unaligned; this is disclosed uncertainty, never duplicate generated evidence. Unknown historical route namespace remains unresolved. Verify no stale write support, cross-session/map/execution repair, conflicting labels override, denominator loss or state duplication.

## C1/C2 independent review correction, revision 3.1

Success requires a complete declarative Korean/English clause, not a past-stem substring. Conditional, future, modal, uncertain, interrogative and instructional markers reject assertion promotion even without question punctuation. Unknown language stays raw. Intervening raw clicks bearing exact SAVE/REGISTER/UPDATE labels use the original generic semantic lexicon; unknown typed submissions and raw input/submit attempts also block stale completion. Same-session/page restriction remains; unrelated pages/sessions and UI lifecycle observations do not blanket-block. No interrupting business step is invented.
