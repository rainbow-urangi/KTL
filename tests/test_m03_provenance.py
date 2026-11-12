"""M03 원생성/사후 평가 경계의 격리된 합성 계약 시험.

OFFICIAL 승인 flag는 코드 경계 검사용이며 실제 공식 시험 증거가 아니다.
모든 파일은 TemporaryDirectory에 쓰며 실제 생성기/GPT/사이트/8000을 호출하지 않는다.
"""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.integration_store import ingest
from backend.m03_provenance import (assess_origins, begin_generation, complete_generation,
                                    generate_recorded, record_assessment)
from backend.m03_reference import load_reference
from backend.official_contracts import OFFICIAL_SPEC
from backend.run_storage import save_run


class M03OriginProvenanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-m03-synthetic-origin-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.folder = self.root / 'data/evaluation/provenance-synthetic'
        self.folder.mkdir(parents=True)
        self.dataset = 'SYNTHETIC-PROVENANCE-CONTRACT-ONLY'
        self.units = [f'BU-{index:02}' for index in range(1, 11)]
        self.source_a = self.folder / 'source-a.csv'
        self.source_b = self.folder / 'source-b.json'
        self.source_a.write_bytes(b'event_id,event_type\nSYNTHETIC-ONLY,click\n')
        self.source_b.write_bytes(b'{"analysis":"SYNTHETIC-CONTRACT-ONLY"}\n')
        source_files = [dict(path=self.relative(path), sha256=self.sha(path))
                        for path in (self.source_a, self.source_b)]
        self.analysis_path = self.folder / 'analysis_manifest.json'
        self.write_json(self.analysis_path, dict(dataset_id=self.dataset, synthetic=False,
                        files=[dict(path=path.name, sha256=self.sha(path))
                               for path in (self.source_a, self.source_b)]))
        self.analysis = dict(dataset_id=self.dataset, manifest_path=self.relative(self.analysis_path),
                             manifest_sha256=self.sha(self.analysis_path), files=source_files)
        self.manifest_path = self.folder / 'data_manifest.json'
        self.manifest = dict(dataset_id=self.dataset, metric_id='M03', source_type='OFFICIAL',
                             run_mode='OFFICIAL', approved_for_official=True, synthetic=False,
                             official=True, business_unit_ids=self.units,
                             official_contract=copy.deepcopy(OFFICIAL_SPEC['M03']),
                             files={f'input_{index}': item for index, item in enumerate(source_files, 1)})
        self.write_json(self.manifest_path, self.manifest)
        self.reference_path = self.folder / 'order-reference.json'
        self.reference = dict(schema_version='m03-order-reference-v1', reference_id='SYNTHETIC-ORIGIN-ONLY',
                              evaluation_only=True, matching_policy='EXACT_ACTION_TARGET_SEQUENCE',
                              fixed_at='2000-01-01T00:00:00+00:00', synthetic=False,
                              approved_for_official=True,
                              business_units=[dict(business_unit_id=unit, workflow_id='WF-'+unit,
                                                   steps=self.steps()) for unit in self.units])
        self.config = dict(targets={'M03': 80, 'M04': 90}, official_manifests={},
                           integration_datasets={self.dataset: dict(run_mode='OFFICIAL',
                               manifest=self.relative(self.manifest_path))},
                           m03_evaluation_references={},
                           adapters={'scenario_generation': ['NEVER-EXECUTED-SYNTHETIC-ADAPTER']},
                           m03=dict(generator_mode='REAL', transport='SUBPROCESS',
                               input_manifest=self.relative(self.analysis_path),
                               source_module='synthetic-test-adapter', source_version='v1',
                               business_units=[dict(business_unit_id=self.units[0], workflow_id='WF-'+self.units[0],
                                   business_name='합성 계약 시험', start_screen='https://example.invalid/',
                                   required_procedures=['합성 저장'], end_condition='합성 저장 완료')]))
        self.register_reference()
        self.request = dict(dataset_id=self.dataset, business_unit_id=self.units[0],
                            workflow_id='WF-'+self.units[0], run_mode='OFFICIAL', generator_mode='REAL')
        self.submission_index = 0

    @staticmethod
    def steps():
        return [dict(order=1, action='open', target='SYNTHETIC screen'),
                dict(order=2, action='click', target='SYNTHETIC save')]

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True)+'\n', encoding='utf-8')

    def relative(self, path):
        return path.relative_to(self.root).as_posix()

    def register_reference(self, value=None, path=None):
        path = path or self.reference_path
        self.write_json(path, self.reference if value is None else value)
        self.config['m03_evaluation_references'][self.dataset] = dict(path=self.relative(path), sha256=self.sha(path))

    def scenario(self):
        return dict(business_unit_id=self.units[0], workflow_id='WF-'+self.units[0],
                    scenario_id='SYNTHETIC-SCN-ONLY', status='SUCCESS', steps=self.steps(),
                    run_mode='OFFICIAL', generator_mode='REAL', synthetic=False)

    def origin(self, analysis=None):
        receipt = begin_generation(self.root, self.config, self.request,
                                   analysis_input=copy.deepcopy(self.analysis if analysis is None else analysis))
        scenario = self.scenario()
        completed = complete_generation(self.root, receipt, scenario)
        self.assertIs(completed, scenario)
        self.assertEqual(scenario['origin_generation_id'], receipt['origin_generation_id'])
        return receipt, scenario

    def body(self, scenarios):
        return dict(dataset_id=self.dataset, run_mode='OFFICIAL', scenarios=copy.deepcopy(scenarios),
                    submitted_at='2099-01-01T00:00:00+00:00')

    def result_rows(self, count, with_origins=False):
        rows = []
        for unit in self.units[:count]:
            row = dict(self.scenario(), business_unit_id=unit, workflow_id='WF-'+unit,
                       scenario_id='SYNTHETIC-SCN-'+unit)
            if with_origins:
                request = dict(self.request, business_unit_id=unit, workflow_id='WF-'+unit)
                receipt = begin_generation(self.root, self.config, request, analysis_input=copy.deepcopy(self.analysis))
                row = complete_generation(self.root, receipt, row)
            rows.append(row)
        return rows

    def integration_payload(self, rows):
        self.submission_index += 1
        return dict(self.body(rows), external_run_id='SYNTHETIC-INGEST-'+str(self.submission_index),
                    source_module='synthetic-test-adapter', source_version='v1',
                    dataset_manifest_sha256=self.sha(self.manifest_path), details={})

    def archived_payload(self, result):
        path = self.root/'results/official'/result['run_id']/'received_payload.json'
        return json.loads(path.read_text(encoding='utf-8'))

    def assess(self, scenarios, body=None, manifest_sha=None):
        body = self.body(scenarios) if body is None else body
        reference, hashes = load_reference(self.root, self.config, self.dataset, 'OFFICIAL', body['submitted_at'])
        return assess_origins(self.root, body, reference, hashes,
                              self.sha(self.manifest_path) if manifest_sha is None else manifest_sha)

    def assert_error(self, call):
        with self.assertRaises(EvaluationError) as raised:
            call()
        self.assertEqual(raised.exception.status, 'ERROR')

    def test_reference_present_before_real_generation_is_bound_to_server_origin(self):
        receipt, scenario = self.origin()
        proof, ids = self.assess([scenario])
        self.assertTrue(proof['official_eligible'])
        self.assertEqual(proof['classification'], 'ORIGINAL_GENERATION_EVALUATION')
        self.assertEqual(ids, [receipt['origin_generation_id']])
        self.assertEqual(proof['submitted_at_role'], 'EVALUATION_RECEIVED_TIME_ONLY')
        self.assertTrue(proof['origins'][0]['reference_preexisted'])
        self.assertEqual(proof['origins'][0]['original_started_at'], receipt['started_at'])
        self.assertNotEqual(proof['origins'][0]['original_started_at'], self.body([])['submitted_at'])

    def test_reference_registered_after_generation_cannot_be_promoted_by_future_submission(self):
        self.config['m03_evaluation_references'].clear()
        _, scenario = self.origin()
        self.register_reference()  # fixed_at is old, but the bytes were absent at generation.
        body = self.body([scenario])
        body.update(generated_at='1999-01-01T00:00:00+00:00', reference_preexisted=True,
                    details={'official_eligible': True, 'classification': 'ORIGINAL_GENERATION_EVALUATION'})
        proof, _ = self.assess([scenario], body=body)
        self.assertFalse(proof['official_eligible'])
        self.assertEqual(proof['classification'], 'POSTHOC_REEVALUATION')
        self.assertFalse(proof['origins'][0]['reference_preexisted'])

    def test_changed_reference_bytes_and_registration_after_generation_are_posthoc(self):
        _, scenario = self.origin()
        changed = copy.deepcopy(self.reference)
        changed['reference_id'] += '-REPLACED'
        self.register_reference(changed)
        proof, _ = self.assess([scenario])
        self.assertFalse(proof['official_eligible'])
        self.assertEqual(proof['classification'], 'POSTHOC_REEVALUATION')

    def test_registration_switched_to_another_path_is_not_the_original_snapshot(self):
        _, scenario = self.origin()
        self.register_reference(path=self.folder/'another-reference.json')
        proof, _ = self.assess([scenario])
        self.assertFalse(proof['official_eligible'])
        self.assertFalse(proof['origins'][0]['reference_preexisted'])

    def test_external_scenario_without_receipt_remains_posthoc_despite_client_claims(self):
        body = self.body([self.scenario()])
        body.update(origin_generation_id='M03-GEN-'+'a'*32, generated_at='2001-01-01T00:00:00+00:00',
                    details={'official_eligible': True, 'reference_preexisted': True})
        proof, ids = self.assess(body['scenarios'], body=body)
        self.assertFalse(proof['official_eligible'])
        self.assertEqual(proof['classification'], 'POSTHOC_REEVALUATION')
        self.assertEqual(ids, [])
        self.assertEqual(proof['origins'][0]['reason'], 'NO_SERVER_GENERATION_RECEIPT')

    def test_unknown_or_invalid_claimed_origin_id_is_error(self):
        for identity in ('M03-GEN-'+'b'*32, '../receipt', 'M03-GEN-not-a-server-id'):
            with self.subTest(identity=identity):
                row = dict(self.scenario(), origin_generation_id=identity)
                self.assert_error(lambda: self.assess([row]))

    def test_client_changed_original_scenario_is_error(self):
        _, scenario = self.origin()
        scenario['steps'][1]['target'] = 'CLIENT-CHANGED-TARGET'
        self.assert_error(lambda: self.assess([scenario]))

    def test_changed_stored_response_bytes_are_error(self):
        receipt, scenario = self.origin()
        path = self.root/'results/m03_generations'/receipt['origin_generation_id']/'response.json'
        path.write_bytes(path.read_bytes()+b' ')
        self.assert_error(lambda: self.assess([scenario]))

    def test_dataset_and_manifest_identity_changes_are_errors(self):
        _, scenario = self.origin()
        changed_dataset = self.body([scenario])
        changed_dataset['dataset_id'] = 'DIFFERENT-SYNTHETIC-DATASET'
        self.assert_error(lambda: self.assess([scenario], body=changed_dataset))
        self.assert_error(lambda: self.assess([scenario], manifest_sha='0'*64))

    def test_changed_manifest_file_is_not_bound_to_the_original_generation(self):
        _, scenario = self.origin()
        changed = dict(self.manifest, description='changed after generation')
        self.write_json(self.manifest_path, changed)
        self.assert_error(lambda: self.assess([scenario]))

    def test_assessment_ledger_marks_re_evaluation_without_changing_origin_snapshots(self):
        receipt, scenario = self.origin()
        folder = self.root/'results/m03_generations'/receipt['origin_generation_id']
        snapshots = {name: (folder/name).read_bytes() for name in ('started.json', 'receipt.json', 'response.json')}
        body = self.body([scenario])
        body_before = copy.deepcopy(body)
        proof, ids = self.assess([scenario], body=body)
        result = dict(run_id='EVAL-M03-20261109T000000-123456789abc', completed_at='2026-11-09T00:00:00+00:00',
                      details={'generation_provenance': proof, 'official_eligible': proof['official_eligible']})
        record_assessment(self.root, ids, result)
        repeated, again_ids = self.assess([scenario], body=body)
        self.assertTrue(repeated['official_eligible'])
        self.assertEqual(repeated['classification'], 'RE_EVALUATION_WITH_PREEXISTING_REFERENCE')
        self.assertTrue(repeated['origins'][0]['evaluated_before'])
        self.assertEqual(ids, again_ids)
        self.assertEqual(body, body_before)
        self.assertEqual(snapshots, {name: (folder/name).read_bytes() for name in snapshots})
        ledger = list((folder/'evaluations').glob('*.json'))
        self.assertEqual(len(ledger), 1)
        self.assertEqual(json.loads(ledger[0].read_text(encoding='utf-8'))['run_id'], result['run_id'])

    def test_missing_analysis_proof_cannot_be_official(self):
        receipt = begin_generation(self.root, self.config, self.request)
        scenario = complete_generation(self.root, receipt, self.scenario())
        proof, _ = self.assess([scenario])
        self.assertFalse(proof['official_eligible'])

    def test_analysis_files_must_match_the_registered_dataset_files(self):
        wrong_hash = copy.deepcopy(self.analysis)
        wrong_hash['files'][0]['sha256'] = '0'*64
        missing_file = copy.deepcopy(self.analysis)
        missing_file['files'].pop()
        unregistered_file = copy.deepcopy(self.analysis)
        unregistered_file['files'][0]['path'] = 'data/evaluation/unregistered.csv'
        for analysis in (wrong_hash, missing_file, unregistered_file):
            with self.subTest(analysis=analysis):
                try:
                    _, scenario = self.origin(analysis)
                except EvaluationError as exc:
                    self.assertEqual(exc.status, 'ERROR')
                else:
                    proof, _ = self.assess([scenario])
                    self.assertFalse(proof['official_eligible'])

    def test_generate_keeps_evaluation_reference_out_of_adapter_input_and_binds_receipt(self):
        reference_before = self.reference_path.read_bytes()
        def adapter(_config, name, outgoing, _root):
            self.assertEqual(name, 'scenario_generation')
            self.assertEqual(set(outgoing), {'business_unit_id', 'workflow_id', 'business_definition', 'analysis_input'})
            serialized = json.dumps(outgoing, ensure_ascii=False)
            for marker in ('m03_evaluation_references', 'evaluation_only', self.reference['reference_id'],
                           self.relative(self.reference_path), self.sha(self.reference_path)):
                self.assertNotIn(marker, serialized)
            self.assertEqual(outgoing['analysis_input']['files'], self.analysis['files'])
            return self.scenario()
        with patch('backend.m03_integration.call_adapter', side_effect=adapter) as mocked:
            scenario = generate_recorded(self.root, self.config, copy.deepcopy(self.request))
        mocked.assert_called_once()
        self.assertIn('origin_generation_id', scenario)
        proof, _ = self.assess([scenario])
        self.assertTrue(proof['official_eligible'])
        self.assertEqual(self.reference_path.read_bytes(), reference_before)

    def test_ingest_nine_external_results_score_ninety_and_archive_only_received_nine(self):
        body = self.integration_payload(self.result_rows(9))
        before = copy.deepcopy(body)
        result = ingest(self.root, self.config, 'M03', body)
        self.assertEqual((result['score'], result['sample_count']), (90, 10))
        self.assertTrue(result['threshold_met'])
        self.assertIsNone(result['official_pass'])
        self.assertEqual(result['details']['raw_counts']['missing_result_count'], 1)
        evidence = result['details']['rows']
        self.assertEqual(len(evidence), 10)
        missing = [row for row in evidence if row['missing_result']]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['business_unit_id'], self.units[-1])
        self.assertEqual(missing[0]['reason'], 'MISSING_RESULT')
        self.assertFalse(missing[0]['success'])
        self.assertEqual(body, before)
        self.assertEqual(self.archived_payload(result), before)
        self.assertEqual(len(self.archived_payload(result)['scenarios']), 9)

    def test_ingest_partial_nine_references_leave_nine_or_ten_results_not_ready(self):
        partial = copy.deepcopy(self.reference)
        partial['business_units'] = partial['business_units'][:9]
        self.register_reference(partial)
        for count in (9, 10):
            with self.subTest(received_result_count=count):
                body = self.integration_payload(self.result_rows(count))
                result = ingest(self.root, self.config, 'M03', body)
                self.assertIsNone(result['score'])
                self.assertEqual(result['sample_count'], 10)
                self.assertEqual(result['status'], 'COMPLETED')
                self.assertEqual(result['details']['evaluation_status'], 'NOT_READY')
                self.assertEqual(result['details']['missing_reference_business_units'], [self.units[-1]])
                self.assertEqual(result['details']['raw_counts']['missing_result_count'], 10-count)
                self.assertIsNone(result['official_pass'])
                self.assertEqual(self.archived_payload(result), body)

    def test_ingest_preexisting_reference_and_nine_real_origins_are_official_but_external_copies_are_not(self):
        rows = self.result_rows(9, with_origins=True)
        original = ingest(self.root, self.config, 'M03', self.integration_payload(rows))
        self.assertEqual((original['score'], original['sample_count']), (90, 10))
        self.assertTrue(original['official_pass'])
        self.assertTrue(original['details']['official_eligible'])
        self.assertEqual(original['details']['generation_provenance']['classification'],
                         'ORIGINAL_GENERATION_EVALUATION')
        copies = copy.deepcopy(rows)
        for row in copies:
            del row['origin_generation_id']
        body = self.integration_payload(copies)
        body['details']['official_eligible'] = True  # Client self-claim must not restore eligibility.
        external = ingest(self.root, self.config, 'M03', body)
        self.assertEqual(external['score'], original['score'])
        self.assertEqual(external['details']['raw_counts'], original['details']['raw_counts'])
        self.assertFalse(external['details']['official_eligible'])
        self.assertIsNone(external['official_pass'])
        self.assertEqual(external['details']['generation_provenance']['classification'], 'POSTHOC_REEVALUATION')

    def test_ingest_late_reference_keeps_ninety_score_posthoc_even_with_future_submission(self):
        self.config['m03_evaluation_references'].clear()
        self.reference_path.unlink()  # A disposable TemporaryDirectory fixture, never repository GT.
        rows = self.result_rows(9, with_origins=True)
        self.register_reference()
        body = self.integration_payload(rows)
        body.update(original_generated_at='1999-01-01T00:00:00+00:00', reference_preexisted=True)
        result = ingest(self.root, self.config, 'M03', body)
        self.assertEqual((result['score'], result['sample_count']), (90, 10))
        self.assertTrue(result['threshold_met'])
        self.assertFalse(result['details']['official_eligible'])
        self.assertIsNone(result['official_pass'])
        proof = result['details']['generation_provenance']
        self.assertEqual(proof['classification'], 'POSTHOC_REEVALUATION')
        self.assertTrue(all(not origin['reference_preexisted'] for origin in proof['origins']))
        self.assertEqual(len(proof['origins']), 9)
        self.assertEqual(self.archived_payload(result), body)

    def test_ledger_failure_preserves_received_evidence_without_publishing_completed_result(self):
        rows = self.result_rows(9, with_origins=True)
        body = self.integration_payload(rows)
        with patch('backend.m03_provenance.record_assessment', side_effect=OSError('synthetic ledger write failure')):
            with self.assertRaisesRegex(OSError, 'synthetic ledger'):
                ingest(self.root, self.config, 'M03', body)
        official = self.root/'results/official'
        self.assertFalse((official/'latest-M03.json').exists())
        directories = list(official.glob('EVAL-M03-*'))
        self.assertEqual(len(directories), 1)
        pending = directories[0]
        self.assertEqual(json.loads((pending/'received_payload.json').read_text(encoding='utf-8')), body)
        self.assertTrue((pending/'evidence.csv').is_file())
        self.assertFalse((pending/'result.json').exists())
        self.assertFalse((pending/'run_manifest.json').exists())
        key = hashlib.sha256(('M03\0'+body['external_run_id']).encode()).hexdigest()
        reservation = json.loads((self.root/'results/integrations'/(key+'.json')).read_text(encoding='utf-8'))
        self.assertEqual(reservation['status'], 'RESERVED')
        with self.assertRaises(EvaluationError) as duplicate:
            ingest(self.root, self.config, 'M03', body)
        self.assertEqual(duplicate.exception.status, 'DUPLICATE_EXTERNAL_RUN')
        completed = ingest(self.root, self.config, 'M03', self.integration_payload(rows))
        self.assertTrue(completed['official_pass'])
        self.assertEqual(completed['details']['generation_provenance']['classification'],
                         'ORIGINAL_GENERATION_EVALUATION')

    def test_failed_ledger_cannot_replace_a_previous_published_latest_result(self):
        rows = self.result_rows(9, with_origins=True)
        original = ingest(self.root, self.config, 'M03', self.integration_payload(rows))
        latest = self.root/'results/official/latest-M03.json'
        before = latest.read_bytes()
        with patch('backend.m03_provenance.record_assessment', side_effect=OSError('synthetic ledger write failure')):
            with self.assertRaisesRegex(OSError, 'synthetic ledger'):
                ingest(self.root, self.config, 'M03', self.integration_payload(rows))
        self.assertEqual(latest.read_bytes(), before)
        self.assertEqual(json.loads(before)['run_id'], original['run_id'])
        directories = list((self.root/'results/official').glob('EVAL-M03-*'))
        pending = [path for path in directories if path.name != original['run_id']]
        self.assertEqual(len(pending), 1)
        self.assertTrue((pending[0]/'received_payload.json').is_file())
        self.assertTrue((pending[0]/'evidence.csv').is_file())
        self.assertFalse((pending[0]/'result.json').exists())
        self.assertFalse((pending[0]/'run_manifest.json').exists())


class M03OfficialEligibilityStorageTests(unittest.TestCase):
    def saved(self, metric='M03', mode='OFFICIAL', eligible=False):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-m03-synthetic-pass-gate-')
        self.addCleanup(temporary.cleanup)
        result = dict(score=90, sample_count=10, status='COMPLETED',
                      details={'official_eligible': eligible}, input_sha256={})
        return save_run(Path(temporary.name).resolve(), metric, mode,
                        {'targets': {'M03': 80, 'M04': 90}}, result, [])

    def test_numeric_official_m03_score_without_origin_eligibility_has_no_official_pass(self):
        result = self.saved(eligible=False)
        self.assertEqual(result['score'], 90)
        self.assertTrue(result['threshold_met'])
        self.assertIsNone(result['official_pass'])
        self.assertIsNone(result['pass'])

    def test_eligible_official_m03_keeps_the_existing_threshold(self):
        result = self.saved(eligible=True)
        self.assertTrue(result['threshold_met'])
        self.assertTrue(result['official_pass'])

    def test_other_metrics_and_nonofficial_modes_keep_existing_pass_behavior(self):
        self.assertTrue(self.saved(metric='M04', eligible=False)['official_pass'])
        development = self.saved(mode='DEVELOPMENT', eligible=True)
        self.assertTrue(development['threshold_met'])
        self.assertIsNone(development['official_pass'])

    def test_before_publish_callback_sees_final_metadata_and_raw_evidence_before_result_files(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-synthetic-before-publish-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        received = {'synthetic-contract-test-only': True}
        result = dict(score=90, sample_count=10, status='COMPLETED', details={}, input_sha256={})
        seen = []
        def before_publish(pending):
            folder = root/'results/official'/pending['run_id']
            self.assertEqual(pending['metric_id'], 'M04')
            self.assertIn('completed_at', pending)
            self.assertTrue(pending['official_pass'])
            self.assertEqual(json.loads((folder/'received_payload.json').read_text(encoding='utf-8')), received)
            self.assertTrue((folder/'evidence.csv').is_file())
            self.assertFalse((folder/'result.json').exists())
            self.assertFalse((folder/'run_manifest.json').exists())
            self.assertFalse((folder.parent/'latest-M04.json').exists())
            seen.append(pending['run_id'])
        completed = save_run(root, 'M04', 'OFFICIAL', {'targets': {'M04': 90}}, result, [],
                             received=received, before_publish=before_publish)
        self.assertEqual(seen, [completed['run_id']])
        folder = root/'results/official'/completed['run_id']
        self.assertTrue((folder/'result.json').is_file())
        self.assertTrue((folder/'run_manifest.json').is_file())
        self.assertEqual(json.loads((folder.parent/'latest-M04.json').read_text(encoding='utf-8'))['run_id'],
                         completed['run_id'])


if __name__ == '__main__':
    unittest.main()
