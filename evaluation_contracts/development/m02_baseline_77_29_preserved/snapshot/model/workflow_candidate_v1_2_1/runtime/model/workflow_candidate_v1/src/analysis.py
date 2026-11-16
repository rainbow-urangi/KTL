"""Prediction-only segmentation, unsupervised clustering and post-hoc diagnostics."""
from collections import Counter, defaultdict
import json
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score, davies_bouldin_score
from .features import event_vector, structure, target_role, normalized_path


def boundary_metrics(labels, predicted, masks, tolerance=1):
    tp=fp=fn=0
    for y,p,m in zip(labels,predicted,masks):
        actual=[i for i in range(1,len(y)) if m[i] and y[i]]
        guesses=[i for i in range(1,len(p)) if m[i] and p[i]]
        # Sorted one-to-one matching maximizes matches within fixed index tolerance.
        a=b=matches=0
        while a<len(actual) and b<len(guesses):
            if guesses[b]<actual[a]-tolerance:b+=1
            elif actual[a]<guesses[b]-tolerance:a+=1
            else:matches+=1;a+=1;b+=1
        tp+=matches;fp+=len(guesses)-matches;fn+=len(actual)-matches
    precision=tp/(tp+fp) if tp+fp else 0.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    return dict(precision=precision,recall=recall,f1=2*precision*recall/(precision+recall) if precision+recall else 0.0,
                tp=tp,fp=fp,fn=fn,predicted_boundary_count=tp+fp,true_boundary_count=tp+fn,tolerance_events=tolerance)


def segments(streams, predicted, probabilities=None):
    result=[]
    for s,(stream,cuts) in enumerate(zip(streams,predicted)):
        starts=[0]+[i for i in range(1,len(stream)) if cuts[i]]
        for begin,end in zip(starts,starts[1:]+[len(stream)]):
            ev=stream[begin:end]
            result.append(dict(workflow_instance_id=f'WF-{len(result)+1:04}',stream_index=s,begin=begin,end=end,
                               start_event_id=ev[0]['event_id'],end_event_id=ev[-1]['event_id'],
                               start_time=ev[0]['event_time'],end_time=ev[-1]['event_time'],event_count=len(ev),
                               source_dataset=ev[0]['source_dataset'],source_session_id=ev[0]['session_id'],
                               boundary_confidence=float(probabilities[s][begin]) if probabilities is not None and begin else None,
                               boundary_source='neural_prediction' if begin else 'source_session_start',
                               source_event_evidence=[e['event_id'] for e in ev]))
    return result


def segmentation_metrics(workflows, streams, metadata):
    owners=defaultdict(set);predowners={};total=Counter()
    for stream in streams:
        for e in stream:total[metadata[(e['source_dataset'],e['event_id'])]['execution_id']]+=1
    for w in workflows:
        counter=Counter(metadata[(e['source_dataset'],e['event_id'])]['execution_id'] for e in streams[w['stream_index']][w['begin']:w['end']])
        predowners[w['workflow_instance_id']]=counter
        for owner in counter:owners[owner].add(w['workflow_instance_id'])
    exact=sum(len(c)==1 and next(iter(c.values()))==total[next(iter(c))] for c in predowners.values())
    return dict(predicted_workflow_count=len(workflows),reference_execution_count=len(total),correct_segmentation_exact=exact,
                over_segmented_execution_count=sum(len(v)>1 for v in owners.values()),
                extra_fragments=sum(max(0,len(v)-1) for v in owners.values()),
                under_segmented_workflow_count=sum(len(v)>1 for v in predowners.values()),
                merged_execution_excess=sum(max(0,len(v)-1) for v in predowners.values()))


def unitnorm(x):
    return x/max(float(np.linalg.norm(x)),1e-8)


def represent(workflows, streams, hidden, config):
    embeddings=[]; signatures=[]
    for w in workflows:
        s,a,b=w['stream_index'],w['begin'],w['end']
        h=hidden[s][a:b]
        neural=unitnorm(np.concatenate([h.mean(axis=0),h.max(axis=0)]))
        ev=streams[s][a:b]
        structural=unitnorm(np.mean([event_vector(e,config,config['structural_embedding_dim']) for e in ev],axis=0))
        weight=config['neural_embedding_weight']
        embeddings.append(unitnorm(np.concatenate([np.sqrt(weight)*neural,np.sqrt(1-weight)*structural])))
        sig={k:[] for k in ('page','action','api')}
        for e in ev:
            st=structure(e,config)
            for k in sig:
                val=st[k] if k!='api' else st['method']+' '+st['api'] if st['api'] else ''
                if val and (not sig[k] or sig[k][-1]!=val):sig[k].append(val)
        signatures.append(sig)
    return np.asarray(embeddings),signatures


def cluster(embeddings, config):
    """Threshold search uses embedding geometry only, never business metadata."""
    candidates=[];best=None
    for threshold in config['cluster_distance_thresholds']:
        labels=AgglomerativeClustering(n_clusters=None,distance_threshold=threshold,affinity='cosine',linkage='average').fit_predict(embeddings)
        counts=Counter(int(x) for x in labels);k=len(counts)
        valid=1<k<len(labels)
        sil=float(silhouette_score(embeddings,labels,metric='cosine')) if valid else None
        dbi=float(davies_bouldin_score(embeddings,labels)) if valid else None
        singleton=sum(n==1 for n in counts.values())/len(labels)
        objective=sil-0.1*singleton if valid else None
        record=dict(threshold=threshold,cluster_count=k,silhouette=sil,dbi=dbi,singleton_fraction=singleton,objective=objective,cluster_sizes=dict(counts))
        candidates.append(record)
        if objective is not None and (best is None or objective>best[0]):best=(objective,labels,record)
    if best is None:
        labels=np.zeros(len(embeddings),dtype=int)
        chosen=dict(threshold=None,cluster_count=1,silhouette=None,dbi=None,reason='No valid unsupervised threshold')
    else:_,labels,chosen=best
    return labels,dict(mode='DEVELOPMENT',official_m06=False,selection='max cosine silhouette - 0.1 * singleton fraction; no BU metadata',selected=chosen,candidates=candidates)


def edit_similarity(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        new=[i]
        for j,y in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=new
    return 1-row[-1]/max(len(a),len(b),1)


def similarities(workflows,embeddings,signatures):
    return [dict(workflow_a=workflows[i]['workflow_instance_id'],workflow_b=workflows[j]['workflow_instance_id'],
                 cosine_similarity=float(embeddings[i]@embeddings[j]),
                 **{k+'_sequence_similarity':edit_similarity(signatures[i][k],signatures[j][k]) for k in ('page','action','api')})
            for i in range(len(workflows)) for j in range(i+1,len(workflows))]


def business_evaluation(workflows, clusters, streams, metadata):
    """Called only after unsupervised clustering is complete."""
    votes=defaultdict(Counter);cluster_bu=defaultdict(Counter);workflow_owners={}
    for w,c in zip(workflows,clusters):
        own=Counter()
        for e in streams[w['stream_index']][w['begin']:w['end']]:
            row=metadata[(e['source_dataset'],e['event_id'])]
            votes[row['execution_id']][int(c)]+=1
            cluster_bu[int(c)][row['business_unit_id']]+=1
            own[row['business_unit_id']]+=1
        workflow_owners[w['workflow_instance_id']]=dict(own)
    primary={eid:min(v,key=lambda c:(-v[c],c)) for eid,v in votes.items()}
    meta_by_exec={r['execution_id']:r for r in metadata.values()}
    by_bu=defaultdict(list)
    for eid,c in primary.items():by_bu[meta_by_exec[eid]['business_unit_id']].append((eid,c))
    consistency={bu:dict(execution_clusters=dict(sorted(vals)),all_three_same_cluster=len(vals)==3 and len({v for _,v in vals})==1,
                         pair_consistency=sum(a[1]==b[1] for i,a in enumerate(vals) for b in vals[i+1:])/3) for bu,vals in sorted(by_bu.items())}
    pairs=[]
    bus=sorted(by_bu)
    for i,a in enumerate(bus):
        for b in bus[i+1:]:
            collisions=sum(ca==cb for _,ca in by_bu[a] for _,cb in by_bu[b])
            pairs.append(dict(business_a=a,business_b=b,same_cluster_execution_pairs=collisions,total_execution_pairs=len(by_bu[a])*len(by_bu[b])))
    pairs.sort(key=lambda r:(-r['same_cluster_execution_pairs'],r['business_a'],r['business_b']))
    requested=[('BU07','BU09'),('BU07','BU11'),('BU09','BU11'),('BU14','BU17'),('BU14','BU20'),('BU17','BU20'),('BU04','BU05'),('BU12','BU13'),('BU15','BU16'),('BU18','BU19')]
    return dict(attribution='event-overlap plurality per execution; ties lowest cluster ID; fragments remain in segmentation diagnostics',
                same_bu_three_repetitions_consistent=sum(r['all_three_same_cluster'] for r in consistency.values()),business_count=len(by_bu),
                by_business=consistency,cluster_event_weighted_purity={str(c):max(v.values())/sum(v.values()) for c,v in cluster_bu.items()},
                overall_event_weighted_purity=sum(max(v.values()) for v in cluster_bu.values())/sum(sum(v.values()) for v in cluster_bu.values()),
                mixed_business_cluster_count=sum(len(v)>1 for v in cluster_bu.values()),cluster_business_event_counts={str(c):dict(v) for c,v in cluster_bu.items()},
                confusion_pairs=pairs,requested_pair_analysis=[p for p in pairs if (p['business_a'],p['business_b']) in requested],workflow_business_overlap=workflow_owners)


def action(e):
    it=e.get('interaction_type','');role=target_role(e)
    if it in ('route_change','page_view') or (it=='click' and role=='navigation'):return 'page_entry'
    if it=='popup_open':return 'detail_open'
    if it=='popup_close':return 'detail_close'
    if it in ('input','change','paste'):return 'input'
    if it=='submit':return 'submit_save'
    if it=='api_transaction':return 'api_confirmation' if e.get('api_status_code','').startswith('2') else 'api_failure'
    if it=='click':return 'selection'
    return None


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
            signature=(a,page,target)
            if steps and steps[-1]['signature']==signature:
                steps[-1]['evidence'].append(e['event_id']);continue
            steps.append(dict(signature=signature,evidence=[e['event_id']]))
        previous=None;instance_steps[wid]=[]
        for order,step in enumerate(steps,1):
            a,page,target=step['signature'];key=(pid,step['signature'])
            if key not in node_lookup:
                node_lookup[key]=f'{pid}-N{sum(k[0]==pid for k in node_lookup)+1:03}'
                tables['process_nodes'].append(dict(process_model_id=pid,node_id=node_lookup[key],action=a,page_path=page,target_role=target,source_event_evidence=[]))
            nid=node_lookup[key]
            node=next(n for n in tables['process_nodes'] if n['node_id']==nid)
            node['source_event_evidence'].extend(step['evidence'])
            tables['process_steps'].append(dict(process_instance_id=wid,process_model_id=pid,step_order=order,node_id=nid,action=a,page_path=page,target_role=target,source_dataset=w['source_dataset'],source_session_id=w['source_session_id'],source_event_evidence=step['evidence']))
            instance_steps[wid].append(nid)
            if a=='input':tables['node_inputs'].append(dict(process_instance_id=wid,node_id=nid,step_order=order,input_value='<redacted>',source_event_evidence=step['evidence']))
            if previous:edges[(pid,previous,nid)].append(wid)
            previous=nid
        tables['process_instances'].append(dict(process_instance_id=wid,process_model_id=pid,start_event_id=w['start_event_id'],end_event_id=w['end_event_id'],event_count=w['event_count'],source_dataset=w['source_dataset'],source_session_id=w['source_session_id']))
    tables['process_edges']=[dict(process_model_id=pid,source_node_id=a,target_node_id=b,occurrence_count=len(ids),source_instance_evidence=ids) for (pid,a,b),ids in sorted(edges.items())]
    for r in tables['process_models']:r['canonical_node_sequence']=instance_steps[canonical[r['process_model_id']]]
    return tables
