"""Synthetic saved-result exports only; never compile, generate, execute, or browse."""
from copy import deepcopy
import csv
import http.client
import io
import json
import threading
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.ktl_evidence import COLUMNS
from backend.m07.ktl_export import existing_ktl_csv
from backend.server import LocalHTTPServer, Service, make_handler
if __package__:
    from .test_m07_existing import ExistingFixture, digest, encoded
else:
    from test_m07_existing import ExistingFixture, digest, encoded


class M07KtlEvidenceTests(ExistingFixture):
    def save_result(self, identity='a', passed=8):
        checker = self.checker()
        context = checker.context()
        result = dict(run_id='M07-CHECK-' + identity * 32, status='COMPLETED', sample_count=10,
                      source_generation_id=self.manifest['source_generation_id'], source_manifest_sha256=self.manifest_sha,
                      score=passed * 10, syntax_pass_count=passed, syntax_fail_count=10 - passed,
                      target=80, threshold_met=passed >= 8, official_pass=None, new_generation=False,
                      gpt_request_count=0, browser_started_count=0, checked_at='2026-11-17T00:00:00.123+00:00', cases=[])
        for index, case in enumerate(context['cases']):
            status = 'PASS' if index < passed else 'FAIL'
            result['cases'].append(dict(case_id=case['case_id'], scenario_id=case['scenario_id'], workflow_id=case['workflow_id'],
                                        code_sha256=case['code_sha256'], syntax_status=status,
                                        expected_syntax_status=case['expected_syntax_status'],
                                        matches_expected=status == case['expected_syntax_status'],
                                        error=None if status == 'PASS' else 'PRIVATE_RAW_SYNTAX_ERROR_INPUT_VALUE'))
        result['matches_expected_count'] = sum(row['matches_expected'] for row in result['cases'])
        path = self.latest.parent / (result['run_id'] + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded(result))
        self.latest.write_bytes(encoded(result))
        return checker, result, path

    def parse(self, raw):
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(raw.count(b'\xef\xbb\xbf'), 1)
        text = raw.decode('utf-8-sig')
        self.assertNotIn('\n', text.replace('\r\n', ''))
        reader = csv.DictReader(io.StringIO(text, newline=''))
        self.assertEqual(tuple(reader.fieldnames), COLUMNS)
        rows = list(reader)
        self.assertTrue(all(len(row) == 12 for row in rows))
        return text, rows

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def test_saved_ten_case_result_exports_korean_summary_comparisons_and_hashes_without_checking(self):
        checker, result, _path = self.save_result()
        before = self.snapshot()
        with patch.object(checker, 'validate', side_effect=AssertionError('Export must not check code')), \
                patch('builtins.compile', side_effect=AssertionError('Export must not compile code')):
            raw = checker.ktl_evidence(result['run_id'])
        self.assertEqual(self.snapshot(), before)
        text, rows = self.parse(raw)
        summary = next(row for row in rows if row['항목'] == '문법통과율')
        self.assertEqual((summary['분자'], summary['분모'], summary['측정값'], summary['단위'], summary['판정']),
                         ('8', '10', '80.00', '%', '통과'))
        self.assertEqual(next(row['결과'] for row in rows if row['항목'] == '검사시각(KST)'), '2026-11-17 09:00:00')
        self.assertEqual([row['결과'] for row in rows if row['항목'] == '공식'], ['미판정'])
        self.assertEqual(next(row['결과'] for row in rows if row['항목'] == '평가'), '개발')
        individual = [row for row in rows if row['구분'] == '문법']
        self.assertEqual(len(individual), 10)
        self.assertEqual([row['번호'] for row in individual], [str(index) for index in range(1, 11)])
        self.assertEqual([row['판정'] for row in individual], ['통과'] * 8 + ['미달'] * 2)
        self.assertEqual([row['기대'] for row in individual], ['정상'] * 10)
        self.assertEqual([row['결과'] for row in individual], ['정상'] * 8 + ['오류'] * 2)
        self.assertIn('기존판정=정상 · 비교=불일치', individual[8]['근거'])
        comparison = next(row for row in rows if row['항목'] == '판정일치')
        self.assertEqual((comparison['구분'], comparison['분자'], comparison['분모'], comparison['판정']),
                         ('검산', '8', '10', '불일치'))
        self.assertIn(result['source_generation_id'], text)
        self.assertIn(self.manifest_sha, text)
        self.assertIn(result['run_id'] + '.json', text)
        for row in result['cases']:
            self.assertIn(row['code_sha256'], text)
        self.assertNotIn('PRIVATE_RAW_SYNTAX_ERROR_INPUT_VALUE', text)
        self.assertNotIn('deliberately_missing_existing_code_dependency', text)
        self.assertNotIn('This program must never execute', text)
        self.assertNotIn('source_scenario.json', text)
        self.assertEqual(next(row['측정값'] for row in rows if row['항목'] == 'GPT호출'), '0')
        self.assertEqual(next(row['측정값'] for row in rows if row['항목'] == '코드실행'), '0')
        self.assertEqual(next(row['결과'] for row in rows if row['항목'] == '범위'), '기존코드 문법검사')
        for phrase in ('이번', '승격', '이 CSV 내보내기', '독립 검사'):
            self.assertNotIn(phrase, text)

    def test_old_result_link_stays_bound_to_its_run_when_latest_changes(self):
        checker, original, _ = self.save_result('a', 8)
        before = checker.ktl_evidence(original['run_id'])
        _checker, newer, _ = self.save_result('b', 7)
        self.assertEqual(checker.ktl_evidence(original['run_id']), before)
        self.assertNotEqual(checker.ktl_evidence(newer['run_id']), before)
        _text, rows = self.parse(checker.ktl_evidence(newer['run_id']))
        summary = next(row for row in rows if row['항목'] == '문법통과율')
        self.assertEqual((summary['측정값'], summary['판정']), ('70.00', '미달'))

    def test_missing_saved_result_is_not_ready_and_never_creates_a_check(self):
        checker = self.checker()
        before = self.snapshot()
        with self.assertRaises(EvaluationError) as error:
            checker.ktl_evidence('M07-CHECK-' + 'a' * 32)
        self.assertEqual(error.exception.status, 'NOT_READY')
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.latest.exists())

    def test_invalid_run_ids_are_rejected_before_any_file_can_be_selected(self):
        checker, result, _ = self.save_result()
        before = self.snapshot()
        for identity in [None, '', result['run_id'] + '/../../latest', 'latest', 'M07-CHECK-' + 'A' * 32]:
            with self.subTest(identity=identity), self.assertRaises(EvaluationError):
                checker.ktl_evidence(identity)
        self.assertEqual(self.snapshot(), before)

    def test_matching_an_expected_failure_remains_a_syntax_failure(self):
        self.manifest['cases'][8]['expected_syntax_status'] = 'FAIL'
        self.write_manifest()
        checker, result, _ = self.save_result()
        _text, rows = self.parse(checker.ktl_evidence(result['run_id']))
        ninth = [row for row in rows if row['구분'] == '문법'][8]
        self.assertEqual(ninth['판정'], '미달')
        self.assertEqual(ninth['기대'], '정상')
        self.assertEqual(ninth['결과'], '오류')
        self.assertIn('기존판정=오류 · 비교=일치', ninth['근거'])
        self.assertEqual(next(row['측정값'] for row in rows if row['항목'] == '문법통과율'), '80.00')

    def test_private_problem_names_inputs_code_and_raw_errors_are_excluded(self):
        marker = 'PRIVATE_INPUT_OR_PERSONAL_CONTENT'
        row = self.manifest['cases'][0]
        path = self.bundle / row['scenario_path']
        value = json.loads(path.read_bytes())
        value.update(scenario_name=marker, customer_input=marker)
        value['steps'][0]['target'] = marker
        path.write_bytes(encoded(value))
        row['scenario_sha256'] = digest(path.read_bytes())
        self.write_manifest()
        checker, result, saved = self.save_result()
        result['cases'][0]['error'] = marker
        saved.write_bytes(encoded(result))
        raw = checker.ktl_evidence(result['run_id'])
        text, rows = self.parse(raw)
        self.assertNotIn(marker, text)
        self.assertEqual(next(row['업무'] for row in rows if row['구분'] == '문법'), 'CU01 일정 조회')

    def test_conflicting_saved_metrics_or_case_bindings_cannot_export_a_plausible_score(self):
        checker, result, saved = self.save_result()
        mutations = [lambda row: row.update(score=100), lambda row: row.update(sample_count=9),
                     lambda row: row.update(syntax_pass_count=9), lambda row: row.update(matches_expected_count=10),
                     lambda row: row.update(official_pass=True), lambda row: row.update(new_generation=True),
                     lambda row: row.update(gpt_request_count=1), lambda row: row.update(browser_started_count=1),
                     lambda row: row.update(status='RUNNING'), lambda row: row.update(checked_at='no timezone'),
                     lambda row: row.update(checked_at='2026-11-17T00:00:00'),
                     lambda row: row.update(source_manifest_sha256='0' * 64),
                     lambda row: row['cases'][0].update(code_sha256='0' * 64),
                     lambda row: row['cases'][0].update(expected_syntax_status='FAIL'),
                     lambda row: row['cases'][0].update(matches_expected=False),
                     lambda row: row['cases'].pop()]
        for index, mutate in enumerate(mutations):
            bad = deepcopy(result)
            mutate(bad)
            saved.write_bytes(encoded(bad))
            with self.subTest(index=index), self.assertRaises(EvaluationError):
                checker.ktl_evidence(result['run_id'])

    def test_source_hash_change_is_rejected_without_rewriting_a_saved_result(self):
        checker, result, saved = self.save_result()
        original = saved.read_bytes()
        source = self.bundle / self.manifest['cases'][0]['code_path']
        source.write_bytes(source.read_bytes() + b'# synthetic source alteration\n')
        with self.assertRaises(EvaluationError):
            checker.ktl_evidence(result['run_id'])
        self.assertEqual(saved.read_bytes(), original)


class M07KtlEvidenceApiTests(ExistingFixture):
    save_result = M07KtlEvidenceTests.save_result
    snapshot = M07KtlEvidenceTests.snapshot
    parse = M07KtlEvidenceTests.parse

    def setUp(self):
        super().setUp()
        self.saved_checker, self.saved, self.saved_path = self.save_result()
        self.service = Service(self.root, session_scoped=True)
        self.service._m07_existing = self.saved_checker
        self.legacy = self.enterContext(patch.object(self.service, 'm07',
            side_effect=AssertionError('Export must not initialize the generation/execution manager')))
        self.validation = self.enterContext(patch.object(self.saved_checker, 'validate',
            side_effect=AssertionError('Export must not check the preserved source again')))
        self.server = LocalHTTPServer(('127.0.0.1', 0), make_handler(self.service))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.legacy.assert_not_called()
        self.validation.assert_not_called()

    def request_csv(self, run_id, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        try:
            connection.request('GET', '/api/development/m07/existing-codes/checks/' + run_id + '/ktl-evidence.csv',
                               headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_real_handler_exports_utf8_csv_attachment_without_check_compile_or_file_changes(self):
        before = self.snapshot()
        with patch('builtins.compile', side_effect=AssertionError('CSV GET must not compile Python')) as compilation:
            status, headers, raw = self.request_csv(self.saved['run_id'])
        compilation.assert_not_called()
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/csv; charset=utf-8')
        self.assertEqual(headers['Content-Disposition'], 'attachment; filename="M07-ktl-evidence.csv"')
        _text, rows = self.parse(raw)
        self.assertEqual(len([row for row in rows if row['구분'] == '문법']), 10)
        self.assertEqual(next(row['측정값'] for row in rows if row['항목'] == '문법통과율'), '80.00')
        self.assertEqual(self.snapshot(), before)

    def test_real_handler_keeps_run_binding_after_latest_changes_and_rejects_corrupt_saved_score(self):
        status, _headers, original = self.request_csv(self.saved['run_id'])
        self.assertEqual(status, 200)
        _checker, newer, _path = self.save_result('b', 7)
        before = self.snapshot()
        self.assertEqual(self.request_csv(self.saved['run_id'])[2], original)
        self.assertNotEqual(self.request_csv(newer['run_id'])[2], original)
        self.assertEqual(self.snapshot(), before)
        altered = deepcopy(self.saved)
        altered['score'] = 100
        self.saved_path.write_bytes(encoded(altered))
        status, _headers, error = self.request_csv(self.saved['run_id'])
        self.assertEqual(status, 422)
        self.assertEqual(json.loads(error)['status'], 'ERROR')

    def test_real_handler_rejects_foreign_origin_and_missing_result_without_writes(self):
        before = self.snapshot()
        status, _headers, _raw = self.request_csv(self.saved['run_id'], {'Origin': 'https://foreign.example.invalid'})
        self.assertEqual(status, 403)
        status, _headers, error = self.request_csv('M07-CHECK-' + 'e' * 32)
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(error)['status'], 'NOT_READY')
        self.assertEqual(self.snapshot(), before)
