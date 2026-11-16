"""Synthetic BU03 remediation contracts; no real raw data, site, browser or GPT."""
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from backend import execution_contexts
from backend.evaluators import EvaluationError
from backend.m03_integration import validate_scenario_result
from backend.m04 import m03_schedule_binding as binding
from backend.m04.scenario_compiler import compile_code
from backend.m04.store import M04Manager
from backend.session import RuntimeSession


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fingerprint(source):
    return sha(json.dumps({key: source.get(key) for key in binding._KEYS}, ensure_ascii=False,
                          sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8'))


class ScheduleRemediationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-bu03-remediation-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.config = dict(targets=dict(M01=65, M02=75, M03=80, M04=90, M05=.79, M06=1, M07=80),
                           adapters={}, official_manifests={}, integration_datasets={}, m03={}, m04={}, m07={})
        (self.root / 'backend').mkdir()
        (self.root / 'backend/config.json').write_bytes(encoded(self.config))
        self.rows = [dict(event_id='SYNTHETIC-EVENT-' + str(n), interaction_type='screen_change',
                          target_selector='#synthetic-observation', element_tag='div') for n in range(2, 262)]
        interactions = {32: ('click', '.synthetic-calendar-date', 'span'),
                        33: ('popup_open', '.synthetic-modal', 'div'),
                        34: ('popup_structure', '.synthetic-modal', 'div'),
                        36: ('change', binding.TITLE, 'input'),
                        43: ('paste', binding.DESCRIPTION, 'textarea'),
                        44: ('change', binding.DESCRIPTION, 'textarea'),
                        46: ('submit', binding.FORM, 'form'),
                        47: ('api_transaction', 'html', 'html'),
                        48: ('api_transaction', 'html', 'html'),
                        49: ('popup_close', '.synthetic-modal', 'div')}
        for row in (35, 37, 38, 39, 40, 41, 42, 45):
            interactions[row] = ('click', '.synthetic-calendar-background', 'div')
        for number, (interaction, selector, tag) in interactions.items():
            self.rows[number - 2].update(interaction_type=interaction, target_selector=selector, element_tag=tag)
        source_rows = [18, 23, 36, 43, 46]
        self.source = dict(business_unit_id='BU03', workflow_id='SYNTHETIC-WF-SCHEDULE',
            scenario_id='SYNTHETIC-BU03-FAILED', generator_version='SYNTHETIC-OBSERVED-V1',
            source_snapshot_sha256='1' * 64, status='FAILED', run_mode='DEVELOPMENT',
            synthetic=True, official=False,
            steps=[dict(order=order, action=action, target='Synthetic observed target ' + str(order),
                        source_step_id='SYNTHETIC-STEP-' + str(order),
                        source_event_ids=[self.rows[row - 2]['event_id']],
                        source_node_ids=['SYNTHETIC-NODE-' + str(order)])
                   for order, action, row in zip([1, 2, 7, 14, 16],
                       ['NAVIGATE', 'DETAIL_OPEN', 'INPUT', 'INPUT', 'REGISTER'], source_rows)],
            issues=[dict(order=order, reason='UNRESOLVED_OR_UNSUPPORTED_OBSERVED_STEP')
                    for order in (3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 15)])
        mapped = [32, 33, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46]
        model_groups = [[18, 23, 27], [28]] + [[n] for n in mapped]
        self.snapshot = dict(processes=[dict(canonical_instance_id=self.source['workflow_id'],
            business_steps=[dict(step_order=i + 1, source_event_ids=[self.rows[n - 2]['event_id'] for n in group])
                            for i, group in enumerate(model_groups)])])
        self.raw_path = self.root / binding.RAW
        self.observed_path = self.root / binding.OBSERVED
        self.raw_path.parent.mkdir(parents=True)
        self.observed_path.parent.mkdir(parents=True)
        self.raw_path.write_bytes(self.csv_bytes(self.rows))
        self.observed_path.write_bytes(encoded(self.snapshot))
        self.enterContext(patch.object(binding, 'SOURCE_PIN', fingerprint(self.source)))
        self.enterContext(patch.object(binding, 'RAW_SHA256', sha(self.raw_path.read_bytes())))
        self.enterContext(patch.object(binding, 'OBSERVED_SHA256', sha(self.observed_path.read_bytes())))
        clock = self.enterContext(patch.object(binding, 'datetime'))
        clock.now.return_value = datetime(2026, 11, 16, 3, tzinfo=timezone.utc)
        self.parameters = dict(date='2026-11-16', title='KTL-synthetic-remediation', description='Synthetic new description')
        self.process = self.enterContext(patch('subprocess.Popen', side_effect=AssertionError('No real process or browser')))
        self.provider = self.enterContext(patch('urllib.request.urlopen', side_effect=AssertionError('No real HTTP or GPT')))
        self.network = self.enterContext(patch('socket.create_connection', side_effect=AssertionError('No external connection')))
        self.enterContext(patch('backend.m04.cu02.login_configured', return_value=False))
        self.run_id = 'DEV-M03-20261116T000000-' + uuid.uuid4().hex[:12]
        self.source_folder = self.root / 'results/development' / self.run_id
        self.source_folder.mkdir(parents=True)
        self.write_source()
        (self.source_folder / 'result.json').write_bytes(encoded(dict(run_id=self.run_id,
            metric_id='M03', run_mode='DEVELOPMENT', status='COMPLETED', score=None, official_pass=None,
            details=dict(evaluation_status='NOT_READY', synthetic=True))))
        self.session = RuntimeSession()
        self.session.claim('RESULT', self.run_id)
        self.manager = M04Manager(self.root, lambda: self.config, session=self.session)

    def tearDown(self):
        self.process.assert_not_called()
        self.provider.assert_not_called()
        self.network.assert_not_called()

    @staticmethod
    def csv_bytes(rows):
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=['event_id', 'interaction_type', 'target_selector', 'element_tag'],
                                lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode('utf-8')

    def write_source(self):
        (self.source_folder / 'received_payload.json').write_bytes(encoded(dict(
            run_mode='DEVELOPMENT', synthetic=True, scenarios=[self.source])))

    def payload(self):
        return dict(m03_run_id=self.run_id, scenario_id=self.source['scenario_id'],
                    source_scenario_sha256=sha(encoded(self.source)), parameters=deepcopy(self.parameters))

    def protected(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in [self.raw_path, self.observed_path,
                self.source_folder / 'received_payload.json', self.source_folder / 'result.json']}

    def test_exact_failed_source_get_descriptor_has_inputs_without_fixing_m03_or_registering(self):
        before = self.protected()
        with patch.object(self.manager, 'register', side_effect=AssertionError('GET is not preparation')):
            catalog = self.manager.m03_scenarios(self.run_id)
        row = catalog['scenarios'][0]
        self.assertTrue(row['ready'])
        self.assertEqual(row['status'], 'NEEDS_INPUT')
        self.assertEqual(row['source_status'], 'FAILED')
        self.assertEqual(row['source_step_count'], 5)
        self.assertEqual([x['name'] for x in row['parameters']], ['date', 'title', 'description'])
        self.assertEqual(row['execution_source_kind'], 'REVIEWED_REMEDIATION')
        self.assertFalse(validate_scenario_result(self.source)['success'])
        self.assertEqual(self.protected(), before)
        self.assertEqual(list(self.manager.script_directory.glob('*/script.json')), [])

    def test_provenance_preserves_all_eighteen_rows_four_model_omissions_and_ambiguous_clicks(self):
        before = self.protected()
        proof = binding.provenance(self.root, self.source)
        self.assertEqual(proof['source_window'], dict(first_csv_row=32, last_csv_row=49, row_count=18))
        ledger = proof['observed_rows']
        self.assertEqual([r['csv_row'] for r in ledger], list(range(32, 50)))
        self.assertEqual([r['event_id'] for r in ledger], [r['event_id'] for r in self.rows[30:48]])
        self.assertEqual([r['csv_row'] for r in ledger if not r['in_m02_business_steps']], [34, 47, 48, 49])
        self.assertEqual(proof['ambiguous_click_rows'], [35, 37, 38, 39, 40, 41, 42, 45])
        self.assertTrue(all(r['disposition'] == 'reference' for r in ledger if r['csv_row'] in proof['ambiguous_click_rows']))
        self.assertEqual(proof['source_issues'], self.source['issues'])
        self.assertEqual(len(proof['source_issues']), 11)
        self.assertTrue(all('fallback, not proven causality' in r['causal_link_policy'] for r in ledger))
        for flag in ('exact_historical_click_replay', 'new_model_inference', 'original_m03_status_modified', 'official'):
            self.assertIs(proof[flag], False)
        self.assertEqual(self.protected(), before)

    def test_remediation_is_separate_eight_steps_and_requires_persisted_values_after_refresh(self):
        before = deepcopy((self.source, self.parameters))
        prepared = binding.prepare(self.root, self.source, self.parameters)
        effective, contract = prepared['scenario'], prepared['contract']
        self.assertEqual((self.source, self.parameters), before)
        self.assertEqual(self.source['status'], 'FAILED')
        self.assertEqual([s['order'] for s in self.source['steps']], [1, 2, 7, 14, 16])
        self.assertEqual(effective['source_generation_status'], 'FAILED')
        self.assertEqual(effective['execution_source_kind'], 'REVIEWED_REMEDIATION')
        self.assertEqual([s['action'] for s in effective['steps']],
                         ['open', 'click', 'input', 'input', 'submit', 'refresh', 'click', 'click'])
        self.assertEqual(len(contract['steps']), 8)
        self.assertEqual(effective['scenario_id'], self.source['scenario_id'])
        self.assertTrue(effective['steps'][1]['target'].endswith('.monthly-calendar__date-number'))
        self.assertEqual(effective['steps'][4]['target'], binding.FORM)
        self.assertEqual(effective['steps'][6]['match_text'], self.parameters['title'])
        self.assertEqual(effective['screenshot_checkpoints'], dict(before=2, after=7))
        markers = [c for step in contract['steps'] for c in step['checks'] if c['kind'] == 'text_count']
        self.assertEqual([c['count'] for c in markers], [0, 1, 1, 1])
        self.assertTrue(all(c['expected'] == self.parameters['title'] for c in markers))
        reopen = contract['steps'][6]['checks']
        self.assertTrue(any(c['kind'] == 'value' and c['expected'] == self.parameters['title'] for c in reopen))
        self.assertTrue(any(c['kind'] == 'value' and c['expected'] == self.parameters['description'] for c in reopen))
        self.assertEqual([r['source_order'] for r in prepared['source_mapping']], [1, 2, 7, 14, 16])
        self.assertIn('M03 생성 실패는 유지', prepared['notice'])
        compile(compile_code(effective, contract), '<synthetic-bu03-remediation>', 'exec')

    def test_raw_or_observed_byte_changes_are_rejected_before_store_registration(self):
        for path in (self.raw_path, self.observed_path):
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            try:
                with self.subTest(source=path.name), patch.object(self.manager, 'register',
                        side_effect=AssertionError('Changed proof cannot register')):
                    with self.assertRaises(EvaluationError) as caught:
                        self.manager.prepare_m03(self.payload())
                    self.assertEqual(caught.exception.status, 'NOT_READY')
            finally:
                path.write_bytes(original)
        self.assertEqual(list(self.manager.script_directory.glob('*/script.json')), [])

    def test_matching_test_hashes_do_not_hide_wrong_row_count_control_or_sixteen_step_binding(self):
        for variant in ('row_count', 'title_selector', 'description_selector', 'submit_tag'):
            rows = deepcopy(self.rows)
            if variant == 'row_count': rows.pop()
            elif variant == 'title_selector': rows[34]['target_selector'] = '#synthetic-wrong'
            elif variant == 'description_selector': rows[41]['target_selector'] = '#synthetic-wrong'
            else: rows[44]['element_tag'] = 'div'
            content = self.csv_bytes(rows)
            self.raw_path.write_bytes(content)
            with self.subTest(variant=variant), patch.object(binding, 'RAW_SHA256', sha(content)):
                with self.assertRaises(ValueError): binding.provenance(self.root, self.source)
        self.raw_path.write_bytes(self.csv_bytes(self.rows))
        for variant in ('workflow', 'duplicate_workflow', 'step_count'):
            snapshot = deepcopy(self.snapshot)
            if variant == 'workflow': snapshot['processes'][0]['canonical_instance_id'] = 'SYNTHETIC-OTHER'
            elif variant == 'duplicate_workflow': snapshot['processes'].append(deepcopy(snapshot['processes'][0]))
            else: snapshot['processes'][0]['business_steps'].pop()
            content = encoded(snapshot)
            self.observed_path.write_bytes(content)
            with self.subTest(variant=variant), patch.object(binding, 'OBSERVED_SHA256', sha(content)):
                with self.assertRaises(ValueError): binding.provenance(self.root, self.source)

    def test_changed_failed_source_success_relabel_or_other_business_never_uses_the_exception(self):
        changes = [lambda s: s.update(status='SUCCESS'), lambda s: s.update(business_unit_id='BU13'),
                   lambda s: s.update(workflow_id='SYNTHETIC-OTHER'), lambda s: s['issues'].pop(),
                   lambda s: s['steps'][0].update(order=2), lambda s: s['steps'][0].update(target='Synthetic changed')]
        original = deepcopy(self.source)
        for change in changes:
            self.source = deepcopy(original)
            change(self.source)
            self.write_source()
            with self.subTest(status=self.source['status']), patch.object(self.manager, 'register',
                    side_effect=AssertionError('An unrelated source cannot register')):
                self.assertFalse(binding.accepts(self.source))
                with self.assertRaises(EvaluationError): self.manager.prepare_m03(self.payload())
        for value in (None, [], {}, 'SYNTHETIC'):
            self.assertFalse(binding.accepts(value))

    def test_missing_extra_nonstring_secret_masked_or_control_inputs_are_not_execution_values(self):
        cases = [{}, dict(self.parameters, extra='Synthetic'), dict(self.parameters, description=True),
                 dict(self.parameters, title='ordinary title'), dict(self.parameters, title='KTL-' + 'S' * 121),
                 dict(self.parameters, description=''), dict(self.parameters, description='[MASKED]'),
                 dict(self.parameters, description='[REDACTED]'), dict(self.parameters, description='[HIDDEN]'),
                 dict(self.parameters, description='****'), dict(self.parameters, description='password=SYNTHETIC_SECRET'),
                 dict(self.parameters, description='Bearer SYNTHETIC_SECRET'),
                 dict(self.parameters, description='Synthetic\nnewline'), dict(self.parameters, description='Synthetic\ue007')]
        for values in cases:
            with self.subTest(keys=list(values)), self.assertRaises(ValueError) as caught:
                binding.prepare(self.root, self.source, values)
            self.assertNotIn('SYNTHETIC_SECRET', str(caught.exception))

    def test_date_requires_a_real_date_in_the_current_kst_month(self):
        for value in ('2026-10-31', '2026-12-01', '2026-11-31', '2026-2-01', '2026-11-16T00:00:00', 'invalid'):
            with self.subTest(date=value), self.assertRaises(ValueError):
                binding.prepare(self.root, self.source, dict(self.parameters, date=value))
        for value in ('2026-11-01', '2026-11-30'):
            result = binding.prepare(self.root, self.source, dict(self.parameters, date=value))
            self.assertEqual(result['parameters']['date'], value)

    def test_truth_or_credentials_in_original_are_rejected_even_when_test_fingerprint_is_patched(self):
        for key, value in [('ground_truth', {'answer': 'SYNTHETIC'}), ('password', 'SYNTHETIC_SECRET')]:
            source = deepcopy(self.source)
            source['steps'][0]['extra'] = {key: value}
            with self.subTest(key=key), patch.object(binding, 'SOURCE_PIN', fingerprint(source)):
                with self.assertRaises(ValueError) as caught: binding.prepare(self.root, source, self.parameters)
                self.assertNotIn('SYNTHETIC_SECRET', str(caught.exception))

    def test_an_explicit_saved_revision_is_not_hidden_by_the_reviewed_remediation(self):
        for record in ({'revision_id': 'SYNTHETIC-EXPLICIT'}, EvaluationError('Synthetic invalid revision', 'ERROR')):
            with self.subTest(record_type=type(record).__name__), patch.object(execution_contexts, '_read',
                    **({'side_effect': record} if isinstance(record, Exception) else {'return_value': record})), \
                    patch.object(binding, 'prepare', side_effect=AssertionError('No fallback over explicit revision')):
                with self.assertRaises(EvaluationError): self.manager.prepare_m03(self.payload())
        self.assertEqual(list(self.manager.script_directory.glob('*/script.json')), [])

    def test_store_pins_separate_original_and_execution_and_archives_full_remediation_proof(self):
        before = self.protected()
        with patch.object(self.manager, 'create', side_effect=AssertionError('Preparation does not execute')):
            response = self.manager.prepare_m03(self.payload())
        metadata = response['script']
        self.assertFalse(response['generated_by_llm'])
        self.assertFalse(metadata['generated_by_llm'])
        self.assertTrue(metadata['execution_ready'])
        self.assertTrue(metadata['business_step_required'])
        self.assertEqual(metadata['source_kind'], 'M03_COMPILED_SCRIPT')
        folder = self.manager.script_directory / metadata['script_id']
        source = json.loads((folder / 'source_scenario.json').read_bytes())
        effective = json.loads((folder / 'execution_scenario.json').read_bytes())
        contract = json.loads((folder / 'execution_contract.json').read_bytes())
        self.assertEqual(len(contract['steps']), 8)
        proof = json.loads((folder / 'm03_compilation.json').read_bytes())
        self.assertEqual(source, self.source)
        self.assertEqual(source['status'], 'FAILED')
        self.assertEqual(len(source['issues']), 11)
        self.assertEqual(effective['source_generation_status'], 'FAILED')
        self.assertEqual(effective['execution_source_kind'], 'REVIEWED_REMEDIATION')
        self.assertEqual(proof['remediation_provenance'], binding.provenance(self.root, self.source))
        self.assertEqual(proof['parameters'], self.parameters)
        self.assertEqual(proof['source_scenario_sha256'], sha(encoded(self.source)))
        self.assertEqual(proof['code_sha256'], sha((folder / 'script.py').read_bytes()))
        self.assertEqual((folder / 'script.py').read_bytes(), compile_code(effective, contract).encode('utf-8'))
        self.assertEqual(self.protected(), before)
        self.assertEqual(self.manager.list_runs()['executions'], [])
        self.assertFalse(list((self.root / 'results/development').glob('latest-M04.json')))

    def test_archived_remediation_proof_changes_are_detected_by_the_store(self):
        metadata = self.manager.prepare_m03(self.payload())['script']
        proof = self.manager.script_directory / metadata['script_id'] / 'm03_compilation.json'
        proof.write_bytes(proof.read_bytes() + b'\n')
        with self.assertRaises(EvaluationError): self.manager._script(metadata['script_id'])


if __name__ == '__main__':
    unittest.main()
