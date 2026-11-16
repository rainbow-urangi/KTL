"""Post-hoc diagnostics only: business labels never enter representation/clustering."""
from collections import defaultdict,Counter
from itertools import combinations
from model.workflow_candidate_v1.src.analysis import business_evaluation
from model.workflow_candidate_v1.src.features import normalized_path


def business_summary(workflows,labels,streams,metadata):
    base=business_evaluation(workflows,labels,streams,metadata)
    cluster_bus=defaultdict(set);bu_clusters=defaultdict(set)
    for w,c in zip(workflows,labels):
        for e in streams[w['stream_index']][w['begin']:w['end']]:
            bu=metadata[(e['source_dataset'],e['event_id'])]['business_unit_id']
            cluster_bus[int(c)].add(bu);bu_clusters[bu].add(int(c))
    merged={pair for bus in cluster_bus.values() for pair in combinations(sorted(bus),2)}
    base['merged_bu_pairs']=len(merged)
    base['merged_bu_pair_list']=[list(p) for p in sorted(merged)]
    base['fragmented_bus']=sum(len(cs)>1 for cs in bu_clusters.values())
    base['bu_all_fragment_clusters']={bu:sorted(cs) for bu,cs in sorted(bu_clusters.items())}
    base['primary_fragmented_bus']=sum(len(set(v['execution_clusters'].values()))>1 for v in base['by_business'].values())
    return base


def process_audit(tables,workflows,streams,metadata):
    raw={e['event_id']:e for stream in streams for e in stream}
    owners={e['event_id']:metadata[(e['source_dataset'],e['event_id'])]['business_unit_id'] for stream in streams for e in stream}
    paths=defaultdict(list);wbus={};families={}
    for w in workflows:
        ids=w['source_event_evidence'];wbus[w['workflow_instance_id']]={owners[i] for i in ids}
        counts=Counter(normalized_path(raw[i]['page_url']) for i in ids)
        families[w['workflow_instance_id']]=min(counts,key=lambda p:(-counts[p],p))
    for s in tables['process_steps']:paths[s['process_instance_id']].append(s['node_id'])
    rows=[];collisions=[];hybrids=[];variants=[]
    for model in tables['process_models']:
        pid=model['process_model_id']
        instance_ids=[i['process_instance_id'] for i in tables['process_instances'] if i['process_model_id']==pid]
        bus=set().union(*(wbus[i] for i in instance_ids))
        family={families[i] for i in instance_ids}
        unique_paths={tuple(paths[i]) for i in instance_ids}
        edge_bu=defaultdict(set);edge_instances=defaultdict(set);triples=set()
        for wid in instance_ids:
            seq=paths[wid]
            triples.update(tuple(seq[i:i+3]) for i in range(len(seq)-2))
            for a,b in zip(seq,seq[1:]):
                edge_bu[(a,b)].update(wbus[wid]);edge_instances[(a,b)].add(wid)
            variants.append(dict(process_model_id=pid,workflow_instance_id=wid,node_sequence=seq,business_units=sorted(wbus[wid]),source='post_hoc only'))
        local_collision=[]
        for node in tables['process_nodes']:
            if node['process_model_id']!=pid:continue
            evidence=node['source_event_evidence'];methods=defaultdict(set)
            for eid in evidence:
                if raw[eid].get('api_method'):methods[raw[eid]['api_method'].upper()].add(owners[eid])
            # Same graph node erases HTTP verb distinction; capture even within one BU.
            read=set().union(*(v for k,v in methods.items() if k in ('GET','HEAD'))) if any(k in ('GET','HEAD') for k in methods) else set()
            write=set().union(*(v for k,v in methods.items() if k in ('POST','PATCH','PUT','DELETE'))) if any(k in ('POST','PATCH','PUT','DELETE') for k in methods) else set()
            if read and write:
                cross=any(a!=b for a in read for b in write)
                record=dict(process_model_id=pid,node_id=node['node_id'],methods={k:sorted(v) for k,v in methods.items()},cross_business=cross,source_event_evidence=evidence)
                collisions.append(record);local_collision.append(record)
        local_hybrids=[]
        for (a,b),left in edge_bu.items():
            for (b2,c),right in edge_bu.items():
                if b!=b2 or (a,b,c) in triples or not left.isdisjoint(right):continue
                record=dict(process_model_id=pid,node_sequence=[a,b,c],left_business_units=sorted(left),right_business_units=sorted(right),left_source_instances=sorted(edge_instances[(a,b)]),right_source_instances=sorted(edge_instances[(b,c)]))
                hybrids.append(record);local_hybrids.append(record)
        upstream=[wid for wid in instance_ids if len(wbus[wid])>1]
        destructive=any(r['cross_business'] for r in local_collision) or bool(local_hybrids) or bool(upstream)
        if len(bus)<=1:classification='SINGLE_BUSINESS'
        elif destructive or len(family)>1:classification='B_MIXING_RISK'
        else:classification='A_FAMILY_WITH_PRESERVED_VARIANTS'
        canonical=model['canonical_instance_id']
        rows.append(dict(process_model_id=pid,business_units=sorted(bus),instance_count=len(instance_ids),distinct_observed_paths=len(unique_paths),same_dominant_page_family=len(family)==1,
                         classification=classification,all_observed_paths_reconstructable=all(paths[i] for i in instance_ids),
                         cross_business_method_collision_nodes=sum(r['cross_business'] for r in local_collision),all_read_write_collision_nodes=len(local_collision),
                         cross_business_unobserved_triples=len(local_hybrids),upstream_mixed_workflows=upstream,
                         canonical_business_units=sorted(wbus[canonical]),noncanonical_business_units=sorted(bus-wbus[canonical]),
                         output_note='Existing adapter exports one observed medoid path; union graph does not itself execute a hybrid. Variant selection for M02/M03 remains unverified.'))
    return dict(summary={'mixed_models':sum(len(r['business_units'])>1 for r in rows),'A_models':sum(r['classification'].startswith('A_') for r in rows),'B_models':sum(r['classification'].startswith('B_') for r in rows),
                         'cross_business_method_collision_nodes':sum(r['cross_business'] for r in collisions),'all_read_write_collision_nodes':len(collisions),'cross_business_unobserved_triples':len(hybrids),
                         'upstream_mixed_workflow_count':len({w for r in rows for w in r['upstream_mixed_workflows']}),'official_m02_computed':False},
                models=rows,node_collisions=collisions,unobserved_cross_business_triples=hybrids,variants=variants)
