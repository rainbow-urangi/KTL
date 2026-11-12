"""Pure provenance-only restoration. No GT, ownership, matching or causal inference.
Original semantic fields/IDs/steps are immutable; only raw-present fields are added.
"""
import copy
from .semantic_enrichment import allowed_event

SCHEMA_VERSION='raw-causal-preservation-1'

def additions(before,after,path=''):
    """Reject any mutation/removal of existing evidence; report additions only."""
    changes=[]
    if isinstance(before,dict) and isinstance(after,dict):
        if not set(before)<=set(after):raise ValueError('Existing evidence field removed: '+path)
        for key,value in after.items():
            current=path+'.'+key if path else key
            if key not in before:changes.append(dict(path=current,value=copy.deepcopy(value)))
            else:changes.extend(additions(before[key],value,current))
    elif before!=after:raise ValueError('Existing evidence field changed: '+path)
    return changes

def restore(snapshot,raw_rows):
    result=copy.deepcopy(snapshot)
    raw=[allowed_event(r) for r in raw_rows]
    lookup={e['event_id']:e for e in raw}
    if len(lookup)!=len(raw):raise ValueError('Duplicate raw event identity')
    ledger=result['raw_evidence_ledger']
    if [e['event_id'] for e in ledger]!=[e['event_id'] for e in raw]:raise ValueError('Raw ledger identity/order mismatch')
    audit=[]
    for event in ledger:
        restored=lookup[event['event_id']]
        changes=additions(event,restored)
        if changes:audit.append(dict(source_event_id=event['event_id'],added_fields=changes))
    def visit(value):
        if isinstance(value,list):return [visit(v) for v in value]
        if not isinstance(value,dict):return copy.deepcopy(value)
        if {'event_id','event','page_path','ui_outcome'}<=set(value):
            eid=value['event_id']
            if eid not in lookup:raise ValueError('Evidence raw identity missing')
            # Sidecar relationship_status remains unchanged; no relationship is made.
            restored=copy.deepcopy(value)
            for key,item in lookup[eid].items():restored[key]=copy.deepcopy(item)
            additions(value,restored)
            return restored
        return {k:visit(v) for k,v in value.items()}
    result=visit(result)
    for process in result['processes']:
        for step in process['business_steps']:
            if not step.get('evidence'):continue
            first=step['evidence'][0]
            if first['event_id']!=step['source_event_ids'][0]:raise ValueError('Step evidence/source order mismatch')
            # Enrichment materialized popup from its first raw source atom.
            # Update only additions, never replace semantic popup text/identity.
            newer=copy.deepcopy(first['popup'])
            additions(step.get('popup',{}),newer)
            step['popup']=newer
    return result,audit
