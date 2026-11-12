"""M01 원본→M04 고정·실행 계약 회귀. 실제 업무/GPT 실행은 하지 않는다."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m01 import M01CsvStore
from backend.m04.store import M04Manager
from backend.session import RuntimeSession


def source_csv():
    fields = ['event_id', 'session_id', 'event_time', 'event_type', 'interaction_type',
              'page_url', 'page_title', 'target_key', 'target_selector', 'element_tag',
              'input_control_type', 'input_data']
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fields)
    writer.writeheader()
    for index, (event, interaction, target, tag, control) in enumerate([
        ('page_view', 'page_view', 'body', 'body', ''),
        ('DOM_EVENT', 'click', '#title', 'input', 'text'),
        ('DOM_EVENT', 'change', '#title', 'input', 'text'),
        ('DOM_EVENT', 'click', '#next', 'button', ''),
    ], 1):
        writer.writerow(dict(event_id='SYNTHETIC-' + str(index), session_id='synthetic-session',
            event_time=f'2026-11-12T00:00:0{index}.000Z', event_type=event, interaction_type=interaction,
            page_url='http://127.0.0.1:9876/start', page_title='Synthetic replay',
            target_key='css:' + target, target_selector=target, element_tag=tag,
            input_control_type=control, input_data=''))
    return buffer.getvalue().encode('utf-8')


class M04M01ImportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ktl-m01-import-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.config = dict(targets={'M01': 65, 'M04': 90}, m04={}, m07={}, integration_datasets={})
        self.session = RuntimeSession()
        self.csv = M01CsvStore(self.root, session=self.session)
        self.manager = M04Manager(self.root, lambda: self.config, session=self.session)
        self.original = source_csv()
        self.upload = self.csv.upload(dict(filename='synthetic.csv',
            csv_base64=base64.b64encode(self.original).decode()), self.config)
        self.dataset = self.upload['dataset']['dataset_id']

    def prepare(self):
        return self.manager.import_m01(dict(dataset_id=self.dataset,
            parameters={'row_3_value': 'Synthetic replay title'}))

    def test_preview_is_read_only_and_only_collected_source_is_used(self):
        before = sorted(str(path.relative_to(self.root)) for path in self.root.rglob('*'))
        with patch('subprocess.Popen', side_effect=AssertionError('No runner during preview')):
            result = self.manager.m01_source(dict(dataset_id=self.dataset))
        self.assertEqual(result['source_sha256'], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(result['missing_inputs'][0]['name'], 'row_3_value')
        self.assertEqual(before, sorted(str(path.relative_to(self.root)) for path in self.root.rglob('*')))

    def test_import_has_strict_contract_original_bytes_and_no_fake_m03_or_llm(self):
        with patch('subprocess.Popen', side_effect=AssertionError('No runner during import')):
            registered = self.prepare()['script']
        self.assertEqual(registered['source_kind'], 'M01_OBSERVED_REPLAY')
        self.assertIs(registered['generated_by_llm'], False)
        self.assertIsNone(registered['source_m03_run_id'])
        self.assertTrue(registered['business_step_required'])
        metadata, code = self.manager._script(registered['script_id'])
        folder = self.manager.script_directory / metadata['script_id']
        self.assertEqual((folder / 'm01_source.csv').read_bytes(), self.original)
        self.assertIn(b'from ktl_runtime import business_step', code)
        self.assertIn(b'Synthetic replay title', code)
        prepared = self.manager._fixed_execution(metadata, folder)
        self.assertEqual(prepared['contract']['scenario_id'], metadata['scenario_id'])
        self.assertEqual(list((self.root / 'results/development').glob('DEV-M03-*')), [])
        self.assertFalse(self.manager.list_runs()['executions'])

    def test_missing_input_foreign_session_and_tampered_source_are_rejected(self):
        with self.assertRaises(EvaluationError):
            self.manager.import_m01(dict(dataset_id=self.dataset))
        foreign = M04Manager(self.root, lambda: self.config, session=RuntimeSession())
        with self.assertRaises(EvaluationError):
            foreign.m01_source(dict(dataset_id=self.dataset))
        (self.csv.directory / self.dataset / 'source.csv').write_bytes(self.original + b'\n')
        with self.assertRaises(EvaluationError):
            self.manager.m01_source(dict(dataset_id=self.dataset))

    def test_fixed_m01_evidence_tampering_cannot_execute(self):
        metadata = self.prepare()['script']
        folder = self.manager.script_directory / metadata['script_id']
        (folder / 'm01_parameters.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(EvaluationError):
            self.manager._script(metadata['script_id'])

    def test_display_options_are_explicit_bounded_and_not_allowed_to_run_on_import(self):
        metadata = self.prepare()['script']
        for fields in [dict(visible_browser='true'), dict(action_delay_ms=True),
                       dict(visible_browser=True, action_delay_ms=2001),
                       dict(visible_browser=True, keep_open_seconds=61), dict(action_delay_ms=100)]:
            with self.subTest(fields=fields), self.assertRaises(EvaluationError):
                self.manager.create(dict(script_ids=[metadata['script_id']], **fields))
        seen = []
        def no_execution(execution_id, lock):
            seen.append(execution_id)
            lock.close()
        class ImmediateThread:
            def __init__(self, *, target, args, **kwargs):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)
        with patch.object(self.manager, '_execute', side_effect=no_execution), patch(
                'backend.m04.store.threading.Thread', ImmediateThread):
            job = self.manager.create(dict(script_ids=[metadata['script_id']], visible_browser=True,
                action_delay_ms=700, keep_open_seconds=15))['execution']
        self.assertEqual(seen, [job['execution_id']])
        self.assertTrue(job['visible_browser'])
        self.assertEqual(job['cases'][0]['source_m01_csv_sha256'], metadata['source_m01_csv_sha256'])
        folder = self.manager.execution_directory / job['execution_id'] / 'CASE-001'
        self.assertEqual((folder / 'm01_source.csv').read_bytes(), self.original)
        self.assertIsNone(job['result'])
        archive = self.root / 'data/evaluation' / job['dataset_id'] / 'scripts.zip'
        with zipfile.ZipFile(archive) as saved:
            self.assertEqual(saved.read('CASE-001/m01_source.csv'), self.original)
        (folder / 'm01_source.csv').write_bytes(self.original + b'\n')
        with self.assertRaises(EvaluationError):
            self.manager._provenance(job)


if __name__ == '__main__':
    unittest.main()
