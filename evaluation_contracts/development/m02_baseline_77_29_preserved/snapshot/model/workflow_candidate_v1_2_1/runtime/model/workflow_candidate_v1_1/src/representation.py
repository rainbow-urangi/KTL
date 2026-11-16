"""Label-free hybrid sequence representation; no new neural training."""
import hashlib
import json
import re
from collections import Counter
import numpy as np
from model.workflow_candidate_v1.src.features import normalized_path, target_role
from model.workflow_candidate_v1.src.analysis import unitnorm


def collapse(sequence):
    out=[]
    for token in sequence:
        if token and (not out or token!=out[-1]):out.append(token)
    return out


def sequence_vector(sequence, config):
    """Adjacent repeats collapsed; log counts avoid long input bursts dominating."""
    sequence=collapse(sequence)
    tokens=Counter()
    for order,weight in zip(config['sequence_ngram_orders'],config['sequence_ngram_weights']):
        grams=Counter(json.dumps(sequence[i:i+order],ensure_ascii=False,separators=(',',':')) for i in range(len(sequence)-order+1))
        for gram,count in grams.items():tokens[f'{order}:{gram}']+=weight*np.log1p(count)
    if not tokens:tokens['<empty>']=1.0
    v=np.zeros(config['structural_dimension'],dtype=np.float32)
    for token,weight in sorted(tokens.items()):
        digest=hashlib.sha256(token.encode()).digest()
        v[int.from_bytes(digest[:8],'big')%len(v)]+=(1 if digest[8]&1 else -1)*weight
    return unitnorm(v)


def generic_actions(e):
    """Only observable structure; opening a modal alone does not imply detail or create."""
    it=e.get('interaction_type','');method=e.get('api_method','').upper()
    result=[it] if it and it not in ('collector_boot','popup_structure','screen_change','page_close') else []
    if it in ('input','change','paste'):result.append('input')
    if it=='submit':result.append('submit_save')
    if it=='click':result.append('select:'+target_role(e))
    if it=='popup_open':result.append('modal_open')
    if it=='popup_close':result.append('modal_close')
    if method:
        result.append('http:'+method)
        if method=='GET':
            path=normalized_path(e.get('api_path',''))
            result.append('read_detail' if path.endswith('/:id') else 'read_collection_or_resource')
        elif method=='POST':result.append('create_or_command')
        elif method in ('PATCH','PUT'):result.append('update_or_command')
        elif method=='DELETE':result.append('delete')
    # Generic URL role tokens, never an endpoint-to-business mapping.
    tokens=set(re.split(r'[/_-]',normalized_path(e.get('page_url',''))))
    for token,role in [('new','create_view'),('create','create_view'),('edit','edit_view'),('detail','detail_view'),('list','list_view')]:
        if token in tokens:result.append(role)
    return result


def components(workflows,streams,hidden,existing,config):
    rows={k:[] for k in ['existing','neural','page','action','api']};evidence=[]
    for w,legacy in zip(workflows,existing):
        si,a,b=w['stream_index'],w['begin'],w['end'];ev=streams[si][a:b];h=hidden[si][a:b]
        page=collapse([normalized_path(e.get('page_url','')) for e in ev])
        actions=collapse([x for e in ev for x in generic_actions(e)])
        api=collapse([e['api_method'].upper()+' '+normalized_path(e['api_path']) for e in ev if e.get('api_method') and e.get('api_path')])
        rows['existing'].append(unitnorm(legacy));rows['neural'].append(unitnorm(np.concatenate([h.mean(0),h.max(0)])))
        for name,seq in [('page',page),('action',actions),('api',api)]:rows[name].append(sequence_vector(seq,config))
        evidence.append(dict(workflow_instance_id=w['workflow_instance_id'],page_sequence=page,action_sequence=actions,api_sequence=api,source_event_evidence=w['source_event_evidence']))
    return {k:np.asarray(v,dtype=np.float32) for k,v in rows.items()},evidence


def combine(blocks,weights):
    if not weights or any(w<=0 for w in weights.values()) or not np.isclose(sum(weights.values()),1):
        raise ValueError('Positive block weights summing to one required')
    vectors=np.concatenate([np.sqrt(weight)*blocks[name] for name,weight in weights.items()],axis=1)
    return np.asarray([unitnorm(v) for v in vectors],dtype=np.float32)
