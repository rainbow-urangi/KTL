"""Frozen intent/state comparison. Missing semantic proof is unmatched, not guessed.
Distinct Accuracy/Completeness numerators; state evidence never creates an intent.
"""
import math
from .m02_logical_comparator import validate_truth,normalize,subject,align,LogicalSchemaError

CONTRACT='M02_USER_CONFIRMED_V1'
VERSION='m02-user-confirmed-comparator-2-causal-semantics'
RULES=dict(contract=CONTRACT,version=VERSION,
 intent_mapping='ORDERED_ONE_TO_ONE_TYPED_ACTION_TARGET_CONTEXT',
 state_mapping='COMPLETION_ATTRIBUTE_ON_ALREADY_MATCHED_COMMIT_NO_GENERATED_STEP_DUPLICATION',
 accuracy='UNIQUE_MATCHED_GENERATED_INTENTS_OVER_ALL_SCOPED_GENERATED_INTENTS',
 completeness='DISTINCT_INCLUDED_ORIGINAL_GT_INTENT_AND_STATE_REQUIREMENTS_OVER_ALL_REQUIRED',
 insufficient='VALID_INPUT_MISSING_OR_AMBIGUOUS_PROOF_UNMATCHED_AND_MISSING_WITH_REASONS',
 invalid='INPUT_SCHEMA_HASH_GATE_FAILURE_UNAVAILABLE_NO_FABRICATED_RESULT',
 context='EXPLICIT_RAW_FORM_CONTEXT_WITH_OWNER_CONFIRMED_SCREEN_ALIASES_NO_URL_LOOKUP')
INTENT_ACTIONS={'ENTER_CONTEXT':{'MENU_ENTER'},'SELECT_OBJECT':{'SELECT'},
 'INPUT_INFORMATION':{'INPUT'},'INITIATE_REGISTRATION':{'REGISTER'},'COMMIT_REGISTRATION':{'REGISTER'},
 'SAVE_INFORMATION':{'SAVE'},'INSPECT_COMPLETION':{'RESULT_CHECK'},'END_WORKFLOW':{'SELECT','CONFIRM'}}

def state_requirement(requirement):
 return (requirement['logical_role']=='END_WORKFLOW' and requirement.get('end_definition')!={'kind':'EXPLICIT_END_CONTROL'}) or (requirement['logical_role']=='INSPECT_COMPLETION' and requirement.get('declared_action_type')!='RESULT_CHECK')

def canonical(value):
 value=normalize(value)
 for group in ALIAS_GROUPS:
  if value in group:return group[0]
 return value

ALIAS_GROUPS=tuple(tuple(normalize(v) for v in g) for g in (('일일업무','일일보고'),('주간업무','주간보고')))

def form_context(step):
 # An explicit raw popup title supplies semantic context; URL never supplies aliases.
 values=set()
 for e in step.get('evidence',[]):
  if e.get('event_id') not in step.get('source_event_ids',[]):raise LogicalSchemaError('Raw context source missing')
  title=(e.get('popup') or {}).get('active_popup_title','')
  if isinstance(title,str) and title.endswith(' 등록'):
   values.add(canonical(title[:-3]))
 existing=canonical(step.get('business_context'))
 if len(values)==1:
  value=next(iter(values))
  # Only owner-approved logical screen names specialize a broader menu context.
  # Other popup object labels must not replace an existing valid menu context.
  return value if any(value in group for group in ALIAS_GROUPS) else (existing or value)
 return existing if not values else ''

def context_matches(step,r):
 physical=r.get('physical_screen')
 if physical:
  field={'page_path':'menu_page','page_title':'page_title','popup_title':'popup_title'}.get(physical['kind'])
  actual=step.get(field,'') if field else (step.get('menu') or {}).get('selected_path_text','')
  if physical['kind']=='page_path':
   if actual!=physical['value']:return False
  elif normalize(actual)!=normalize(physical['value']):return False
 value=form_context(step)
 return bool(value) and value in {canonical(r['logical_context']['name']),*(canonical(x) for x in r['logical_context'].get('allowed_aliases',[]))}

def completion_supported(step,completion):
 if completion.get('causal_rule')!='EXPLICIT_CAUSAL_ID':return False
 if completion.get('kind') in ('SUCCESS_POPUP','UI_OUTCOME'):return True
 if completion.get('kind')!='WRITE_SUCCESS_FORM_CLOSE':return False
 # Re-run the generic raw-chain check rather than trust a declared outcome kind.
 from copy import deepcopy
 from .m02_causal_form_completion import recover
 evidence=step.get('evidence',[]);ids=[e['event_id'] for e in evidence]
 required=[completion.get(k) for k in ('write_source_event_id','http_source_event_id','source_event_id')]
 if any(x not in ids or x not in step.get('source_event_ids',[]) for x in required):return False
 if len(set(ids))!=len(ids):return False
 candidate=deepcopy(step);candidate['completion_evidence']=[]
 candidate.setdefault('generated_step_id',step.get('id','validation'))
 result=dict(raw_evidence_ledger=deepcopy(evidence),raw_event_disposition=[dict(event_id=eid,generated_step_ids=[],source_node_ids=[]) for eid in ids],processes=[dict(business_steps=[candidate])])
 recover(result)
 return any(all(c.get(k)==completion.get(k) for k in ('kind','source_event_id','write_source_event_id','http_source_event_id')) for c in candidate['completion_evidence'])

def calendar_date_selection(step):
 if step.get('selection_kind')!='CALENDAR_CELL':return False
 proof=step.get('selection_provenance') or {};events={e['event_id']:e for e in step.get('evidence',[])}
 click=events.get(proof.get('click_source_event_id'));popup=events.get(proof.get('popup_source_event_id'))
 if not click or not popup or any(e['event_id'] not in step.get('source_event_ids',[]) for e in (click,popup)):return False
 if click['event_id'] not in step.get('intent_source_event_ids',[]):return False
 # Use the same generic raw serializer, no GT/model input, to reject unsupported metadata.
 from .m02_business_abstraction import validated_popup_opener
 import re
 grid=click.get('grid') or {};target=(popup.get('popup') or {}).get('target_popup') or {}
 positions={e['event_id']:i for i,e in enumerate(step.get('evidence',[]))}
 interactions={}
 for e in events.values():
  iid=e.get('event',{}).get('interaction_id')
  if iid:interactions.setdefault((e['session_id'],iid),set()).add(e['event_id'])
 opener,_=validated_popup_opener(popup,events,positions,interactions)
 return (opener==click['event_id'] and click.get('event',{}).get('action')=='click'
  and not click.get('popup',{}).get('active_popup_id') and grid.get('detected') is True
  and bool(re.search(r'(^|[. #_>\-])calendar([. #_>\-]|$)',grid.get('grid_selector',''),re.I))
  and bool(click.get('element_text')) and grid.get('cell_value')==click['element_text']
  and any(str(target.get('title','')).lower().endswith(v) for v in (' 등록',' 작성',' register',' create',' add')))

# Generic temporal target ontology, not business/GT sentence aliases. Week is distinct.
DATE_TARGETS={normalize(x) for x in ('날짜','date','calendar date')}

def successful_form(step):
 if step.get('action_type') not in ('SAVE','REGISTER','UPDATE') or step.get('intent_phase')!='COMMIT':return []
 proof=[]
 for c in step.get('completion_evidence',[]):
  eid=c.get('source_event_id')
  if eid not in step.get('source_event_ids',[]) or not any(e.get('event_id')==eid for e in step.get('evidence',[])):raise LogicalSchemaError('Completion provenance missing')
  if completion_supported(step,c) and type(c.get('raw_order')) is int and c['raw_order']>step.get('last_intent_order',-1):proof.append(eid)
 return proof

from .m02_generic_preservation import same_live_form

def prepare(generated):
 # Add interpretation attributes, never events, steps, field values, or source IDs.
 from copy import deepcopy
 result=deepcopy(generated)
 for process in result['processes']:
  steps=sorted(process['procedures'],key=lambda s:s['comparison_order'])
  for i,s in enumerate(steps):
   s['required_input_proof']=[]
   if s.get('action_type')!='INPUT' or not s.get('form_identity') or not s.get('fields'):continue
   for w in steps[i+1:]:
    if w.get('action_type') in ('REGISTER','CANCEL','UNRESOLVED') and w.get('intent_phase')!='COMMIT':break
    if w.get('action_type') not in ('SAVE','REGISTER','UPDATE'):continue
    if (w.get('form_identity')==s['form_identity'] and w.get('execution_ids')==s.get('execution_ids')
      and (w.get('source_process_ids')==s.get('source_process_ids') or same_live_form(s,w)) and w.get('matching_eligible')
      and w.get('resolution_status')=='RESOLVED' and form_context(w)==form_context(s)):
     proof=successful_form(w)
     if proof:s['required_input_proof']=[{'write_step_id':w['id'],'success_source_event_ids':proof,'rule':'OWNER_CONFIRMED_SUCCESS_IMPLIES_REQUIRED_FIELDS'}]
    break
 return result

def intent_state(step,r):
 if state_requirement(r):return 'STATE_ATTRIBUTE_NOT_INTENT'
 if not step.get('matching_eligible') or step.get('resolution_status')!='RESOLVED':return 'UNRESOLVED_OR_MIXED_INTENT'
 role=r['logical_role']
 if step['action_type'] not in INTENT_ACTIONS.get(role,set()):return 'ACTION_MISMATCH'
 if r.get('declared_action_type') and step['action_type']!=r['declared_action_type']:return 'DECLARED_ACTION_MISMATCH'
 if not context_matches(step,r):return 'MISSING_OR_DIFFERENT_DIRECT_CONTEXT'
 if role in ('INITIATE_REGISTRATION','COMMIT_REGISTRATION'):
  if step.get('intent_phase')!=('INITIATE' if role=='INITIATE_REGISTRATION' else 'COMMIT'):return 'UNKNOWN_OR_DIFFERENT_REGISTRATION_PHASE'
 forms=[r['source_label'],*r['allowed_aliases']]
 if role=='INPUT_INFORMATION':
  return 'MATCH' if step.get('fields') and step.get('required_input_proof') else 'MISSING_SAME_FORM_SUCCESS_PROOF'
 if role=='SELECT_OBJECT':
  from .m02_weekly_date_contract import temporal_target_state
  state=temporal_target_state(step,forms,subject,normalize,role)
  if state is not None:return state
 if role=='SELECT_OBJECT' and calendar_date_selection(step):
  return 'MATCH' if any(subject(x,role) in DATE_TARGETS for x in forms) else 'TARGET_TYPE_MISMATCH'
 target=step.get('business_object') if role=='INPUT_INFORMATION' and step.get('business_object') else step.get('target_field_label')
 if role=='ENTER_CONTEXT':return 'MATCH' if canonical(target) in {canonical(x) for x in forms} else 'TARGET_MISMATCH'
 return 'MATCH' if subject(target,role) and subject(target,role) in {subject(x,role) for x in forms} else 'TARGET_MISMATCH'

def evaluate(generated,truth,roles):
 generated=prepare(generated)
 requirements=validate_truth(truth,roles)
 processes=generated.get('processes')
 if not isinstance(processes,list):raise LogicalSchemaError('Generated process list missing')
 actual={p['id']:p for p in processes}
 if len(actual)!=len(processes):raise LogicalSchemaError('Duplicate process identity')
 total=defined=correct=included=0;seen=set();evidence=[];summaries=[];uncertainties=[]
 for pid in dict.fromkeys([*requirements,*actual]):
  steps=actual.get(pid,{}).get('procedures',[]);steps=sorted(steps,key=lambda s:s['comparison_order']);req=requirements.get(pid,[])
  ids=[s.get('id') for s in steps]
  if any(not x or x in seen for x in ids) or len(set(ids))!=len(ids):raise LogicalSchemaError('Duplicate/missing step identity')
  seen.update(ids)
  if len({s['comparison_order'] for s in steps})!=len(steps):raise LogicalSchemaError('Duplicate comparison order')
  if req:
   executions=[s.get('execution_ids',[]) for s in steps if s.get('matching_eligible')]
   if any(len(x)!=1 for x in executions) or len({x[0] for x in executions})>1:raise LogicalSchemaError('Ambiguous execution comparison; no best-instance selection')
  total+=len(steps);defined+=len(req)
  states=[[intent_state(s,r) for r in req] for s in steps];hits=align(states);direct_steps={steps[i]['id'] for i in hits.values()}
  own_included=0;last_order=-1;used_state_aspects=set()
  for j,r in enumerate(req):
   step=steps[hits[j]] if j in hits else None;match_kind='INTENT' if step else None;proof=[];reason=None
   if state_requirement(r):
    candidates=[]
    next_order=min((steps[i].get('intent_order',-1) for k,i in hits.items() if k>j),default=float('inf'))
    for k,i in hits.items():
     write=steps[i]
     if k>=j or write['action_type'] not in ('SAVE','REGISTER','UPDATE') or write.get('intent_phase')!='COMMIT' or not context_matches(write,r):continue
     # Only the latest current operation can prove its terminal normal state.
     pending=any(s.get('intent_order',-1)>write.get('intent_order',-1) and s['action_type'] in ('INPUT','SAVE','REGISTER','UPDATE','UNRESOLVED','CANCEL')
        and (not s.get('business_context') or normalize(s['business_context'])==normalize(write.get('business_context'))) for s in steps)
     if r['logical_role']=='END_WORKFLOW' and pending:continue
     for completion in write.get('completion_evidence',[]):
      eid=completion.get('source_event_id');order=completion.get('raw_order')
      if eid not in write['source_event_ids'] or not any(e.get('event_id')==eid for e in write.get('evidence',[])):raise LogicalSchemaError('Completion source provenance missing')
      if not completion_supported(write,completion):continue
      if (write['id'],r['logical_role']) in used_state_aspects:continue
      if type(order) is not int or order<=write.get('last_intent_order',-1) or order<last_order or order>=next_order:continue
      candidates.append((order,write,completion))
    if candidates:
     order,step,completion=min(candidates,key=lambda item:(item[0],item[1]['id']));proof=[completion['source_event_id']];match_kind='STATE_ATTRIBUTE';last_order=order;used_state_aspects.add((step['id'],r['logical_role']))
    else:reason='MISSING_MATCHED_WRITE_OR_DIRECT_COMPLETION_STATE'
   elif step:last_order=max(last_order,step.get('last_intent_order',step.get('intent_order',-1)))
   else:
    reasons=sorted({row[j] for row in states if row[j]!='ACTION_MISMATCH'})
    reason='|'.join(reasons) or 'NO_TYPED_DIRECT_INTENT'
   covered=step is not None;own_included+=covered
   if not covered:uncertainties.append(dict(process_id=pid,required_step_id=r['required_step_id'],reason=reason,treatment='MISSING_NOT_GUESSED_SUCCESS'))
   evidence.append(dict(process_id=pid,required_step_id=r['required_step_id'],ground_truth_step=r['source_label'],
    required_logical_role=r['logical_role'],required_included=covered,direct_match=match_kind=='INTENT',match_kind=match_kind or 'MISSING',
    detected_id=step['id'] if step else '',detected_step=step['target_field_label'] if step else '',
    source_event_ids=step['source_event_ids'] if step else [],source_node_ids=step['source_node_ids'] if step else [],
    completion_source_event_ids=proof,input_completion_proof=step.get('required_input_proof',[]) if step else [],missing_reason=reason))
  own_correct=len(direct_steps);correct+=own_correct;included+=own_included
  if req:
   accuracy=100*own_correct/len(steps) if steps else None;completeness=100*own_included/len(req)
   summaries.append(dict(business_unit_id=pid,generated_count=len(steps),required_count=len(req),matched_count=own_correct,
    included_required_count=own_included,unmatched_count=len(steps)-own_correct,missing_count=len(req)-own_included,
    accuracy=accuracy,completeness=completeness,score=math.sqrt(accuracy*completeness) if accuracy is not None else None,
    status='COMPLETED_WITH_MISSING_EVIDENCE' if own_included<len(req) else 'COMPLETED'))
 if not total or not defined:raise LogicalSchemaError('No generated/required data; numeric measurement unavailable')
 accuracy=100*correct/total;completeness=100*included/defined
 return math.sqrt(accuracy*completeness),len(requirements),dict(accuracy=accuracy,completeness=completeness,
  correctly_mapped=correct,evaluated_procedures=total,included_required=included,defined_required=defined,
  formula='sqrt(Accuracy * Completeness)',auxiliary_evidence_counted=False,matching_method=CONTRACT,
  per_business_unit=summaries,semantic_uncertainties=uncertainties),evidence
