"""Main structural compatibility is synthetic and separate from strict evaluation."""
from copy import deepcopy
import unittest

from backend.evaluators import EvaluationError
from backend.m03_integration import evaluate_scenarios
from backend.m03_main_compat import evaluate_development, validate_scenario_result


def scenarios():
    return [dict(business_unit_id='SYN-' + str(index), workflow_id='WF-' + str(index),
                 scenario_id='SYNTHETIC-' + str(index), status='SUCCESS',
                 steps=[dict(order=1, action='open', target='/synthetic'),
                        dict(order=2, action='click', target='#synthetic')]) for index in range(10)]


class MainCompatibilityTests(unittest.TestCase):
    def test_ratio_is_recalculated_and_does_not_read_any_historical_score(self):
        for failures in (0, 1, 2, 10):
            rows = scenarios()
            for row in rows[:failures]:
                row['status'] = 'FAILED'
            payload = dict(run_mode='DEVELOPMENT', scenarios=rows, details=dict(historical_score=12.345))
            original = deepcopy(payload)
            score, total, details, evidence = evaluate_development(payload)
            self.assertEqual(score, 100 * (10 - failures) / 10)
            self.assertEqual(total, 10)
            self.assertEqual(details['raw_counts']['failed_scenario_count'], failures)
            self.assertEqual(sum(row['success'] for row in evidence), 10 - failures)
            self.assertEqual(payload, original)

    def test_original_structure_checks_reject_missing_targets_reordered_ordinals_and_bool_order(self):
        for change in (lambda row: row['steps'][0].pop('target'),
                       lambda row: row['steps'][1].update(order=3),
                       lambda row: row['steps'][0].update(order=True),
                       lambda row: row.update(steps=[]),
                       lambda row: row.update(status='FAILED')):
            row = scenarios()[0]
            change(row)
            self.assertFalse(validate_scenario_result(row)['success'])

    def test_compatibility_cannot_be_called_for_official_or_reference_measurement(self):
        for mode in ('OFFICIAL', 'REFERENCE', None):
            with self.subTest(mode=mode), self.assertRaises(EvaluationError):
                evaluate_development(dict(run_mode=mode, scenarios=scenarios()))

    def test_strict_evaluator_is_unchanged_and_stays_not_ready_without_order_reference(self):
        payload = dict(run_mode='DEVELOPMENT', scenarios=scenarios())
        self.assertEqual(evaluate_development(payload)[0], 100)
        score, count, details, rows = evaluate_scenarios(payload)
        self.assertIsNone(score)
        self.assertEqual(count, 10)
        self.assertEqual(details['success_policy'], 'STRUCTURE_AND_REFERENCE_ORDER')
        self.assertEqual(details['evaluation_status'], 'NOT_READY')
        self.assertTrue(all(row['success'] is None for row in rows))

    def test_duplicate_business_ids_scenario_ids_and_wrong_reported_counts_remain_rejected(self):
        for mutate in (lambda rows: rows[1].update(business_unit_id=rows[0]['business_unit_id']),
                       lambda rows: rows[1].update(scenario_id=rows[0]['scenario_id'])):
            rows = scenarios()
            mutate(rows)
            with self.assertRaises(EvaluationError):
                evaluate_development(dict(run_mode='DEVELOPMENT', scenarios=rows))
        with self.assertRaises(EvaluationError):
            evaluate_development(dict(run_mode='DEVELOPMENT', scenarios=scenarios(),
                                      counts=dict(successful_scenario_count=9)))


if __name__ == '__main__':
    unittest.main()
