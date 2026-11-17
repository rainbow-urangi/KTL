"""Synthetic readable M04 export checks; no browser, provider, or business run."""
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.ktl_evidence import COLUMNS
from backend.m04.ktl_export import export_ktl_evidence
from backend.m04.store import M04Manager


EXECUTION = 'M04-RUN-' + 'a' * 32
PRIVATE = 'PRIVATE_SYNTHETIC_VALUE_782'


def case(index, status='PASS'):
    return dict(case_id='CASE-' + str(index).zfill(3), scenario_id=PRIVATE,
                business_unit_id='BU03', scenario_name=PRIVATE, script_name=PRIVATE,
                status=status, error=PRIVATE, error_message=PRIVATE, source_synthetic=True,
                code_source='SCENARIO_COMPILER', source_kind='M03_COMPILED_SCRIPT',
                compiler_version='m03-selenium-compiler-v3-empty-input', code_sha256='b' * 64,
                step_evidence_mode='BUSINESS_STEPS', required_step_count=1, expected_check_count=2,
                action_logs=[dict(target=PRIVATE, error=PRIVATE, action='click')] * 1000,
                steps=[dict(sequence=1, action='input', target=PRIVATE, expected_result=PRIVATE,
                            status=status, error=PRIVATE, check_results=[
                                dict(check_index=1, kind='value', expected=PRIVATE, observed=PRIVATE,
                                     status=status, comparison_mode=PRIVATE),
                                dict(check_index=2, kind='fill_empty', expected=PRIVATE, observed={'private': PRIVATE},
                                     status=status, observation_status='REDACTED'),
                            ])])


def snapshot(statuses=None):
    statuses = statuses or ['PASS'] * 10
    passed = statuses.count('PASS')
    failed = sum(status in {'FAIL', 'ERROR', 'TIMEOUT', 'SKIPPED'} for status in statuses)
    return dict(execution_id=EXECUTION, run_mode='DEVELOPMENT', status='COMPLETED',
                started_at='2026-11-16T01:00:00.123Z', completed_at='2026-11-16T01:01:00.456Z',
                dataset_id='m04-development-' + 'c' * 12, logs=[PRIVATE], error=PRIVATE,
                cases=[case(index, status) for index, status in enumerate(statuses, 1)],
                counts=dict(total_execution_count=len(statuses), successful_execution_count=passed,
                            failed_execution_count=failed),
                result=dict(status='COMPLETED', score=passed / len(statuses) * 100,
                            evaluator_version='external-integration-v3-ktl-20261026',
                            target=90, threshold_met=passed / len(statuses) >= .9, official_pass=None))


def parse(raw):
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    rows = list(reader)
    return reader.fieldnames, rows


def summary(rows):
    return next(row for row in rows if row['구분'] == '요약')


class M04ReadableEvidenceTests(unittest.TestCase):
    def test_bom_twelve_columns_failed_attempt_denominator_and_scenario_recalculation(self):
        job = snapshot(['PASS'] * 7 + ['FAIL', 'TIMEOUT', 'SKIPPED'])
        raw = export_ktl_evidence(job)
        fields, rows = parse(raw)
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf'))
        self.assertEqual(raw.count(b'\xef\xbb\xbf'), 1)
        self.assertEqual(tuple(fields), COLUMNS)
        total = summary(rows)
        self.assertEqual((total['분자'], total['분모'], total['측정값'], total['판정']), ('7', '10', '70.00', '미달'))
        cases = [row for row in rows if row['구분'] == '시나리오']
        self.assertEqual(len(cases), 10)
        self.assertEqual(sum(int(row['분자']) for row in cases), 7)
        self.assertEqual(sum(int(row['분모']) for row in cases), 10)
        self.assertEqual(len([row for row in rows if row['구분'] == '단계']), 10)
        self.assertEqual(len([row for row in rows if row['구분'] == '조건']), 20)
        self.assertEqual({row['판정'] for row in cases}, {'성공', '실패'})
        self.assertTrue(any('시간초과' in row['근거'] for row in cases))
        self.assertTrue(any('미실행' in row['근거'] for row in cases))
        self.assertLess(len(rows), 100, 'ten thousand browser traces must not become export rows')

    def test_single_case_keeps_real_one_denominator_and_declares_scope(self):
        _, rows = parse(export_ktl_evidence(snapshot(['PASS'])))
        self.assertEqual(summary(rows)['분모'], '1')
        self.assertEqual(summary(rows)['측정값'], '100.00')
        scopes = [row['결과'] for row in rows if row['항목'] == '범위']
        self.assertEqual(scopes, ['단건 1/10건'])
        self.assertEqual(len([row for row in rows if row['구분'] == '시나리오']), 1)

    def test_running_or_unfinished_cases_do_not_gain_final_percentage(self):
        for status in ('RUNNING', 'INTERRUPTED', 'COMPLETED'):
            job = snapshot(['PASS'] * 9 + ['PENDING'])
            job['status'] = status
            job['result']['score'] = 90
            _, rows = parse(export_ktl_evidence(job))
            self.assertEqual(summary(rows)['측정값'], '')
            self.assertEqual(summary(rows)['판정'], '대기')
            self.assertEqual(summary(rows)['분모'], '10')
            last = [row for row in rows if row['구분'] == '시나리오'][-1]
            self.assertEqual((last['분자'], last['분모'], last['판정']), ('', '1', '대기'))

    def test_real_zero_is_preserved_but_inconsistent_or_missing_score_stays_pending(self):
        _, rows = parse(export_ktl_evidence(snapshot(['FAIL'] * 10)))
        self.assertEqual((summary(rows)['측정값'], summary(rows)['판정']), ('0.00', '미달'))
        for mutate in (lambda job: job['result'].update(score=None),
                       lambda job: job['result'].update(score=90),
                       lambda job: job['counts'].update(total_execution_count=9)):
            job = snapshot()
            mutate(job)
            _, rows = parse(export_ktl_evidence(job))
            self.assertEqual(summary(rows)['측정값'], '')
            self.assertEqual(summary(rows)['판정'], '대기')

    def test_private_values_raw_selectors_errors_and_nested_logs_are_excluded(self):
        raw = export_ktl_evidence(snapshot())
        self.assertNotIn(PRIVATE.encode(), raw)
        _, rows = parse(raw)
        self.assertTrue(all(len(value) < 500 for row in rows for value in row.values()))
        self.assertTrue(any('입력값 비공개' in row['근거'] for row in rows))
        self.assertTrue(all(not value.startswith(('{', '[')) for row in rows for value in row.values()))
        self.assertEqual([row['결과'] for row in rows if row['항목'] == '공식'], ['미판정'])
        self.assertTrue(any('official_pass=null' in row['근거'] for row in rows))

    def test_condition_states_preserve_hidden_zero_and_absent_observations(self):
        job = snapshot(['PASS'])
        conditions = [
            dict(kind='visible', expected=False, observed=dict(visible_count=0, target=PRIVATE),
                 status='PASS', observation_status='RECORDED'),
            dict(kind='visible', expected=True, observed=dict(visible_count=2),
                 status='PASS', observation_status='RECORDED'),
            dict(kind='text_count', expected=dict(text=PRIVATE, count=0), observed=0,
                 status='PASS', observation_status='RECORDED'),
            dict(kind='nonempty', expected=dict(left_nonempty=True), observed=dict(left_nonempty=True),
                 status='PASS', observation_status='RECORDED'),
            dict(kind='value', expected=PRIVATE, observed=None, status='PASS', observation_status='NOT_RECORDED'),
        ]
        job['cases'][0]['steps'][0]['check_results'] = conditions
        job['cases'][0]['expected_check_count'] = len(conditions)
        raw = export_ktl_evidence(job)
        self.assertNotIn(PRIVATE.encode(), raw)
        _, rows = parse(raw)
        checks = [row for row in rows if row['구분'] == '조건']
        self.assertEqual([(row['기대'], row['결과']) for row in checks],
                         [('숨김', '숨김'), ('표시', '표시'), ('0개', '0개'), ('존재', '존재'), ('일치', '미확인')])
        self.assertIn('표시 2개', checks[1]['근거'])
        self.assertEqual(checks[-1]['판정'], '성공', 'preserve the stored verdict without inventing an observation')
        self.assertEqual(summary(rows)['측정값'], '100.00')

    def test_relational_missing_target_is_unknown_without_equality_observation(self):
        job = snapshot(['PASS'])
        job['cases'][0]['steps'][0]['check_results'] = [
            dict(kind='text_equals_target', expected=dict(equal=True),
                 observed=dict(left_count=1, left_nonempty=True, right_count=0),
                 status='FAIL', observation_status='RECORDED'),
            dict(kind='text_equals_target', expected=dict(equal=True), observed=dict(equal=False),
                 status='FAIL', observation_status='RECORDED'),
            dict(kind='text_equals_target', expected=dict(equal=True), observed=dict(equal=True),
                 status='PASS', observation_status='RECORDED'),
        ]
        _, rows = parse(export_ktl_evidence(job))
        checks = [row for row in rows if row['구분'] == '조건']
        self.assertEqual([row['결과'] for row in checks], ['미확인', '불일치', '일치'])
        self.assertEqual([row['판정'] for row in checks], ['실패', '실패', '성공'])
        self.assertEqual(summary(rows)['측정값'], '100.00', 'preserve the saved aggregate without regrading')

    def test_null_scalar_observations_are_unknown_and_focus_shows_recorded_state(self):
        job = snapshot(['PASS'])
        job['cases'][0]['steps'][0]['check_results'] = [
            dict(kind=kind, expected=PRIVATE, observed=None, status='PASS', observation_status='RECORDED')
            for kind in ('value', 'text_equals', 'url_path')
        ] + [
            dict(kind='focus', expected=True, observed=False, status='FAIL', observation_status='RECORDED'),
            dict(kind='focus', expected=True, observed=True, status='PASS', observation_status='RECORDED'),
            dict(kind='focus', expected=False, observed=None, status='PASS', observation_status='RECORDED'),
        ]
        _, rows = parse(export_ktl_evidence(job))
        checks = [row for row in rows if row['구분'] == '조건']
        self.assertEqual([row['결과'] for row in checks], ['미확인'] * 3 + ['비활성', '활성', '미확인'])
        self.assertEqual([row['판정'] for row in checks[:3]], ['성공'] * 3)
        self.assertEqual(summary(rows)['측정값'], '100.00')

    def test_legacy_browser_trace_is_not_labeled_as_business_evidence(self):
        job = snapshot(['PASS'])
        job['cases'][0]['step_evidence_mode'] = 'LEGACY_TRACE'
        _, rows = parse(export_ktl_evidence(job))
        self.assertFalse(any(row['구분'] in {'단계', '조건'} for row in rows))
        self.assertEqual('상세 미보관', next(row['결과'] for row in rows if row['구분'] == '시나리오'))
        self.assertEqual(summary(rows)['측정값'], '100.00', 'do not regrade a stored legacy result')

    def test_policy_provenance_time_and_code_hash_are_readable_without_invented_hashes(self):
        _, rows = parse(export_ktl_evidence(snapshot(['PASS'])))
        info = {row['항목']: row for row in rows if row['구분'] == '정보'}
        self.assertEqual(info['완료시각(KST)']['결과'], '2026-11-16 10:01:00')
        self.assertEqual(info['데이터셋']['결과'], 'm04-development-' + 'c' * 12)
        self.assertIn('external-integration-v3-ktl-20261026', info['버전']['결과'])
        self.assertIn('m03-selenium-compiler-v3-empty-input', info['버전']['결과'])
        self.assertTrue(info['원본']['근거'].endswith('/' + EXECUTION + '/artifacts/steps.csv'))
        self.assertTrue(any('code_sha256=' + 'b' * 64 in row['근거'] for row in rows))
        self.assertFalse(any('report_sha256=' in row['근거'] for row in rows))

    def test_export_is_deterministic_and_does_not_mutate_execution_snapshot(self):
        job = snapshot(['PASS', 'FAIL'])
        original = deepcopy(job)
        with patch('subprocess.Popen', side_effect=AssertionError('Export must never start a process')):
            self.assertEqual(export_ktl_evidence(job), export_ktl_evidence(job))
        self.assertEqual(job, original)

    def test_artifact_path_exports_without_rewriting_saved_job_or_raw_steps(self):
        with tempfile.TemporaryDirectory(prefix='ktl-synthetic-readable-m04-') as temporary:
            root = Path(temporary)
            folder = root / 'data/development/m04_runner/executions' / EXECUTION
            folder.mkdir(parents=True)
            job = snapshot(['PASS'])
            path = folder / 'execution.json'
            original = json.dumps(job, ensure_ascii=False).encode()
            path.write_bytes(original)
            manager = M04Manager(root, lambda: {}, session=None)
            old_raw, old_mime = manager.artifact(EXECUTION, 'steps.csv')
            raw, mime = manager.artifact(EXECUTION, 'ktl-evidence.csv')
            self.assertEqual(mime, 'text/csv; charset=utf-8')
            self.assertEqual(raw, export_ktl_evidence(job))
            self.assertEqual(manager.artifact(EXECUTION, 'steps.csv'), (old_raw, old_mime))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), hashlib.sha256(original).hexdigest())
            self.assertEqual(set(p.name for p in folder.iterdir()), {'execution.json'})


if __name__ == '__main__':
    unittest.main()
