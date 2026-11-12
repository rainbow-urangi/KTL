"""Synthetic archive association tests; no browser/provider/runtime file access."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from backend import execution_plan as plans
from backend import execution_target_bindings as bindings
from backend.execution_contexts import prepare_plan
from backend.evaluators import EvaluationError


sha = lambda raw: hashlib.sha256(raw).hexdigest()
loc = lambda css: dict(by='css selector', value=css)


class ArchivedTargetBindingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='ktl-archive-binding-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.rows = [dict(id=str(i), event_id='e' + str(i), session_id='s1', event_time=f'2026-11-09T00:00:0{i}.000Z',
            interaction_type=kind, page_url='https://example.invalid/synthetic', target_selector=selector,
            element_tag='div' if selector else 'html', input_control_type='', target_key='css:' + selector,
            locators_json=json.dumps(dict(selector_css=selector)), capture_run_id='r1', capture_tab_id='7',
            capture_frame_id='0', capture_root_tab_id='7', capture_tab_path='[7]')
            for i, (kind, selector) in enumerate([('page_view', ''), ('click', '#cell'), ('api_transaction', '')], 1)]
        self.manifest = dict(capture_scope_version=2, active=False, official=False, run_id='r1', scenario_id='SYNTHETIC',
            target_tab_id=7, capture_tab_paths={'7': [7]}, started_at='2026-11-09T00:00:00.000Z',
            stopped_at='2026-11-09T00:00:04.000Z')
        self.source = dict(scenario_id='s1', business_unit_id='SYNTHETIC', workflow_id='w1', official=False,
            steps=[dict(order=i, id='n' + str(i), occurrence_id='o' + str(i), action=action,
                target='observed', evidence=['e' + str(i)], source_csv_rows=[i], source_session_id='s1')
                for i, action in enumerate(['page_entry', 'selection', 'api_confirmation'], 1)])
        self.trace = [dict(at='2026-11-09T00:00:00.200Z', label='CAPTURE_START SYNTHETIC'),
            dict(at='2026-11-09T00:00:01.100Z', label='NAVIGATE https://example.invalid/synthetic'),
            dict(at='2026-11-09T00:00:02.100Z', label='CLICK #cell .date'),
            dict(at='2026-11-09T00:00:05.200Z', label='CAPTURE_START NEXT')]
        self.summary = dict(business_unit_id='SYNTHETIC', run_id='r1', target_tab_id=7, action_offset=0,
            started_at='2026-11-09T00:00:00.100Z', completed_at='2026-11-09T00:00:04.500Z', status='COMPLETED')
        self.following = dict(business_unit_id='NEXT', action_offset=3, started_at='2026-11-09T00:00:05.000Z')
        self.binding = dict(version=1, business_unit_id='SYNTHETIC', capture_run_id='r1', target_tab_id=7,
            event_id='e2', csv_row=2, element_tag='div', observed_target='#cell', command_target='#cell .date',
            command_index=2, capture_start_index=0, next_capture_start_index=3,
            association_method=bindings.ASSOCIATION, clock_policy=bindings.CLOCK,
            review_evidence_sha256=dict(synthetic_ui_review='0' * 64))
        self.plan = dict(version=1, parameter_source='NEW_TEST_PARAMETERS', parameters={}, items=[
            dict(kind='execute', source_refs=[dict(order=1, event_ids=['e1'])], action='navigate',
                target=dict(url=self.rows[0]['page_url']), expected_result='Independent screen expectation',
                checks=[dict(kind='url_path', expected='/synthetic')]),
            dict(kind='execute', source_refs=[dict(order=2, event_ids=['e2'])], action='click', target=loc('#cell .date'),
                target_binding_id='SYNTHETIC-REVIEWED-BINDING', expected_result='New entry form, not editing',
                checks=[dict(kind='count', target=loc('#delete-button'), expected=0)]),
            dict(kind='reference', source_refs=[dict(order=3, event_ids=['e3'])], reason='Original API observation')])
        self.config = dict(m07=dict(execution_target_bindings={'SYNTHETIC-REVIEWED-BINDING': self.binding}))
        (self.root / 'logger.cjs').write_bytes(b'// synthetic post mouse release completion logger\n')
        self.refresh_observations()
        self.refresh_archive()

    def spec(self, filename):
        return dict(path=filename, sha256=sha((self.root / filename).read_bytes()))

    def refresh_observations(self):
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=list(self.rows[0]))
        writer.writeheader()
        writer.writerows(self.rows)
        raw = output.getvalue().encode('utf-8-sig')
        (self.root / 'events.csv').write_bytes(raw)
        self.manifest.update(csv_sha256=sha(raw), csv_byte_count=len(raw), columns=list(self.rows[0]),
            event_count=len(self.rows), event_evidence=[dict(csv_row=i, event_id=row['event_id'],
                session_id=row['session_id'], event_time=row['event_time'], tab_id=7, frame_id=0, event_sequence=i)
                for i, row in enumerate(self.rows, 1)])
        (self.root / 'manifest.json').write_bytes(plans.encoded(self.manifest))
        self.source.update(source_csv_sha256=sha(raw), source_capture_manifest_sha256=sha((self.root / 'manifest.json').read_bytes()))
        self.plan.update(source_scenario_sha256=plans.source_digest(self.source), observation_sources=dict(
            csv=self.spec('events.csv'), capture_manifest=self.spec('manifest.json')))
        self.binding['source_scenario_sha256'] = plans.source_digest(self.source)
        self.summary.update(csv_sha256=sha(raw), csv_bytes=len(raw), event_count=len(self.rows))

    def refresh_archive(self):
        for name, value in [('trace.json', self.trace), ('summary.json', self.summary), ('next.json', self.following)]:
            (self.root / name).write_bytes(plans.encoded(value))
        archive = dict(csv='events.csv', capture_manifest='manifest.json', command_trace='trace.json',
                       attempt_summary='summary.json', next_attempt_summary='next.json', command_logger='logger.cjs')
        index = [dict(path=filename, bytes=(self.root / filename).stat().st_size,
                      sha256=sha((self.root / filename).read_bytes())) for filename in archive.values()]
        for name in ['index.json', 'final.json']:
            (self.root / name).write_bytes(plans.encoded(index))
        self.binding['archive_paths'] = archive
        self.binding['files'] = {name: self.spec(filename) for name, filename in dict(
            collection_index='index.json', final_index='final.json', command_trace='trace.json',
            attempt_summary='summary.json', next_attempt_summary='next.json', command_logger='logger.cjs').items()}
        self.plan['observation_sources']['command_trace'] = self.spec('trace.json')

    def observed(self):
        return plans.load_observations(self.root, self.source, self.plan, self.config)

    def reject(self, callback):
        with self.assertRaises(EvaluationError) as error:
            callback()
        self.assertEqual(error.exception.status, 'NOT_READY')

    def test_exact_registered_child_compiles_without_changing_observed_source(self):
        original = plans.encoded(self.source)
        result = prepare_plan(self.root, self.source, self.config, self.plan)
        self.assertEqual(result['contract']['steps'][1]['target'], loc('#cell .date'))
        mapping = result['execution_plan']['source_mapping'][1]
        self.assertFalse(mapping['target_binding']['direct_causal_id_proven'])
        self.assertEqual(mapping['target_binding']['command_index'], 2)
        self.assertEqual(mapping['source_refs'][0]['event_ids'], ['e2'])
        self.assertEqual(plans.encoded(self.source), original)
        self.assertEqual(result, prepare_plan(self.root, self.source, self.config, result['execution_plan']))

    def test_unregistered_binding_or_trace_without_binding_is_not_ready(self):
        self.reject(lambda: plans.load_observations(self.root, self.source, self.plan))
        del self.plan['items'][1]['target_binding_id']
        self.reject(self.observed)

    def test_guessed_descendant_and_nonclick_cannot_reuse_approval(self):
        observed = self.observed()
        self.plan['items'][1]['target'] = loc('#cell .guessed')
        self.reject(lambda: plans.prepare(self.source, self.plan, self.config, observations=observed))
        self.plan['items'][1].update(target=loc('#cell .date'), action='input', value_param='fresh')
        self.plan['parameters']['fresh'] = 'New input'
        self.reject(lambda: plans.prepare(self.source, self.plan, self.config, observations=observed))

    def test_another_raw_event_cannot_use_the_same_approval(self):
        observed = self.observed()
        self.plan['items'][1]['source_refs'] = [dict(order=3, event_ids=['e3'])]
        self.reject(lambda: plans.prepare(self.source, self.plan, self.config, observations=observed))

    def test_raw_trace_hash_tampering_is_not_normalized_away(self):
        (self.root / 'trace.json').write_bytes((self.root / 'trace.json').read_bytes() + b' ')
        self.reject(self.observed)

    def test_index_must_independently_pin_trace_even_if_file_hash_is_refreshed(self):
        self.trace[2]['at'] = '2026-11-09T00:00:02.200Z'
        (self.root / 'trace.json').write_bytes(plans.encoded(self.trace))
        self.binding['files']['command_trace'] = self.spec('trace.json')
        self.plan['observation_sources']['command_trace'] = self.spec('trace.json')
        self.reject(self.observed)

    def test_post_completion_window_is_strict_without_a_clock_tolerance(self):
        self.trace[2]['at'] = '2026-11-09T00:00:01.900Z'
        self.refresh_archive()
        self.reject(self.observed)

    def test_trace_command_selector_must_match_exactly(self):
        self.trace[2]['label'] = 'CLICK #cell .other'
        self.refresh_archive()
        self.reject(self.observed)

    def test_summary_offset_run_and_tab_are_not_interchangeable(self):
        for key, invalid in [('action_offset', 1), ('run_id', 'other'), ('target_tab_id', 8)]:
            with self.subTest(key=key):
                original = self.summary[key]
                self.summary[key] = invalid
                self.refresh_archive()
                self.reject(self.observed)
                self.summary[key] = original

    def test_two_raw_clicks_in_same_completion_window_are_ambiguous(self):
        self.rows[2].update(interaction_type='click', event_time='2026-11-09T00:00:01.900Z')
        self.refresh_observations()
        self.refresh_archive()
        self.reject(self.observed)

    def test_approval_cannot_change_between_loading_and_pure_compilation(self):
        observed = self.observed()
        self.binding['command_target'] = '#cell .changed'
        self.reject(lambda: plans.prepare(self.source, self.plan, self.config, observations=observed))

    def test_truth_payload_and_path_escape_still_fail(self):
        observed = self.observed()
        self.plan['parameters']['reference'] = 'forbidden'
        self.reject(lambda: plans.prepare(self.source, self.plan, self.config, observations=observed))
        del self.plan['parameters']['reference']
        self.binding['files']['command_trace']['path'] = '../outside.json'
        self.plan['observation_sources']['command_trace'] = copy.deepcopy(self.binding['files']['command_trace'])
        self.reject(self.observed)


if __name__ == '__main__':
    unittest.main()
