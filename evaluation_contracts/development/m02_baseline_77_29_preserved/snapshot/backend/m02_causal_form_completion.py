"""Strict recorded write-success plus form-close evidence; never success-UI synthesis."""
import copy
VERSION='causal-write-form-close-1'
RULE_ID='GENERIC-EXPLICIT-WRITE-2XX-SAME-FORM-CLOSE'
EXPLICIT={'explicit','explicit_event_id','explicit_interaction_id','correlation_id'}
# Exhaustive lifecycle actions recognized by the raw abstraction. A close at
# the candidate endpoint is allowed; any lifecycle boundary inside breaks it.
LIFECYCLE_BARRIERS=frozenset({'popup_open','popup_close','route_change','page_view','screen_change','page_close','collector_boot'})
INTERVENING_INTENTS=frozenset({'input','change','paste','submit','click'})

def recover(result):
 events=result['raw_evidence_ledger'];lookup={e['event_id']:e for e in events};pos={e['event_id']:i for i,e in enumerate(events)}
 dispositions={e['event_id']:e for e in result['raw_event_disposition']}
 for process in result['processes']:
  for step in process['business_steps']:
   if step['action_type'] not in ('SAVE','REGISTER','UPDATE') or step.get('intent_phase')!='COMMIT':continue
   intents=step['intent_source_event_ids'];write=lookup[intents[-1]];wid=write['event_id'];interaction=write['event'].get('interaction_id');pid=write['popup'].get('active_popup_id')
   if not pid:continue
   def compatible(e):return e['session_id']==write['session_id'] and e['page_path']==write['page_path'] and bool(write['page_path'])
   def linked(refs,iref=None):
    refs=[r for r in refs if r]
    return bool(refs or iref) and all(r in intents for r in refs) and (not iref or bool(interaction) and iref==interaction)
   apis=[];contradictory_response=False
   for e in events[pos[wid]+1:]:
    api=e.get('api') or {}
    if e['session_id']!=write['session_id']:continue
    if str(e.get('http_method','')).upper() not in ('POST','PUT','PATCH'):continue
    try:valid_status=200<=int(e.get('http_status'))<300
    except (TypeError,ValueError):valid_status=False
    same_write=linked([api.get('related_event_id')],api.get('related_interaction_id'))
    # A recorded non-success/unknown response for this write invalidates the
    # composite even if another response succeeded. Never select the best one.
    if same_write and not valid_status:contradictory_response=True
    if same_write and valid_status and compatible(e) and api.get('related_strategy') in EXPLICIT:apis.append(e)
   if contradictory_response or len(apis)!=1:continue
   api=apis[0]
   for close in events[pos[api['event_id']]+1:]:
    if not compatible(close):continue
    action=close['event'].get('action');pc=close['popup'];target=pc.get('target_popup') or {}
    if action in ('route_change','page_view','screen_change','input','change','submit'):break
    if action=='click':break
    if action!='popup_close':continue
    if target.get('popup_id')!=pid:break
    refs=[pc.get('closer_event_id'),target.get('closer_event_id'),close['event'].get('cause_event_id'),close['event'].get('related_event_id')]
    if not linked(refs,pc.get('closer_interaction_id')):break
    # Existing contradictory failure/outcome or another write prevents closure promotion.
    middle=events[pos[wid]+1:pos[close['event_id']]]
    if any(e['event'].get('action') in LIFECYCLE_BARRIERS|INTERVENING_INTENTS for e in middle if e['session_id']==write['session_id']):break
    if any((e.get('ui_outcome') or {}).get('status') in ('error','failure','failed') for e in middle):break
    for evidence in (api,close):
     eid=evidence['event_id']
     if eid not in step['source_event_ids']:step['source_event_ids'].append(eid);step['evidence'].append(copy.deepcopy(evidence))
     step.setdefault('evidence_roles',{})[eid]='CAUSAL_WRITE_FORM_CLOSE'
     d=dispositions[eid];owners=d.setdefault('generated_step_ids',[])
     if step['generated_step_id'] not in owners:owners.append(step['generated_step_id'])
     d.update(disposition='LINKED_SAME_INTENT_EVIDENCE',generated_step_id=owners[0] if len(owners)==1 else None)
     step['source_node_ids']=sorted(set(step['source_node_ids'])|set(d.get('source_node_ids',[])))
    step['source_event_ids'].sort(key=pos.get)
    step['completion_evidence'].append(dict(kind='WRITE_SUCCESS_FORM_CLOSE',source_event_id=close['event_id'],write_source_event_id=wid,http_source_event_id=api['event_id'],raw_order=pos[close['event_id']],causal_rule='EXPLICIT_CAUSAL_ID',rule_id=RULE_ID,success_ui_asserted=False))
    break
 result['causal_form_completion_version']=VERSION
 return result
