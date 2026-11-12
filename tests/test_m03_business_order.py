"""M03 형식 AND 정답 업무 순서: 격리된 합성 evaluator/API 회귀 시험.

실제 생성기·모델·GPT·업무 사이트·기존 8000 서버는 사용하지 않는다.
"""
import copy
import hashlib
import http.client
import json
import tempfile
import threading
import unittest
import uuid
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.integration_store import ingest
from backend.m03_integration import _no_truth, evaluate_scenarios, generate
from backend.server import Service, make_handler


POLICY = 'EXACT_ACTION_TARGET_SEQUENCE'
EXPECTED = [('click', '고객 검색'), ('click', '고객 선택'),
            ('input', '주문 작성'), ('click', '주문 저장')]


def scenario(unit='BU-A', scenario_id='SCN-A', workflow='WF-A', pairs=None):
    return dict(business_unit_id=unit, workflow_id=workflow, scenario_id=scenario_id,
                status='SUCCESS', steps=[dict(order=i, action=action, target=target)
                                         for i, (action, target) in enumerate(pairs or EXPECTED, 1)])


def order_reference(rows):
    return dict(schema_version='m03-order-reference-v1', reference_id='AUDIT-ORDER-ONLY',
                evaluation_only=True, matching_policy=POLICY,
                fixed_at='2026-11-01T00:00:00+00:00',
                business_units=[dict(business_unit_id=row['business_unit_id'],
                                     workflow_id=row['workflow_id'], steps=copy.deepcopy(row['steps']))
                                for row in rows])


def payload_for(rows, mode='DEVELOPMENT'):
    return dict(run_mode=mode, scenarios=copy.deepcopy(rows))


class M03BusinessOrderEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.row = scenario()
        self.reference = order_reference([self.row])

    def test_a_normal_order_passes_structure_and_business_order(self):
        score, total, details, evidence = evaluate_scenarios(payload_for([self.row]), self.reference)
        self.assertEqual((score, total), (100, 1))
        self.assertEqual(details['evaluation_status'], 'COMPLETED')
        self.assertEqual(details['successful_scenario_count'], 1)
        self.assertTrue(evidence[0]['structure_valid'])
        self.assertTrue(evidence[0]['semantic_order_valid'])
        self.assertTrue(evidence[0]['reference_available'])
        self.assertTrue(evidence[0]['success'])

    def test_b_swapped_business_steps_with_continuous_numbers_fails(self):
        pairs = [EXPECTED[0], EXPECTED[2], EXPECTED[1], EXPECTED[3]]
        swapped = scenario(pairs=pairs)
        self.assertEqual([s['order'] for s in swapped['steps']], [1, 2, 3, 4])
        score, total, _, evidence = evaluate_scenarios(payload_for([swapped]), self.reference)
        self.assertEqual((score, total), (0, 1))
        self.assertTrue(evidence[0]['structure_valid'])
        self.assertFalse(evidence[0]['semantic_order_valid'])
        self.assertFalse(evidence[0]['success'])

    def test_c_missing_business_step_fails(self):
        missing = scenario(pairs=[EXPECTED[0], EXPECTED[2], EXPECTED[3]])
        score, total, _, evidence = evaluate_scenarios(payload_for([missing]), self.reference)
        self.assertEqual((score, total), (0, 1))
        self.assertTrue(evidence[0]['structure_valid'])
        self.assertFalse(evidence[0]['semantic_order_valid'])

    def test_repeated_extra_changed_target_or_action_are_not_exact_order(self):
        variants = {
            'repeat': [EXPECTED[0], EXPECTED[1], EXPECTED[1], *EXPECTED[2:]],
            'extra': [*EXPECTED, ('click', '불필요한 메뉴')],
            'target': [EXPECTED[0], ('click', '다른 고객 선택'), *EXPECTED[2:]],
            'action': [('input', EXPECTED[0][1]), *EXPECTED[1:]],
            'missing_start': EXPECTED[1:],
            'missing_end': EXPECTED[:-1],
        }
        for name, pairs in variants.items():
            with self.subTest(name=name):
                score, total, _, evidence = evaluate_scenarios(payload_for([scenario(pairs=pairs)]), self.reference)
                self.assertEqual((score, total), (0, 1))
                self.assertFalse(evidence[0]['semantic_order_valid'])
                self.assertFalse(evidence[0]['success'])

    def test_matching_workflow_is_required_even_when_steps_match(self):
        changed = scenario(workflow='WF-OTHER')
        score, _, _, evidence = evaluate_scenarios(payload_for([changed]), self.reference)
        self.assertEqual(score, 0)
        self.assertFalse(evidence[0]['semantic_order_valid'])
        self.assertFalse(evidence[0]['success'])

    def test_schema_invalid_and_explicit_failed_cannot_pass_matching_reference(self):
        wrong_order = copy.deepcopy(self.row)
        wrong_order['steps'][1]['order'] = 9
        absent_target = copy.deepcopy(self.row)
        del absent_target['steps'][0]['target']
        failed = dict(self.row, status='FAILED')
        for name, row in [('wrong_order', wrong_order), ('absent_target', absent_target), ('FAILED', failed)]:
            with self.subTest(name=name):
                score, total, _, evidence = evaluate_scenarios(payload_for([row]), self.reference)
                self.assertEqual((score, total), (0, 1))
                self.assertFalse(evidence[0]['structure_valid'])
                self.assertFalse(evidence[0]['success'])

    def test_no_reference_returns_unknown_score_instead_of_zero_or_success(self):
        score, total, details, evidence = evaluate_scenarios(payload_for([self.row]))
        self.assertIsNone(score)
        self.assertEqual(total, 1)
        self.assertEqual(details['evaluation_status'], 'NOT_READY')
        self.assertIsNone(details['successful_scenario_count'])
        self.assertEqual(details['missing_reference_business_units'], ['BU-A'])
        self.assertTrue(evidence[0]['structure_valid'])
        self.assertFalse(evidence[0]['reference_available'])
        self.assertIsNone(evidence[0]['success'])

    def test_partial_reference_preserves_total_and_unavailable_result(self):
        second = scenario('BU-B', 'SCN-B', 'WF-B')
        score, total, details, evidence = evaluate_scenarios(payload_for([self.row, second]), self.reference)
        self.assertIsNone(score)
        self.assertEqual(total, 2)
        self.assertEqual(details['evaluation_status'], 'NOT_READY')
        self.assertIsNone(details['successful_scenario_count'])
        self.assertEqual(details['missing_reference_business_units'], ['BU-B'])
        self.assertTrue(evidence[0]['success'])
        self.assertIsNone(evidence[1]['success'])

    def test_known_generation_failure_remains_false_when_reference_is_missing(self):
        failed = dict(self.row, status='FAILED', steps=[])
        score, total, details, evidence = evaluate_scenarios(payload_for([failed]))
        self.assertIsNone(score)
        self.assertEqual(total, 1)
        self.assertEqual(details['evaluation_status'], 'NOT_READY')
        self.assertFalse(evidence[0]['success'])

    def test_official_ten_keeps_failures_in_denominator_and_eighty_boundary(self):
        rows = [scenario(f'BU-{i:02}', f'SCN-{i:02}', f'WF-{i:02}') for i in range(10)]
        reference = order_reference(rows)
        rows[8]['status'] = 'FAILED'
        rows[8]['steps'] = []
        rows[9]['steps'] = list(reversed(rows[9]['steps']))
        for i, step in enumerate(rows[9]['steps'], 1):
            step['order'] = i
        score, total, details, evidence = evaluate_scenarios(payload_for(rows, 'OFFICIAL'), reference)
        self.assertEqual((score, total), (80, 10))
        self.assertEqual(details['successful_scenario_count'], 8)
        self.assertEqual(details['denominator'], 10)
        self.assertEqual(sum(row['success'] for row in evidence), 8)
        rows[7]['status'] = 'FAILED'
        self.assertEqual(evaluate_scenarios(payload_for(rows, 'OFFICIAL'), reference)[:2], (70, 10))

    def test_official_missing_row_is_rejected_and_duplicate_ids_cannot_fill_count(self):
        with self.assertRaises(EvaluationError):
            evaluate_scenarios(payload_for([self.row], 'OFFICIAL'), self.reference)
        other = scenario('BU-B', 'SCN-B', 'WF-B')
        for field in ('business_unit_id', 'scenario_id'):
            duplicate = copy.deepcopy(other)
            duplicate[field] = self.row[field]
            with self.subTest(field=field), self.assertRaises(EvaluationError):
                evaluate_scenarios(payload_for([self.row, duplicate]), self.reference)

    def test_client_success_booleans_score_and_reference_do_not_override_trusted_reference(self):
        swapped = scenario(pairs=[EXPECTED[0], EXPECTED[2], EXPECTED[1], EXPECTED[3]])
        swapped.update(success=True, semantic_order_valid=True, structure_valid=True)
        payload = payload_for([swapped])
        payload.update(score=100, reference=order_reference([swapped]),
                       details={'semantic_order_valid': True, 'successful_scenario_count': 1})
        score, _, _, evidence = evaluate_scenarios(payload, self.reference)
        self.assertEqual(score, 0)
        self.assertFalse(evidence[0]['semantic_order_valid'])
        self.assertFalse(evidence[0]['success'])

    def test_evaluation_preserves_prediction_and_reference_inputs(self):
        payload = payload_for([self.row])
        before_payload, before_reference = copy.deepcopy(payload), copy.deepcopy(self.reference)
        evaluate_scenarios(payload, self.reference)
        self.assertEqual(payload, before_payload)
        self.assertEqual(self.reference, before_reference)

    def test_evaluation_reference_markers_are_blocked_recursively_in_generation_inputs(self):
        prohibited = [dict(nested=[dict(evaluation_only=True)]),
                      dict(nested=[dict(m03_evaluation_references={'dataset': {'path': 'private-reference.json'}})]),
                      dict(nested=[dict(evaluation_reference=copy.deepcopy(self.reference))])]
        for value in prohibited:
            with self.subTest(value=value), self.assertRaises(EvaluationError):
                _no_truth(value)


class M03BusinessOrderIngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='ktl-m03-order-api-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.folder = self.root / 'data/evaluation/audit-order-only'
        self.folder.mkdir(parents=True)
        self.row = scenario()
        self.reference = order_reference([self.row])
        self.source_path = self.folder / 'input.csv'
        self.source_path.write_text('event_id,event_type\nSYNTHETIC-ONLY,click\n', encoding='utf-8')
        self.reference_path = self.folder / 'order-reference.json'
        self.reference_path.write_text(json.dumps(self.reference, ensure_ascii=False), encoding='utf-8')
        self.reference_sha = self.sha(self.reference_path)
        manifest = dict(dataset_id='audit-m03-order-only', metric_id='M03', run_mode='DEVELOPMENT',
                        source_type='DEVELOPMENT', official=False, data_class='DEVELOPMENT',
                        files=[dict(path=self.source_path.name, sha256=self.sha(self.source_path))])
        self.manifest_path = self.folder / 'data_manifest.json'
        self.manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
        self.config = dict(targets={'M03': 80}, adapters={}, official_manifests={},
                           integration_datasets={manifest['dataset_id']: dict(run_mode='DEVELOPMENT',
                               manifest=self.manifest_path.relative_to(self.root).as_posix())},
                           m03_evaluation_references={manifest['dataset_id']: dict(
                               path=self.reference_path.relative_to(self.root).as_posix(), sha256=self.reference_sha)})
        self.payload = dict(external_run_id='AUDIT-ORDER-' + uuid.uuid4().hex,
                            dataset_id=manifest['dataset_id'], run_mode='DEVELOPMENT',
                            source_module='temporary-audit-only', source_version='v1',
                            submitted_at=datetime.now(timezone.utc).isoformat(),
                            dataset_manifest_sha256=self.sha(self.manifest_path),
                            details={}, scenarios=[copy.deepcopy(self.row)])

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_trusted_config_reference_scores_and_preserves_original_payload(self):
        before = copy.deepcopy(self.payload)
        result = ingest(self.root, self.config, 'M03', self.payload)
        self.assertEqual(result['score'], 100)
        self.assertTrue(result['threshold_met'])
        self.assertIsNone(result['official_pass'])
        folder = self.root / 'results/development' / result['run_id']
        received = json.loads((folder / 'received_payload.json').read_text(encoding='utf-8'))
        self.assertEqual(received, before)
        self.assertEqual(self.payload, before)
        self.assertEqual(self.sha(self.reference_path), self.reference_sha)
        self.assertEqual(self.sha(self.manifest_path), before['dataset_manifest_sha256'])

    def test_body_supplied_reference_cannot_make_missing_server_reference_ready(self):
        self.config.pop('m03_evaluation_references')
        self.payload.update(reference=copy.deepcopy(self.reference), score=100)
        result = ingest(self.root, self.config, 'M03', self.payload)
        self.assertIsNone(result['score'])
        self.assertIsNone(result['threshold_met'])
        self.assertIsNone(result['official_pass'])
        self.assertEqual(result['details']['evaluation_status'], 'NOT_READY')
        self.assertIsNone(result['details']['successful_scenario_count'])

    def test_bad_reference_sha_is_error_without_result_or_reservation(self):
        self.config['m03_evaluation_references'][self.payload['dataset_id']]['sha256'] = '0' * 64
        with self.assertRaises(EvaluationError):
            ingest(self.root, self.config, 'M03', self.payload)
        self.assertFalse((self.root / 'results').exists())

    def test_changed_reference_file_is_error_and_source_evidence_is_untouched(self):
        original_source = self.source_path.read_bytes()
        self.reference_path.write_bytes(self.reference_path.read_bytes() + b' ')
        with self.assertRaises(EvaluationError):
            ingest(self.root, self.config, 'M03', self.payload)
        self.assertFalse((self.root / 'results').exists())
        self.assertEqual(self.source_path.read_bytes(), original_source)

    def test_duplicate_external_id_stays_rejected(self):
        ingest(self.root, self.config, 'M03', self.payload)
        with self.assertRaises(EvaluationError) as caught:
            ingest(self.root, self.config, 'M03', self.payload)
        self.assertEqual(caught.exception.status, 'DUPLICATE_EXTERNAL_RUN')

    def test_real_adapter_input_never_receives_server_reference_registry_or_reference_contents(self):
        config = copy.deepcopy(self.config)
        config['adapters']['scenario_generation'] = ['never-executed-synthetic-adapter']
        definition = dict(business_unit_id='BU-A', workflow_id='WF-A', business_name='합성 주문',
                          start_screen='https://example.invalid/', required_procedures=['주문 저장'],
                          end_condition='합성 결과')
        config['m03'] = dict(generator_mode='REAL', transport='SUBPROCESS',
                             input_manifest=self.manifest_path.relative_to(self.root).as_posix(),
                             business_units=[definition], source_module='temporary-audit-only', source_version='v1')
        def adapter(_config, name, outgoing, _root):
            self.assertEqual(name, 'scenario_generation')
            self.assertEqual(set(outgoing), {'business_unit_id', 'workflow_id', 'business_definition', 'analysis_input'})
            raw = json.dumps(outgoing, ensure_ascii=False)
            for forbidden in ('m03_evaluation_references', 'evaluation_only', self.reference['reference_id'],
                              self.reference_path.relative_to(self.root).as_posix(), self.reference_sha):
                self.assertNotIn(forbidden, raw)
            self.assertEqual(outgoing['analysis_input']['files'], [dict(
                path=self.source_path.relative_to(self.root).as_posix(), sha256=self.sha(self.source_path))])
            return copy.deepcopy(self.row)
        with patch('backend.m03_integration.call_adapter', side_effect=adapter) as mocked:
            result = generate(self.root, config, dict(business_unit_id='BU-A', workflow_id='WF-A',
                                                     generator_mode='REAL', run_mode='DEVELOPMENT'))
        self.assertEqual(result['steps'], self.row['steps'])
        mocked.assert_called_once()
        self.assertEqual(self.sha(self.reference_path), self.reference_sha)

    def test_loopback_result_api_uses_trusted_order_and_ignores_body_reference(self):
        (self.root / 'backend').mkdir()
        (self.root / 'backend/config.json').write_text(json.dumps(self.config), encoding='utf-8')
        handler = make_handler(Service(self.root))
        handler.log_message = lambda *_args: None
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            wrong = scenario(pairs=[EXPECTED[0], EXPECTED[2], EXPECTED[1], EXPECTED[3]])
            for label, row, expected_score in [('normal', self.row, 100), ('swapped', wrong, 0)]:
                payload = copy.deepcopy(self.payload)
                payload['external_run_id'] += '-' + label
                payload['scenarios'] = [row]
                payload.update(reference=order_reference([row]), score=100)
                payload['scenarios'][0].update(success=True, semantic_order_valid=True)
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    connection.request('POST', '/api/integrations/m03/result', json.dumps(payload),
                                       {'Content-Type': 'application/json'})
                    response = connection.getresponse()
                    result = json.loads(response.read())
                    self.assertEqual(response.status, 201, result)
                    self.assertEqual(result['score'], expected_score)
                    self.assertEqual(result['details']['rows'][0]['success'], bool(expected_score))
                finally:
                    connection.close()
        finally:
            server.shutdown()
            worker.join()
            server.server_close()
        self.assertEqual(self.sha(self.reference_path), self.reference_sha)


if __name__ == '__main__':
    unittest.main(verbosity=2)
