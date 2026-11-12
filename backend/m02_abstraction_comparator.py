"""Frozen intent/state comparison. Missing semantic proof is unmatched, not guessed.
Distinct Accuracy/Completeness numerators; state evidence never creates an intent.
"""
import math
from .m02_logical_comparator import validate_truth,normalize,subject,align,LogicalSchemaError

CONTRACT='BUSINESS_INTENT_STATE_V1'
VERSION='m02-intent-state-comparator-1'
RULES=dict(contract=CONTRACT,version=VERSION,
 intent_mapping='ORDERED_ONE_TO_ONE_TYPED_ACTION_TARGET_CONTEXT',
 state_mapping='COMPLETION_ATTRIBUTE_ON_ALREADY_MATCHED_COMMIT_NO_GENERATED_STEP_DUPLICATION',
 accuracy='UNIQUE_MATCHED_GENERATED_INTENTS_OVER_ALL_SCOPED_GENERATED_INTENTS',
 completeness='DISTINCT_INCLUDED_ORIGINAL_GT_INTENT_AND_STATE_REQUIREMENTS_OVER_ALL_REQUIRED',
 insufficient='VALID_INPUT_MISSING_OR_AMBIGUOUS_PROOF_UNMATCHED_AND_MISSING_WITH_REASONS',
 invalid='INPUT_SCHEMA_HASH_GATE_FAILURE_UNAVAILABLE_NO_FABRICATED_RESULT',
 context='EXACT_RAW_DERIVED_CANONICAL_CONTEXT_NO_URL_ALIASES_NO_AUXILIARY_ANSWER_LOOKUP')
INTENT_ACTIONS={'ENTER_CONTEXT':{'MENU_ENTER','PAGE_ENTER'},'SELECT_OBJECT':{'SELECT'},
 'INPUT_INFORMATION':{'INPUT'},'INITIATE_REGISTRATION':{'REGISTER'},'COMMIT_REGISTRATION':{'REGISTER'},
 'SAVE_INFORMATION':{'SAVE'},'INSPECT_COMPLETION':{'RESULT_CHECK'},'END_WORKFLOW':{'SELECT','CONFIRM'}}

def state_requirement(requirement):
 return (requirement['logical_role']=='END_WORKFLOW' and requirement.get('end_definition')!={'kind':'EXPLICIT_END_CONTROL'}) or (requirement['logical_role']=='INSPECT_COMPLETION' and requirement.get('declared_action_type')!='RESULT_CHECK')

def context_matches(step,r):
 value=normalize(step.get('business_context'))
 physical=r.get('physical_screen')
 if physical:
  field={'page_path':'menu_page','page_title':'page_title','popup_title':'popup_title'}.get(physical['kind'])
  actual=step.get(field,'') if field else (step.get('menu') or {}).get('selected_path_text','')
  if physical['kind']=='page_path':
   if actual!=physical['value']:return False
  elif normalize(actual)!=normalize(physical['value']):return False
 return bool(value) and value in {normalize(r['logical_context']['name']),*(normalize(x) for x in r['logical_context'].get('allowed_aliases',[]))}

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
 target=step.get('business_object') if role=='INPUT_INFORMATION' and step.get('business_object') else step.get('target_field_label')
 if role=='ENTER_CONTEXT':return 'MATCH' if normalize(target) in {normalize(x) for x in forms} else 'TARGET_MISMATCH'
 return 'MATCH' if subject(target,role) and subject(target,role) in {subject(x,role) for x in forms} else 'TARGET_MISMATCH'

def evaluate(generated,truth,roles):
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
      if completion.get('kind') not in ('SUCCESS_POPUP','UI_OUTCOME'):continue
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
    completion_source_event_ids=proof,missing_reason=reason))
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
