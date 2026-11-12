"""새 추론 없이 관측 canonical을 옮기는 adapter의 합성 원본·경계 검증."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m03_canonical_adapter import generate_canonical, main
from backend.m03_integration import evaluate_scenarios


class CanonicalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ktl-canonical-adapter-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.directory = self.root / 'analysis'
        self.directory.mkdir()
        self.canonical = self.directory / 'canonical.json'
        self.models = self.directory / 'process_models.csv'
        self.document = [dict(schema_version='workflow-canonical-1.1', process_model_id='PM-TEST', procedures=[
            dict(id='NODE-1', order=1, action='input', http_method='',
                 target=dict(page_path='/example', role='input', normalized_endpoint=''), evidence=['SYNTHETIC-E1']),
            dict(id='NODE-2', order=2, action='api_confirmation', http_method='POST',
                 target=dict(page_path='/example', role='/api/example', normalized_endpoint='/api/example'),
                 evidence=['SYNTHETIC-E2', 'SYNTHETIC-E3'])])]
        self.canonical.write_text(json.dumps(self.document, ensure_ascii=False), encoding='utf-8')
        self.models.write_text('process_model_id,canonical_instance_id,mode\nPM-TEST,WF-TEST,DEVELOPMENT\n', encoding='utf-8')
        self.payload = dict(business_unit_id='DEV-TEST', workflow_id='WF-TEST',
                            business_definition=dict(business_unit_id='DEV-TEST', workflow_id='WF-TEST',
                                                     canonical_process_model_id='PM-TEST', canonical_instance_id='WF-TEST'),
                            analysis_input=dict(files=[]))
        self.refresh()

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def refresh(self):
        self.payload['analysis_input']['files'] = [dict(path=p.relative_to(self.root).as_posix(), sha256=self.sha(p))
                                                  for p in (self.canonical, self.models)]

    def write_document(self, value):
        self.canonical.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        self.refresh()

    def test_observed_order_actions_targets_ids_evidence_and_methods_are_preserved(self):
        before = copy.deepcopy(self.payload)
        source_bytes = (self.canonical.read_bytes(), self.models.read_bytes())
        result = generate_canonical(self.root, self.payload)
        self.assertEqual(result['status'], 'SUCCESS')
        self.assertEqual(result['generation_method'], 'DETERMINISTIC_CANONICAL_ADAPTER')
        self.assertFalse(result['model_inference_during_generation'])
        self.assertFalse(result['generated_by_llm'])
        self.assertFalse(result['synthetic'])
        self.assertFalse(result['official'])
        self.assertEqual(result['data_class'], 'DEVELOPMENT')
        self.assertEqual(result['workflow_id'], 'WF-TEST')
        for observed, generated in zip(self.document[0]['procedures'], result['steps']):
            for key in ('id', 'order', 'action', 'evidence', 'http_method'):
                self.assertEqual(generated[key], observed[key])
            self.assertEqual(generated['target_details'], observed['target'])
            self.assertEqual(generated['target'], json.dumps(observed['target'], sort_keys=True,
                                                            separators=(',', ':'), ensure_ascii=False))
        self.assertEqual(self.payload, before)
        self.assertEqual((self.canonical.read_bytes(), self.models.read_bytes()), source_bytes)

    def revisited_document(self):
        value = copy.deepcopy(self.document)
        repeated = copy.deepcopy(value[0]['procedures'][0])
        repeated.update(order=3, evidence=['SYNTHETIC-E4'])
        value[0]['procedures'].append(repeated)
        return value

    def test_graph_revisit_retains_three_occurrences_and_distinct_evidence(self):
        document = self.revisited_document()
        self.write_document(document)
        before = self.canonical.read_bytes()
        result = generate_canonical(self.root, self.payload)
        self.assertEqual([step['id'] for step in result['steps']], ['NODE-1', 'NODE-2', 'NODE-1'])
        self.assertEqual([step['node_id'] for step in result['steps']], ['NODE-1', 'NODE-2', 'NODE-1'])
        self.assertEqual([step['occurrence_id'] for step in result['steps']], ['OCC-0001', 'OCC-0002', 'OCC-0003'])
        self.assertEqual([step['order'] for step in result['steps']], [1, 2, 3])
        self.assertEqual([step['evidence'] for step in result['steps']],
                         [step['evidence'] for step in document[0]['procedures']])
        self.assertEqual(self.canonical.read_bytes(), before)

    def test_explicit_occurrences_are_preserved_and_duplicate_occurrences_are_rejected(self):
        document = self.revisited_document()
        for index, procedure in enumerate(document[0]['procedures'], 1):
            procedure.update(node_id=procedure['id'], occurrence_id='SOURCE-OCC-'+str(index))
        self.write_document(document)
        result = generate_canonical(self.root, self.payload)
        self.assertEqual([step['occurrence_id'] for step in result['steps']],
                         ['SOURCE-OCC-1', 'SOURCE-OCC-2', 'SOURCE-OCC-3'])
        document[0]['procedures'][-1]['occurrence_id'] = 'SOURCE-OCC-1'
        self.write_document(document)
        with self.assertRaisesRegex(EvaluationError, 'occurrence'):
            generate_canonical(self.root, self.payload)

    def test_revisited_node_cannot_change_action_target_or_method_within_original_model(self):
        for key in ('action', 'target', 'http_method'):
            document = self.revisited_document()
            repeated = document[0]['procedures'][-1]
            if key == 'target':
                repeated[key]['role'] = 'different-control'
            else:
                repeated[key] = 'DIFFERENT'
            with self.subTest(key=key):
                self.write_document(document)
                with self.assertRaisesRegex(EvaluationError, 'graph nodes'):
                    generate_canonical(self.root, self.payload)

    def test_capture_scope_and_per_occurrence_lineage_are_preserved(self):
        document = self.revisited_document()
        canonical = document[0]
        canonical.update(schema_version='workflow-canonical-1.2', canonical_kind='CAPTURE_OBSERVED_SEQUENCE',
                         source_workflow_ids=['WF-SOURCE-A', 'WF-SOURCE-B'],
                         source_process_model_ids=['PM-SOURCE'], source_session_ids=['SESSION-SYNTHETIC'],
                         source_csv_sha256='1'*64, source_capture_manifest_sha256='2'*64, capture_policy_sha256='3'*64)
        for index, procedure in enumerate(canonical['procedures'], 1):
            procedure.update(source_workflow_id='WF-SOURCE-A' if index < 3 else 'WF-SOURCE-B',
                             source_process_model_id='PM-SOURCE', source_session_id='SESSION-SYNTHETIC',
                             source_csv_rows=[index])
        self.write_document(document)
        before = self.canonical.read_bytes()
        result = generate_canonical(self.root, self.payload)
        self.assertEqual(result['source_canonical_schema'], 'workflow-canonical-1.2')
        for key in ('canonical_kind', 'source_workflow_ids', 'source_process_model_ids', 'source_session_ids',
                    'source_csv_sha256', 'source_capture_manifest_sha256', 'capture_policy_sha256'):
            self.assertEqual(result[key], canonical[key])
        for procedure, step in zip(canonical['procedures'], result['steps']):
            for key in ('source_workflow_id', 'source_process_model_id', 'source_session_id', 'source_csv_rows'):
                self.assertEqual(step[key], procedure[key])
        self.assertEqual(self.canonical.read_bytes(), before)
        result['steps'][-1]['source_csv_rows'].append(999)
        self.assertEqual(canonical['procedures'][-1]['source_csv_rows'], [3])

    def test_same_node_identifier_in_distinct_source_models_has_separate_graph_identity(self):
        document = copy.deepcopy(self.document)
        first, second = document[0]['procedures']
        first['source_process_model_id'] = 'PM-SOURCE-A'
        second.update(id=first['id'], source_process_model_id='PM-SOURCE-B')
        self.write_document(document)
        result = generate_canonical(self.root, self.payload)
        self.assertEqual([step['id'] for step in result['steps']], ['NODE-1', 'NODE-1'])
        self.assertEqual([step['source_process_model_id'] for step in result['steps']], ['PM-SOURCE-A', 'PM-SOURCE-B'])
        self.assertEqual(len({step['occurrence_id'] for step in result['steps']}), 2)

    def test_new_occurrence_metadata_does_not_relax_order_action_target_or_lineage_checks(self):
        variants = [('order', True), ('order', 2), ('action', ''), ('action', []),
                    ('target', {}), ('target', []), ('target', None), ('node_id', 'OTHER-NODE'),
                    ('occurrence_id', ''), ('source_workflow_id', []), ('source_session_id', ''),
                    ('source_csv_rows', []), ('source_csv_rows', [True]), ('source_csv_rows', [0])]
        for key, value in variants:
            document = self.revisited_document()
            document[0]['procedures'][0][key] = value
            with self.subTest(key=key, value=value):
                self.write_document(document)
                before = self.canonical.read_bytes()
                with self.assertRaises(EvaluationError):
                    generate_canonical(self.root, self.payload)
                self.assertEqual(self.canonical.read_bytes(), before)
        document = self.revisited_document()
        document[0]['schema_version'] = 'workflow-canonical-1.2'
        self.write_document(document)
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, self.payload)

    def test_exact_order_accepts_expected_revisit_but_rejects_an_extra_repeat(self):
        self.write_document(self.revisited_document())
        scenario = generate_canonical(self.root, self.payload)
        reference_steps = [{key: step[key] for key in ('order', 'action', 'target')} for step in scenario['steps']]
        reference = dict(schema_version='m03-order-reference-v1', reference_id='SYNTHETIC-EXPECTED-ABA',
                         evaluation_only=True, matching_policy='EXACT_ACTION_TARGET_SEQUENCE',
                         fixed_at='2000-01-01T00:00:00+00:00', business_units=[dict(
                             business_unit_id=scenario['business_unit_id'], workflow_id=scenario['workflow_id'],
                             steps=reference_steps)])
        payload = dict(run_mode='DEVELOPMENT', scenarios=[scenario])
        self.assertEqual(evaluate_scenarios(payload, reference)[0], 100)
        reference['business_units'][0]['steps'] = reference_steps[:2]
        score, count, _, rows = evaluate_scenarios(payload, reference)
        self.assertEqual((score, count), (0, 1))
        self.assertEqual(rows[0]['reason'], 'STEP_COUNT_MISMATCH')
        self.assertFalse(rows[0]['success'])

    def test_same_source_and_selection_keep_scenario_id_and_changed_source_changes_id(self):
        first = generate_canonical(self.root, self.payload)
        self.assertEqual(first, generate_canonical(self.root, self.payload))
        altered = copy.deepcopy(self.document)
        altered[0]['procedures'][0]['target']['role'] = 'different-control'
        self.write_document(altered)
        second = generate_canonical(self.root, self.payload)
        self.assertNotEqual(first['scenario_id'], second['scenario_id'])
        self.assertNotEqual(first['steps'][0]['target'], second['steps'][0]['target'])

    def test_explicit_model_is_selected_without_first_or_best_candidate_fallback(self):
        other = copy.deepcopy(self.document[0])
        other['process_model_id'] = 'PM-OTHER'
        other['procedures'][0]['action'] = 'click'
        self.write_document([other, self.document[0]])
        result = generate_canonical(self.root, self.payload)
        self.assertEqual(result['source_process_model_id'], 'PM-TEST')
        self.assertEqual(result['steps'][0]['action'], 'input')

    def test_model_and_instance_selection_are_required_even_for_one_candidate(self):
        for key in ('canonical_process_model_id', 'canonical_instance_id'):
            with self.subTest(key=key):
                value = copy.deepcopy(self.payload)
                value['business_definition'].pop(key)
                with self.assertRaises(EvaluationError):
                    generate_canonical(self.root, value)

    def test_duplicate_or_missing_selected_model_is_rejected(self):
        for rows in ([self.document[0], self.document[0]], [dict(self.document[0], process_model_id='PM-OTHER')]):
            with self.subTest(rows=len(rows)):
                self.write_document(rows)
                with self.assertRaises(EvaluationError):
                    generate_canonical(self.root, self.payload)

    def test_workflow_and_business_identity_must_match_preselection(self):
        for location, key in [('top', 'workflow_id'), ('definition', 'workflow_id'), ('definition', 'business_unit_id')]:
            with self.subTest(location=location, key=key):
                value = copy.deepcopy(self.payload)
                target = value if location == 'top' else value['business_definition']
                target[key] = 'WRONG'
                with self.assertRaises(EvaluationError):
                    generate_canonical(self.root, value)

    def test_csv_canonical_instance_must_independently_match_workflow(self):
        self.models.write_text('process_model_id,canonical_instance_id,mode\nPM-TEST,WF-OTHER,DEVELOPMENT\n', encoding='utf-8')
        self.refresh()
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, self.payload)

    def test_missing_duplicate_or_non_development_metadata_is_rejected(self):
        values = ['process_model_id,canonical_instance_id,mode\n',
                  'process_model_id,canonical_instance_id,mode\nPM-TEST,WF-TEST,DEVELOPMENT\nPM-TEST,WF-TEST,DEVELOPMENT\n',
                  'process_model_id,canonical_instance_id,mode\nPM-TEST,WF-TEST,OFFICIAL\n']
        for value in values:
            with self.subTest(value=value):
                self.models.write_text(value, encoding='utf-8')
                self.refresh()
                with self.assertRaises(EvaluationError):
                    generate_canonical(self.root, self.payload)

    def test_canonical_and_metadata_hash_mismatches_are_rejected_without_modification(self):
        for source in (self.canonical, self.models):
            with self.subTest(source=source.name):
                original = source.read_bytes()
                source.write_bytes(original + b' ')
                changed = source.read_bytes()
                with self.assertRaises(EvaluationError):
                    generate_canonical(self.root, self.payload)
                self.assertEqual(source.read_bytes(), changed)
                source.write_bytes(original)

    def test_multiple_json_inputs_need_explicit_registered_canonical_path(self):
        extra = self.directory / 'other.json'
        extra.write_text('{}', encoding='utf-8')
        self.payload['analysis_input']['files'].append(dict(path='analysis/other.json', sha256=self.sha(extra)))
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, self.payload)
        self.payload['business_definition']['canonical_input_path'] = 'analysis/canonical.json'
        self.assertEqual(generate_canonical(self.root, self.payload)['source_process_model_id'], 'PM-TEST')
        self.payload['business_definition']['canonical_input_path'] = 'analysis/unregistered.json'
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, self.payload)

    def test_model_metadata_must_be_registered_and_can_be_explicitly_selected(self):
        self.payload['analysis_input']['files'].pop()
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, self.payload)
        self.refresh()
        self.payload['business_definition']['canonical_models_path'] = 'analysis/process_models.csv'
        self.assertEqual(generate_canonical(self.root, self.payload)['source_canonical_instance_id'], 'WF-TEST')

    def test_unsupported_version_and_invalid_steps_are_never_repaired(self):
        variants = []
        version = copy.deepcopy(self.document)
        version[0]['schema_version'] = 'unknown'
        variants.append(version)
        for mutation in ('wrong_order', 'missing_target', 'oversized_target', 'empty_evidence', 'duplicate_id', 'empty_steps'):
            altered = copy.deepcopy(self.document)
            if mutation == 'wrong_order':
                altered[0]['procedures'][0]['order'] = 2
            elif mutation == 'missing_target':
                altered[0]['procedures'][0].pop('target')
            elif mutation == 'oversized_target':
                altered[0]['procedures'][0]['target']['role'] = 'x' * 257
            elif mutation == 'empty_evidence':
                altered[0]['procedures'][0]['evidence'] = []
            elif mutation == 'duplicate_id':
                altered[0]['procedures'][1]['id'] = altered[0]['procedures'][0]['id']
            else:
                altered[0]['procedures'] = []
            variants.append(altered)
        for index, altered in enumerate(variants):
            with self.subTest(index=index):
                self.write_document(altered)
                before = self.canonical.read_bytes()
                with self.assertRaises(EvaluationError):
                    generate_canonical(self.root, self.payload)
                self.assertEqual(self.canonical.read_bytes(), before)

    def test_older_canonical_schema_does_not_invent_missing_http_method(self):
        value = copy.deepcopy(self.document)
        value[0]['schema_version'] = 'workflow-canonical-1'
        for step in value[0]['procedures']:
            step.pop('http_method')
        self.write_document(value)
        result = generate_canonical(self.root, self.payload)
        self.assertEqual(result['source_canonical_schema'], 'workflow-canonical-1')
        self.assertTrue(all('http_method' not in step for step in result['steps']))

    def test_independent_inference_document_canonical_field_is_supported(self):
        self.write_document(dict(mode='DEVELOPMENT', canonical=self.document, tables={}))
        self.assertEqual(len(generate_canonical(self.root, self.payload)['steps']), 2)

    def test_evaluation_markers_in_request_source_and_csv_are_blocked(self):
        value = copy.deepcopy(self.payload)
        value['business_definition']['nested'] = {'evaluation_only': True}
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, value)
        source = copy.deepcopy(self.document)
        source[0]['evaluation_reference'] = {'steps': []}
        self.write_document(source)
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, self.payload)
        self.write_document(self.document)
        self.models.write_text('process_model_id,canonical_instance_id,mode,ground_truth\nPM-TEST,WF-TEST,DEVELOPMENT,private\n', encoding='utf-8')
        self.refresh()
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, self.payload)

    def test_parent_absolute_and_ground_truth_paths_are_blocked(self):
        for path in ('../outside.json', str(self.canonical), 'analysis/ground_truth.json'):
            with self.subTest(path=path):
                value = copy.deepcopy(self.payload)
                value['analysis_input']['files'][0]['path'] = path
                with self.assertRaises(EvaluationError):
                    generate_canonical(self.root, value)

    def test_symlink_guard_branch_rejects_registered_source(self):
        original = Path.is_symlink
        def linked(path):
            return path == self.canonical or original(path)
        with patch.object(Path, 'is_symlink', linked):
            with self.assertRaises(EvaluationError):
                generate_canonical(self.root, self.payload)

    def test_duplicate_json_keys_fail_before_model_selection(self):
        raw = json.dumps(self.document).replace('"process_model_id": "PM-TEST"',
                                                 '"process_model_id":"PM-OTHER","process_model_id":"PM-TEST"')
        self.canonical.write_text(raw, encoding='utf-8')
        self.refresh()
        with self.assertRaises(EvaluationError):
            generate_canonical(self.root, self.payload)

    def test_cli_stdout_is_only_json_and_stderr_stays_empty_on_success(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        stdin = SimpleNamespace(buffer=io.BytesIO(json.dumps(self.payload).encode('utf-8')))
        with patch('sys.stdin', stdin), redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(self.root)
        self.assertEqual(status, 0)
        self.assertEqual(stderr.getvalue(), '')
        self.assertEqual(json.loads(stdout.getvalue())['source_process_model_id'], 'PM-TEST')
        self.assertEqual(len(stdout.getvalue().splitlines()), 1)

    def test_cli_error_has_no_stdout_or_raw_sensitive_diagnostics(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        raw = b'{"PRIVATE_SYNTHETIC_PAYLOAD":'
        with patch('sys.stdin', SimpleNamespace(buffer=io.BytesIO(raw))), redirect_stdout(stdout), redirect_stderr(stderr):
            status = main(self.root)
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), '')
        self.assertNotIn('PRIVATE_SYNTHETIC_PAYLOAD', stderr.getvalue())
        self.assertNotIn(str(self.root), stderr.getvalue())


if __name__ == '__main__':
    unittest.main(verbosity=2)
