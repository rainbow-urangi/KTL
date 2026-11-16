"""Track A isolated synthetic native-submit recovery and shared dispatch tests."""
import copy,csv,hashlib,importlib.util,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_m02_business_abstraction as fixtures
from backend.m02_track_a_native_submit import recover,RULES_HASH
from backend.evaluators import csv_evidence

class NativeSubmitTests(unittest.TestCase):
 def fixture(self,text='등록',tag='form',action='submit'):
  row=fixtures.row('native',action=action,tag=tag)
  row['locators_json']['raw_payload']={'submitter_text':text,'submitter_selector':'form#alpha > button','form_id':'alpha','form_name':'example','password':'SECRET-MUST-NOT-COPY'}
  row['locators_json']['relation_context']={'related_strategy':'submit_recent_action_fallback','related_event_id':'old-click'}
  return fixtures.generate([row]),[row]
 def test_exact_recorded_write_verbs_native_commit_no_click_inference(self):
  for text,kind in [('저장','SAVE'),('등록','REGISTER'),('수정','UPDATE'),('save','SAVE'),('register','REGISTER'),('update','UPDATE')]:
   source,raw=self.fixture(text);step=fixtures.steps(recover(source,raw))[0]
   self.assertEqual((step['action_type'],step['intent_phase'],step['target_field_label']),(kind,'COMMIT',text))
   self.assertEqual(step['intent_source_event_ids'],['native']);self.assertEqual(step['source_event_ids'],['native'])
   self.assertEqual(step['native_submit_previous_semantics']['action_type'],'UNRESOLVED')
   self.assertEqual(step['native_submit_evidence']['relation_context']['related_strategy'],'submit_recent_action_fallback')
 def test_unknown_verb_form_type_or_non_submit_not_promoted(self):
  for text,tag,action in [('로그인','form','submit'),('','form','submit'),('저장','div','submit'),('저장','form','click')]:
   source,raw=self.fixture(text,tag,action);result=recover(source,raw)
   self.assertEqual([s['action_type'] for s in fixtures.steps(result)],[s['action_type'] for s in fixtures.steps(source)])
 def test_all_existing_raw_values_and_other_intents_preserved(self):
  source,raw=self.fixture();before=copy.deepcopy((source,raw));result=recover(source,raw)
  self.assertEqual((source,raw),before);self.assertEqual(result,recover(source,raw))
  self.assertEqual(result['serializer_rules_hash'],RULES_HASH)
  old=fixtures.steps(source)[0];new=fixtures.steps(result)[0]
  for key in ['generated_step_id','process_id','workflow_id','source_event_ids','source_node_ids','intent_source_event_ids','step_order','business_context','completion_evidence']:
   self.assertEqual(new[key],old[key])
  self.assertNotIn('SECRET-MUST-NOT-COPY',json.dumps(result))
  for k,v in source['raw_evidence_ledger'][0].items():self.assertEqual(v,result['raw_evidence_ledger'][0][k])
 def test_submit_already_consumed_via_fallback_fails_closed(self):
  click=fixtures.row('click',text='저장');submit=fixtures.row('native','submit',tag='form',cause='click')
  submit['locators_json']['raw_payload']={'submitter_text':'저장','submitter_selector':'form > button'}
  submit['locators_json']['relation_context']={'related_strategy':'submit_recent_action_fallback'}
  source=fixtures.generate([click,submit]);before=copy.deepcopy(source)
  with self.assertRaisesRegex(ValueError,'fallback submit already consumed'):recover(source,[click,submit])
  self.assertEqual(source,before)
 def test_verified_same_kind_existing_write_no_duplicate(self):
  click=fixtures.row('click',text='저장');submit=fixtures.row('native','submit',tag='form',cause='click')
  submit['locators_json']['raw_payload']={'submitter_text':'저장','submitter_selector':'form > button'}
  submit['locators_json']['relation_context']={'related_strategy':'explicit_event_id'}
  source=fixtures.generate([click,submit]);result=recover(source,[click,submit])
  self.assertEqual(len(fixtures.steps(result)),1);self.assertEqual(result['native_submit_recovery_audit'][0]['status'],'EXISTING_WRITE_EVIDENCE_PRESERVED')
 def test_existing_conflicting_action_fails_closed(self):
  click=fixtures.row('click',text='저장');submit=fixtures.row('native','submit',tag='form',cause='click')
  submit['locators_json']['raw_payload']={'submitter_text':'등록','submitter_selector':'form > button'}
  source=fixtures.generate([click,submit])
  with self.assertRaisesRegex(ValueError,'Conflicting native submit'):recover(source,[click,submit])
 def test_ambiguous_map_not_promoted_to_matching_eligible_semantics(self):
  source,raw=self.fixture();fixtures.steps(source)[0]['process_id']='AMBIGUOUS_MODEL_MEMBERSHIP'
  result=recover(source,raw);self.assertEqual(fixtures.steps(result)[0]['resolution_status'],'UNRESOLVED')
 def test_missing_duplicate_or_changed_raw_identity_rejected(self):
  source,raw=self.fixture()
  with self.assertRaises(ValueError):recover(source,[])
  with self.assertRaises(ValueError):recover(source,raw*2)
 def test_gt_score_business_payload_are_not_inputs(self):
  source,raw=self.fixture();expected=recover(source,raw)
  raw[0].update(ground_truth='forbidden',business_unit_id='forbidden',score=100)
  raw[0]['locators_json']['raw_payload'].update(gt_label='forbidden',score=100)
  self.assertEqual(recover(source,raw),expected)
 def test_csv_roundtrip_exact_submitter_and_fallback_metadata(self):
  source,raw=self.fixture();result=recover(source,raw);step=fixtures.steps(result)[0]
  row=next(csv.DictReader(io.StringIO(csv_evidence([dict(row_type='generated_step',**step)]).lstrip('\ufeff'))))
  self.assertEqual(json.loads(row['native_submit_evidence']),step['native_submit_evidence'])
  self.assertEqual(json.loads(row['evidence'])[0]['native_submit']['submitter_text'],'등록')

class SharedDispatchTests(unittest.TestCase):
 def test_old_and_new_server_m02_dispatch_same_synthetic_sentinel(self):
  from backend.server import Service
  import backend.server as current
  old=Path(__file__).resolve().parents[1]/'evaluation_contracts/development/m02_logical_support_fix_baseline_archive/backend/server.py'
  spec=importlib.util.spec_from_file_location('backend._track_a_old_server',old);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  for cls in [module.Service,current.Service]:
   with patch.object(cls,'config',return_value={}),patch.object(cls,'source',return_value=object()),patch('backend.m02_candidate.run',return_value={'synthetic':'M02_DISPATCH_ONLY'}) as run:
    result=cls().run('M02','DEVELOPMENT','v1_2_1_unseen_m02_development')
    self.assertEqual(result,{'synthetic':'M02_DISPATCH_ONLY'});self.assertEqual(run.call_count,1)

class NativeCandidateGateTests(unittest.TestCase):
 def fixture(self,root):
  import shutil
  import test_m02_business_abstraction as fixtures
  from backend.m02_track_a_candidate import REQUIRED_DEPENDENCIES,SNAPSHOT
  old,gt=fixtures.AbstractionGateTests().fixture(root);dest=root/SNAPSHOT;shutil.copytree(old,dest)
  manifest=json.loads((dest/'manifest.json').read_text());manifest['stage']='PRE_TRACK_A_COMPARISON'
  for name in REQUIRED_DEPENDENCIES:
   p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
   if not p.exists():p.write_text('synthetic dependency '+name)
   manifest['input_code_sha256'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
  manifest['comparison_dependencies']=sorted(REQUIRED_DEPENDENCIES)
  for entry in manifest['generated_artifacts'].values():
   name=Path(entry['path']).name;entry['path']=str((dest/name).relative_to(root));manifest['input_code_sha256'][entry['path']]=entry['sha256']
  (dest/'manifest.json').write_text(json.dumps(manifest));return dest,gt
 def gate(self,dest,native=False):
  from backend.m02_abstraction_comparator import CONTRACT
  value=dict(verdict='PASS',snapshot_manifest_sha256=hashlib.sha256((dest/'manifest.json').read_bytes()).hexdigest(),gt_leakage_check='PASS',scope_check='PASS',direct_comparison_contract=CONTRACT)
  if native:value['native_submit_recovery_check']='PASS'
  (dest/'independent_verification.json').write_text(json.dumps(value))
 def test_native_specific_pass_required_before_gt_read(self):
  from backend.m02_track_a_candidate import assess
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);d,gt=self.fixture(root);gt.unlink()
   with patch('backend.m02_track_a_candidate.evaluate',side_effect=AssertionError('forbidden before native PASS')):
    self.assertIsNone(assess(root)[0]['score']);self.gate(d);self.assertIsNone(assess(root)[0]['score'])
 def test_synthetic_correct_native_gate_uses_unchanged_comparison_contract(self):
  from backend.m02_track_a_candidate import assess
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);d,_=self.fixture(root);self.gate(d,True);result,rows=assess(root)
   self.assertEqual(result['score'],100);self.assertEqual(result['details']['correctly_mapped'],1);self.assertEqual(result['details']['included_required'],2)
 def test_native_dependency_tamper_fails_closed(self):
  from backend.m02_track_a_candidate import assess
  from backend.evaluators import EvaluationError
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);d,_=self.fixture(root);self.gate(d,True);(root/'backend/m02_track_a_native_submit.py').write_text('tampered')
   with self.assertRaises(EvaluationError):assess(root)
