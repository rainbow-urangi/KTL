"""Synthetic structural cases; no BU IDs, raw production values or GT."""
import copy
import unittest
from backend.m02_generic_preservation import opening_for, date_picker_proof, compress
from backend.m02_weekly_date_contract import verified_date_picker, temporal_target_state
from backend.m02_logical_comparator import normalize,subject

def event(eid,action='click',pid=None,parent=None,text='',selector='',tag='button'):
    return dict(event_id=eid,session_id='s',page_path='/arbitrary',event=dict(action=action,interaction_id='i-'+eid),
        popup=dict(active_popup_id=pid,active_parent_popup_id=parent),popup_stack=[],popup_containment=dict(is_inside_popup=bool(pid)),
        element_text=text,selector=selector,tag=tag)
def fixture(title='주간보고 등록'):
    opener=event('start');parent=event('parent','popup_open','form');parent['popup']['target_popup']=dict(popup_id='form',title=title,opened_at='t0',opened_by_event_id='start')
    live=dict(popup_id='form',opened_at='t0',opened_by_event_id='start')
    button=event('open','click','form');button['popup_stack']=[live]
    picker=event('picker','popup_open','picker','form');picker['popup'].update(opener_event_id='open',target_popup=dict(popup_id='picker',parent_popup_id='form',opened_at='t1',opened_by_event_id='open'))
    picker['popup_stack']=[live];picker['event']['cause_event_id']='open'
    click=event('day',pid='picker',parent='form',text='arbitrary captured day',selector='div.calendar__grid > button.calendar__day');click['popup_stack']=[live,dict(popup_id='picker',opened_at='t1',opened_by_event_id='open')]
    close=event('close','popup_close','picker','form');close['popup'].update(closer_event_id='day',target_popup=dict(popup_id='picker',parent_popup_id='form',opened_at='t1'));close['event']['cause_event_id']='day';close['popup_stack']=[live]
    save=event('save',pid='form');save['popup_stack']=[live]
    return [opener,parent,button,picker,click,close,save]
class PreservationTests(unittest.TestCase):
    def proof(self,es):return date_picker_proof(es[4],es,{e['event_id']:i for i,e in enumerate(es)},{'picker':dict(valid=True,source_event_id='open')})
    def test_parent_survives_nested_popup(self):
        es=fixture();self.assertEqual(opening_for(es[-1],es,{e['event_id']:i for i,e in enumerate(es)})['event_id'],'parent')
    def test_parent_identity_reuse_and_missing_stack_rejected(self):
        for mode in ('identity','missing','route'):
            es=fixture()
            if mode=='identity':es[-1]['popup_stack'][0]=dict(popup_id='form',opened_at='OTHER',opened_by_event_id='start')
            if mode=='missing':es[-1]['popup_stack']=[]
            if mode=='route':es[5]['event']['action']='route_change'
            self.assertIsNone(opening_for(es[-1],es,{e['event_id']:i for i,e in enumerate(es)}),mode)
    def test_date_needs_action_parent_and_direct_close(self):
        self.assertIsNotNone(self.proof(fixture()))
        for mode in ('default','cause','parent','outside','selector'):
            es=fixture()
            if mode=='default':es[4]['event']['action']='popup_structure'
            if mode=='cause':es[5]['event']['cause_event_id']='other'
            if mode=='parent':es[4]['popup']['active_parent_popup_id']='other'
            if mode=='outside':es[4]['popup_containment']['is_inside_popup']=False
            if mode=='selector':es[4]['selector']='button.next-month'
            self.assertIsNone(self.proof(es),mode)
    def test_weekly_contract_rechecks_raw_not_metadata(self):
        for title,expected in [('주간보고 등록','MATCH'),('주간업무 등록','MATCH'),('일일보고 등록','TARGET_TYPE_MISMATCH'),('Other register','TARGET_TYPE_MISMATCH')]:
            es=fixture(title);proof=self.proof(es);s=dict(selection_kind='DATE_PICKER_DAY',selection_provenance=proof,evidence=es,source_event_ids=[e['event_id'] for e in es],intent_source_event_ids=['day'])
            self.assertTrue(verified_date_picker(s))
            self.assertEqual(temporal_target_state(s,['대상 주차 선택'],subject,normalize,'SELECT_OBJECT'),expected)
            old=copy.deepcopy(s);s['evidence'][4]['event']['action']='popup_structure';self.assertFalse(verified_date_picker(s));self.assertEqual(old['selection_provenance'],s['selection_provenance'])
    def test_nav_ancestry_without_expansion_proof_never_compressed(self):
        for nested in (True,False):
            a=event('a',text='Group',selector='aside > nav.menu > li.group > button');b=event('b',text='Leaf',selector='nav.menu > li.'+('group' if nested else 'other')+' > ul > li',tag='li')
            def step(e):return dict(generated_step_id=e['event_id'],intent_source_event_ids=[e['event_id']],source_event_ids=[e['event_id']],action_type='MENU_ENTER',process_id='same')
            ss=[step(a),step(b)];lookup={'a':a,'b':b}
            result=compress(ss,lookup,{'a':0,'b':1},lambda s,e,k:s['source_event_ids'].append(e['event_id']))
            self.assertEqual(len(result),2)
            self.assertEqual([x['source_event_ids'] for x in result],[['a'],['b']])
    def test_same_form_cross_model_fragment_requires_unchanged_raw_lifetime(self):
        from backend.m02_generic_preservation import same_live_form
        es=fixture();parent=es[1];a=es[2];b=es[-1]
        def step(e):return dict(form_identity=['s','opaque','form'],form_lifecycle_provenance=dict(opening_source_event_id='parent'),intent_source_event_ids=[e['event_id']],source_event_ids=['parent',e['event_id']],evidence=[copy.deepcopy(parent),copy.deepcopy(e)])
        left,right=step(a),step(b);self.assertTrue(same_live_form(left,right))
        for mode in ('id','time','page','source'):
            bad=copy.deepcopy(right)
            if mode=='id':bad['form_lifecycle_provenance']['opening_source_event_id']='other'
            if mode=='time':bad['evidence'][1]['popup_stack'][0]['opened_at']='different'
            if mode=='page':bad['evidence'][1]['page_path']='/other'
            if mode=='source':bad['source_event_ids'].remove('parent')
            self.assertFalse(same_live_form(left,bad),mode)

    def test_sibling_export_refresh_are_independent(self):
        a=event('export',text='Export',selector='nav.main > li.tools > button.export')
        b=event('refresh',text='Refresh',selector='nav.main > li.tools > button.refresh')
        def step(e):return dict(generated_step_id=e['event_id'],intent_source_event_ids=[e['event_id']],source_event_ids=[e['event_id']],action_type='MENU_ENTER',process_id='same')
        result=compress([step(a),step(b)],{'export':a,'refresh':b},{'export':0,'refresh':1},lambda s,e,k:s['source_event_ids'].append(e['event_id']))
        self.assertEqual([s['generated_step_id'] for s in result],['export','refresh'])
        self.assertEqual([s['source_event_ids'] for s in result],[['export'],['refresh']])
