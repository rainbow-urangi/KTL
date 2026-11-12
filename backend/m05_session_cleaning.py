"""Conservative session-context cleaning v2; no GT or task-based reset.

New predicates only remove collector boot diagnostics, redundant focus runs with
explicit empty pre-paste state, and already-current navigation with no observable
outcome before the next user action. Unknown input state is never treated empty.
The full sequence is batch context, so bounded lookahead is intentional.
"""
import json
import re
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.m05_baseline_adapter import load_rules, predict as baseline_predict

VERSION = 'session-context-cleaning-v2'
CONTEXT_FIELDS = {'session_id','timestamp_utc','action','page','target','tag','text','popup_id',
                  'input_value','selection_start','selection_end','input_type','interaction_id',
                  'related_interaction_id','has_api','has_outcome'}


def context_from_raw(raw, timestamp_utc):
    loc = json.loads(raw.get('locators_json') or '{}')
    ec = loc.get('event_context') or {}; inp = loc.get('input_context') or {}
    payload = loc.get('raw_payload') or {}
    return dict(session_id=raw['session_id'],timestamp_utc=timestamp_utc,
                action=(raw.get('interaction_type') or ec.get('action') or '').lower(),
                page=raw.get('page_url') or '',target=raw.get('target_selector') or '',
                tag=(raw.get('element_tag') or '').lower(),text=' '.join((raw.get('element_text') or '').split()),
                popup_id=ec.get('active_popup_id'), input_value=inp.get('value'),
                selection_start=payload.get('selection_start'),selection_end=payload.get('selection_end'),
                input_type=inp.get('type'),interaction_id=ec.get('interaction_id'),
                related_interaction_id=ec.get('related_interaction_id'),
                has_api=bool(raw.get('api_path') or loc.get('api_context')),
                has_outcome=bool(loc.get('ui_outcome')))


def stamp(c):
    d=datetime.fromisoformat(c['timestamp_utc'].replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('Timezone required')
    return d.timestamp()


def field_key(c):
    return c['session_id'],c['page'],c['popup_id'],c['target'],c['tag']


def nav_key(c):
    # Use generic DOM nav + list-item ancestry, not business labels or routes.
    parts=[p.strip() for p in c['target'].split('>')]
    nav=next((i for i,p in enumerate(parts) if re.match(r'^nav(?:[.#\[:]|$)',p)),None)
    if nav is None or c['action']!='click' or c['popup_id'] or not c['text']: return None
    tail=parts[nav:]
    li=[i for i,p in enumerate(tail) if re.match(r'^li(?:[.#\[:]|$)',p)]
    if li: tail=tail[:li[-1]+1]
    tail=[re.sub(r'\.(?:is-active|active|selected)(?=[.#\[:\s]|$)','',p) for p in tail]
    return tuple(tail),c['text']


def predict(events, rules):
    if not isinstance(events,list): raise ValueError('events list required')
    base=[]; groups={}
    for index,event in enumerate(events):
        if set(event)!={'id','features'} or set(event['features'])!={'case_id','activity','ts','context'}:
            raise ValueError('Only id and approved raw features accepted; labels forbidden')
        c=event['features']['context']
        if set(c)!=CONTEXT_FIELDS or not c['session_id']: raise ValueError('Context schema mismatch')
        stamp(c)
        base.append({'id':event['id'],'features':{k:event['features'][k] for k in ('case_id','activity','ts')}})
        groups.setdefault(c['session_id'],[]).append(index)
    result=baseline_predict(base,rules); preds=result['predictions']
    def remove(index,reason,anchor=None,evidence=None):
        if preds[index]['label']=='KEEP':
            preds[index].update(label='REMOVE',remove_reason=reason,duplicate_of_event_id=None if anchor is None else events[anchor]['id'],rule_evidence_event_ids=[events[k]['id'] for k in (evidence or [])])
    for indices in groups.values():
        indices.sort(key=lambda i:(stamp(events[i]['features']['context']),i))
        cs=[events[i]['features']['context'] for i in indices]
        for pos,(index,c) in enumerate(zip(indices,cs)):
            if c['action']=='collector_boot' and events[index]['features']['activity']=='EVT:collector_boot' and c['tag']=='html' and not c['has_api'] and not c['has_outcome']:
                remove(index,'collector_boot_diagnostic')
        # Focus-only consecutive run. All mutations/keys/popup/other targets break it.
        pos=0
        while pos<len(indices):
            c=cs[pos]
            if c['action']!='click' or c['tag'] not in {'input','textarea'} or not c['target'] or (c['tag']=='input' and c['input_type'] not in {None,'text','search','email','tel','url','password','number'}):
                pos+=1; continue
            end=pos+1
            while end<len(indices) and cs[end]['action']=='click' and field_key(cs[end])==field_key(c) and 0<=stamp(cs[end])-stamp(cs[end-1])<=2 and not cs[end]['has_outcome']:
                end+=1
            # Explicit pre-paste empty value + collapsed 0 selection, same field.
            # Null on clicks is not itself evidence of emptiness; conflicting known
            # values or selection abort this optimization.
            run=cs[pos:end]; nxt=cs[end] if end<len(cs) else None
            empty=(nxt is not None and nxt['action']=='paste' and field_key(nxt)==field_key(c)
                   and 0<=stamp(nxt)-stamp(cs[end-1])<=2 and nxt['input_value']==''
                   and nxt['selection_start']==nxt['selection_end']==0)
            safe=all(x['input_value'] in (None,'') and x['selection_start'] in (None,0) and x['selection_end'] in (None,0) and not x['has_outcome'] for x in run)
            if end-pos>1 and empty and safe and preds[indices[pos]]['label']=='KEEP':
                for k in range(pos+1,end):remove(indices[k],'redundant_empty_field_focus',indices[pos],[indices[pos],indices[end]])
            pos=end
        # A previous same-session nav click immediately followed by an observed
        # route establishes the destination. Keep the original click/route. This
        # is temporal observation, not a fabricated direct causal link.
        destinations={}
        for pos,(index,c) in enumerate(zip(indices,cs)):
            key=nav_key(c)
            if key is None:continue
            nxt=cs[pos+1] if pos+1<len(cs) else None
            if nxt and nxt['action']=='route_change' and 0<=stamp(nxt)-stamp(c)<=2 and nxt['page']!=c['page'] and preds[index]['label']=='KEEP':
                destinations[key]=(nxt['page'],index,indices[pos+1]);continue
            known=destinations.get(key)
            if not known or known[0]!=c['page'] or c['has_outcome'] or nxt is None:continue
            # No intervening UI/API/lifecycle event: the very next event must be
            # another user interaction on the same page, not a refresh/response.
            if nxt['action'] in {'click','input','change','paste','keydown','submit'} and nxt['page']==c['page'] and 0<=stamp(nxt)-stamp(c)<=10:
                remove(index,'current_navigation_no_observed_change',known[1],[known[1],known[2],indices[pos+1]])
    result['model_version']=VERSION
    result['engine_type']='existing_deterministic_rules_with_conservative_session_context'
    return result


def main():
    if len(sys.argv)!=3 or sys.argv[1]!='--model':raise SystemExit('usage: --model CONFIG')
    cfg=json.loads(Path(sys.argv[2]).read_text())
    rules,_=load_rules(cfg['baseline_rules_path'])
    if cfg['rule_version']!=VERSION:raise ValueError('Version mismatch')
    payload=json.load(sys.stdin)
    if set(payload)!={'events'}:raise ValueError('Only events allowed')
    print(json.dumps(predict(payload['events'],rules),ensure_ascii=False,sort_keys=True))
if __name__=='__main__':main()
