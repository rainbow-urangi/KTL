"""Track A: recover recorded native submitter metadata only. No GT or inference.
Baseline serializer, comparator, model and shared server/UI remain untouched.
"""
import copy,hashlib,json
from .semantic_enrichment import LEXICON,normalized

VERSION='track-a-native-submit-1+causal-form-close-1'
RULES=dict(version=VERSION,source='EXACT_TOP_LEVEL_RAW_PAYLOAD_SUBMITTER_FIELDS_ONLY',
 action='NATIVE_SUBMIT_FORM_WITH_EXACT_UNIQUE_GENERIC_SAVE_REGISTER_UPDATE_VERB',
 phase='NATIVE_FORM_SUBMIT_IS_COMMIT_NOT_FORM_OPEN',
 causality='NO_PRECEDING_CLICK_INFERENCE_FALLBACK_ALREADY_CONSUMED_SUBMIT_FAILS_CLOSED',
 conservation='SAME_INTENT_IDS_NODES_ORDER_OWNERSHIP_ALL_EXISTING_RAW_VALUES_PRESERVED',
 completion='EXPLICIT_WRITE_2XX_AND_CAUSALLY_LINKED_SAME_FORM_CLOSE_ONLY',scope='ALL_BUSINESSES_NO_GT_OR_SCORE_INPUT')
def canonical(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode()
RULES_HASH=hashlib.sha256(canonical(RULES)).hexdigest()

def recover(snapshot,raw_rows):
 result=copy.deepcopy(snapshot);raw_by={str(r['event_id']):r for r in raw_rows}
 if len(raw_by)!=len(raw_rows):raise ValueError('Duplicate raw identity')
 if list(raw_by)!=[e['event_id'] for e in result['raw_evidence_ledger']]:raise ValueError('Raw identity/order mismatch')
 metadata={}
 for eid,row in raw_by.items():
  context=row.get('locators_json') or {}
  if isinstance(context,str):context=json.loads(context)
  payload=context.get('raw_payload') or {}
  fields={k:copy.deepcopy(payload[k]) for k in ('form_id','form_name','submitter_text','submitter_selector') if k in payload}
  if fields:
   fields['source_path']='locators_json.raw_payload'
   fields['relation_context']={k:copy.deepcopy((context.get('relation_context') or {})[k]) for k in ('related_event_id','related_interaction_id','related_strategy','related_action') if k in (context.get('relation_context') or {})}
   metadata[eid]=fields
 def visit(value):
  if isinstance(value,list):return [visit(x) for x in value]
  if not isinstance(value,dict):return copy.deepcopy(value)
  out={k:visit(v) for k,v in value.items()}
  if {'event_id','event','page_path','ui_outcome'}<=set(out) and out['event_id'] in metadata:
   if 'native_submit' in out and out['native_submit']!=metadata[out['event_id']]:raise ValueError('Existing native submit metadata conflict')
   out['native_submit']=copy.deepcopy(metadata[out['event_id']])
  return out
 result=visit(result);lookup={e['event_id']:e for e in result['raw_evidence_ledger']};audit=[]
 for eid,event in lookup.items():
  if event['event'].get('action')!='submit':continue
  info=metadata.get(eid,{});text=normalized(info.get('submitter_text'))
  kinds=[k for k in ('SAVE','REGISTER','UPDATE') if text in {normalized(v) for v in LEXICON[k]}]
  owners=[s for p in result['processes'] for s in p['business_steps'] if eid in s['source_event_ids']]
  strategy=str(info.get('relation_context',{}).get('related_strategy',''))
  own=[s for s in owners if s['intent_source_event_ids']==[eid]]
  if any(s not in own for s in owners) and ('fallback' in strategy.casefold() or 'recent_action' in strategy.casefold()):
   raise ValueError('Unverified fallback submit already consumed; no causal promotion allowed')
  status='NO_UNIQUE_RECORDED_WRITE_VERB'
  if len(kinds)==1 and normalized(event.get('tag'))=='form':
   if len(own)==1 and own[0]['action_type']=='UNRESOLVED':
    step=own[0];step['native_submit_previous_semantics']={k:copy.deepcopy(step.get(k)) for k in ('action_type','intent_phase','target','target_field_label','resolution_status','serializer_rule_id','field_provenance')}
    step.update(action_type=kinds[0],intent_phase='COMMIT',target=info['submitter_text'],target_field_label=info['submitter_text'],
     resolution_status='UNRESOLVED' if step['process_id'] in ('UNMAPPED_RAW','AMBIGUOUS_MODEL_MEMBERSHIP') else 'RESOLVED',
     serializer_rule_id='TRACK-A-RECORDED-NATIVE-SUBMIT',native_submit_evidence=copy.deepcopy(info),
     native_submit_source_event_id=eid)
    step.setdefault('field_provenance',{}).update(action_type='locators_json.raw_payload.submitter_text',target='locators_json.raw_payload.submitter_text',intent_phase='raw event.action=submit and element_tag=form')
    status='RECORDED_NATIVE_COMMIT_RECOVERED'
   elif owners:
    if any(s['action_type']!=kinds[0] or s.get('intent_phase')!='COMMIT' for s in owners):raise ValueError('Conflicting native submit action and existing canonical owner')
    status='EXISTING_WRITE_EVIDENCE_PRESERVED'
   else:status='NO_UNIQUE_OWN_CANONICAL_SUBMIT_INTENT'
  elif len(kinds)==1:status='NATIVE_FORM_TYPE_NOT_PROVEN'
  audit.append(dict(source_event_id=eid,status=status,recorded_submitter_text=info.get('submitter_text'),source_path='locators_json.raw_payload.submitter_text',relationship_strategy=strategy))
 result.update(base_serializer_version=snapshot['serializer_version'],base_serializer_rules_hash=snapshot['serializer_rules_hash'],
  serializer_version=snapshot['serializer_version']+'+'+VERSION,serializer_rules_hash=RULES_HASH,native_submit_recovery_audit=audit)
 from .m02_causal_form_completion import recover as recover_completion
 return recover_completion(result)
