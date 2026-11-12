import unittest
from copy import deepcopy
from backend.m02_user_confirmed_comparator import prepare,intent_state,form_context,successful_form
class OwnerContractTests(unittest.TestCase):
 def fixtures(self):
  form=['session','/any','FORM_POPUP','popup-1','selector','일일업무 등록']
  def step(id,action,order):
   return dict(id=id,action_type=action,comparison_order=order,intent_order=order,last_intent_order=order,matching_eligible=True,resolution_status='RESOLVED',business_context='업무 관리',form_identity=form,fields=[],execution_ids=['EX'],source_process_ids=['PM'],source_event_ids=[id],evidence=[dict(event_id=id,popup=dict(active_popup_title='일일업무 등록'))],completion_evidence=[],intent_phase='UNKNOWN')
  a=step('input','INPUT',1);a['fields']=[{'label':'제목','source_event_id':'input'}]
  w=step('write','SAVE',2);w['intent_phase']='COMMIT';w['source_event_ids'].append('success');w['evidence'].append({'event_id':'success'});w['completion_evidence']=[dict(source_event_id='success',raw_order=3,kind='SUCCESS_POPUP',causal_rule='EXPLICIT_CAUSAL_ID')]
  return dict(processes=[dict(id='ARBITRARY_ID',procedures=[a,w])])
 def test_success_required_and_provenance_immutable(self):
  g=self.fixtures();old=deepcopy(g);p=prepare(g);self.assertTrue(p['processes'][0]['procedures'][0]['required_input_proof']);self.assertEqual(g,old)
  for a,b in zip(g['processes'][0]['procedures'],p['processes'][0]['procedures']):
   self.assertEqual(a['source_event_ids'],b['source_event_ids']);self.assertEqual(a['evidence'],b['evidence'])
 def test_no_success_no_input_proof(self):
  g=self.fixtures();g['processes'][0]['procedures'][1]['completion_evidence']=[];self.assertFalse(prepare(g)['processes'][0]['procedures'][0]['required_input_proof'])
 def test_wrong_form_no_proof(self):
  g=self.fixtures();g['processes'][0]['procedures'][1]['form_identity']=['different'];self.assertFalse(prepare(g)['processes'][0]['procedures'][0]['required_input_proof'])
 def test_alias_not_url(self):
  g=self.fixtures();s=g['processes'][0]['procedures'][0];self.assertEqual(form_context(s),'일일업무');s['evidence']=[];s['business_context']='';s['menu_page']='/mypage/work/daily';self.assertEqual(form_context(s),'')
 def test_page_enter_not_menu(self):
  s=dict(action_type='PAGE_ENTER',matching_eligible=True,resolution_status='RESOLVED');r=dict(logical_role='ENTER_CONTEXT');self.assertEqual(intent_state(s,r),'ACTION_MISMATCH')
 def test_missing_success_provenance_rejected(self):
  w=self.fixtures()['processes'][0]['procedures'][1];w['source_event_ids']=['write']
  with self.assertRaises(ValueError):successful_form(w)
 def test_different_execution_no_proof(self):
  g=self.fixtures();g['processes'][0]['procedures'][1]['execution_ids']=['OTHER'];self.assertFalse(prepare(g)['processes'][0]['procedures'][0]['required_input_proof'])
 def test_menu_alias_is_symmetric_and_specific(self):
  for left,right in [('일일업무','일일보고'),('일일보고','일일업무'),('주간업무','주간보고'),('주간보고','주간업무')]:
   with self.subTest(left=left,right=right):
    step=dict(action_type='MENU_ENTER',matching_eligible=True,resolution_status='RESOLVED',business_context=left,target_field_label=left,evidence=[])
    requirement=dict(logical_role='ENTER_CONTEXT',logical_context=dict(name=right),source_label=right,allowed_aliases=[])
    self.assertEqual(intent_state(step,requirement),'MATCH')
    step['action_type']='PAGE_ENTER';self.assertEqual(intent_state(step,requirement),'ACTION_MISMATCH')
    step['action_type']='MENU_ENTER';step['target_field_label']='미승인 다른 화면';self.assertEqual(intent_state(step,requirement),'TARGET_MISMATCH')
 def test_menu_alias_does_not_merge_daily_weekly(self):
  step=dict(action_type='MENU_ENTER',matching_eligible=True,resolution_status='RESOLVED',business_context='일일보고',target_field_label='주간업무',evidence=[])
  requirement=dict(logical_role='ENTER_CONTEXT',logical_context=dict(name='일일보고'),source_label='일일보고',allowed_aliases=[])
  self.assertEqual(intent_state(step,requirement),'TARGET_MISMATCH')
 def test_popup_object_does_not_replace_existing_menu_context(self):
  for context,title in [('거래처 정보 관리','거래처 정보 등록'),('자산 관리','자산 정보 등록')]:
   with self.subTest(context=context):
    step=dict(business_context=context,source_event_ids=['event'],evidence=[dict(event_id='event',popup=dict(active_popup_title=title))])
    self.assertEqual(form_context(step),''.join(context.split()))
 def test_approved_report_popup_specializes_broad_menu(self):
  for title,expected in [('일일업무 등록','일일업무'),('주간보고 등록','주간업무')]:
   step=dict(business_context='업무 관리',source_event_ids=['event'],evidence=[dict(event_id='event',popup=dict(active_popup_title=title))])
   self.assertEqual(form_context(step),expected)
if __name__=='__main__':unittest.main()
