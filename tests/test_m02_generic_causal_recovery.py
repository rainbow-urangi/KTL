"""Generic counterexamples, deliberately independent of BU IDs, GT and scores."""
import copy
import unittest
from tests.test_m02_business_abstraction import row, form_open, success, generate, steps

class GenericCausalRecoveryTests(unittest.TestCase):
 def calendar(self):
  click=row('cell',text='8',tag='div',menu='')
  click['locators_json']['grid_context']=dict(detected=True,grid_selector='.monthly-calendar .calendar-grid',cell_value='8')
  return [click,form_open('opened','cell')]
 def test_direct_calendar_create_select_without_date_inference(self):
  s=steps(generate(self.calendar()))[0]
  self.assertEqual(s['action_type'],'SELECT')
  self.assertEqual(s['selection_kind'],'CALENDAR_CELL')
  self.assertEqual(s['selected_cell_text'],'8')
  self.assertIsNone(s['selected_date'])
  self.assertEqual(s['selection_provenance']['popup_source_event_id'],'opened')
 def test_calendar_requires_exact_opener_and_create_form(self):
  for variant in ('missing','detail','not_calendar','mismatch','inside_popup','fallback'):
   rows=self.calendar()
   if variant=='missing': rows[1]['locators_json']['popup_context'].pop('opener_event_id'); rows[1]['locators_json']['popup_context']['target_popup'].pop('opened_by_event_id');rows[1]['locators_json']['event_context'].pop('cause_event_id')
   if variant=='detail':rows[1]['locators_json']['popup_context']['target_popup']['title']='Record details'
   if variant=='not_calendar':rows[0]['locators_json']['grid_context']['grid_selector']='.table-grid'
   if variant=='mismatch':rows[0]['locators_json']['grid_context']['cell_value']='9'
   if variant=='inside_popup':rows[0]['locators_json']['popup_context']['active_popup_id']='other'
   if variant=='fallback':rows[1]['locators_json']['event_context']['related_strategy']='recent_action_fallback'
   self.assertFalse(any(s.get('selection_kind')=='CALENDAR_CELL' for s in steps(generate(rows))),variant)
 def lifecycle(self):
  save=row('write',text='저장',popup={'active_popup_id':'editor'})
  done=success('done','write',pid='notice')
  done['locators_json']['popup_context']['target_popup']['opened_at']='2026-01-01T01:00:00Z'
  close=row('close','popup_close',popup=dict(closer_event_id='write',target_popup={'popup_id':'editor'},stack=[dict(popup_id='notice',opened_at='2026-01-01T01:00:00Z',opened_by_event_id='write')]),cause='write')
  ack=row('ack',text='확인',popup={'active_popup_id':'notice'})
  return [save,done,close,ack]
 def test_input_close_does_not_end_distinct_live_success_popup(self):
  s=steps(generate(self.lifecycle()))
  self.assertEqual(len(s),1)
  self.assertIn('ack',s[0]['source_event_ids'])
 def test_close_requires_exact_owner_and_live_success_identity(self):
  for variant in ('same_popup','missing_stack','reused_id','wrong_owner','no_cause'):
   rows=self.lifecycle();pc=rows[2]['locators_json']['popup_context']
   if variant=='same_popup':pc['target_popup']['popup_id']='notice'
   if variant=='missing_stack':pc['stack']=[]
   if variant=='reused_id':pc['stack'][0]['opened_at']='other'
   if variant=='wrong_owner':pc['stack'][0]['opened_by_event_id']='other'
   if variant=='no_cause':pc.pop('closer_event_id');rows[2]['locators_json']['event_context'].pop('cause_event_id')
   self.assertEqual(len(steps(generate(rows))),2,variant)

class CompositeCompletionTests(unittest.TestCase):
 def sample(self):
  save=row('save',text='저장',popup={'active_popup_id':'editor'})
  api=row('api','http',api={'method':'POST','path':'/arbitrary','status':201,'related_event_id':'save','related_strategy':'explicit'})
  close=row('close','popup_close',popup={'target_popup':{'popup_id':'editor'},'closer_event_id':'save'},cause='save')
  return [save,api,close]
 def test_explicit_write_success_and_same_form_close(self):
  from backend.m02_causal_form_completion import recover
  s=steps(recover(generate(self.sample())))[0]
  self.assertEqual(s['completion_evidence'][0]['kind'],'WRITE_SUCCESS_FORM_CLOSE')
  self.assertFalse(s['completion_evidence'][0]['success_ui_asserted'])
 def test_unproven_chain_is_never_completion(self):
  from backend.m02_causal_form_completion import recover
  for variant in ('fallback','no_close_cause','other_form','failed_http','intervening','http_only'):
   rows=self.sample()
   if variant=='fallback':rows[1]['locators_json']['api_context']['related_strategy']='recent_action_fallback'
   if variant=='no_close_cause':rows[2]['locators_json']['popup_context'].pop('closer_event_id');rows[2]['locators_json']['event_context'].pop('cause_event_id')
   if variant=='other_form':rows[2]['locators_json']['popup_context']['target_popup']['popup_id']='other'
   if variant=='failed_http':rows[1]['api_status_code']=500;rows[1]['locators_json']['api_context']['status']=500
   if variant=='intervening':rows.insert(2,row('another',text='Other'))
   if variant=='http_only':rows.pop()
   self.assertFalse(steps(recover(generate(rows)))[0]['completion_evidence'],variant)


class GenericContractIntegrationTests(unittest.TestCase):
 def test_calendar_date_but_not_week_and_requires_provenance(self):
  from backend.m02_user_confirmed_comparator import intent_state
  s=steps(generate(GenericCausalRecoveryTests().calendar()))[0]
  s.update(matching_eligible=True,resolution_status='RESOLVED',business_context='Arbitrary calendar')
  req=dict(logical_role='SELECT_OBJECT',logical_context={'name':'Arbitrary calendar'},source_label='date select',allowed_aliases=[])
  self.assertEqual(intent_state(s,req),'MATCH')
  req['source_label']='week select';self.assertNotEqual(intent_state(s,req),'MATCH')
  req['source_label']='date select';s['selection_provenance']['popup_source_event_id']='missing'
  self.assertNotEqual(intent_state(s,req),'MATCH')
 def test_composite_enters_success_proof_only_with_complete_chain(self):
  from backend.m02_causal_form_completion import recover
  from backend.m02_user_confirmed_comparator import successful_form
  s=steps(recover(generate(CompositeCompletionTests().sample())))[0]
  self.assertEqual(successful_form(s),['close'])
  s['evidence'][1]['api']['related_strategy']='recent_action_fallback'
  self.assertEqual(successful_form(s),[])
 def test_lifecycle_boundaries_even_on_other_page(self):
  from backend.m02_causal_form_completion import recover
  for variant in ('other_page_route','reopen','prior_close'):
   rows=CompositeCompletionTests().sample()
   if variant=='other_page_route':middle=row('boundary','route_change',page='/elsewhere')
   if variant=='reopen':middle=form_open('boundary','save',pid='editor')
   if variant=='prior_close':middle=row('boundary','popup_close',popup={'target_popup':{'popup_id':'editor'}})
   rows.insert(1,middle)
   self.assertFalse(steps(recover(generate(rows)))[0]['completion_evidence'],variant)


class ContradictoryWriteResponseTests(unittest.TestCase):
 def test_same_write_non_success_or_unknown_response_blocks_completion(self):
  from backend.m02_causal_form_completion import recover
  for status in (500,400,302,0,'',None):
   for where in (1,2,3):
    rows=CompositeCompletionTests().sample()
    failed=row('contradiction','http',api={'method':'POST','path':'/arbitrary','status':status,'related_event_id':'save','related_strategy':'explicit'})
    rows.insert(where,failed)
    self.assertFalse(steps(recover(generate(rows)))[0]['completion_evidence'],(status,where))
 def test_other_write_failure_is_not_this_write_proof(self):
  from backend.m02_causal_form_completion import recover
  rows=CompositeCompletionTests().sample()
  failed=row('other','http',api={'method':'POST','path':'/arbitrary','status':500,'related_event_id':'unrelated','related_strategy':'explicit'})
  rows.insert(2,failed)
  self.assertEqual(steps(recover(generate(rows)))[0]['completion_evidence'][0]['kind'],'WRITE_SUCCESS_FORM_CLOSE')


class ExhaustiveLifecycleBarrierTests(unittest.TestCase):
 def test_all_known_lifecycle_actions_before_and_after_response(self):
  from backend.m02_causal_form_completion import recover,LIFECYCLE_BARRIERS
  # This explicit list follows abstraction active_opening/acknowledgement boundaries.
  expected={'popup_open','popup_close','route_change','page_view','screen_change','page_close','collector_boot'}
  self.assertEqual(LIFECYCLE_BARRIERS,expected)
  for action in expected:
   for page in ('/opaque','/another'):
    for index in (1,2):
     rows=CompositeCompletionTests().sample()
     boundary=row('boundary',action,page=page,popup={'target_popup':{'popup_id':'editor'}})
     rows.insert(index,boundary)
     self.assertFalse(steps(recover(generate(rows)))[0]['completion_evidence'],(action,page,index))
