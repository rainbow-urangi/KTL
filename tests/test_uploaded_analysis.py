"""Temporary fixtures and mocked inference only; no model/browser/external API calls."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.evaluators import EvaluationError
from backend.m03_canonical_adapter import generate_canonical
from backend.m03_integration import development_context
from backend.uploaded_analysis import analyze_upload, apply_analysis_config


class UploadedAnalysisTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-uploaded-analysis-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.dataset_id = 'a' * 32
        self.source_dir = self.root / 'data/development/m01_uploads' / self.dataset_id
        self.source_dir.mkdir(parents=True)
        self.fields = ['id', 'event_id', 'session_id', 'event_time', 'event_type', 'interaction_type',
                       'element_tag', 'api_method', 'api_status_code', 'api_path', 'page_url',
                       'page_title', 'target_selector', 'input_data', 'target_key']
        self.rows = [dict.fromkeys(self.fields, '') for _ in range(3)]
        for index, row in enumerate(self.rows, 1):
            row.update(id=str(index), event_id='SYNTHETIC-E' + str(index),
                       session_id='SYNTHETIC-S1' if index < 3 else 'SYNTHETIC-S2',
                       event_time=f'2026-01-01T00:00:0{3-index}.000+00:00',
                       event_type='DOM_EVENT', interaction_type='click', element_tag='button',
                       page_url='https://example.invalid/fixture', page_title='Synthetic fixture',
                       target_selector='#synthetic', input_data='PRIVATE_SENTINEL_NOT_MODEL_INPUT')
        self.save_source()

    @staticmethod
    def sha(raw):
        return hashlib.sha256(raw).hexdigest()

    def save_source(self):
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, self.fields)
        writer.writeheader()
        writer.writerows(self.rows)
        self.raw = output.getvalue().encode('utf-8-sig')
        (self.source_dir / 'source.csv').write_bytes(self.raw)
        (self.source_dir / 'manifest.json').write_text(json.dumps(dict(
            dataset_id=self.dataset_id, sha256=self.sha(self.raw), target_selector_mapping=False,
            filename='synthetic.csv', run_mode='DEVELOPMENT')), encoding='utf-8')

    def fake_inference(self, streams, directory, *, model_count=2, empty=False):
        """Explicit simulated engine contract, never evidence of an actual torch call."""
        self.observed_streams = copy.deepcopy(streams)
        models, canonical, workflows = [], [], []
        for index in range(model_count):
            model_id, workflow = f'PM-{index + 1:03}', f'WF-{index + 1:04}'
            ids = [event['event_id'] for event in streams[index % len(streams)]]
            models.append(dict(process_model_id=model_id, canonical_instance_id=None if empty else workflow,
                               canonical_status='NO_ACTIONFUL_WORKFLOW' if empty else 'READY',
                               mode='DEVELOPMENT', scope='LEARNED_PROCESS_MEDOID'))
            workflows.append(dict(workflow_instance_id=workflow, event_ids=ids, stream_index=index % len(streams)))
            if not empty:
                canonical.append(dict(schema_version='workflow-canonical-1.1', process_model_id=model_id,
                                      canonical_instance_id=workflow, canonical_kind='LEARNED_PROCESS_MEDOID',
                                      procedures=[dict(id='NODE-1', order=1, action='click', http_method='',
                                          target=dict(page_path='/fixture', role='button', normalized_endpoint=''), evidence=ids)]))
        result = dict(candidate_id='workflow_candidate_v1_3', mode='DEVELOPMENT', official=False,
                      workflows=workflows, cluster_labels=list(range(model_count)),
                      tables=dict(process_models=models, process_steps=[], process_nodes=[], process_edges=[],
                                  process_instances=[], node_inputs=[]), canonical=canonical,
                      forward_evidence=dict(completed=True, evidence_type='COMPLETED_TORCH_FORWARD_HOOKS',
                          boundary_forward_calls=len(streams), representation_forward_calls=len(streams),
                          input_stream_count=len(streams), input_event_count=sum(map(len, streams)), retrained=False))
        return result, dict(source_modified=False, mock_fixture=True), 'f' * 64

    def analyze(self, callback=None, session=None):
        with patch('backend.uploaded_analysis._run_inference', side_effect=callback or self.fake_inference) as infer:
            result = analyze_upload(self.root, self.dataset_id, session=session)
        self.assertEqual(infer.call_count, 1)
        return result

    def test_upload_whole_scope_preserves_bytes_rows_sessions_and_twelve_field_model_boundary(self):
        result = self.analyze()
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(result['model_status'], 'COMPLETED')
        self.assertRegex(result['analysis_id'], r'^UPLOAD-ANALYSIS-[a-f0-9]{32}$')
        self.assertEqual(result['source_csv_sha256'], self.sha(self.raw))
        self.assertEqual(result['counts']['event_count'], 3)
        self.assertEqual(result['counts']['session_count'], 2)
        self.assertEqual((self.source_dir / 'source.csv').read_bytes(), self.raw)
        output = self.root / result['output_directory']
        self.assertEqual((output / 'source.csv').read_bytes(), self.raw)
        self.assertEqual([row['event_id'] for row in result['source_input']['rows']], [row['event_id'] for row in self.rows])
        self.assertEqual([row['data_row'] for row in result['source_input']['rows']], [1, 2, 3])
        self.assertEqual([row['physical_csv_row'] for row in result['source_input']['rows']], [2, 3, 4])
        self.assertEqual([row['worker_ordinal'] for row in result['source_input']['rows']], ['1', '2', '3'])
        self.assertFalse(result['source_input']['capture_evidence_supplied'])
        self.assertEqual(self.observed_streams[0][0]['event_id'], 'SYNTHETIC-E2')
        self.assertEqual(len(result['model_input_fields']), 12)
        for stream in self.observed_streams:
            for event in stream:
                self.assertEqual(set(event), set(result['model_input_fields']) | {'source_dataset'})
                self.assertNotIn('input_data', event)
                self.assertNotIn('PRIVATE_SENTINEL', json.dumps(event))
        self.assertIsNone(result['score'])
        self.assertIsNone(result['official_pass'])

    def test_all_nonempty_models_are_prepared_without_inventing_capture_or_business_labels(self):
        result = self.analyze()
        self.assertEqual(result['counts']['canonical_count'], 2)
        self.assertEqual(result['counts']['procedure_count'], 2)
        settings = result['m03_settings']
        self.assertEqual([unit['canonical_process_model_id'] for unit in settings['business_units']], ['PM-001', 'PM-002'])
        self.assertEqual([unit['business_unit_id'] for unit in settings['business_units']], ['UPLOAD-PM-001', 'UPLOAD-PM-002'])
        serialized = json.dumps(settings, ensure_ascii=False)
        self.assertNotIn('CU02', serialized)
        self.assertNotIn('BU14', serialized)
        self.assertNotIn('CAPTURE_OBSERVED_SEQUENCE', serialized)
        self.assertEqual({unit['scope'] for unit in settings['business_units']}, {'LEARNED_PROCESS_MEDOID'})

    def test_prepared_manifest_passes_existing_context_and_actual_pure_canonical_adapter(self):
        snapshot = self.analyze()
        config = apply_analysis_config({}, snapshot)
        context = development_context(self.root, config)
        self.assertEqual(len(context['business_units']), 2)
        for definition in snapshot['m03_settings']['business_units']:
            scenario = generate_canonical(self.root, dict(business_unit_id=definition['business_unit_id'],
                workflow_id=definition['workflow_id'], business_definition=definition, analysis_input=context['verified_input']))
            self.assertEqual(scenario['status'], 'SUCCESS')
            self.assertEqual(scenario['generation_method'], 'DETERMINISTIC_CANONICAL_ADAPTER')
            self.assertFalse(scenario['generated_by_llm'])
            self.assertEqual(scenario['steps'][0]['action'], 'click')

    def test_every_output_sha_is_root_relative_and_original_data_is_not_changed(self):
        result = self.analyze()
        for relative, expected in result['output_sha256'].items():
            self.assertFalse(Path(relative).is_absolute())
            self.assertEqual(self.sha((self.root / relative).read_bytes()), expected)
        saved = json.loads((self.root / result['output_directory'] / 'snapshot.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, result)

    def test_m03_manifest_binds_original_source_copy_and_ordered_row_evidence(self):
        result = self.analyze()
        path = self.root / result['input_manifest']
        manifest = json.loads(path.read_text(encoding='utf-8'))
        files = {row['path']: row['sha256'] for row in manifest['files']}
        self.assertEqual(len(files), 6)
        self.assertEqual(files['source.csv'], self.sha(self.raw))
        self.assertEqual(files['source_input.json'], self.sha((path.parent / 'source_input.json').read_bytes()))
        (path.parent / 'source.csv').write_bytes(self.raw + b'\n')
        with self.assertRaisesRegex(EvaluationError, 'SHA'):
            development_context(self.root, apply_analysis_config({}, result))

    def test_repeated_analysis_creates_new_outputs_and_keeps_the_previous_snapshot(self):
        first = self.analyze()
        path = self.root / first['output_directory'] / 'snapshot.json'
        original = path.read_bytes()
        second = self.analyze()
        self.assertNotEqual(first['analysis_id'], second['analysis_id'])
        self.assertEqual(path.read_bytes(), original)

    def test_request_config_is_copied_without_global_config_mutation(self):
        snapshot = self.analyze()
        base = dict(targets=dict(M03=80), m03=dict(generator_mode='MOCK'), adapters=dict(other=['unchanged']),
                    m03_evaluation_references={'existing': dict(path='evaluation-only.json', sha256='a' * 64)})
        before = copy.deepcopy(base)
        config = apply_analysis_config(base, snapshot)
        self.assertEqual(base, before)
        self.assertEqual(config['targets'], before['targets'])
        self.assertEqual(config['m03_evaluation_references'], before['m03_evaluation_references'])
        self.assertIn('backend.m03_canonical_adapter', config['adapters']['scenario_generation'])
        self.assertNotIn('m03_evaluation_references', config['m03'])

    def test_more_than_ten_models_preserve_all_outputs_and_block_implicit_subset_selection(self):
        result = self.analyze(lambda streams, directory: self.fake_inference(streams, directory, model_count=11))
        self.assertEqual(result['status'], 'NOT_READY')
        self.assertEqual(result['model_status'], 'COMPLETED')
        self.assertEqual(result['error_code'], 'CANONICAL_SELECTION_REQUIRED')
        self.assertEqual(result['counts']['process_model_count'], 11)
        self.assertEqual(result['counts']['canonical_count'], 11)
        self.assertIsNone(result['m03_settings'])
        output = self.root / result['output_directory']
        self.assertEqual(len(json.loads((output / 'canonical_workflows.json').read_text(encoding='utf-8'))), 11)
        with self.assertRaises(EvaluationError):
            apply_analysis_config({}, result)

    def test_empty_canonical_is_visible_as_not_ready_after_successful_model_forward(self):
        result = self.analyze(lambda streams, directory: self.fake_inference(streams, directory, empty=True))
        self.assertEqual(result['status'], 'NOT_READY')
        self.assertEqual(result['model_status'], 'COMPLETED')
        self.assertEqual(result['error_code'], 'NO_NONEMPTY_CANONICAL')
        self.assertEqual(result['counts']['empty_canonical_count'], 2)
        self.assertEqual(result['empty_canonical_models'], ['PM-001', 'PM-002'])
        self.assertTrue(result['forward_evidence']['completed'])
        self.assertIsNone(result['input_manifest'])

    def test_partial_empty_models_keep_their_reason_and_every_nonempty_model(self):
        def partly_empty(streams, directory):
            result, proof, identity = self.fake_inference(streams, directory)
            result['tables']['process_models'].append(dict(process_model_id='PM-EMPTY',
                canonical_instance_id=None, canonical_status='NO_ACTIONFUL_WORKFLOW',
                mode='DEVELOPMENT', scope='LEARNED_PROCESS_MEDOID'))
            return result, proof, identity
        result = self.analyze(partly_empty)
        self.assertEqual(result['status'], 'COMPLETED')
        self.assertEqual(result['model_status'], 'COMPLETED')
        self.assertEqual(result['counts']['process_model_count'], 3)
        self.assertEqual(result['counts']['canonical_count'], 2)
        self.assertEqual(result['counts']['empty_canonical_count'], 1)
        self.assertEqual(result['empty_canonical_diagnostics'], [dict(process_model_id='PM-EMPTY',
            reason='NO_ACTIONFUL_WORKFLOW', scope='LEARNED_PROCESS_MEDOID', excluded_from_generation=True)])
        self.assertEqual(len(result['m03_settings']['business_units']), 2)

    def test_hash_tampering_before_read_never_calls_inference(self):
        (self.source_dir / 'source.csv').write_bytes(self.raw + b'\n')
        with patch('backend.uploaded_analysis._run_inference') as infer:
            result = analyze_upload(self.root, self.dataset_id)
        infer.assert_not_called()
        self.assertEqual(result['status'], 'ERROR')
        self.assertIsNone(result['m03_settings'])

    def test_source_change_during_model_run_cannot_bind_a_different_csv_to_the_result(self):
        def mutate(streams, directory):
            output = self.fake_inference(streams, directory)
            (self.source_dir / 'source.csv').write_bytes(self.raw + b'\n')
            return output
        result = self.analyze(mutate)
        self.assertEqual(result['status'], 'ERROR')
        self.assertIsNone(result['m03_settings'])

    def test_invalid_ids_and_symlink_components_are_rejected_without_outside_writes(self):
        for value in ['../outside', '', 'a' * 31, 'g' * 32]:
            with self.assertRaises(EvaluationError):
                analyze_upload(self.root, value)
        original = Path.is_symlink
        with patch.object(Path, 'is_symlink', lambda path: path == self.source_dir or original(path)):
            with self.assertRaises(EvaluationError):
                analyze_upload(self.root, self.dataset_id)

    def test_duplicate_ids_missing_timezone_and_truth_headers_fail_before_model_calls(self):
        for kind in ['duplicate', 'timezone', 'truth']:
            with self.subTest(kind=kind):
                original_rows, original_fields = copy.deepcopy(self.rows), self.fields[:]
                if kind == 'duplicate':
                    self.rows[1]['event_id'] = self.rows[0]['event_id']
                elif kind == 'timezone':
                    self.rows[0]['event_time'] = '2026-01-01T00:00:00'
                else:
                    self.fields.append('ground_truth')
                self.save_source()
                with patch('backend.uploaded_analysis._run_inference') as infer:
                    result = analyze_upload(self.root, self.dataset_id)
                infer.assert_not_called()
                self.assertNotEqual(result['status'], 'COMPLETED')
                self.assertIsNone(result['m03_settings'])
                self.rows, self.fields = original_rows, original_fields
                self.save_source()

    def test_forward_evidence_cannot_be_claimed_for_an_incomplete_model_call(self):
        def incomplete(streams, directory):
            result, proof, identity = self.fake_inference(streams, directory)
            result['forward_evidence']['boundary_forward_calls'] = 0
            return result, proof, identity
        result = self.analyze(incomplete)
        self.assertEqual(result['status'], 'ERROR')
        self.assertEqual(result['model_status'], 'ERROR')
        self.assertIsNone(result['forward_evidence'])

    def test_inference_error_is_persisted_without_secret_exception_values(self):
        with patch('backend.uploaded_analysis._run_inference', side_effect=RuntimeError('PRIVATE_EXCEPTION_SENTINEL')):
            result = analyze_upload(self.root, self.dataset_id)
        self.assertEqual(result['status'], 'ERROR')
        self.assertEqual(result['model_status'], 'ERROR')
        self.assertNotIn('PRIVATE_EXCEPTION_SENTINEL', json.dumps(result))
        self.assertIsNone(result['m03_settings'])

    def test_existing_server_session_guard_is_applied_before_source_analysis(self):
        guard = Mock()
        self.analyze(session=guard)
        guard.check.assert_called_once_with('CSV', self.dataset_id)


if __name__ == '__main__':
    unittest.main()
