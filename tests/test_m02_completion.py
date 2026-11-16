"""Temporary synthetic evidence only; no real GT or actual metric invocation."""
import copy,unittest
from backend.m02_completion_semantics import extend,affirmative_success
from backend.m02_logical_comparator import final_projection,candidate_state,support_context_state
from backend.m02_logical_gt import compile_roles

def event(eid,action,interaction='i',outcome=None,page='/opaque',session='s'):
    return dict(event_id=eid,session_id=session,event={'action':action,'interaction_id':interaction},
        page_path=page,page_title='Product',ui_outcome=outcome or {},popup={},selector='',tag='div')
def fixture():
    write_event=event('w','click')
    write=dict(generated_step_id='write',action_type='SAVE',source_event_ids=['w'],source_node_ids=['n'],
        evidence=[write_event],step_order=1,menu={'selected_path_text':'공통 업무','source':'nav'},
        menu_page='/opaque',page_title='Product',target_field_label='저장',resolution_status='RESOLVED')
    result=event('r','ui_outcome','outcome',dict(message='정보가 저장되었습니다.',source_interaction_id='i',type='modal_message'))
    return dict(processes=[dict(business_steps=[write])],raw_evidence_ledger=[write_event,result],raw_unclaimed_event_ids=['r'])
class CompletionTests(unittest.TestCase):
    def test_pure_and_deterministic_preserves_old_ids_nodes_fields(self):
        source=fixture();before=copy.deepcopy(source);a=extend(source)
        self.assertEqual(a,extend(source));self.assertEqual(source,before)
        self.assertEqual(a['processes'][0]['business_steps'][0],source['processes'][0]['business_steps'][0])
        state=a['processes'][0]['business_steps'][1]
        self.assertEqual(state['source_event_ids'],['r']);self.assertEqual(state['source_node_ids'],[])
        self.assertEqual(state['completion_observation']['write_source_event_ids'],['w'])
        self.assertEqual(state['action_type'],'RESULT_CHECK')
    def test_failure_negation_future_question_not_success(self):
        for message in ['저장되지 않았습니다','저장 실패','저장되었습니다. 오류가 발생했습니다','저장하시겠습니까?','not saved successfully','저장 예정','취소되었습니다']:
            self.assertFalse(affirmative_success(message))
        for message in ['정보가 등록되었습니다.','저장되었습니다.','saved successfully']:
            self.assertTrue(affirmative_success(message))
    def test_missing_duplicate_cross_session_page_and_future_link_stay_raw(self):
        for change in ['missing','duplicate','session','page','future']:
            value=fixture()
            if change=='missing':value['raw_evidence_ledger'][1]['ui_outcome']['source_interaction_id']='other'
            if change=='duplicate':value['processes'].append(copy.deepcopy(value['processes'][0]))
            if change=='session':value['raw_evidence_ledger'][1]['session_id']='other'
            if change=='page':value['raw_evidence_ledger'][1]['page_path']='/other'
            if change=='future':value['raw_evidence_ledger'].reverse()
            result=extend(value)
            self.assertFalse(any(s.get('completion_observation') for p in result['processes'] for s in p['business_steps']))
            self.assertIn('r',result['raw_unclaimed_event_ids'])
    def test_http_or_close_alone_never_creates_completion(self):
        value=fixture();value['raw_evidence_ledger'][1].update(ui_outcome={},http_method='POST',http_status=200)
        self.assertEqual(len(extend(value)['processes'][0]['business_steps']),1)
        value['raw_evidence_ledger'][1]['event']['action']='popup_close'
        self.assertEqual(len(extend(value)['processes'][0]['business_steps']),1)
    def test_pending_operation_blocks_outcome(self):
        value=fixture();e=event('new','input','j');value['raw_evidence_ledger'].insert(1,e)
        new=copy.deepcopy(value['processes'][0]['business_steps'][0]);new.update(generated_step_id='input',action_type='INPUT',source_event_ids=['new'],evidence=[e])
        value['processes'][0]['business_steps'].append(new)
        self.assertFalse(any(s.get('completion_observation') for s in extend(value)['processes'][0]['business_steps']))
    def test_intervening_split_map_or_unclaimed_input_blocks_stale_outcome(self):
        for claimed in (False,True):
            value=fixture();e=event('new','input','j');value['raw_evidence_ledger'].insert(1,e)
            if claimed:
                step=copy.deepcopy(value['processes'][0]['business_steps'][0]);step.update(generated_step_id='new',action_type='INPUT',source_event_ids=['new'],evidence=[e])
                value['processes'].append(dict(business_steps=[step]))
            self.assertFalse(any(s.get('completion_observation') for p in extend(value)['processes'] for s in p['business_steps']))
    def test_c1_complete_assertions_reject_uncertainty_and_keep_raw(self):
        for message in ['will be saved successfully','If confirmed, this will be registered successfully',
                '저장되었는지 확인해 주세요','저장되었나요','등록되었을 수 있습니다',
                'The record may have been saved successfully','This is going to be saved successfully',
                'It was about to be saved successfully','등록되었습니다만 실패했습니다']:
            self.assertFalse(affirmative_success(message),message)
            value=fixture();value['raw_evidence_ledger'][1]['ui_outcome']['message']=message
            result=extend(value)
            self.assertEqual(result['processes'][0]['business_steps'],value['processes'][0]['business_steps'])
            self.assertEqual(result['raw_evidence_ledger'],value['raw_evidence_ledger'])
            self.assertIn('r',result['raw_unclaimed_event_ids'])
    def test_c2_unclaimed_raw_write_clicks_block_stale_response(self):
        for text in ['저장','등록','수정','save','register','update']:
            value=fixture();e=event('new-write','click','other-write');e.update(element_text=text,tag='button')
            value['raw_evidence_ledger'].insert(1,e)
            result=extend(value)
            self.assertEqual(len(result['processes'][0]['business_steps']),1,text)
            self.assertEqual(result['completion_rule_audit'][0]['status'],'INTERVENING_OPERATION_AMBIGUITY')
            self.assertEqual(result['raw_evidence_ledger'],value['raw_evidence_ledger'])
            self.assertIn('r',result['raw_unclaimed_event_ids'])
    def test_c2_lifecycle_and_other_session_page_do_not_blanket_block(self):
        for action,text,page,session in [('popup_open','', '/opaque','s'),
                ('click','저장','/different','s'),('click','저장','/opaque','different')]:
            value=fixture();e=event('extra',action,'extra',page=page,session=session);e['element_text']=text
            value['raw_evidence_ledger'].insert(1,e)
            self.assertEqual(len(extend(value)['processes'][0]['business_steps']),2)
    def test_c2_raw_unknown_submit_is_unresolved_operation(self):
        for action in ('submit','click'):
            value=fixture();e=event('new-submit',action,'other');e['input']={'type':'submit'}
            value['raw_evidence_ledger'].insert(1,e)
            self.assertEqual(len(extend(value)['processes'][0]['business_steps']),1)
    def test_url_namespace_not_human_conflict_or_translation(self):
        from backend.m02_logical_comparator import context_state
        p=final_projection(dict(action_type='INPUT',menu={'selected_path_text':'opaque','source':'url','parser':'location_path'},menu_page='/opaque'))
        self.assertEqual(context_state(p,dict(logical_context=dict(name='공통 업무'))),'UNKNOWN')
        q=dict(p,menu_leaf='공통 업무',menu_source='nav',menu_parser='sidebar_active_dom')
        self.assertEqual(support_context_state(p,q),'MATCH')
        self.assertEqual(context_state(p,dict(logical_context=dict(name='공통 업무'))),'UNKNOWN')
    def test_end_and_inspection_match_observed_state_without_click(self):
        value=extend(fixture());steps=value['processes'][0]['business_steps']
        for index,s in enumerate(steps):s.update(id=s['generated_step_id'],execution_ids=['x'],evidence_type='direct',matching_eligible=True,comparison_order=index+1)
        p=[final_projection(s) for s in steps]
        for label in ['종료','완료 확인']:
            truth=dict(processes=[dict(id='arbitrary',procedures=[dict(id='g',label=label,step_order=1,menu_screen_name='공통 업무',allowed_aliases=[])])])
            r=compile_roles(truth)['processes'][0]['procedures'][0]
            self.assertEqual(candidate_state(p,1,r),'MATCH')
            # A state is not invented from a successful SAVE action alone.
            self.assertNotEqual(candidate_state(p,0,r),'MATCH')
    def test_register_start_not_a_completed_write(self):
        value=extend(fixture());steps=value['processes'][0]['business_steps'];steps[0]['action_type']='REGISTER'
        for index,s in enumerate(steps):s.update(id=s['generated_step_id'],execution_ids=['x'],evidence_type='direct',matching_eligible=True,comparison_order=index+1)
        p=[final_projection(s) for s in steps]
        r=compile_roles(dict(processes=[dict(id='z',procedures=[dict(id='g',label='종료',step_order=1,menu_screen_name='공통 업무',allowed_aliases=[])])]))['processes'][0]['procedures'][0]
        self.assertEqual(candidate_state(p,1,r),'UNKNOWN_COMPLETION_SCOPE')
if __name__=='__main__':unittest.main()
