import copy
import unittest
from datetime import datetime
from backend.m05_session_cleaning import predict,CONTEXT_FIELDS

RULES={'parse_ts':lambda x:datetime.fromisoformat(x),'rle_dedupe_rows':lambda x:x,
       'should_drop_activity':lambda x:False,'DROP_EXACT':set()}

def event(n,action='click',target='#field',tag='input',page='https://example.test/form',session='s',popup='p',value=None,selection=None,text='Field',time=None):
    c=dict.fromkeys(CONTEXT_FIELDS)
    c.update(session_id=session,timestamp_utc=f'2026-01-01T00:00:{n if time is None else time:06.3f}+00:00',action=action,page=page,target=target,tag=tag,text=text,popup_id=popup,input_value=value,selection_start=selection,selection_end=selection,input_type='text',interaction_id=f'i{n}',has_api=False,has_outcome=False)
    return {'id':f'e{n}','features':{'case_id':n,'activity':('EVT:collector_boot' if action=='collector_boot' else action.upper()+':'+text),'ts':c['timestamp_utc'],'context':c}}

def labels(es):return [p['label'] for p in predict(es,RULES)['predictions']]

def focus():return [event(0),event(1),event(2,action='paste',value='',selection=0)]

def navseq():
    return [event(0,target='aside > nav.main > ul > li:nth-of-type(2) > button',tag='button',page='https://example.test/home',popup=None,text='Accounts'),event(1,action='route_change',tag='html',target='html',popup=None),event(2,action='popup_open'),event(3,action='popup_close'),event(4,target='nav.main > ul > li:nth-of-type(2) > button.is-active',tag='button',popup=None,text='Accounts'),event(5,target='#next',tag='button')]

class CleaningTests(unittest.TestCase):
    def test_cross_task_empty_focus(self):self.assertEqual(labels(focus()),['KEEP','REMOVE','KEEP'])
    def test_unknown_not_empty(self):
        es=focus();es[-1]['features']['context']['input_value']=None
        self.assertEqual(labels(es),['KEEP']*3)
    def test_nonempty_or_selection_preserved(self):
        for key,value in [('input_value','abc'),('selection_start',1),('selection_end',3)]:
            es=focus();es[1]['features']['context'][key]=value;self.assertEqual(labels(es),['KEEP']*3)
    def test_session_popup_page_target_isolation(self):
        for key in ['session_id','popup_id','page','target']:
            es=focus();es[1]['features']['context'][key]='different';self.assertEqual(labels(es),['KEEP']*3)
    def test_state_change_breaks_run(self):
        es=[event(0),event(1,action='change',value='x'),event(2),event(3,action='paste',value='',selection=0)]
        self.assertEqual(labels(es),['KEEP']*4)
    def test_slow_repeat_preserved(self):
        es=[event(0),event(4),event(5,action='paste',value='',selection=0)];self.assertEqual(labels(es),['KEEP']*3)
    def test_button_not_focus(self):
        es=focus()
        for e in es:e['features']['context']['tag']='button'
        self.assertEqual(labels(es),['KEEP']*3)
    def test_boot_diagnostic_only(self):
        es=[event(0,action='collector_boot',tag='html'),event(1,action='collector_boot',tag='button'),event(2,action='api_transaction',tag='html')]
        self.assertEqual(labels(es),['REMOVE','KEEP','KEEP'])
    def test_boot_with_business_outcome_kept(self):
        e=event(0,action='collector_boot',tag='html');e['features']['context']['has_outcome']=True;self.assertEqual(labels([e]),['KEEP'])
    def test_current_nav_after_popup_kept_original(self):
        self.assertEqual(labels(navseq()),['KEEP']*4+['REMOVE','KEEP'])
    def test_nav_refresh_is_kept(self):
        for action in ['route_change','api_transaction','popup_open']:
            es=navseq();es[-1]['features']['context']['action']=action;self.assertEqual(labels(es),['KEEP']*6)
    def test_no_known_destination_is_kept(self):
        es=navseq()[2:];self.assertEqual(labels(es),['KEEP']*4)
    def test_different_menu_identity_is_kept(self):
        es=navseq();es[4]['features']['context']['target']='nav.main > ul > li:nth-of-type(3)';self.assertEqual(labels(es),['KEEP']*6)
    def test_deterministic_and_no_input_mutation(self):
        es=focus();old=copy.deepcopy(es);self.assertEqual(predict(es,RULES),predict(es,RULES));self.assertEqual(es,old)
    def test_gt_rejected(self):
        es=focus();es[0]['expected_label']='REMOVE'
        with self.assertRaises(ValueError):predict(es,RULES)
    def test_chronological_and_original_order(self):
        es=focus();es=[es[2],es[0],es[1]];self.assertEqual(labels(es),['KEEP','KEEP','REMOVE'])
    def test_checkbox_preserved(self):
        es=focus()
        for e in es:e['features']['context']['input_type']='checkbox'
        self.assertEqual(labels(es),['KEEP']*3)
if __name__=='__main__':unittest.main()
