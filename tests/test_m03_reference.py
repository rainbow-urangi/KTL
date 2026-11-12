"""M03 평가 전용 정답 경계. 임시 합성 자료만 사용하며 모델·외부 서버를 호출하지 않는다."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.evaluators import EvaluationError
from backend.m03_reference import (MATCHING_POLICY, MAX_REFERENCE_BYTES, SCHEMA_VERSION,
                                   compare_business_order, load_reference, validate_reference)


def step(order, action, target):
    return dict(order=order, action=action, target=target)


def reference():
    return dict(schema_version=SCHEMA_VERSION, reference_id='SYNTHETIC-REFERENCE', evaluation_only=True,
                matching_policy=MATCHING_POLICY, fixed_at='2026-11-01T00:00:00Z', synthetic=True,
                business_units=[dict(business_unit_id='SYNTHETIC-BU', workflow_id='SYNTHETIC-WF',
                                     steps=[step(1, 'click', 'customer search'), step(2, 'click', 'customer select'),
                                            step(3, 'input', 'order form'), step(4, 'submit', 'order save')])])


class ReferenceComparisonTests(unittest.TestCase):
    def setUp(self):
        self.reference = reference()
        self.unit = self.reference['business_units'][0]
        self.scenario = copy.deepcopy(self.unit)
        self.scenario['scenario_id'] = 'SYNTHETIC-SCENARIO'

    def compare(self, scenario=None):
        return compare_business_order(self.scenario if scenario is None else scenario, self.unit)

    def test_exact_order_and_inputs_remain_unchanged(self):
        before = copy.deepcopy((self.scenario, self.reference))
        validated = validate_reference(self.reference)
        self.assertIs(validated, self.reference)
        result = self.compare()
        self.assertTrue(result['semantic_order_valid'])
        self.assertEqual(result['reason'], 'EXACT_MATCH')
        self.assertEqual(result['mismatched_positions'], [])
        self.assertEqual(result['expected_step_count'], 4)
        self.assertEqual(before, (self.scenario, self.reference))

    def test_reordered_content_fails_even_with_new_consecutive_numbers(self):
        rows = self.scenario['steps']
        rows[1], rows[2] = rows[2], rows[1]
        for order, row in enumerate(rows, 1):
            row['order'] = order
        result = self.compare()
        self.assertFalse(result['semantic_order_valid'])
        self.assertEqual(result['reason'], 'STEP_SEQUENCE_MISMATCH')
        self.assertEqual(result['mismatched_positions'], [2, 3])

    def test_missing_step_fails_without_shortening_expected_sequence(self):
        self.scenario['steps'].pop(1)
        for order, row in enumerate(self.scenario['steps'], 1):
            row['order'] = order
        result = self.compare()
        self.assertFalse(result['semantic_order_valid'])
        self.assertEqual(result['reason'], 'STEP_COUNT_MISMATCH')
        self.assertEqual((result['expected_step_count'], result['actual_step_count']), (4, 3))
        self.assertEqual(result['mismatched_positions'], [2, 3, 4])

    def test_extra_duplicate_is_not_reused_or_ignored(self):
        self.scenario['steps'].append(dict(self.scenario['steps'][-1], order=5))
        result = self.compare()
        self.assertFalse(result['semantic_order_valid'])
        self.assertEqual(result['mismatched_positions'], [5])

    def test_repeated_action_is_valid_if_reference_requires_it(self):
        self.unit['steps'].append(dict(self.unit['steps'][0], order=5))
        self.scenario['steps'] = copy.deepcopy(self.unit['steps'])
        self.assertTrue(self.compare()['semantic_order_valid'])

    def test_changed_target_action_case_or_whitespace_has_no_implicit_alias(self):
        for field, value in [('target', 'another customer'), ('action', 'CLICK'), ('target', ' customer search')]:
            scenario = copy.deepcopy(self.scenario)
            scenario['steps'][0][field] = value
            with self.subTest(field=field, value=value):
                self.assertFalse(self.compare(scenario)['semantic_order_valid'])
                self.assertEqual(self.compare(scenario)['mismatched_positions'], [1])

    def test_other_business_or_workflow_cannot_match(self):
        for field, expected in [('business_unit_id', 'BUSINESS_UNIT_MISMATCH'), ('workflow_id', 'WORKFLOW_MISMATCH')]:
            scenario = copy.deepcopy(self.scenario)
            scenario[field] = 'OTHER'
            with self.subTest(field=field):
                result = self.compare(scenario)
                self.assertFalse(result['semantic_order_valid'])
                self.assertEqual(result['reason'], expected)

    def test_invalid_scenario_is_not_repaired(self):
        for steps in (None, [], ['invalid'], [step(True, 'click', 'customer search')],
                      [step(2, 'click', 'customer search')], [dict(order=1, action='click')]):
            scenario = dict(self.scenario, steps=steps)
            with self.subTest(steps=steps):
                before = copy.deepcopy(scenario)
                self.assertFalse(self.compare(scenario)['semantic_order_valid'])
                self.assertEqual(scenario, before)

    def test_invalid_reference_unit_is_configuration_error(self):
        unit = copy.deepcopy(self.unit)
        unit['steps'][0]['order'] = 2
        with self.assertRaises(EvaluationError) as raised:
            compare_business_order(self.scenario, unit)
        self.assertEqual(raised.exception.status, 'ERROR')


class ReferenceLoadingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ktl-m03-reference-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.folder = self.root / 'data/evaluation/synthetic-reference'
        self.folder.mkdir(parents=True)
        self.path = self.folder / 'reference.json'
        self.dataset = 'SYNTHETIC-DATASET'
        self.config = {}

    def register(self, value=None, raw=None):
        raw = (json.dumps(reference() if value is None else value, ensure_ascii=False).encode('utf-8')
               if raw is None else raw)
        self.path.write_bytes(raw)
        self.config = dict(m03_evaluation_references={self.dataset: dict(
            path=self.path.relative_to(self.root).as_posix(), sha256=hashlib.sha256(raw).hexdigest())})
        return raw

    def load(self, mode='DEVELOPMENT', submitted='2026-11-09T00:00:00Z'):
        return load_reference(self.root, self.config, self.dataset, mode, submitted)

    def assert_error(self, callable_):
        with self.assertRaises(EvaluationError) as raised:
            callable_()
        self.assertEqual(raised.exception.status, 'ERROR')

    def test_missing_registration_is_pending_without_file_access(self):
        self.assertEqual(self.load(), (None, {}))
        self.config = dict(m03_evaluation_references={})
        self.assertEqual(self.load(), (None, {}))
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_registered_bytes_sha_and_input_are_preserved(self):
        original = reference()
        raw = self.register(original, raw=b'\xef\xbb\xbf' + json.dumps(original, indent=2).replace('\n', '\r\n').encode())
        before = copy.deepcopy(self.config)
        result, hashes = self.load()
        self.assertEqual(result, original)
        self.assertEqual(hashes, {self.path.relative_to(self.root).as_posix(): hashlib.sha256(raw).hexdigest()})
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(self.config, before)

    def test_tampered_missing_or_invalid_registered_reference_never_falls_back(self):
        self.register()
        self.path.write_bytes(self.path.read_bytes()+b' ')
        self.assert_error(self.load)
        self.path.unlink()
        self.assert_error(self.load)
        for registered in (None, {}, dict(path='data/evaluation/x.json', sha256='bad'),
                           dict(path='data/evaluation/x.json', sha256='0'*64, extra=True)):
            self.config = dict(m03_evaluation_references={self.dataset: registered})
            with self.subTest(registered=registered):
                self.assert_error(self.load)

    def test_absolute_parent_and_outside_evaluation_paths_are_rejected(self):
        self.register()
        entry = self.config['m03_evaluation_references'][self.dataset]
        for path in (str(self.path), '../outside.json', 'data/evaluation/../reference.json',
                     r'data\evaluation\..\reference.json', 'backend/reference.json',
                     r'C:\external\reference.json', r'C:reference.json', r'\\server\share\reference.json'):
            entry['path'] = path
            with self.subTest(path=path):
                self.assert_error(self.load)

    def test_symlink_file_and_parent_are_rejected(self):
        self.register()
        linked = self.folder / 'linked.json'
        try:
            linked.symlink_to(self.path)
        except (OSError, NotImplementedError):
            self.skipTest('OS does not permit temporary symlink creation')
        self.config['m03_evaluation_references'][self.dataset]['path'] = linked.relative_to(self.root).as_posix()
        self.assert_error(self.load)
        parent = self.root / 'data/evaluation/linked-folder'
        parent.symlink_to(self.folder, target_is_directory=True)
        self.config['m03_evaluation_references'][self.dataset]['path'] = (parent/'reference.json').relative_to(self.root).as_posix()
        self.assert_error(self.load)

    def test_link_guard_rejects_file_or_ancestor_without_following_it(self):
        self.register()
        original = Path.is_symlink
        for linked in (self.path, self.folder):
            with self.subTest(linked=linked), patch.object(Path, 'is_symlink', autospec=True,
                    side_effect=lambda path: path == linked or original(path)):
                self.assert_error(self.load)

    def test_reference_must_be_fixed_before_submission_with_timezone(self):
        for fixed, submitted, valid in [('2026-11-09T00:00:00Z', '2026-11-09T00:00:00+00:00', True),
                                        ('2026-11-09T09:00:00+09:00', '2026-11-09T00:00:00Z', True),
                                        ('2026-11-10T00:00:00Z', '2026-11-09T00:00:00Z', False),
                                        ('2026-11-01T00:00:00', '2026-11-09T00:00:00Z', False),
                                        ('2026-11-01T00:00:00Z', '2026-11-09T00:00:00', False),
                                        ('invalid', '2026-11-09T00:00:00Z', False)]:
            self.register(dict(reference(), fixed_at=fixed))
            with self.subTest(fixed=fixed, submitted=submitted):
                if valid:
                    self.assertIsNotNone(self.load(submitted=submitted)[0])
                else:
                    self.assert_error(lambda: self.load(submitted=submitted))

    def test_official_requires_explicit_non_synthetic_approval(self):
        for flags, valid in [({}, False), ({'synthetic': True, 'approved_for_official': True}, False),
                             ({'synthetic': False, 'approved_for_official': False}, False),
                             ({'synthetic': 0, 'approved_for_official': 1}, False),
                             ({'synthetic': False, 'approved_for_official': True}, True)]:
            value = reference()
            value.pop('synthetic')
            value.update(flags)
            self.register(value)
            with self.subTest(flags=flags):
                if valid:
                    self.assertIsNotNone(self.load(mode='OFFICIAL')[0])
                else:
                    self.assert_error(lambda: self.load(mode='OFFICIAL'))

    def test_invalid_schema_policy_units_and_steps_are_rejected(self):
        mutations = [lambda r:r.update(schema_version='other'), lambda r:r.update(reference_id=''),
                     lambda r:r.update(evaluation_only=False), lambda r:r.update(matching_policy='FUZZY'),
                     lambda r:r.update(business_units=[]),
                     lambda r:r['business_units'].append(copy.deepcopy(r['business_units'][0])),
                     lambda r:r['business_units'][0].update(workflow_id=''),
                     lambda r:r['business_units'][0].update(steps=[]),
                     lambda r:r['business_units'][0]['steps'][0].update(order=True),
                     lambda r:r['business_units'][0]['steps'][0].update(order=2),
                     lambda r:r['business_units'][0]['steps'][0].update(action='x'*257),
                     lambda r:r['business_units'][0]['steps'][0].update(target=' ')]
        for change in mutations:
            value = reference()
            change(value)
            self.register(value)
            with self.subTest(change=change):
                self.assert_error(self.load)

    def test_exact_unit_and_step_limits(self):
        value = reference()
        base = value['business_units'][0]
        value['business_units'] = [dict(copy.deepcopy(base), business_unit_id=f'BU-{i}') for i in range(10)]
        value['business_units'][0]['steps'] = [step(i, 'click', 'repeat target') for i in range(1, 1001)]
        self.register(value)
        self.assertIsNotNone(self.load()[0])
        value['business_units'].append(dict(copy.deepcopy(base), business_unit_id='BU-11'))
        self.register(value)
        self.assert_error(self.load)
        value['business_units'].pop()
        value['business_units'][0]['steps'].append(step(1001, 'click', 'repeat target'))
        self.register(value)
        self.assert_error(self.load)

    def test_invalid_json_duplicate_keys_encoding_and_size_are_rejected(self):
        for raw in (b'{', b'\xff', b'{}', b'{"schema_version":"a","schema_version":"b"}',
                    b'{"number":NaN}', b' '*(MAX_REFERENCE_BYTES+1)):
            self.register(raw=raw)
            with self.subTest(prefix=raw[:80]):
                self.assert_error(self.load)

    def test_invalid_registry_is_not_silently_missing(self):
        self.config = dict(m03_evaluation_references=[])
        self.assert_error(self.load)


if __name__ == '__main__':
    unittest.main()
