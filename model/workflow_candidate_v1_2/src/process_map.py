"""HTTP method를 보존하는 압축 process map 생성기."""
from collections import defaultdict
import numpy as np
from model.workflow_candidate_v1.src.analysis import action
from model.workflow_candidate_v1.src.features import normalized_path,target_role

def process_maps(workflows,clusters,streams,embeddings):
    tables={name:[] for name in ('process_models','process_nodes','process_edges','process_instances','process_steps','node_inputs')}
    node_lookup={};edges=defaultdict(list);canonical={};instance_steps={}
    for c in sorted(set(int(c) for c in clusters)):
        indices=np.flatnonzero(clusters==c)
        medoid=int(indices[np.argmax((embeddings[indices]@embeddings[indices].T).mean(axis=1))])
        pid=f'PM-{c+1:03}'
        tables['process_models'].append(dict(process_model_id=pid,cluster_id=c,instance_count=len(indices),canonical_instance_id=workflows[medoid]['workflow_instance_id'],canonical_policy='cosine medoid observed procedure; variants retained in graph',mode='DEVELOPMENT'))
        canonical[pid]=workflows[medoid]['workflow_instance_id']
    for w,c in zip(workflows,clusters):
        pid=f'PM-{int(c)+1:03}';wid=w['workflow_instance_id'];steps=[]
        for e in streams[w['stream_index']][w['begin']:w['end']]:
            a=action(e)
            if not a:continue
            page=normalized_path(e.get('page_url',''))
            endpoint=normalized_path(e.get('api_path',''))
            target=endpoint if a.startswith('api_') else target_role(e)
            # Adjacent input controls become one business-level input step.
            method=e.get('api_method','').upper() if endpoint else ''
            signature=(a,method,endpoint,page,target)
            if steps and steps[-1]['signature']==signature:
                steps[-1]['evidence'].append(e['event_id']);continue
            steps.append(dict(signature=signature,evidence=[e['event_id']]))
        previous=None;instance_steps[wid]=[]
        for order,step in enumerate(steps,1):
            a,method,endpoint,page,target=step['signature'];key=(pid,step['signature'])
            if key not in node_lookup:
                node_lookup[key]=f'{pid}-N{sum(k[0]==pid for k in node_lookup)+1:03}'
                tables['process_nodes'].append(dict(process_model_id=pid,node_id=node_lookup[key],action=a,http_method=method,normalized_endpoint=endpoint,page_path=page,target_role=target,source_event_evidence=[]))
            nid=node_lookup[key]
            node=next(n for n in tables['process_nodes'] if n['node_id']==nid)
            node['source_event_evidence'].extend(step['evidence'])
            tables['process_steps'].append(dict(process_instance_id=wid,process_model_id=pid,step_order=order,node_id=nid,action=a,http_method=method,normalized_endpoint=endpoint,page_path=page,target_role=target,source_dataset=w['source_dataset'],source_session_id=w['source_session_id'],source_event_evidence=step['evidence']))
            instance_steps[wid].append(nid)
            if a=='input':tables['node_inputs'].append(dict(process_instance_id=wid,node_id=nid,step_order=order,input_value='<redacted>',source_event_evidence=step['evidence']))
            if previous:edges[(pid,previous,nid)].append(wid)
            previous=nid
        tables['process_instances'].append(dict(process_instance_id=wid,process_model_id=pid,start_event_id=w['start_event_id'],end_event_id=w['end_event_id'],event_count=w['event_count'],source_dataset=w['source_dataset'],source_session_id=w['source_session_id']))
    tables['process_edges']=[dict(process_model_id=pid,source_node_id=a,target_node_id=b,occurrence_count=len(ids),source_instance_evidence=ids) for (pid,a,b),ids in sorted(edges.items())]
    for r in tables['process_models']:r['canonical_node_sequence']=instance_steps[canonical[r['process_model_id']]]
    return tables
