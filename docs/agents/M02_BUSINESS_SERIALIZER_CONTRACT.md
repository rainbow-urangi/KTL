# Business Process Serializer v3 — DEVELOPMENT pre-GT contract

## Authority and gate

FINAL PDF pp6–7 and R&D_COMPLIANCE.md govern the formula and inclusion of all generated procedures. On 2026-11-03 the user reports KTL confirmed that comparison units are business-semantic procedures in the final generated map, and HTTP request/response occurrences may be evidence rather than separate procedures. This is user-reported clarification, not a new signed KTL document. It supersedes WAITING_FOR_KTL_CONFIRMATION for this boundary decision. No GT comparison occurs until separate independent verification PASS. No model or OFFICIAL freeze is performed.

## Pure inputs and minimum categories

serialize(models, nodes, occurrences) accepts persisted canonical map sequences, graph nodes and frozen instance occurrences only. It has no I/O or GT parameter. It neither reads TD-04 nor accepts business labels, aliases, score feedback, execution exceptions or hand-picked steps. Categories are the minimum supported by the actual typed output; SEARCH and COMPLETION_CONFIRM are not inferred from a GET or successful response. No unsupported new action or missing procedure is fabricated.

| rule_id | Input pattern | Output business action | Merge / split condition | Auxiliary condition |
|---|---|---|---|---|
| BPS-01 | page_entry | SCREEN_ENTRY | one typed occurrence; no merge/split | none |
| BPS-02 | input | INPUT | one typed occurrence; no merge/split | none |
| BPS-03 | selection | SELECT | one typed occurrence; no merge/split | none |
| BPS-04 | detail_open | DETAIL_OPEN | one typed occurrence; no merge/split | none |
| BPS-05 | detail_close | DETAIL_CLOSE | separate from save or confirmation | none |
| BPS-06 | submit_save | SUBMIT_SAVE | separate from close or confirmation | none |
| BPS-07 | api_confirmation | no business step; HTTP evidence | no association inferred | all such occurrences retained unlinked |
| BPS-08 | api_failure | no business step; failed HTTP evidence | no association inferred | failures retained identically |
| BPS-09 | other action | UNRESOLVED business step | retained conservatively; no merge/split | none |

This is type-based serialization, not a claim that adjacent UI actions are causally identical. No UI steps are selected or compressed by score. All UI/unknown occurrences, repeated nodes, unpaired processes and failed actions remain. HTTP is never automatically a business procedure. There is no adjacency-based attachment: current heuristic recent_action_fallback does not establish causal ownership. All HTTP evidence remains at process level with linked_generated_step_id=null and explicit unlinked status. A future linkage/merge rule would require a separately frozen generic nonheuristic operation contract and fresh verification, not GT score feedback.

## Evidence and conservation

Resolve canonical_instance_id + original sequence order to exactly one occurrence, verify node/process and action/method/endpoint/page/target fields. Reject missing, duplicate, empty or mismatched provenance. Each business step retains generated_step_id, contiguous step_order, source_occurrence_order, source_instance_id, action_type, menu_page, target, HTTP method/endpoint if present, source_event_ids, source_node_ids, full occurrence_evidence/evidence, graph_node_evidence, source_action, rule ID and semantic limitation. Graph unions are auxiliary and cannot replace occurrence event IDs. Every HTTP record retains the same original row/node/event/method/endpoint fields, its original position and a technical_evidence_id. GET/HEAD/OPTIONS remain HTTP_READ; POST/PUT/PATCH/DELETE HTTP_WRITE; other methods HTTP_UNKNOWN. 2xx is not completion and failure is not discarded.

For every canonical process, input occurrences = generated business steps + unlinked technical evidence, disjoint by original occurrence order. Every canonical occurrence appears exactly once in this partition. Complete source_occurrence_evidence also preserves noncanonical instance rows; graph_evidence preserves all aggregate nodes, with neither substituted for canonical steps. Raw event existence and session agreement require independent audit against the immutable raw source; this serializer does not invent event content.

## Denominator, determinism and freeze

Accuracy denominator is ALL business_steps across ALL processes, including unknown and unmatched steps. Technical records are evidence rather than denominator steps per clarified contract, never direct matches. No evaluator/web integration is certified by this development snapshot. Inputs determine process/sequence order and IDs; canonical sorted JSON is byte deterministic, no timestamps/randomness. Writer hashes rules, implementation, frozen map/node files, source occurrences and companion prediction identity, and output before comparison. It has no evaluator/GT access. Snapshot stage PRE_GT_COMPARISON, score_computed=false, verification=PENDING_INDEPENDENT_VERIFICATION. Previous snapshots are preserved. All current readiness statements are pending independent verification, not a scoring authorization.
