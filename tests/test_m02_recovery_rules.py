"""Synthetic recovery regression; no real BU/GT labels, identities or scores."""
import copy, unittest
from test_m02_business_abstraction import row,edit,form_open,success,generate,steps

class RecoveryRulesTests(unittest.TestCase):
 def test_tree_requires_navigation_ancestry_and_exact_text(self):
  for path,source,label,want in [('nav.main > ul > li','tree','Arbitrary','MENU_ENTER'),('div.grid > li','tree','Arbitrary','UNRESOLVED'),('nav.main > li','tree','Other','UNRESOLVED')]:
   r=row('x',text='Arbitrary',tag='li',menu=label);r['target_selector']=path;r['locators_json']['menu_context'].update(source=source,parser='generic_dom_tree')
   self.assertEqual(steps(generate([r]))[0]['action_type'],want)
 def dialog_rows(self,inside=True):
  a=row('open',text='등록',menu='Unrelated entity');b=form_open('popup','open')
  b['locators_json']['popup_context']['target_popup'].update(tag='div',selector_css='div.dialog',role='dialog',title='Unrelated entity 등록')
  c=edit('field');c['locators_json']['input_context'].pop('form_id');c['locators_json']['popup_context']={'active_popup_id':'form-popup','is_inside_popup':inside};c['target_selector']='#field'
  c['locators_json']['menu_context']={'source':'url','parser':'location_path'}
  return [a,b,c]
 def test_div_dialog_form_requires_observed_containment(self):
  s=steps(generate(self.dialog_rows()));self.assertEqual(s[0]['intent_phase'],'INITIATE');self.assertTrue(s[1]['form_identity']);self.assertEqual(s[1]['business_context'],'Unrelated entity')
  self.assertEqual(s[0]['source_event_ids'],['open','popup']);self.assertEqual(s[1]['form_detection_evidence'][0]['source_event_id'],'field')
  self.assertIsNone(steps(generate(self.dialog_rows(False)))[1]['form_identity'])
 def test_dialog_opener_missing_reference_never_guessed(self):
  r=self.dialog_rows();r[1]['locators_json']['popup_context']['opener_event_id']='absent'
  self.assertEqual(steps(generate(r))[0]['intent_phase'],'UNKNOWN');self.assertEqual(steps(generate(r))[1]['business_context'],'')
 def test_success_text_click_is_context_only_when_linked_exact_noninteractive(self):
  for tag,text,expected in [('div','정보가 저장되었습니다.',1),('button','정보가 저장되었습니다.',2),('div','다른 내용',2)]:
   rows=[row('save',text='저장'),success('done','save'),row('touch',text=text,tag=tag,popup={'active_popup_id':'success','active_popup_title':'정보가 저장되었습니다.'})]
   rows[-1]['locators_json']['element']['role']=''
   s=steps(generate(rows));self.assertEqual(len(s),expected)
   if expected==1:self.assertIn('touch',s[0]['source_event_ids']);self.assertEqual(s[0]['evidence_roles']['touch'],'SUCCESS_ACKNOWLEDGEMENT_CONTEXT')
 def test_unlinked_success_text_remains_unresolved(self):
  s=steps(generate([row('x',text='정보가 저장되었습니다.',tag='div',popup={'active_popup_id':'absent','active_popup_title':'정보가 저장되었습니다.'})]))
  self.assertEqual(s[0]['action_type'],'UNRESOLVED')
 def test_raw_is_immutable_and_no_source_generated(self):
  r=self.dialog_rows();before=copy.deepcopy(r);x=generate(r);self.assertEqual(r,before)
  self.assertEqual(len(x['raw_event_disposition']),len(r));self.assertTrue(set(e for s in steps(x) for e in s['source_event_ids'])<={e['event_id'] for e in r})

 def test_success_ack_rejects_interactive_roles(self):
  for role in ('button','link','checkbox','menuitem'):
   touch=row('touch',text='정보가 저장되었습니다.',tag='div',popup={'active_popup_id':'success','active_popup_title':'정보가 저장되었습니다.'})
   touch['locators_json']['element']['role']=role
   s=steps(generate([row('save',text='저장'),success('done','save'),touch]))
   self.assertEqual(len(s),2,role);self.assertNotIn('touch',s[0]['source_event_ids'])
 def test_success_ack_rejects_page_input_and_lifecycle_boundaries(self):
  for variant in ('other_page','page_return','input','focus','intent','popup_close','popup_open','route_change','page_view','screen_change','page_close'):
   for text in ('정보가 저장되었습니다.','확인'):
    touch=row('touch',text=text,tag='div',popup={'active_popup_id':'success','active_popup_title':'정보가 저장되었습니다.'})
    touch['locators_json']['element']['role']=''
    rows=[row('save',text='저장'),success('done','save')]
    if variant=='other_page':touch['page_url']='https://example.invalid/other'
    elif variant=='page_return':rows.append(row('middle','page_view',page='/other'))
    elif variant=='input':rows.append(edit('middle'))
    elif variant=='focus':rows.append(edit('middle',action='click'))
    elif variant=='intent':rows.append(row('middle',text='조회'))
    else:rows.append(row('middle',variant))
    rows.append(touch);s=steps(generate(rows))
    self.assertTrue(any(x['intent_source_event_ids']==['touch'] for x in s),(variant,text))
    self.assertNotIn('touch',s[0]['source_event_ids'],(variant,text))
 def test_success_ack_cannot_use_future_popup_or_wrong_title(self):
  for variant in ('future','wrong_title'):
   touch=row('touch',text='정보가 저장되었습니다.',tag='div',popup={'active_popup_id':'success','active_popup_title':'정보가 저장되었습니다.'})
   touch['locators_json']['element']['role']=''
   rows=[row('save',text='저장'),success('done','save'),touch]
   if variant=='future':rows=[touch,*rows[:2]]
   else:touch['locators_json']['popup_context']['active_popup_title']='다른 내용'
   s=steps(generate(rows));self.assertTrue(any(x['intent_source_event_ids']==['touch'] for x in s),variant)

 def test_dialog_proof_rejects_cross_page_future_and_closed_lifecycle(self):
  for variant in ('other_page','future_open','popup_close','route_change','page_return','popup_reopen'):
   rows=self.dialog_rows()
   if variant=='other_page':rows[-1]['page_url']='https://example.invalid/other'
   elif variant=='future_open':rows=[rows[0],rows[2],rows[1]]
   elif variant=='page_return':rows.insert(2,row('boundary','page_view',page='/other'))
   elif variant=='popup_reopen':
    reopening=copy.deepcopy(rows[1]);reopening['event_id']='reopen';rows.insert(2,reopening)
   else:rows.insert(2,row('boundary',variant))
   s=steps(generate(rows));opening=next(x for x in s if x['intent_source_event_ids']==['open'])
   if variant!='popup_reopen':
    self.assertEqual(opening['intent_phase'],'UNKNOWN',variant)
    self.assertIsNone(next(x for x in s if 'field' in x['intent_source_event_ids'])['form_identity'],variant)
   else:
    self.assertNotIn('popup',opening['source_event_ids'])
    proof=next(x for x in s if 'field' in x['intent_source_event_ids'])['form_detection_evidence']
    self.assertEqual([x['source_event_id'] for x in proof],['field'])
