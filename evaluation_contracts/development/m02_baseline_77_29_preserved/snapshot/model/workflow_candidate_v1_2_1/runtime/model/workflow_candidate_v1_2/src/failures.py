"""Boundary-only inspection before post-hoc business attribution."""
from collections import defaultdict,Counter
from model.workflow_candidate_v1.src.features import structure
from model.workflow_candidate_v1.src.data import time_of


def inspect_errors(streams,metadata,labels,predicted,workflows,config):
    true_events=defaultdict(set);membership=defaultdict(set);owners={};ordered=[]
    for stream in streams:
        for e in stream:
            k=(e['source_dataset'],e['event_id']);owner=metadata[k]['execution_id']
            if owner not in true_events:ordered.append(owner)
            true_events[owner].add(k)
    anonymous={eid:f'EXECUTION-{i+1:03}' for i,eid in enumerate(ordered)}
    for w in workflows:
        keys={(w['source_dataset'],eid) for eid in w['source_event_evidence']}
        owners[w['workflow_instance_id']]={metadata[k]['execution_id'] for k in keys}
        for k in keys:membership[metadata[k]['execution_id']].add(w['workflow_instance_id'])
    predicted_sets=[{(w['source_dataset'],eid) for eid in w['source_event_evidence']} for w in workflows]
    errors=[];windows=[]
    for owner,keys in true_events.items():
        if keys in predicted_sets:continue
        ids=membership[owner];categories=[]
        if len(ids)>1:categories.append('OVER_SEGMENTATION')
        if any(len(owners[wid])>1 for wid in ids):categories+=['UNDER_SEGMENTATION','CROSS_WORKFLOW_MERGE']
        ev=[(si,i,e) for si,s in enumerate(streams) for i,e in enumerate(s) if (e['source_dataset'],e['event_id']) in keys]
        si,start,a=ev[0];_,end,b=ev[-1]
        if start and not predicted[si][start]:categories.append('START_BOUNDARY_ERROR')
        if end+1<len(streams[si]) and not predicted[si][end+1]:categories.append('END_BOUNDARY_ERROR')
        errors.append(dict(anonymous_execution=anonymous[owner],start_event_id=a['event_id'],end_event_id=b['event_id'],categories=categories,overlapping_workflows=sorted(ids)))
    for si,(stream,y,p) in enumerate(zip(streams,labels,predicted)):
        for i,e in enumerate(stream):
            if bool(y[i])==bool(p[i]):continue
            cause=('TERMINAL_LIFECYCLE_AS_START' if e['interaction_type']=='page_close' else 'POST_POPUP_CONTEXT_ACTION_TOO_EARLY' if p[i] else 'NEW_MODAL_TRIGGER_WITHOUT_ROUTE_MISSED')
            for j in range(max(0,i-10),min(len(stream),i+11)):
                cur=stream[j];st=structure(cur,config)
                windows.append(dict(error_event_id=e['event_id'],error_type='FALSE_POSITIVE' if p[i] else 'FALSE_NEGATIVE',generic_cause=cause,relative_event=j-i,event_id=cur['event_id'],source_dataset=cur['source_dataset'],session_id=cur['session_id'],event_time=cur['event_time'],page_path=st['page'],interaction_type=st['action'],target_role=st['role'],http_method=st['method'],normalized_endpoint=st['api'],response_status=cur['api_status_code'],inactivity_gap=time_of(cur)-time_of(stream[j-1]) if j else 0,reference_boundary=bool(y[j]),predicted_boundary=bool(p[j])))
    return errors,windows,anonymous
