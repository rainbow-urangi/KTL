"""Synthetic-only abstraction/intent-state counterexamples. No actual GT or scores."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backend.semantic_enrichment import allowed_event
from backend.m02_business_abstraction import abstract,RULES_HASH
from backend.m02_abstraction_comparator import evaluate,CONTRACT
from backend.m02_logical_gt import compile_roles
from backend.m02_semantic_scope import scope_steps

def row(eid,action='click',text='',tag='button',page='/opaque',popup=None,form=None,field=None,menu='공통 업무',cause=None,api=None):
 context=dict(event_context=dict(action=action,interaction_id='i-'+eid),element=dict(role='button'),
  menu_context=dict(source='nav',parser='synthetic',selected_label=menu,selected_path_text=menu),
  popup_context=popup or {},input_context=field or {})
 if form:context['input_context'].update(form)
 if cause:context['event_context']['cause_event_id']=cause
 if api:context['api_context']=api
 return dict(event_id=eid,session_id='s',page_url='https://example.invalid'+page,page_title='Product',element_text=text,element_tag=tag,target_selector='#'+eid,locators_json=context,
  api_method=(api or {}).get('method',''),api_path=(api or {}).get('path',''),api_status_code=(api or {}).get('status',''))
def snapshot(rows,maps=None):
 maps=maps or ['p']*len(rows);processes=[]
 for pid in dict.fromkeys(maps):
  processes.append(dict(source_process_id=pid,canonical_instance_id='w-'+pid,
   business_steps=[dict(source_event_ids=[e['event_id']],source_node_ids=['n-'+e['event_id']],action_type='IGNORED_PREDICTION',target='ignored') for e,m in zip(rows,maps) if m==pid],unlinked_technical_evidence=[]))
 return dict(processes=processes,raw_evidence_ledger=[allowed_event(e) for e in rows],technical_evidence_count=0,graph_evidence=[{'synthetic':True}],source_occurrence_evidence=[])
def generate(rows,maps=None):return abstract(snapshot(rows,maps),rows)
def edit(eid,label='Field',form='form-1',purpose='정보 등록',action='change'):
 return row(eid,action,text=label,tag='input',form=dict(form_id=form,form_purpose=purpose),field=dict(id=eid,name=label,type='text',associated_label=label,detected=True))
def form_open(eid,opener,pid='form-popup'):
 return row(eid,'popup_open',tag='div',popup=dict(active_popup_id=pid,opener_event_id=opener,target_popup=dict(popup_id=pid,title='정보 등록',selector_css='form#edit',tag='form',opened_by_event_id=opener)),cause=opener)
def success(eid,opener,message='정보가 저장되었습니다.',pid='success'):
 return row(eid,'popup_open',tag='div',popup=dict(active_popup_id=pid,opener_event_id=opener,target_popup=dict(popup_id=pid,title=message,selector_css='div.notice',tag='div',opened_by_event_id=opener)),cause=opener)
def steps(result):return [s for p in result['processes'] for s in p['business_steps']]

class AbstractionTests(unittest.TestCase):
 def test_same_explicit_form_aggregate_fields_and_focus_not_intent(self):
  rows=[edit('a','Name'),edit('focus','Email',action='click'),edit('b','Email')];result=generate(rows);s=steps(result)
  self.assertEqual(len(s),1);self.assertEqual(s[0]['action_type'],'INPUT')
  self.assertEqual([f['label'] for f in s[0]['fields']],['Name','Email']);self.assertEqual(s[0]['intent_source_event_ids'],['a','b'])
  self.assertEqual(len(result['raw_event_disposition']),3);self.assertEqual(len(result['raw_evidence_ledger']),3)
 def test_different_form_page_purpose_and_missing_identity_not_merged(self):
  for change in ('form','purpose','page','missing'):
   a=edit('a');b=edit('b')
   if change=='form':b['locators_json']['input_context']['form_id']='other'
   if change=='purpose':b['locators_json']['input_context']['form_purpose']='다른 목적 등록'
   if change=='page':b['page_url']='https://example.invalid/other'
   if change=='missing':
    for x in (a,b):x['locators_json']['input_context'].pop('form_id')
   self.assertEqual(len(steps(generate([a,b]))),2,change)
 def test_typed_control_edit_belongs_to_known_form_but_unscoped_selection_stays_independent(self):
  a=edit('a');b=edit('b');b['element_tag']='select'
  self.assertEqual(len(steps(generate([a,b]))),1)
  b['locators_json']['input_context'].pop('form_id')
  self.assertEqual([s['action_type'] for s in steps(generate([a,b]))],['INPUT','SELECT'])
 def test_cross_execution_aggregate_is_mixed_not_repaired_or_duplicated(self):
  rows=[edit('a'),edit('b')];result=generate(rows)
  executions=[dict(execution_id='x',business_unit_id='A',session_id='s',start_event_id='a',end_event_id='a'),dict(execution_id='y',business_unit_id='B',session_id='s',start_event_id='b',end_event_id='b')]
  scoped=scope_steps(result,executions,['A'])
  self.assertEqual(scoped['scope_summary']['total_generated_steps'],1);self.assertEqual(scoped['scope_summary']['mixed_count'],1)
  self.assertEqual(scoped['mixed_steps'][0]['business_unit_ownership'],'CROSS_EXECUTION_MIXED');self.assertFalse(scoped['mixed_steps'][0]['matching_eligible'])
 def test_different_map_same_form_not_merged(self):
  self.assertEqual(len(steps(generate([edit('a'),edit('b')],['p','q']))),2)
 def test_known_dynamic_form_popup_and_inner_form_separation(self):
  rows=[row('register',text='등록'),form_open('open','register')]
  for eid in ('a','b'):
   e=edit(eid);e['locators_json']['input_context'].pop('form_id');e['locators_json']['popup_context']={'active_popup_id':'form-popup'};rows.append(e)
  s=steps(generate(rows));self.assertEqual([x['action_type'] for x in s],['REGISTER','INPUT']);self.assertEqual(s[0]['intent_phase'],'INITIATE');self.assertEqual(len(s[1]['fields']),2)
  rows[2]['locators_json']['input_context']['form_id']='inner-a';rows[3]['locators_json']['input_context']['form_id']='inner-b'
  self.assertEqual(len(steps(generate(rows))),3)
 def test_input_interrupted_by_different_intent_is_not_merged(self):
  self.assertEqual([s['action_type'] for s in steps(generate([edit('a'),row('query',text='조회'),edit('b')]))],['INPUT','QUERY','INPUT'])
 def test_route_popup_and_automatic_outcome_are_context(self):
  rows=[row('route','route_change',tag='html'),row('load','page_view',tag='html'),row('pop','popup_open',tag='div'),row('close','popup_close',tag='div')]
  self.assertEqual(steps(generate(rows)),[]);self.assertEqual(len(generate(rows)['raw_evidence_ledger']),4)
 def test_nonform_detail_user_intent_preserved(self):
  rows=[row('click',text='Record'),row('open','popup_open',popup=dict(opener_event_id='click',target_popup=dict(popup_id='detail',title='상세 내용',opened_by_event_id='click',tag='div')))]
  self.assertEqual([s['action_type'] for s in steps(generate(rows))],['DETAIL_OPEN'])
 def test_explicit_menu_click_preserved_auto_route_not_extra(self):
  rows=[row('menu',text='공통 업무'),row('route','route_change',tag='html')]
  self.assertEqual([s['action_type'] for s in steps(generate(rows))],['MENU_ENTER'])
 def test_popup_success_attaches_to_save_no_result_check_step(self):
  result=generate([row('save',text='저장'),success('done','save')]);s=steps(result)
  self.assertEqual([x['action_type'] for x in s],['SAVE']);self.assertEqual(s[0]['source_event_ids'],['save','done'])
  self.assertEqual(s[0]['completion_evidence'][0]['kind'],'SUCCESS_POPUP');self.assertEqual(len(result['raw_evidence_ledger']),2)
 def test_generic_completion_applies_arbitrary_objects_not_business_ids(self):
  for noun in ('일정','보고서','거래처 정보','자산 정보','arbitrary entity'):
   result=generate([row('w',text='저장'),success('c','w',noun+'가 등록되었습니다.')]);self.assertEqual(len(steps(result)[0]['completion_evidence']),1)
 def test_failure_future_ambiguous_cross_page_and_stale_no_completion(self):
  for variant in ('failure','future','conflict','page','stale','missing','unknown'):
   rows=[row('a',text='저장'),success('done','a')]
   if variant=='failure':rows[1]=success('done','a','저장 실패')
   if variant=='future':rows[1]=success('done','a','will be saved successfully')
   if variant=='conflict':rows.insert(1,row('b',text='저장'));rows[-1]['locators_json']['event_context']['cause_event_id']='b'
   if variant=='page':rows[-1]['page_url']='https://example.invalid/other'
   if variant=='stale':rows.insert(1,edit('new'))
   if variant=='missing':rows[-1]=success('done','missing')
   if variant=='unknown':rows.insert(1,row('unknown',text=''))
   self.assertFalse(any(s['completion_evidence'] for s in steps(generate(rows))),variant)
 def test_read_write_and_recent_fallback_are_preserved_not_completion(self):
  for method in ('GET','POST','PATCH'):
   rows=[row('save',text='저장'),row('http','network',tag='',api=dict(method=method,path='/arbitrary',status=200,related_event_id='save',related_interaction_id='i-save',related_strategy='recent_action_fallback'))]
   result=generate(rows);s=steps(result)
   self.assertEqual(len(s),1);self.assertEqual(s[0]['http_evidence'],[]);self.assertEqual(result['raw_evidence_ledger'][1]['http_method'],method)
 def test_explicit_http_read_write_compatibility_and_endpoint_provenance(self):
  for verb,text,linked in [('GET','조회',True),('POST','저장',True),('GET','저장',False),('POST','조회',False)]:
   rows=[row('intent',text=text),row('http','network',tag='',api=dict(method=verb,path='/api/items/42?view=all',status=200,related_event_id='intent',related_interaction_id='i-intent',related_strategy='explicit_event_id'))]
   result=generate(rows);http=steps(result)[0]['http_evidence'];self.assertEqual(bool(http),linked)
   self.assertEqual(result['raw_evidence_ledger'][1]['http_method'],verb)
   if linked:self.assertEqual(http[0]['normalized_endpoint'],'/api/items/{id}');self.assertEqual(http[0]['raw_endpoint'],'/api/items/42?view=all')
 def test_explicit_submit_and_write_http_same_intent(self):
  submit=row('submit','submit',tag='form',cause='save');submit['locators_json']['event_context']['related_event_id']='save'
  rows=[row('save',text='저장'),submit,row('http','network',tag='',api=dict(method='POST',path='/arbitrary',status=201,related_event_id='save',related_interaction_id='i-save',related_strategy='explicit_event_id')),success('done','save')]
  s=steps(generate(rows));self.assertEqual(len(s),1);self.assertEqual(s[0]['source_event_ids'],['save','submit','http','done']);self.assertEqual(len(s[0]['http_evidence']),1);self.assertEqual(len(s[0]['completion_evidence']),1)
 def test_separate_write_actions_never_merged_and_stale_response_rejected(self):
  s=steps(generate([row('a',text='저장'),row('b',text='저장'),success('old','a')]))
  self.assertEqual(len(s),2);self.assertFalse(s[0]['completion_evidence'])
 def test_success_ack_context_but_independent_result_check_preserved(self):
  ack=row('ack',text='확인',popup=dict(active_popup_id='success'))
  result=generate([row('save',text='저장'),success('done','save'),ack,row('inspect',text='결과 확인')]);s=steps(result)
  self.assertEqual([x['action_type'] for x in s],['SAVE','RESULT_CHECK']);self.assertIn('ack',s[0]['source_event_ids'])
 def test_unknown_user_attempt_retained_and_cancel_is_independent(self):
  s=steps(generate([row('unknown',text=''),row('cancel',text='취소')]))
  self.assertEqual([x['action_type'] for x in s],['UNRESOLVED','CANCEL'])
 def test_purity_determinism_gt_prediction_label_and_score_invariance(self):
  rows=[edit('a'),edit('b'),row('save',text='저장'),success('done','save')];source=snapshot(rows);before=copy.deepcopy((source,rows));expected=abstract(source,rows)
  self.assertEqual(expected,abstract(source,rows));self.assertEqual((source,rows),before)
  for p in source['processes']:
   for s in p['business_steps']:s.update(action_type='WRONG',target='GT-like secret',score=100,ground_truth='forbidden')
  for r in rows:r.update(business_unit_id='forbidden',score=100,ground_truth='forbidden');r['locators_json']['analysis']={'prediction':'forbidden'}
  self.assertEqual(expected,abstract(source,rows));self.assertEqual(expected['serializer_rules_hash'],RULES_HASH)
 def test_generic_repeated_dom_tree_is_not_a_proven_menu(self):
  e=row('tree',text='공통 업무');e['locators_json']['menu_context'].update(source='tree',parser='generic_dom_tree')
  self.assertEqual(steps(generate([e]))[0]['action_type'],'UNRESOLVED')
 def test_source_ids_and_all_raw_dispositions_conserved(self):
  rows=[row('save',text='저장'),success('done','save'),row('route','route_change',tag='html')];result=generate(rows)
  self.assertEqual([e['event_id'] for e in result['raw_evidence_ledger']],['save','done','route']);self.assertEqual({e['event_id'] for e in result['raw_event_disposition']},{e['event_id'] for e in result['raw_evidence_ledger']})
  self.assertTrue(all(e['source_process_ids']==['p'] and e['source_node_ids']==['n-'+e['event_id']] for e in result['raw_event_disposition']))

class IndependentA1A2A3Tests(unittest.TestCase):
 def test_a1_explicit_different_context_same_form_separates(self):
  a=edit('a','Name');b=edit('b','Email')
  a['locators_json']['menu_context'].update(selected_label='Context A',selected_path_text='Context A')
  b['locators_json']['menu_context'].update(selected_label='Context B',selected_path_text='Context B')
  result=steps(generate([a,b]));self.assertEqual(len(result),2)
  self.assertEqual([x['business_context'] for x in result],['Context A','Context B'])
  self.assertEqual([x['intent_source_event_ids'] for x in result],[['a'],['b']])
 def test_a1_unknown_context_never_merge_wildcard(self):
  for missing in ('both','second'):
   a=edit('a');b=edit('b')
   for item in ([a,b] if missing=='both' else [b]):item['locators_json']['menu_context'].update(source='url',parser='location_path',selected_path_text='opaque')
   self.assertEqual(len(steps(generate([a,b]))),2)
  self.assertEqual(len(steps(generate([edit('a'),edit('b')]))),1)
 def test_a1_commit_support_cannot_borrow_other_context_input(self):
  a=edit('a');r=row('register',text='등록',form=dict(form_id='form-1',form_purpose='정보 등록'))
  r['locators_json']['menu_context'].update(selected_path_text='Context B',selected_label='Context B')
  self.assertEqual(steps(generate([a,r]))[-1]['intent_phase'],'UNKNOWN')
  r['locators_json']['menu_context'].update(selected_path_text='공통 업무',selected_label='공통 업무')
  self.assertEqual(steps(generate([a,r]))[-1]['intent_phase'],'COMMIT')
 def test_a2_invalid_opener_never_proves_initiation(self):
  for variant in ('session','page','future','conflict','interaction','fallback','last_user_only'):
   source=row('register',text='등록');opening=form_open('open','register');rows=[source,opening]
   if variant=='session':opening['session_id']='other'
   if variant=='page':opening['page_url']='https://example.invalid/other'
   if variant=='future':rows.reverse()
   if variant=='conflict':
    rows.insert(1,row('different',text='등록'));opening['locators_json']['popup_context']['target_popup']['opened_by_event_id']='different'
   if variant=='interaction':
    rows.insert(1,row('different',text='등록'));opening['locators_json']['popup_context']['opener_interaction_id']='i-different'
   if variant=='fallback':opening['locators_json']['event_context']['related_strategy']='recent_action_fallback'
   if variant=='last_user_only':
    opening['locators_json']['popup_context'].pop('opener_event_id');opening['locators_json']['popup_context']['target_popup'].pop('opened_by_event_id');opening['locators_json']['event_context'].pop('cause_event_id');opening['locators_json']['event_context']['last_user_event_id']='register'
   result=generate(rows);register=next(x for x in steps(result) if x['generated_step_id']=='BA-register')
   self.assertEqual(register['intent_phase'],'UNKNOWN',variant)
   self.assertFalse(result['popup_opener_validation'][0]['valid'],variant)
   self.assertEqual(len(result['raw_evidence_ledger']),len(rows))
 def test_a2_valid_opener_initiation_and_inherited_context_have_proof(self):
  rows=[row('register',text='등록'),form_open('open','register')]
  for eid in ('a','b'):
   e=edit(eid);e['locators_json']['input_context'].pop('form_id');e['locators_json']['popup_context']={'active_popup_id':'form-popup'}
   e['locators_json']['menu_context'].update(source='url',parser='location_path',selected_path_text='opaque');rows.append(e)
  result=generate(rows);s=steps(result);self.assertEqual(s[0]['intent_phase'],'INITIATE');self.assertEqual(len(s),2)
  self.assertEqual(s[1]['business_context'],'공통 업무');self.assertEqual(result['popup_opener_validation'][0]['source_event_id'],'register')
  rows[1]['page_url']='https://example.invalid/other';result=generate(rows)
  self.assertTrue(all(x['business_context']=='' for x in steps(result) if x['action_type']=='INPUT'))
  self.assertEqual(len([x for x in steps(result) if x['action_type']=='INPUT']),2)
 def test_a2_invalid_opener_cannot_prove_detail_intent(self):
  click=row('click',text='Record');opening=row('open','popup_open',page='/different',popup=dict(opener_event_id='click',target_popup=dict(popup_id='detail',title='Details',opened_by_event_id='click')))
  self.assertFalse(any(x['action_type']=='DETAIL_OPEN' for x in steps(generate([click,opening]))))
 def test_a2_interaction_conflict_cannot_be_ignored_by_completion_consumer(self):
  rows=[row('save',text='저장'),row('other',text='저장'),success('done','save')]
  rows[-1]['locators_json']['popup_context']['opener_interaction_id']='i-other'
  result=generate(rows);self.assertFalse(result['popup_opener_validation'][0]['valid']);self.assertFalse(any(x['completion_evidence'] for x in steps(result)))
 def test_a3_graph_and_occurrence_only_edges_reach_csv_without_assignment(self):
  import csv,io
  from backend.evaluators import csv_evidence
  rows=[row('save',text='저장'),row('outside','route_change',tag='html')];source=snapshot(rows)
  source['processes'][0]['business_steps']=[source['processes'][0]['business_steps'][0]]
  source['graph_evidence']=[dict(node_id='g1',process_model_id='graph-map-1',source_event_evidence=['outside']),dict(node_id='g2',process_model_id='graph-map-2',source_event_evidence=['outside'])]
  source['source_occurrence_evidence']=[dict(node_id='g1',process_model_id='graph-map-1',process_instance_id='aux',step_order=4,source_event_evidence=['outside'])]
  result=abstract(source,rows);record=next(x for x in result['raw_event_disposition'] if x['event_id']=='outside')
  self.assertEqual(record['source_node_ids'],[]);self.assertEqual(record['source_process_ids'],[])
  self.assertEqual([x['node_id'] for x in record['original_graph_memberships']],['g1','g2']);self.assertEqual(len(record['original_occurrence_memberships']),1)
  self.assertEqual(steps(result)[0]['process_id'],'p');self.assertEqual(steps(result)[0]['source_node_ids'],['n-save'])
  text=csv_evidence([dict(row_type='evidence_disposition',**x) for x in result['raw_event_disposition']]);records=list(csv.DictReader(io.StringIO(text.lstrip('\ufeff'))))
  restored=next(x for x in records if x['event_id']=='outside')
  self.assertEqual(json.loads(restored['original_graph_memberships']),record['original_graph_memberships'])
  self.assertTrue(all(x['relationship_role']=='ORIGINAL_GRAPH_PROVENANCE_ONLY' and x['source_path'].startswith('graph_evidence[') for x in record['original_graph_memberships']))
  expected={(eid,g['node_id']) for g in source['graph_evidence'] for eid in g['source_event_evidence']}
  traced={(r['event_id'],g['node_id']) for r in result['raw_event_disposition'] for g in r['original_graph_memberships']}
  self.assertEqual(expected,traced)

class IntentStateComparisonTests(unittest.TestCase):
 def truth(self,labels):return dict(processes=[dict(id='arbitrary',procedures=[dict(id='r'+str(i),label=label,menu_screen_name='공통 업무',step_order=i+1,allowed_aliases=[]) for i,label in enumerate(labels)])])
 def generated(self,complete=True):
  rows=[row('save',text='저장')]+([success('done','save')] if complete else []);result=generate(rows);s=steps(result)
  for i,x in enumerate(s,1):x.update(id=x['generated_step_id'],comparison_order=i,execution_ids=['e'],matching_eligible=True)
  return dict(processes=[dict(id='arbitrary',procedures=s)])
 def test_unique_accuracy_and_distinct_intent_state_completeness(self):
  truth=self.truth(['저장','완료 확인','종료']);score,_,stats,evidence=evaluate(self.generated(),truth,compile_roles(truth))
  self.assertEqual((stats['correctly_mapped'],stats['included_required'],stats['evaluated_procedures'],stats['defined_required']),(1,3,1,3));self.assertEqual(score,100)
  self.assertEqual(sum(e['direct_match'] for e in evidence),1);self.assertEqual(sum(e['match_kind']=='STATE_ATTRIBUTE' for e in evidence),2)
 def test_missing_proof_is_explicit_missing_not_null_or_success(self):
  truth=self.truth(['저장','완료 확인','종료']);_,_,stats,ev=evaluate(self.generated(False),truth,compile_roles(truth))
  self.assertEqual(stats['included_required'],1);self.assertEqual(len(stats['semantic_uncertainties']),2);self.assertEqual(stats['per_business_unit'][0]['missing_count'],2)
 def test_wrong_or_missing_context_not_wildcard(self):
  for context in ('','wrong'):
   gen=self.generated();gen['processes'][0]['procedures'][0]['business_context']=context;truth=self.truth(['저장','종료'])
   self.assertEqual(evaluate(gen,truth,compile_roles(truth))[2]['correctly_mapped'],0)
 def test_explicit_user_check_cannot_be_passive_state(self):
  truth=self.truth(['저장','완료 확인']);truth['processes'][0]['procedures'][1]['action_type']='RESULT_CHECK'
  self.assertEqual(evaluate(self.generated(),truth,compile_roles(truth))[2]['included_required'],1)
 def test_same_state_role_not_double_counted(self):
  truth=self.truth(['저장','완료 확인','완료 확인']);gen=self.generated()
  write=gen['processes'][0]['procedures'][0];other=copy.deepcopy(write['completion_evidence'][0]);other['source_event_id']='duplicate-observer';other['raw_order']+=1
  write['completion_evidence'].append(other);write['source_event_ids'].append('duplicate-observer');write['evidence'].append({'event_id':'duplicate-observer'})
  self.assertEqual(evaluate(gen,truth,compile_roles(truth))[2]['included_required'],2)
 def test_physical_constraint_not_ignored(self):
  truth=self.truth(['저장']);truth['processes'][0]['procedures'][0]['screen_context']={'kind':'page_path','value':'/other'}
  self.assertEqual(evaluate(self.generated(),truth,compile_roles(truth))[2]['correctly_mapped'],0)
 def test_mixed_stays_once_ineligible_denominator(self):
  gen=self.generated();mixed=copy.deepcopy(gen['processes'][0]['procedures'][0]);mixed.update(id='mixed',matching_eligible=False,execution_ids=['e','other'])
  gen['processes'].append(dict(id='CROSS_EXECUTION_MIXED',procedures=[mixed]));truth=self.truth(['저장'])
  stats=evaluate(gen,truth,compile_roles(truth))[2];self.assertEqual((stats['correctly_mapped'],stats['evaluated_procedures']),(1,2))
 def test_field_list_does_not_expand_direct_whole_object_label(self):
  gen=self.generated();step=gen['processes'][0]['procedures'][0];step.update(action_type='INPUT',business_object='개별 필드',target_field_label='개별 필드',fields=[{'label':'업무 정보'}]);truth=self.truth(['업무 정보 입력'])
  self.assertEqual(evaluate(gen,truth,compile_roles(truth))[2]['correctly_mapped'],0)

class AbstractionGateTests(unittest.TestCase):
 def fixture(self,root):
  from backend.m02_abstraction_candidate import REQUIRED_DEPENDENCIES,SNAPSHOT
  hashes={}
  for name in REQUIRED_DEPENDENCIES:
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('synthetic '+name);hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
  model=root/'model/manifest.json';model.parent.mkdir();model.write_text('{"file_sha256":{}}');hashes['model/manifest.json']=hashlib.sha256(model.read_bytes()).hexdigest()
  helper=IntentStateComparisonTests();truth=helper.truth(['저장','종료']);generated=helper.generated();s=generated['processes'][0]['procedures'][0]
  s.update(generated_step_id=s['id'],business_unit_ownership='ASSIGNED',business_unit_ids=['arbitrary'],in_m02_denominator=True)
  generated.update(ownership_ledger=[s],scope_summary=dict(target_units=['arbitrary'],total_generated_steps=1,all_generated_steps=1,mixed_count=0,unassigned_count=0,out_of_scope_count=0,per_business_unit={'arbitrary':1},policy='synthetic'))
  snapshot_value=dict(processes=[dict(business_steps=[s])],serializer_version='synthetic',serializer_rules_hash='synthetic',technical_evidence_count=0,original_technical_evidence_ledger=[],raw_evidence_ledger=[],raw_event_disposition=[])
  gt=root/'gt.json';gt.write_text(json.dumps(truth));directory=root/SNAPSHOT;directory.mkdir(parents=True);artifacts={};outputs={}
  for key,name,value in [('business_steps','business_steps.json',snapshot_value),('scope','scope.json',generated),('roles','gt_roles.json',compile_roles(truth))]:
   p=directory/name;p.write_text(json.dumps(value));h=hashlib.sha256(p.read_bytes()).hexdigest();outputs[name]=h
   if key!='roles':artifacts[key]=dict(path=str(p.relative_to(root)),sha256=h);hashes[str(p.relative_to(root))]=h
  m=dict(stage='PRE_ABSTRACTION_COMPARISON',score_computed=False,input_code_sha256=hashes,comparison_dependencies=sorted(REQUIRED_DEPENDENCIES),outputs=outputs,generated_artifacts=artifacts,
   model_version='synthetic',source_snapshot_sha256='synthetic',model_binding=dict(manifest_path='model/manifest.json',manifest_sha256=hashes['model/manifest.json'],file_sha256={}),
   evaluation_boundary=dict(comparison_contract=CONTRACT,td04_path='gt.json',td04_sha256=hashlib.sha256(gt.read_bytes()).hexdigest()))
  (directory/'manifest.json').write_text(json.dumps(m));return directory,gt
 def gate(self,directory,contract=CONTRACT):
  (directory/'independent_verification.json').write_text(json.dumps(dict(verdict='PASS',snapshot_manifest_sha256=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),gt_leakage_check='PASS',scope_check='PASS',direct_comparison_contract=contract)))
 def test_gate_precedes_gt_read_and_wrong_contract_cannot_score(self):
  from backend.m02_abstraction_candidate import assess
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);d,gt=self.fixture(root);gt.unlink()
   with patch('backend.m02_abstraction_candidate.evaluate',side_effect=AssertionError('forbidden')):
    self.assertIsNone(assess(root)[0]['score']);self.gate(d,'LOGICAL_BUSINESS_PROCEDURE_V1');self.assertIsNone(assess(root)[0]['score'])
 def test_synthetic_pass_has_separate_accuracy_and_completeness_counts(self):
  from backend.m02_abstraction_candidate import assess
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);d,_=self.fixture(root);self.gate(d);result,rows=assess(root)
   self.assertEqual(result['score'],100);self.assertEqual(result['details']['correctly_mapped'],1);self.assertEqual(result['details']['included_required'],2)
   self.assertTrue(any(r.get('match_kind')=='STATE_ATTRIBUTE' for r in rows))
 def test_dependency_and_generated_tampering_fails_before_comparison(self):
  from backend.m02_abstraction_candidate import assess,SNAPSHOT
  from backend.evaluators import EvaluationError
  for name in ('backend/m02_business_abstraction.py','backend/m02_abstraction_comparator.py',SNAPSHOT+'/scope.json'):
   with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);d,_=self.fixture(root);self.gate(d);(root/name).write_text('tampered')
    with self.assertRaises(EvaluationError):assess(root)
