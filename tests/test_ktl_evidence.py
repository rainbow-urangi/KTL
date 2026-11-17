"""Readable exports use temporary synthetic records and do not execute a model."""
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from backend.evaluators import EvaluationError
from backend.ktl_evidence import COLUMNS, csv_bytes, local_time, number, verdict
from backend.m01.compare import M01ComparisonStore
from backend.m01.presence import M01PresenceStore
from backend.m01.scenarios import catalog
from backend.m01.upload import M01CsvStore


def records(raw):
    return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline='')))


class ReadableCSVTests(unittest.TestCase):
    def test_excel_encoding_rectangular_rows_and_formula_protection(self):
        raw = csv_bytes([{'구분': '시험 정보', '검증 항목': '\ufeff\t=2+2',
                          '실제 결과': '첫째\r\n둘째\t셋째'},
                         {'검증 항목': '\u200b@SUM(A1)', '실제 결과': '-1+1'}])
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\r\r\n', raw)
        self.assertEqual(raw.count(b'\r\n'), 3)
        parsed = records(raw)
        self.assertEqual(tuple(parsed[0]), COLUMNS)
        self.assertEqual(parsed[0]['항목'], "'=2+2")
        self.assertEqual(parsed[0]['결과'], '첫째 둘째 셋째')
        self.assertEqual(parsed[1]['항목'], "'@SUM(A1)")
        self.assertEqual(parsed[1]['결과'], "'-1+1")
        with self.assertRaises(ValueError):
            csv_bytes([{'실제 결과': {'raw': 'nested input'}}])

    def test_unknown_and_missing_values_never_become_zero_or_pass(self):
        self.assertEqual(number(None), '')
        self.assertEqual(number(float('nan')), '')
        self.assertEqual(number(94.54545), '94.55')
        self.assertEqual(verdict(None), '대기')
        self.assertEqual(verdict(True), '통과')
        self.assertEqual(verdict(False), '미달')
        self.assertEqual(local_time('2026-11-16T23:30:01+00:00'), '2026-11-17 08:30:01')
        self.assertEqual(local_time('2026-11-17T08:30:01'), '시간대 확인 필요')


class M01ReadableEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.config = json.loads((Path(__file__).resolve().parents[1] / 'backend/config.json').read_text(encoding='utf-8'))
        output = io.StringIO(newline='')
        fields = ['event_id', 'session_id', 'event_time', 'event_type', 'page_url',
                  'page_title', 'target_key', 'interaction_type', 'target_selector', 'input_value']
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerow(dict(event_id='synthetic-event', session_id='synthetic-session',
                             event_time='2026-11-17T00:00:00Z', event_type='PAGE_VIEW',
                             page_url='https://rainbowlab.ai.kr/mypage/schedule', page_title='Synthetic',
                             target_key='html', interaction_type='route_change', target_selector='html',
                             input_value='SENSITIVE_SYNTHETIC_VALUE'))
        writer.writerow(dict(event_id='synthetic-unclassified', session_id='synthetic-session',
                             event_time='2026-11-17T00:00:01Z', event_type='SYNTHETIC_UNKNOWN',
                             page_url='https://rainbowlab.ai.kr/mypage/schedule', page_title='Synthetic',
                             target_key='html', interaction_type='synthetic_unknown', target_selector='html'))
        import base64
        uploaded = M01CsvStore(self.root).upload(dict(filename='synthetic.csv',
            csv_base64=base64.b64encode(output.getvalue().encode()).decode()), self.config)
        fixed = catalog()
        batch = M01PresenceStore(self.root).compare_all(dict(dataset_id=uploaded['dataset']['dataset_id'],
            catalog_version=fixed['version'], catalog_sha256=fixed['sha256']), self.config)
        self.result = batch['result']
        self.store = M01ComparisonStore(self.root)
        self.folder = self.store.directory / self.result['comparison_id']

    def test_readable_totals_match_saved_result_without_changing_any_original(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        exported = self.store.ktl_evidence(self.result['comparison_id'])
        rows = records(exported)
        summary = {row['항목']: row for row in rows if row['구분'] == '요약'}
        counts = self.result['measurement']['counts']
        self.assertEqual(int(summary['C1 수집률']['분모']),
                         counts['defined_required_event_count'])
        self.assertEqual(int(summary['C1 수집률']['분자']), counts['collected_required_event_count'])
        self.assertEqual(summary['수집정확도']['측정값'], number(self.result['measurement']['collection_accuracy']))
        expected = [row for row in rows if row['구분'] == '이벤트']
        self.assertEqual(len(expected), counts['defined_required_event_count'])
        self.assertEqual(sum(row['판정'] == '통과' for row in expected), counts['collected_required_event_count'])
        self.assertTrue(all(row['기대'] == '수집' and row['결과'] in {'수집', '누락'} for row in expected))
        info = {row['항목']: row for row in rows if row['구분'] == '정보'}
        self.assertEqual(info['평가']['결과'], '개발')
        self.assertEqual(info['공식']['결과'], '미판정')
        self.assertEqual(info['검산']['결과'], '일치')
        self.assertIn('비교시각(KST)', info)
        types = {row['항목']: row for row in rows if row['구분'] == '유형'}
        self.assertEqual(types['미분류']['결과'], '1')
        self.assertEqual(sum(int(row['결과']) for row in types.values()), counts['total_collected_events'])
        self.assertNotIn('SENSITIVE_SYNTHETIC_VALUE', exported.decode('utf-8-sig'))
        self.assertNotIn('target_selector', exported.decode('utf-8-sig'))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir()})

    def test_tampered_original_cannot_be_published_as_a_readable_report(self):
        path = self.folder / 'evidence.csv'
        path.write_bytes(path.read_bytes() + b'corrupted')
        with self.assertRaises(EvaluationError):
            self.store.ktl_evidence(self.result['comparison_id'])


if __name__ == '__main__':
    unittest.main()
