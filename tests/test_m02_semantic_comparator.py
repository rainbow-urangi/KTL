"""Synthetic-only counterexamples from independent verification; no actual TD-04 IO."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from backend.m02_semantic_comparator import evaluate, CONTRACT, SemanticSchemaError
from backend.m02_semantic_candidate import verify_frozen_inputs, REQUIRED_DEPENDENCIES
from backend.evaluators import EvaluationError


def dependency_fixture(root):
    hashes = {}
    for name in REQUIRED_DEPENDENCIES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('synthetic dependency: ' + name)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    model = root / 'model/synthetic/manifest.json'
    model.parent.mkdir(parents=True)
    (model.parent/'weights.bin').write_bytes(b'synthetic model, not inference')
    weight_hash = hashlib.sha256((model.parent/'weights.bin').read_bytes()).hexdigest()
    model.write_text(json.dumps({'file_sha256': {'weights.bin': weight_hash}}))
    source = root/'synthetic-source.json'
    source.write_text('{"synthetic":true}')
    for path in (model, model.parent/'weights.bin', source):
        hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(input_code_sha256=hashes, comparison_dependencies=sorted(REQUIRED_DEPENDENCIES),
        model_binding=dict(manifest_path='model/synthetic/manifest.json',
            manifest_sha256=hashes['model/synthetic/manifest.json'],
            file_sha256={'model/synthetic/weights.bin': weight_hash}),
        evaluation_boundary=dict(source_manifest_path='synthetic-source.json',
            source_manifest_sha256=hashes['synthetic-source.json'], td04_path='never-opened-gt.json',
            td04_sha256='1'*64, comparison_contract=CONTRACT))

class ComparatorTests(unittest.TestCase):
    def step(self, action='INPUT', target='Status', page='/edit', order=1, sid='s'):
        return dict(id=sid, action_type=action, target_field_label=target, menu_page=page,
            comparison_order=order, evidence_type='direct', matching_eligible=True,
            resolution_status='RESOLVED')

    def gt(self, action='INPUT', target='Status', page='/edit', order=1, gid='g', aliases=None):
        return dict(id=gid, action_type=action, target_label=target, label=target,
            screen_context={'kind':'page_path', 'value':page}, step_order=order,
            allowed_aliases=aliases or [])

    def compare(self, steps, requirements):
        return evaluate({'processes':[dict(id='unit',procedures=steps)]},
            {'processes':[dict(id='unit',procedures=requirements)]})

    def test_compatible_complete_business_procedure_matches(self):
        _, _, stats, evidence = self.compare([self.step()], [self.gt()])
        self.assertEqual(stats['correctly_mapped'], 1)
        self.assertEqual(evidence[0]['required_step_id'], 'g')

    def test_input_cannot_match_result_check_same_target(self):
        _, _, stats, _ = self.compare([self.step()], [self.gt(action='RESULT_CHECK', page='/result')])
        self.assertEqual(stats['correctly_mapped'], 0)
        self.assertEqual(stats['evaluated_procedures'], 1)

    def test_save_cannot_match_confirm_even_with_target_alias(self):
        _, _, stats, _ = self.compare([self.step(action='SAVE', target='Confirm')],
            [self.gt(action='CONFIRM', target='Acknowledgement', aliases=['Confirm'])])
        self.assertEqual(stats['correctly_mapped'], 0)

    def test_wrong_screen_rejected_even_if_action_and_alias_match(self):
        _, _, stats, _ = self.compare([self.step(target='state')],
            [self.gt(target='Status', page='/other', aliases=['state'])])
        self.assertEqual(stats['correctly_mapped'], 0)

    def test_case_sensitive_page_path_is_not_normalized_into_match(self):
        self.assertEqual(self.compare([self.step(page='/Edit')],[self.gt(page='/edit')])[2]['correctly_mapped'],0)

    def test_aliases_scoped_to_action_and_screen_not_global(self):
        steps = [self.step(action='INPUT', target='shared', sid='first'),
            self.step(action='RESULT_CHECK', target='shared', page='/result', sid='second', order=2)]
        truth = [self.gt(action='INPUT', target='Input state', aliases=['shared']),
            self.gt(action='RESULT_CHECK', target='Result state', page='/result', aliases=['shared'], gid='g2', order=2)]
        self.assertEqual(self.compare(steps, truth)[2]['correctly_mapped'], 2)
        steps[1]['action_type'] = 'INPUT'
        self.assertEqual(self.compare(steps, truth)[2]['correctly_mapped'], 1)

    def test_ambiguous_alias_within_action_screen_blocks_measurement(self):
        truth = [self.gt(target='alpha', aliases=['shared']),
            self.gt(target='beta', aliases=['shared'], gid='g2', order=2)]
        with self.assertRaises(SemanticSchemaError):
            self.compare([self.step(target='shared')], truth)

    def test_missing_gt_semantics_blocks_instead_of_zero_or_guess(self):
        for field in ['action_type','screen_context','step_order']:
            gt = self.gt();gt.pop(field)
            with self.assertRaisesRegex(SemanticSchemaError, 'GT_SEMANTIC_SCHEMA_REQUIRED'):
                self.compare([self.step()], [gt])

    def test_typed_screen_no_fallback_to_other_context_or_auxiliary(self):
        step = self.step(page='/wrong')
        step['page_title'] = '/edit'
        step['evidence'] = [{'page_path':'/edit', 'target_field_label':'Status'}]
        self.assertEqual(self.compare([step],[self.gt()])[2]['correctly_mapped'],0)

    def test_order_preserved_and_one_to_one(self):
        steps = [self.step(target='second'), self.step(target='first',sid='s2',order=2)]
        truth = [self.gt(target='first'), self.gt(target='second',gid='g2',order=2)]
        self.assertEqual(self.compare(steps,truth)[2]['correctly_mapped'],1)
        self.assertEqual(self.compare([self.step()],[self.gt(),self.gt(gid='g2',order=2)])[2]['correctly_mapped'],1)

    def test_required_ids_and_aliases_are_scoped_per_business_process(self):
        generated={'processes':[dict(id=pid,procedures=[self.step(sid=pid+'-step')]) for pid in ('a','b')]}
        truth={'processes':[dict(id=pid,procedures=[self.gt(gid='local-step-id')]) for pid in ('a','b')]}
        self.assertEqual(evaluate(generated,truth)[2]['correctly_mapped'],2)

    def test_auxiliary_mixed_unresolved_never_match_but_stay_denominator(self):
        for field, value in [('evidence_type','mixed'),('matching_eligible',False),('resolution_status','UNRESOLVED')]:
            step=self.step();step[field]=value
            stats=self.compare([step],[self.gt()])[2]
            self.assertEqual(stats['correctly_mapped'],0)
            self.assertEqual(stats['evaluated_procedures'],1)

class DependencyTests(unittest.TestCase):
    def test_dependency_tampering_rejected(self):
        for name in ['backend/m02_semantic_comparator.py','backend/evaluators.py',
                'backend/run_storage.py','model/synthetic/weights.bin','synthetic-source.json']:
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest=dependency_fixture(root)
                verify_frozen_inputs(root,manifest,{})
                (root/name).write_text('tampered')
                with self.assertRaisesRegex(EvaluationError,'Frozen semantic input changed'):
                    verify_frozen_inputs(root,manifest,{})

    def test_missing_dependency_or_model_binding_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);manifest=dependency_fixture(root)
            manifest['input_code_sha256'].pop('backend/evaluators.py')
            with self.assertRaises(EvaluationError):verify_frozen_inputs(root,manifest,{})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);manifest=dependency_fixture(root)
            manifest['model_binding']['file_sha256']={}
            with self.assertRaises(EvaluationError):verify_frozen_inputs(root,manifest,{})
class AdapterGateTests(unittest.TestCase):
    def fixture(self, root, missing_schema=False):
        from backend.semantic_enrichment import enrich
        from backend.m02_semantic_scope import scope_steps
        from backend.business_process_serializer import canonical_bytes
        from backend.m02_semantic_candidate import SNAPSHOT
        from test_semantic_enrichment import SemanticTests
        snapshot = enrich(*SemanticTests().fixture())
        scoped = scope_steps(snapshot, [dict(execution_id='execution', business_unit_id='unit',
            session_id='session',start_event_id='e0',end_event_id='e1')], ['unit'])
        manifest = dependency_fixture(root)
        gt = dict(version='synthetic', processes=[dict(id='unit', business_name='synthetic',
            procedures=[ComparatorTests().gt(target='Name',page='/form')])])
        if missing_schema:
            gt['processes'][0]['procedures'][0].pop('action_type')
        gt_path=root/'never-opened-gt.json';gt_path.write_text(json.dumps(gt))
        manifest['evaluation_boundary']['td04_sha256']=hashlib.sha256(gt_path.read_bytes()).hexdigest()
        manifest.update(stage='PRE_GT_COMPARISON', score_computed=False, model_version='synthetic',
            serializer_version='synthetic', outputs={})
        directory=root/SNAPSHOT;directory.mkdir(parents=True)
        for name,value in [('business_steps.json',snapshot),('scope.json',scoped)]:
            path=directory/name;path.write_bytes(canonical_bytes(value))
            manifest['outputs'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
        (directory/'manifest.json').write_bytes(canonical_bytes(manifest))
        return directory,gt_path

    def gate(self, directory, contract=CONTRACT):
        gate=dict(verdict='PASS',snapshot_manifest_sha256=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),
            gt_leakage_check='PASS',scope_check='PASS',direct_comparison_contract=contract)
        (directory/'independent_verification.json').write_text(json.dumps(gate))

    def test_old_contract_cannot_open_new_gate(self):
        from backend.m02_semantic_candidate import assess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory,gt=self.fixture(root)
            gt.unlink()  # no GT semantic access is possible in this fixture
            self.gate(directory,'EXACT_GENERATED_TARGET_WITH_TD04_ALIASES_V1')
            self.assertIsNone(assess(root)[0]['score'])

    def test_synthetic_pass_only_then_semantic_match_and_csv(self):
        from backend.m02_semantic_candidate import assess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory,_=self.fixture(root)
            self.assertIsNone(assess(root)[0]['score'])
            self.gate(directory)
            result,rows=assess(root)
            self.assertEqual(result['details']['correctly_mapped'],1)
            self.assertEqual(result['details']['evaluated_procedures'],2)
            self.assertEqual(sum(r.get('match_status')=='MATCHED' and r['row_type']=='generated_step' for r in rows),1)
            self.assertTrue(any(r.get('matched_required_step_id')=='g' for r in rows))
            self.assertTrue(any(r['row_type']=='required_step' and r.get('required_step_id')=='g' for r in rows))

    def test_authorized_synthetic_gt_schema_missing_returns_null(self):
        from backend.m02_semantic_candidate import assess
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory,_=self.fixture(root,missing_schema=True)
            self.gate(directory)
            result,_=assess(root)
            self.assertEqual(result['details']['comparison_status'],'GT_SEMANTIC_SCHEMA_REQUIRED')
            self.assertIsNone(result['score'])
