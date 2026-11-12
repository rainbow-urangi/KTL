"""Logical M02 contract counterexamples. Temporary synthetic GT/outputs ONLY."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.m02_logical_gt import compile_roles,CONTRACT
from backend.m02_logical_comparator import evaluate,LogicalSchemaError,LogicalMeaningIncomplete,candidate_state,final_projection

class LogicalTests(unittest.TestCase):
    context='공통 메뉴'
    def gt(self,labels,physical=None,aliases=None,end_explicit=False):
        rows=[dict(id='g'+str(i),label=label,menu_screen_name=self.context,step_order=i+1,
            allowed_aliases=(aliases or {}).get(i,[])) for i,label in enumerate(labels)]
        if physical:rows[0]['screen_context']=physical
        if end_explicit:rows[-1]['direct_end_definition']={'kind':'EXPLICIT_END_CONTROL'}
        return {'processes':[dict(id='arbitrary-unit',business_name='synthetic',procedures=rows)]}
    def step(self,action,target,order=1,sid=None,menu=None,page='/anything'):
        return dict(id=sid or 's'+str(order),action_type=action,target_field_label=target,
            comparison_order=order,menu={'selected_path_text':self.context if menu is None else menu},
            page_title='Product',menu_page=page,execution_ids=['synthetic-execution'],
            evidence_type='direct',matching_eligible=True,resolution_status='RESOLVED')
    def compare(self,steps,truth):
        return evaluate({'processes':[dict(id='arbitrary-unit',procedures=steps)]},truth,compile_roles(truth))
    def test_no_physical_screen_is_required_if_logical_context_is_explicit(self):
        truth=self.gt(['정보 입력'])
        stats=self.compare([self.step('INPUT','정보',page='/arbitrary/not-from-GT')],truth)[2]
        self.assertEqual(stats['correctly_mapped'],1)
        self.assertIsNone(compile_roles(truth)['processes'][0]['procedures'][0]['physical_screen'])
    def test_wrong_logical_menu_cannot_use_same_bu_as_wildcard(self):
        stats=self.compare([self.step('INPUT','정보',menu='다른 메뉴')],self.gt(['정보 입력']))[2]
        self.assertEqual(stats['correctly_mapped'],0)
    def test_unknown_context_is_incomparable_not_zero(self):
        with self.assertRaisesRegex(LogicalMeaningIncomplete,'UNKNOWN_CONTEXT'):
            self.compare([self.step('INPUT','정보',menu='')],self.gt(['정보 입력']))
    def test_explicit_physical_screen_guard_is_retained(self):
        truth=self.gt(['정보 입력'],physical={'kind':'page_path','value':'/correct'})
        self.assertEqual(self.compare([self.step('INPUT','정보',page='/wrong')],truth)[2]['correctly_mapped'],0)
        self.assertEqual(self.compare([self.step('INPUT','정보',page='/Correct')],truth)[2]['correctly_mapped'],0)
    def test_input_does_not_match_result_check_with_same_label_or_alias(self):
        truth=self.gt(['완료 확인'],aliases={0:['상태']})
        stats=self.compare([self.step('SAVE','저장'),self.step('INPUT','상태',2)],truth)[2]
        self.assertEqual(stats['correctly_mapped'],0)
    def test_confirm_does_not_match_completion_inspection(self):
        steps=[self.step('SAVE','저장'),self.step('CONFIRM','완료 확인',2)]
        self.assertEqual(self.compare(steps,self.gt(['완료 확인']))[2]['correctly_mapped'],0)
    def test_passive_outcome_cannot_supply_completion_procedure(self):
        step=self.step('SAVE','저장');step['evidence']=[{'ui_outcome':{'message':'완료 확인'}}]
        self.assertEqual(self.compare([step],self.gt(['완료 확인']))[2]['correctly_mapped'],0)
    def test_direct_completion_inspection_after_write(self):
        steps=[self.step('SAVE','저장'),self.step('RESULT_CHECK','완료 확인',2)]
        steps[1]['completion_observation']={'kind':'SUCCESS_MESSAGE','write_step_id':steps[0]['id']}
        self.assertEqual(self.compare(steps,self.gt(['저장','완료 확인']))[2]['correctly_mapped'],2)
    def test_result_check_without_known_completion_scope_is_incomparable(self):
        with self.assertRaisesRegex(LogicalMeaningIncomplete,'UNKNOWN_COMPLETION_SCOPE'):
            self.compare([self.step('RESULT_CHECK','완료 확인')],self.gt(['완료 확인']))
    def test_registration_start_and_commit_have_different_phases(self):
        truth=self.gt([self.context,'등록','정보 입력','저장'])
        steps=[self.step('PAGE_ENTER',self.context),self.step('REGISTER','등록',2),
            self.step('INPUT','정보',3),self.step('SAVE','저장',4)]
        self.assertEqual(self.compare(steps,truth)[2]['correctly_mapped'],4)
        moved=[self.step('PAGE_ENTER',self.context),self.step('INPUT','정보',2),
            self.step('REGISTER','등록',3),self.step('SAVE','저장',4)]
        self.assertEqual(self.compare(moved,truth)[2]['correctly_mapped'],3)
        commit=self.gt([self.context,'정보 입력','등록'])
        self.assertEqual(self.compare(moved[:3],commit)[2]['correctly_mapped'],3)
        self.assertEqual(self.compare(steps,commit)[2]['correctly_mapped'],2)
    def test_missing_registration_phase_is_not_a_wildcard_or_zero(self):
        with self.assertRaisesRegex(LogicalMeaningIncomplete,'UNKNOWN_REGISTRATION_PHASE'):
            self.compare([self.step('REGISTER','등록')],self.gt([self.context,'정보 입력','등록']))
    def test_entry_requires_typed_entry_action_and_named_context(self):
        self.assertEqual(self.compare([self.step('MENU_ENTER',self.context)],self.gt([self.context]))[2]['correctly_mapped'],1)
        self.assertEqual(self.compare([self.step('SELECT',self.context)],self.gt([self.context]))[2]['correctly_mapped'],0)
        named_page=self.step('PAGE_ENTER','html',menu='');named_page['page_title']=self.context
        self.assertEqual(self.compare([named_page],self.gt([self.context]))[2]['correctly_mapped'],1)
    def test_compound_input_requires_whole_named_object_not_any_field(self):
        truth=self.gt(['거래처 정보 입력'])
        self.assertEqual(self.compare([self.step('INPUT','거래처 정보')],truth)[2]['correctly_mapped'],1)
        self.assertEqual(self.compare([self.step('INPUT','대표 전화번호')],truth)[2]['correctly_mapped'],0)
        fields=[self.step('INPUT','대표 전화번호'),self.step('INPUT','대표 이메일',2)]
        stats=self.compare(fields,truth)[2]
        self.assertEqual((stats['correctly_mapped'],stats['evaluated_procedures'],stats['defined_required']),(0,2,1))
    def test_raw_label_cannot_expand_partial_field_into_compound(self):
        step=self.step('INPUT','전화번호');step['evidence']=[{'associated_label':'거래처 정보 입력'}]
        self.assertEqual(self.compare([step],self.gt(['거래처 정보 입력']))[2]['correctly_mapped'],0)
    def test_selection_numeric_control_not_inferred_as_date(self):
        self.assertEqual(self.compare([self.step('SELECT','날짜')],self.gt(['날짜 선택']))[2]['correctly_mapped'],1)
        step=self.step('SELECT','12');step['evidence']=[{'associated_label':'날짜'}]
        self.assertEqual(self.compare([step],self.gt(['날짜 선택']))[2]['correctly_mapped'],0)
    def test_explicit_final_end_control_is_sufficient_but_close_is_not(self):
        truth=self.gt([self.context,'종료'],end_explicit=True)
        steps=[self.step('PAGE_ENTER',self.context),self.step('SELECT','종료',2)]
        self.assertEqual(self.compare(steps,truth)[2]['correctly_mapped'],2)
        steps[1]=self.step('POPUP_CLOSE','아무 창',2)
        self.assertEqual(self.compare(steps,truth)[2]['correctly_mapped'],1)
    def test_end_label_does_not_bypass_action_or_terminal_order(self):
        truth=self.gt(['종료'],end_explicit=True)
        self.assertEqual(self.compare([self.step('INPUT','종료')],truth)[2]['correctly_mapped'],0)
        steps=[self.step('SELECT','종료'),self.step('INPUT','정보',2)]
        self.assertEqual(self.compare(steps,truth)[2]['correctly_mapped'],0)
    def test_end_position_alone_or_unresolved_cannot_match(self):
        for action,target in [('CONFIRM','확인'),('UNRESOLVED','종료'),('POPUP_CLOSE','종료')]:
            with self.assertRaises(LogicalMeaningIncomplete):
                self.compare([self.step(action,target)],self.gt(['종료']))
    def test_order_and_one_to_one_preserved(self):
        truth=self.gt(['A 입력','B 입력'])
        stats=self.compare([self.step('INPUT','B'),self.step('INPUT','A',2)],truth)[2]
        self.assertEqual(stats['correctly_mapped'],1)
        repeated=self.gt(['A 입력','A 입력'])
        self.assertEqual(self.compare([self.step('INPUT','A')],repeated)[2]['correctly_mapped'],1)
    def test_mixed_and_unresolved_stay_denominator_ineligible(self):
        truth=self.gt(['정보 입력']);steps=[self.step('INPUT','정보')]
        mixed=self.step('INPUT','정보',sid='mixed');mixed.update(evidence_type='mixed',matching_eligible=False,execution_ids=['e1','e2'])
        gen={'processes':[dict(id='arbitrary-unit',procedures=steps),dict(id='CROSS_EXECUTION_MIXED',procedures=[mixed])]}
        stats=evaluate(gen,truth,compile_roles(truth))[2]
        self.assertEqual((stats['correctly_mapped'],stats['evaluated_procedures']),(1,2))
        unresolved=self.step('INPUT','정보');unresolved['resolution_status']='UNRESOLVED'
        self.assertEqual(self.compare([unresolved],truth)[2]['evaluated_procedures'],1)
    def test_no_cross_execution_stitching_or_best_instance(self):
        steps=[self.step('INPUT','A'),self.step('INPUT','B',2)];steps[1]['execution_ids']=['different']
        with self.assertRaisesRegex(LogicalSchemaError,'Multiple executions'):
            self.compare(steps,self.gt(['A 입력','B 입력']))
    def test_source_names_order_aliases_and_ids_conserved(self):
        truth=self.gt(['정보 입력']);sidecar=compile_roles(truth)
        before=copy.deepcopy(truth);self.assertEqual(sidecar,compile_roles(truth));self.assertEqual(truth,before)
        sidecar['processes'][0]['procedures'][0]['logical_context']['name']='output-derived-name'
        with self.assertRaises(LogicalSchemaError):evaluate({'processes':[]},truth,sidecar)
    def test_scoped_alias_not_cross_action_and_ambiguity_rejected(self):
        truth=self.gt(['A 입력','B 입력'],aliases={0:['공유'],1:['공유']})
        with self.assertRaisesRegex(LogicalSchemaError,'Ambiguous scoped alias'):
            self.compare([self.step('INPUT','공유')],truth)
        source=self.gt(['정보 입력'],aliases={0:['Info']})
        self.assertEqual(self.compare([self.step('INPUT','Info')],source)[2]['correctly_mapped'],1)
        self.assertEqual(self.compare([self.step('RESULT_CHECK','Info')],source)[2]['correctly_mapped'],0)
    def test_unknown_gt_role_cannot_be_wildcard(self):
        with self.assertRaises(LogicalSchemaError):self.compare([self.step('SELECT','알수없는 행위')],self.gt(['알수없는 행위']))
    def test_explicit_authoritative_action_is_not_ignored(self):
        truth=self.gt(['정보 입력']);truth['processes'][0]['procedures'][0]['action_type']='RESULT_CHECK'
        with self.assertRaisesRegex(LogicalSchemaError,'Authoritative action conflicts'):
            self.compare([self.step('INPUT','정보')],truth)
        truth['processes'][0]['procedures'][0]['action_type']='INPUT'
        self.assertEqual(self.compare([self.step('INPUT','정보')],truth)[2]['correctly_mapped'],1)

    def test_no_input_mutation_and_determinism(self):
        truth=self.gt(['정보 입력']);step=self.step('INPUT','정보');before=copy.deepcopy((truth,step))
        self.assertEqual(self.compare([step],truth),self.compare([step],truth));self.assertEqual((truth,step),before)
class LogicalBoundaryTests(unittest.TestCase):
    def fixture(self,root,end=False):
        from backend.m02_logical_candidate import REQUIRED_DEPENDENCIES,SNAPSHOT
        from backend.m02_logical_gt import RULES
        hashes={}
        for name in REQUIRED_DEPENDENCIES:
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic dependency '+name)
            hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        model=root/'model/synthetic/manifest.json';model.parent.mkdir(parents=True)
        model.write_text(json.dumps({'file_sha256':{}}));hashes[str(model.relative_to(root))]=hashlib.sha256(model.read_bytes()).hexdigest()
        baseline=root/'baseline.json';baseline.write_text('{"synthetic_original_snapshot":true}')
        hashes[baseline.name]=hashlib.sha256(baseline.read_bytes()).hexdigest()
        source=root/'source-manifest.json';source.write_text('{"synthetic":true}')
        hashes[source.name]=hashlib.sha256(source.read_bytes()).hexdigest()
        helper=LogicalTests();truth=helper.gt(['종료'] if end else ['정보 입력'])
        step=helper.step('POPUP_CLOSE','임의의 창') if end else helper.step('INPUT','정보')
        step.update(generated_step_id=step['id'],business_unit_ownership='ASSIGNED',in_m02_denominator=True)
        gt=root/'gt.json';gt.write_text(json.dumps(truth,ensure_ascii=False))
        snapshot=dict(processes=[dict(source_process_id='P',unlinked_technical_evidence=[])],
            serializer_rules_hash='synthetic-rules',technical_evidence_count=0,raw_evidence_ledger=[])
        generated=dict(processes=[dict(id='arbitrary-unit',source_process_id='P',canonical_instance_id='execution',procedures=[step])],
            ownership_ledger=[step],scope_summary=dict(target_units=['arbitrary-unit'],total_generated_steps=1,
            all_generated_steps=1,mixed_count=0,unassigned_count=0,out_of_scope_count=0,
            per_business_unit={'arbitrary-unit':1},policy='synthetic-scope'))
        artifacts={}
        for key,name,value in [('business_steps','generated-steps.json',snapshot),('scope','generated-scope.json',generated)]:
            path=root/name;path.write_text(json.dumps(value,ensure_ascii=False));hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
            artifacts[key]=dict(path=name,sha256=hashes[name])
        directory=root/SNAPSHOT;directory.mkdir(parents=True)
        outputs={}
        for name,value in [('gt_roles.json',compile_roles(truth)),('logical_contract.json',RULES)]:
            path=directory/name;path.write_text(json.dumps(value,ensure_ascii=False));outputs[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        manifest=dict(stage='PRE_LOGICAL_COMPARISON',score_computed=False,contract=CONTRACT,
            input_code_sha256=hashes,comparison_dependencies=sorted(REQUIRED_DEPENDENCIES),outputs=outputs,
            serializer_version='synthetic',model_version='synthetic',generated_artifacts=artifacts,
            baseline_manifest_path=baseline.name,baseline_manifest_sha256=hashes[baseline.name],
            model_binding=dict(manifest_path=str(model.relative_to(root)),manifest_sha256=hashes[str(model.relative_to(root))],file_sha256={}),
            evaluation_boundary=dict(source_manifest_path=source.name,source_manifest_sha256=hashes[source.name],
                td04_path=gt.name,td04_sha256=hashlib.sha256(gt.read_bytes()).hexdigest(),comparison_contract=CONTRACT))
        (directory/'manifest.json').write_text(json.dumps(manifest))
        return directory,gt
    def gate(self,directory,contract=CONTRACT):
        (directory/'independent_verification.json').write_text(json.dumps(dict(verdict='PASS',
            snapshot_manifest_sha256=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),
            gt_leakage_check='PASS',scope_check='PASS',direct_comparison_contract=contract)))
    def test_no_gate_or_old_v2_contract_cannot_compare(self):
        from backend.m02_logical_candidate import assess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory,gt=self.fixture(root);gt.unlink()
            with patch('backend.m02_logical_candidate.evaluate',side_effect=AssertionError('comparison forbidden')):
                self.assertIsNone(assess(root)[0]['score'])
                self.gate(directory,'ACTION_SCREEN_TARGET_ORDER_V2')
                self.assertIsNone(assess(root)[0]['score'])
    def test_synthetic_new_pass_does_not_require_physical_gt_schema(self):
        from backend.m02_logical_candidate import assess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory,_=self.fixture(root);self.gate(directory)
            result,rows=assess(root)
            self.assertEqual(result['details']['correctly_mapped'],1)
            self.assertTrue(any(row.get('matched_required_step_id')=='g0' for row in rows))
    def test_conditional_end_unknown_returns_null_not_missing_zero(self):
        from backend.m02_logical_candidate import assess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory,_=self.fixture(root,end=True);self.gate(directory)
            result,rows=assess(root)
            self.assertIsNone(result['score'])
            self.assertEqual(result['details']['comparison_status'],'LOGICAL_SEMANTICS_INCOMPARABLE')
            self.assertIsNone(result['details']['per_business_unit'][0]['missing_count'])
            self.assertTrue(all(row.get('match_status')=='NOT_EVALUATED' for row in rows if row['row_type']=='generated_step'))
    def test_executing_dependency_sidecar_and_frozen_generated_bytes_are_bound(self):
        from backend.m02_logical_candidate import assess
        from backend.evaluators import EvaluationError
        for name in ['backend/m02_logical_comparator.py','backend/evaluators.py','source-manifest.json','generated-scope.json']:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);directory,_=self.fixture(root);self.gate(directory);(root/name).write_text('tampered')
                with self.assertRaises(EvaluationError):assess(root)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory,_=self.fixture(root);self.gate(directory);(directory/'gt_roles.json').write_text('{}')
            with self.assertRaises(EvaluationError):assess(root)
class SupportStateTests(unittest.TestCase):
    """Independent L1/L2 counterexamples inspect states, never actual GT or scores."""
    def setUp(self):self.h=LogicalTests()
    def projected(self,steps):
        steps=copy.deepcopy(steps)
        for i,step in enumerate(steps):
            if step['action_type']=='RESULT_CHECK':
                prior=next((s for s in reversed(steps[:i]) if s['action_type'] in ('SAVE','REGISTER','UPDATE') and (not s['menu'].get('selected_path_text') or s['menu']==step['menu'])),None)
                if prior:step['completion_observation']={'kind':'SUCCESS_MESSAGE','write_step_id':prior['id']}
        return [final_projection(step) for step in steps]
    def requirement(self,role,physical=None):
        labels=([self.h.context,'정보 입력','등록','완료 확인'] if role=='COMMIT_REGISTRATION'
            else [self.h.context,'등록','정보 입력','저장','완료 확인'])
        truth=self.h.gt(labels)
        if physical:truth['processes'][0]['procedures'][-1]['screen_context']=physical
        return next(r for r in compile_roles(truth)['processes'][0]['procedures'] if r['logical_role']==role)
    def test_unknown_preceding_input_cannot_be_skipped_to_prove_start(self):
        from backend.m02_logical_comparator import phase
        h=self.h
        p=self.projected([h.step('INPUT','정보',menu=''),h.step('REGISTER','등록',2),h.step('INPUT','정보',3),h.step('SAVE','저장',4)])
        self.assertEqual(phase(p,1),'UNKNOWN')
        self.assertEqual(candidate_state(p,1,self.requirement('INITIATE_REGISTRATION')),'UNKNOWN_REGISTRATION_PHASE')
    def test_ineligible_preceding_input_cannot_prove_commit(self):
        from backend.m02_logical_comparator import phase
        h=self.h;support=h.step('INPUT','정보');support.update(evidence_type='mixed',matching_eligible=False)
        p=self.projected([support,h.step('REGISTER','등록',2)])
        self.assertEqual(phase(p,1),'UNKNOWN')
        self.assertEqual(candidate_state(p,1,self.requirement('COMMIT_REGISTRATION')),'UNKNOWN_REGISTRATION_PHASE')
    def test_ineligible_write_cannot_erase_prior_input_to_prove_start(self):
        from backend.m02_logical_comparator import phase
        h=self.h;write=h.step('SAVE','저장',2);write['matching_eligible']=False
        p=self.projected([h.step('INPUT','정보'),write,h.step('REGISTER','등록',3),h.step('INPUT','정보',4),h.step('SAVE','저장',5)])
        self.assertEqual(phase(p,2),'UNKNOWN')
        self.assertEqual(candidate_state(p,2,self.requirement('INITIATE_REGISTRATION')),'UNKNOWN_REGISTRATION_PHASE')
    def test_ineligible_future_input_or_write_cannot_prove_start(self):
        from backend.m02_logical_comparator import phase
        h=self.h
        for position,field,value in [(1,'matching_eligible',False),(2,'evidence_type','auxiliary'),(2,'resolution_status','UNRESOLVED')]:
            steps=[h.step('REGISTER','등록'),h.step('INPUT','정보',2),h.step('SAVE','저장',3)]
            steps[position][field]=value;p=self.projected(steps)
            self.assertEqual(phase(p,0),'UNKNOWN')
            self.assertEqual(candidate_state(p,0,self.requirement('INITIATE_REGISTRATION')),'UNKNOWN_REGISTRATION_PHASE')
    def test_explicit_different_context_can_be_ignored(self):
        from backend.m02_logical_comparator import phase
        h=self.h;p=self.projected([h.step('INPUT','정보',menu='다른 메뉴'),h.step('REGISTER','등록',2),h.step('INPUT','정보',3),h.step('SAVE','저장',4)])
        self.assertEqual(phase(p,1),'INITIATE')
        self.assertEqual(candidate_state(p,1,self.requirement('INITIATE_REGISTRATION')),'MATCH')
    def test_verified_boundary_can_remove_older_irrelevant_ambiguity(self):
        from backend.m02_logical_comparator import phase
        h=self.h;p=self.projected([h.step('INPUT','정보',menu=''),h.step('SAVE','저장',2),h.step('REGISTER','등록',3),h.step('INPUT','정보',4),h.step('SAVE','저장',5)])
        self.assertEqual(phase(p,2),'INITIATE')
        self.assertEqual(candidate_state(p,2,self.requirement('INITIATE_REGISTRATION')),'MATCH')
    def test_registration_initiation_is_not_completed_write_for_check(self):
        from backend.m02_logical_comparator import phase,verified_write_state
        h=self.h;p=self.projected([h.step('REGISTER','등록'),h.step('INPUT','정보',2),h.step('RESULT_CHECK','완료 확인',3),h.step('SAVE','저장',4)])
        self.assertEqual(phase(p,0),'INITIATE')
        self.assertEqual(verified_write_state(p,0,p[2]),'NOT_WRITE')
        self.assertEqual(candidate_state(p,2,self.requirement('INSPECT_COMPLETION')),'UNKNOWN_COMPLETION_SCOPE')
    def test_ineligible_save_update_or_committed_register_not_completion_proof(self):
        from backend.m02_logical_comparator import verified_write_state
        h=self.h
        for action in ['SAVE','UPDATE','REGISTER']:
            steps=([h.step('INPUT','정보')] if action=='REGISTER' else [])
            index=len(steps);write=h.step(action,'등록' if action=='REGISTER' else '저장',index+1)
            write['matching_eligible']=False;steps += [write,h.step('RESULT_CHECK','완료 확인',index+2)]
            p=self.projected(steps)
            self.assertEqual(verified_write_state(p,index,p[-1]),'UNKNOWN')
            self.assertEqual(candidate_state(p,len(p)-1,self.requirement('INSPECT_COMPLETION')),'UNKNOWN_COMPLETION_SCOPE')
    def test_direct_save_update_and_committed_register_support_check(self):
        from backend.m02_logical_comparator import verified_write_state,phase
        h=self.h
        for action in ['SAVE','UPDATE','REGISTER']:
            steps=([h.step('INPUT','정보')] if action=='REGISTER' else [])
            index=len(steps);steps += [h.step(action,'등록' if action=='REGISTER' else '저장',index+1),h.step('RESULT_CHECK','완료 확인',index+2)]
            p=self.projected(steps)
            if action=='REGISTER':self.assertEqual(phase(p,index),'COMMIT')
            self.assertEqual(verified_write_state(p,index,p[-1]),'VERIFIED')
            self.assertEqual(candidate_state(p,len(p)-1,self.requirement('INSPECT_COMPLETION')),'MATCH')
    def test_new_registration_or_pending_input_blocks_stale_earlier_save(self):
        h=self.h
        sequences=[
            [h.step('SAVE','저장'),h.step('REGISTER','등록',2),h.step('INPUT','정보',3),h.step('RESULT_CHECK','완료 확인',4),h.step('SAVE','저장',5)],
            [h.step('SAVE','저장'),h.step('INPUT','정보',2),h.step('RESULT_CHECK','완료 확인',3)]]
        for steps in sequences:
            p=self.projected(steps);index=next(i for i,x in enumerate(p) if x['action']=='RESULT_CHECK')
            self.assertEqual(candidate_state(p,index,self.requirement('INSPECT_COMPLETION')),'UNKNOWN_COMPLETION_SCOPE')
    def test_unknown_support_context_is_not_proved_different(self):
        h=self.h
        for menu,expected in [('', 'UNKNOWN_COMPLETION_SCOPE'),('다른 메뉴','MATCH')]:
            p=self.projected([h.step('SAVE','저장'),h.step('SAVE','저장',2,menu=menu),h.step('RESULT_CHECK','완료 확인',3)])
            self.assertEqual(candidate_state(p,2,self.requirement('INSPECT_COMPLETION')),expected)
    def test_support_write_uses_logical_not_candidate_physical_context(self):
        h=self.h;p=self.projected([h.step('SAVE','저장',page='/edit'),h.step('RESULT_CHECK','완료 확인',2,page='/result')])
        requirement=self.requirement('INSPECT_COMPLETION',physical={'kind':'page_path','value':'/result'})
        self.assertEqual(candidate_state(p,1,requirement),'MATCH')
