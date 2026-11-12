"""공식 M03: 결과 누락은 실패, 정답 부족은 평가 대기. 외부 호출 없는 합성 시험."""
import copy
import unittest

from backend.evaluators import EvaluationError
from backend.external_results import calculate
from backend.m03_integration import evaluate_scenarios
from backend.m03_reference import validate_reference


def scenarios():
    return [dict(business_unit_id=f'SYNTHETIC-BU-{i:02}', workflow_id=f'SYNTHETIC-WF-{i:02}',
                 scenario_id=f'SYNTHETIC-SCN-{i:02}', status='SUCCESS',
                 steps=[dict(order=1, action='open', target=f'SYNTHETIC screen {i}'),
                        dict(order=2, action='click', target='SYNTHETIC save')])
            for i in range(1, 11)]


def reference(rows):
    return dict(schema_version='m03-order-reference-v1', reference_id='SYNTHETIC-MISSING-RESULTS',
                evaluation_only=True, matching_policy='EXACT_ACTION_TARGET_SEQUENCE',
                fixed_at='2026-11-01T00:00:00+00:00',
                business_units=[{key: copy.deepcopy(row[key])
                                 for key in ('business_unit_id', 'workflow_id', 'steps')}
                                for row in rows])


def payload(rows, mode='OFFICIAL'):
    return dict(run_mode=mode, scenarios=copy.deepcopy(rows))


class M03MissingResultTests(unittest.TestCase):
    def setUp(self):
        self.rows = scenarios()
        self.units = [row['business_unit_id'] for row in self.rows]
        self.reference = reference(self.rows)

    def evaluate(self, rows, truth=None):
        return evaluate_scenarios(payload(rows), self.reference if truth is None else truth,
                                  expected_business_units=self.units)

    def assert_error(self, call):
        with self.assertRaises(EvaluationError) as raised:
            call()
        self.assertEqual(raised.exception.status, 'ERROR')

    def test_nine_valid_results_with_ten_references_are_ninety(self):
        score, total, details, evidence = self.evaluate(self.rows[:-1])
        self.assertEqual((score, total), (90, 10))
        self.assertEqual(details['raw_counts'], dict(total_business_units=10,
                         successful_scenario_count=9, failed_scenario_count=1, missing_result_count=1))
        self.assertEqual(details['evaluation_status'], 'COMPLETED')
        self.assertEqual(details['missing_result_business_units'], [self.units[-1]])
        self.assertEqual(details['missing_reference_business_units'], [])
        self.assertEqual(len(evidence), 10)
        missing = evidence[-1]
        self.assertTrue(missing['missing_result'])
        self.assertEqual(missing['reason'], 'MISSING_RESULT')
        self.assertEqual(missing['business_unit_id'], self.units[-1])
        self.assertIsNone(missing['scenario_id'])
        self.assertFalse(missing['success'])
        self.assertTrue(missing['reference_available'])
        self.assertTrue(all(not row['missing_result'] for row in evidence[:-1]))

    def test_zero_results_with_ten_references_are_zero_of_ten(self):
        score, total, details, evidence = self.evaluate([])
        self.assertEqual((score, total), (0, 10))
        self.assertEqual(details['raw_counts']['failed_scenario_count'], 10)
        self.assertEqual(details['raw_counts']['missing_result_count'], 10)
        self.assertEqual([row['business_unit_id'] for row in evidence], self.units)
        self.assertTrue(all(row['missing_result'] and row['success'] is False for row in evidence))

    def test_partial_reference_keeps_score_unknown_for_nine_or_ten_results(self):
        partial = reference(self.rows[:-1])
        for rows in (self.rows[:-1], self.rows):
            with self.subTest(result_count=len(rows)):
                score, total, details, evidence = self.evaluate(rows, partial)
                self.assertIsNone(score)
                self.assertEqual(total, 10)
                self.assertEqual(details['evaluation_status'], 'NOT_READY')
                self.assertEqual(details['missing_reference_business_units'], [self.units[-1]])
                self.assertIsNone(details['raw_counts']['successful_scenario_count'])
                self.assertIsNone(details['raw_counts']['failed_scenario_count'])
                self.assertEqual(details['raw_counts']['missing_result_count'], 10-len(rows))
                self.assertEqual(len(evidence), 10)
                self.assertEqual(evidence[-1]['success'], False if len(rows) == 9 else None)

    def test_missing_reference_and_missing_result_can_be_different_units(self):
        score, _, details, evidence = self.evaluate(self.rows[:-1], reference(self.rows[1:]))
        self.assertIsNone(score)
        self.assertEqual(details['missing_reference_business_units'], [self.units[0]])
        self.assertEqual(details['missing_result_business_units'], [self.units[-1]])
        self.assertIsNone(evidence[0]['success'])
        self.assertFalse(evidence[-1]['success'])
        self.assertTrue(evidence[-1]['reference_available'])

    def test_no_reference_never_turns_missing_results_into_zero_measurement(self):
        for rows in ([], self.rows[:-1], self.rows):
            with self.subTest(result_count=len(rows)):
                score, total, details, evidence = evaluate_scenarios(
                    payload(rows), expected_business_units=self.units)
                self.assertIsNone(score)
                self.assertEqual(total, 10)
                self.assertEqual(details['evaluation_status'], 'NOT_READY')
                self.assertEqual(details['missing_reference_business_units'], self.units)
                self.assertEqual(len(evidence), 10)

    def test_wrong_order_and_missing_result_both_remain_in_denominator(self):
        rows = copy.deepcopy(self.rows[:-1])
        rows[0]['steps'].reverse()
        for index, step in enumerate(rows[0]['steps'], 1):
            step['order'] = index
        score, total, details, evidence = self.evaluate(rows)
        self.assertEqual((score, total), (80, 10))
        self.assertEqual(details['raw_counts']['failed_scenario_count'], 2)
        self.assertTrue(evidence[0]['structure_valid'])
        self.assertFalse(evidence[0]['semantic_order_valid'])

    def test_failed_response_is_distinct_from_absent_response(self):
        row = dict(self.rows[0], status='FAILED', steps=[])
        score, total, details, evidence = self.evaluate([row])
        self.assertEqual((score, total), (0, 10))
        self.assertEqual(details['raw_counts']['missing_result_count'], 9)
        self.assertFalse(evidence[0]['missing_result'])
        self.assertFalse(evidence[0]['success'])
        self.assertEqual(sum(row['missing_result'] for row in evidence), 9)

    def test_duplicate_business_or_scenario_ids_are_errors(self):
        for field in ('business_unit_id', 'scenario_id'):
            rows = copy.deepcopy(self.rows)
            rows[-1][field] = rows[0][field]
            with self.subTest(field=field):
                self.assert_error(lambda: self.evaluate(rows))

    def test_unknown_business_unit_is_not_accepted_as_replacement(self):
        rows = copy.deepcopy(self.rows)
        rows[-1]['business_unit_id'] = 'SYNTHETIC-UNREGISTERED'
        self.assert_error(lambda: self.evaluate(rows))

    def test_eleven_results_are_errors_even_with_unique_identifiers(self):
        extra = dict(self.rows[0], business_unit_id='SYNTHETIC-EXTRA', scenario_id='SYNTHETIC-EXTRA-SCN')
        self.assert_error(lambda: self.evaluate(self.rows + [extra]))

    def test_expected_official_universe_requires_ten_unique_nonempty_ids(self):
        invalid = [self.units[:-1], self.units + ['EXTRA'], [self.units[0]]*10,
                   self.units[:-1]+[''], self.units[:-1]+[{}], tuple(self.units), 'ten units']
        for units in invalid:
            with self.subTest(units=units):
                self.assert_error(lambda: evaluate_scenarios(payload(self.rows), self.reference,
                                                             expected_business_units=units))

    def test_reference_outside_official_universe_is_configuration_error(self):
        truth = copy.deepcopy(self.reference)
        truth['business_units'][-1]['business_unit_id'] = 'SYNTHETIC-UNREGISTERED'
        self.assert_error(lambda: self.evaluate(self.rows, truth))

    def test_duplicate_reference_units_remain_configuration_error(self):
        truth = copy.deepcopy(self.reference)
        truth['business_units'][-1] = copy.deepcopy(truth['business_units'][0])
        self.assert_error(lambda: self.evaluate(self.rows, truth))

    def test_untrusted_payload_universe_cannot_enable_partial_official_evaluation(self):
        body = payload(self.rows[:-1])
        body['expected_business_units'] = self.units
        self.assert_error(lambda: evaluate_scenarios(body, self.reference))

    def test_legacy_official_without_expected_universe_requires_ten_results(self):
        self.assert_error(lambda: evaluate_scenarios(payload(self.rows[:-1]), self.reference))
        self.assert_error(lambda: evaluate_scenarios(payload([]), self.reference))
        score, total, details, _ = evaluate_scenarios(payload(self.rows), self.reference)
        self.assertEqual((score, total), (100, 10))
        self.assertEqual(details['raw_counts']['missing_result_count'], 0)

    def test_nonofficial_denominator_and_reference_format_stay_sample_based(self):
        for mode, rows in [('DEVELOPMENT', self.rows[:-1]), ('REFERENCE', self.rows[:1])]:
            with self.subTest(mode=mode):
                truth = reference(rows)
                self.assertIs(validate_reference(truth), truth)
                score, total, details, evidence = evaluate_scenarios(payload(rows, mode), truth)
                self.assertEqual((score, total), (100, len(rows)))
                self.assertEqual(details['raw_counts']['missing_result_count'], 0)
                self.assertEqual(len(evidence), len(rows))
        self.assert_error(lambda: evaluate_scenarios(payload([], 'DEVELOPMENT'), self.reference))

    def test_payload_reference_and_expected_universe_are_not_mutated(self):
        body = payload(self.rows[:-1])
        before = copy.deepcopy((body, self.reference, self.units))
        _, _, _, evidence = evaluate_scenarios(body, self.reference, expected_business_units=self.units)
        self.assertEqual((body, self.reference, self.units), before)
        self.assertEqual(len(body['scenarios']), 9)
        self.assertNotIn('MISSING_RESULT', repr(body))
        self.assertEqual(len(evidence), 10)

    def test_claimed_counts_cannot_exclude_missing_results_or_override_score(self):
        body = payload(self.rows[:-1])
        for counts in (dict(total_business_units=9), dict(successful_scenario_count=10),
                       dict(failed_scenario_count=0), dict(missing_result_count=0)):
            body['counts'] = counts
            with self.subTest(counts=counts):
                self.assert_error(lambda: evaluate_scenarios(body, self.reference,
                                                             expected_business_units=self.units))

    def test_calculate_forwards_trusted_universe_and_preserves_submitted_payload(self):
        body = dict(payload(self.rows[:-1]), external_run_id='SYNTHETIC-EVAL-ONLY',
                    dataset_id='SYNTHETIC-DATASET', source_module='synthetic-tests', source_version='v1',
                    submitted_at='2026-11-09T00:00:00+00:00', dataset_manifest_sha256='0'*64, details={})
        before = copy.deepcopy(body)
        score, total, details, evidence = calculate('M03', body, m03_reference=self.reference,
                                                   m03_expected_business_units=self.units)
        self.assertEqual((score, total), (90, 10))
        self.assertEqual(details['raw_counts']['missing_result_count'], 1)
        self.assertEqual(len(evidence), 10)
        self.assertEqual(body, before)


if __name__ == '__main__':
    unittest.main()
