"""Owner-confirmed temporal meaning, 2026-11-08. Not a GT ID/value mapping.
Source: Sentinel_1fa9caa9bfbc8191a82dbff36eeac339.
No changes to alignment, scoring, requirements or default-value policy.
"""
def verified_date_picker(step):
    if step.get('selection_kind')!='DATE_PICKER_DAY':return False
    from .m02_generic_preservation import date_picker_proof
    from .m02_business_abstraction import validated_popup_opener
    evidence=step.get('evidence',[]);lookup={e['event_id']:e for e in evidence}
    if len(lookup)!=len(evidence):return False
    proof=step.get('selection_provenance') or {};click=lookup.get(proof.get('click_source_event_id'))
    if not click or click['event_id'] not in step.get('intent_source_event_ids',[]):return False
    if any(eid not in step.get('source_event_ids',[]) for eid in lookup):return False
    positions={e['event_id']:i for i,e in enumerate(evidence)};interactions={};validated={}
    for e in evidence:
        iid=e.get('event',{}).get('interaction_id')
        if iid:interactions.setdefault((e['session_id'],iid),set()).add(e['event_id'])
    for e in evidence:
        if e.get('event',{}).get('action')=='popup_open':
            source,reason=validated_popup_opener(e,lookup,positions,interactions)
            validated[e['event_id']]=dict(valid=source is not None,source_event_id=source,reason=reason)
    actual=date_picker_proof(click,evidence,positions,validated)
    return bool(actual and actual==proof)

def temporal_target_state(step,forms,subject,normalize,role):
    if not verified_date_picker(step):return None
    targets={subject(x,role) for x in forms}
    if targets & {normalize(x) for x in ('날짜','date','calendar date')}:return 'MATCH'
    title=normalize((step.get('selection_provenance') or {}).get('parent_popup_title',''))
    if title in {normalize('주간업무 등록'),normalize('주간보고 등록')} and targets & {normalize(x) for x in ('대상 주차','주차','target week','week')}:
        return 'MATCH'
    return 'TARGET_TYPE_MISMATCH'
