# M02 recovery common rules v1

User authorization: Sentinel_76b45d0dd4fc8191825faf8003bd1039. DEVELOPMENT only. No model, threshold, feature, clustering, matcher or GT changes. Previous snapshots and results remain immutable.

- BA-TREE-MENU: an exact clicked menu label captured by generic_dom_tree is a menu only with nav ancestry. A repeated list/table without navigation proof remains unresolved.
- BA-DIALOG-DESCENDANT-INPUT: a captured dialog with actual editable child events (explicit is_inside_popup or selector descendant proof) is a form, even without a form tag. Only input after the same-page opening and before a popup/page lifecycle boundary proves that opening; reused popup IDs and future openings cannot supply past form evidence. Captured popup identity and raw editable event IDs are preserved in form_detection_evidence. Popup opener/menu references are recorded in context_provenance.
- BA-VALIDATED-FORM-OPENER: append the explicitly linked form-open observation to its registration intent as context evidence, not another intent. Conflicting, missing, cross-page, or stale opener references remain rejected. The unchanged matcher applies only previously approved aliases.
- BA-LINKED-SUCCESS-ACK: clicking the exact declarative text inside an already causally validated success popup (div/span/p with no captured element role) is mechanical context, like its confirmation button. It cannot invent success, bypass an unknown operation, or count as an additional direct match. Unlinked text and buttons with unknown semantics remain independent unresolved actions. A preceding validated popup opening, matching title and page, and no intervening user intent, input focus, page change or popup lifecycle boundary are required. Future openings and reused popup IDs cannot revive an earlier write.

No workflow-specific branch, screen-title mapping or route-based alias is added. Calendar-date semantics are not guessed from numbers; absent raw menu/success/week evidence remains RAW_EVIDENCE_MISSING.

The new server option is DEVELOPMENT m02_recovery_data_01 only. Generation reuses independently reproduced frozen predictions and rebuilds semantic/serializer layers before any GT access. Source raw and collection-order-based execution ownership are immutable. All generated steps remain scoped and counted; no best-instance selection.

Manifest must be reviewed independently before a PASS gate is written. Required checks: generic_contract_check, gt_leakage_check, provenance_check, regression_check. Only afterward run scripts/freeze_m02_recovery_rules.py. Measurement is blocked until exact-manifest PASS and post-PASS freeze exist. No real measurement was performed while preparing this implementation.
