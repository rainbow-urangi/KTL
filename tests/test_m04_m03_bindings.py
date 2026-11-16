"""Pure binding regression; no browser, model, business write or provider call."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.m04 import m03_bindings as bindings


FIXTURE = Path(__file__).resolve().parents[1] / 'data/runtime/rainbow-m03-frozen-20261112/results/development/m03_menu_enter_20261112/scenarios.json'


class FrozenM03BindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_bytes()
        cls.rows = {row['business_unit_id']: row for row in json.loads(cls.raw)}
        candidate = FIXTURE.parents[3] / 'docs/agents/m03_final_10_candidate_20261112/M03_FINAL_10_CANDIDATE.json'
        cls.names = {row['business_unit_id']: row['name'] for row in json.loads(candidate.read_bytes())['selection']}

    def source(self, name):
        return deepcopy(self.rows[name])

    def parameters(self, source):
        return {spec['name']: '문서' if spec['type'] == 'select' else '2026-11-16' if spec['type'] == 'date' else 'KTL-synthetic-new-value'
                for spec in bindings.describe(source)['parameters']}

    def test_supported_nine_are_binding_ready_and_inputs_are_separate(self):
        for name in ['BU01', 'BU05', 'BU07', 'BU09', 'BU12', 'BU13', 'BU14', 'BU17', 'BU20']:
            with self.subTest(name=name):
                row = self.source(name); detail = bindings.describe(row)
                self.assertTrue(detail['ready']); self.assertTrue(detail['binding_ready'])
                self.assertEqual(detail['name'], self.names[name])
                self.assertEqual(detail['parameters_required'], bool(detail['parameters']))
                self.assertEqual(detail['status'], 'NEEDS_INPUT' if detail['parameters'] else 'READY')
                result = bindings.prepare(row, self.parameters(row))
                self.assertEqual(result['scenario']['scenario_id'], row['scenario_id'])
                self.assertEqual(result['scenario']['scenario_name'], self.names[name])
                self.assertEqual(result['contract']['scenario_id'], row['scenario_id'])

    def test_failed_bu03_remains_blocked_by_the_original_binding_and_keeps_its_missing_steps(self):
        row = self.source('BU03')
        with self.assertRaises(ValueError): bindings._validate(row)
        with self.assertRaises(ValueError): bindings.prepare(row, {})
        self.assertEqual([s['order'] for s in self.rows['BU03']['steps']], [1, 2, 7, 14, 16])
        self.assertEqual(len(self.rows['BU03']['issues']), 11)

    def test_unknown_action_target_selector_identity_or_duplicate_change_is_not_accepted(self):
        edits = [lambda s:s.update(workflow_id='WF-OTHER'),
                 lambda s:s.update(scenario_id='OTHER'),
                 lambda s:s['steps'][0].update(action='OTHER'),
                 lambda s:s['steps'][0].update(target='OTHER'),
                 lambda s:s['steps'][1]['fields'][0].update(selector='#forged'),
                 lambda s:s['steps'][1]['fields'].pop(),
                 lambda s:s['steps'][1]['fields'].reverse()]
        for edit in edits:
            row=self.source('BU07');edit(row)
            self.assertFalse(bindings.describe(row)['ready'])
            with self.assertRaises(ValueError):bindings.prepare(row,{})

    def test_every_original_step_and_duplicate_input_observation_has_a_mapping(self):
        row=self.source('BU07');result=bindings.prepare(row,self.parameters(row))
        self.assertEqual(len(result['source_mapping']),4)
        self.assertEqual([m['source_order'] for m in result['source_mapping']], [1,2,3,4])
        inputs=[s for s in result['scenario']['steps'] if s['action']=='input']
        self.assertEqual(len(inputs),3)
        self.assertEqual([s['source_field_index'] for s in inputs],[0,1,2])
        self.assertEqual(inputs[1]['target'],inputs[2]['target'])
        self.assertEqual(inputs[1]['value'],inputs[2]['value'])
        self.assertEqual([o for m in result['source_mapping'] for o in m['effective_orders']],list(range(1,7)))
        self.assertEqual(len(result['source_mapping'][1]['effective_orders']),3)

    def test_original_fields_are_verbatim_and_all_source_files_remain_unchanged(self):
        for name in ['BU07','BU09','BU14','BU17','BU20']:
            row=self.source(name);before=deepcopy(row)
            result=bindings.prepare(row,self.parameters(row))
            self.assertEqual([s['target'] for s in result['scenario']['steps'] if s['action'] in {'input','select'}],
                             [f['selector'] for s in row['steps'] for f in s.get('fields',[])])
            self.assertEqual(row,before)
        self.assertEqual(FIXTURE.read_bytes(),self.raw)

    def test_required_extra_nonstring_masked_secret_and_selenium_key_parameters_fail_without_echo(self):
        row=self.source('BU07');good=self.parameters(row)
        bad=[{},dict(good,extra='x'),dict(good,field_1=True),dict(good,field_1='[MASKED]'),
             dict(good,field_1='password=SYNTHETIC_SECRET'),dict(good,field_1='KTL-\ue007'),
             dict(good,field_1='KTL-value\nsubmit'),dict(good,field_1='ordinary-existing-title')]
        for values in bad:
            with self.assertRaises(ValueError) as raised: bindings.prepare(row,values)
            self.assertNotIn('SYNTHETIC_SECRET',str(raised.exception))

    def test_truth_or_credentials_in_source_are_never_generator_or_binding_inputs(self):
        for extra in [{'ground_truth':{'answer':'x'}},{'authorization':'Bearer SYNTHETIC_SECRET'}]:
            row=self.source('BU01');row.update(extra)
            self.assertFalse(bindings.describe(row)['ready'])
            with self.assertRaises(ValueError):bindings.prepare(row,{})

    def test_lookup_uses_operator_exact_title_and_never_first_record(self):
        row=self.source('BU05');result=bindings.prepare(row,{'record_title':'KTL-selected-report'})
        step=result['scenario']['steps'][0]
        self.assertEqual(step['match_text'],'KTL-selected-report')
        self.assertNotIn('first',step['target'])
        self.assertTrue(any(c['kind']=='text_equals' and c['expected']=='KTL-selected-report'
                            for c in result['contract']['steps'][0]['checks']))

    def test_bu12_source_page_is_setup_only_and_destination_is_cards(self):
        result=bindings.prepare(self.source('BU12'),{})
        self.assertTrue(result['scenario']['start_url'].endswith('/mypage/work/monthly'))
        self.assertEqual(result['scenario']['steps'][0]['match_text'],'명함 관리')
        self.assertIn({'kind':'url_path','expected':'/mypage/cards'},result['contract']['steps'][0]['checks'])

    def test_save_requires_fresh_marker_zero_then_one_and_success_message(self):
        for name in ['BU07','BU09','BU14','BU17','BU20']:
            with self.subTest(name=name):
                row=self.source(name);r=bindings.prepare(row,self.parameters(row))
                first=r['contract']['steps'][0]['checks']
                self.assertTrue(any(c['kind']=='text_count' and c['count']==0 for c in first))
                last_order=next(m['effective_orders'][0] for m in r['source_mapping'] if m['source_action']=='SAVE')
                outcomes=r['contract']['steps'][last_order-1]['checks']
                self.assertTrue(any(c['kind']=='text_count' and c['count']==1 for c in outcomes))
                self.assertTrue(any(c['kind']=='text_contains' for c in outcomes))
                self.assertTrue(any(c['kind']=='visible' and c['expected'] is False for c in outcomes))

    def test_asset_select_requires_checked_static_choice_and_preserves_original_select(self):
        row=self.source('BU20');params=self.parameters(row)
        r=bindings.prepare(row,params)
        selected=[s for s in r['scenario']['steps'] if s['action']=='select']
        self.assertEqual(len(selected),1);self.assertEqual(selected[0]['value'],'문서')
        self.assertEqual(selected[0]['target'],row['steps'][1]['fields'][0]['selector'])
        params['field_1']='__custom__'
        with self.assertRaises(ValueError):bindings.prepare(row,params)

    def test_weekly_exact_display_title_uses_declared_date_and_requires_that_form_date(self):
        source = self.source('BU09')
        original = deepcopy(source)
        values = self.parameters(source)
        values['field_1'] = 'KTL-weekly-exact-title'
        result = bindings.prepare(source, values)
        self.assertEqual(source, original)
        self.assertEqual(len(result['source_mapping']), len(source['steps']))
        expected = '26-11 3주차 KTL-weekly-exact-title'
        checks = [c for step in result['contract']['steps'] for c in step['checks']]
        markers = [c for c in checks if c['kind'] == 'text_count']
        self.assertTrue(markers)
        self.assertTrue(all(c['expected'] == expected for c in markers))
        self.assertEqual(markers[0]['count'], 0)
        self.assertTrue(any(c['count'] == 1 for c in markers))
        date_checks = [c for c in checks if c['kind'] == 'text_equals' and 'date-button' in c['target']['value']]
        self.assertEqual(len(date_checks), 1)
        self.assertEqual(date_checks[0]['expected'], '2026.11.16 (월)')
        title_input = next(s for s in result['scenario']['steps'] if s.get('value') == values['field_1'])
        self.assertEqual(title_input['value'], values['field_1'])
        self.assertNotIn('주차', title_input['value'])

    def test_weekly_period_boundaries_are_exact_and_invalid_or_missing_dates_are_rejected(self):
        source = self.source('BU09')
        cases = [('2026-11-01', '26-11 1주차'), ('2026-11-07', '26-11 1주차'),
                 ('2026-11-08', '26-11 2주차'), ('2026-11-30', '26-11 5주차'),
                 ('2026-09-01', '26-9 1주차'), ('2026-09-05', '26-9 1주차'),
                 ('2026-09-06', '26-9 2주차'), ('2026-09-30', '26-9 5주차'),
                 ('2025-03-31', '25-3 6주차'), ('2000-01-01', '00-1 1주차')]
        for current, label in cases:
            with self.subTest(current=current):
                values = dict(self.parameters(source), report_date=current)
                result = bindings.prepare(source, values)
                markers = [c for s in result['contract']['steps'] for c in s['checks'] if c['kind'] == 'text_count']
                self.assertTrue(all(c['expected'] == label + ' ' + values['field_1'] for c in markers))
        for invalid in ('', '2026-02-29', '2026-2-01', '20261116', '2026-11-16 ', 'KTL-date'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                bindings.prepare(source, dict(self.parameters(source), report_date=invalid))
        values = self.parameters(source)
        del values['report_date']
        with self.assertRaises(ValueError): bindings.prepare(source, values)

    def test_bu13_requires_explicit_new_company_and_preserves_historical_target_and_order(self):
        source = self.source('BU13')
        original = deepcopy(source)
        detail = bindings.describe(source)
        self.assertEqual(detail['status'], 'NEEDS_INPUT')
        self.assertEqual([s['name'] for s in detail['parameters']], ['record_company'])
        self.assertEqual(detail['parameters'][0]['default'], '')
        for values in ({}, {'record_company': ''}, {'record_company': '[MASKED]'},
                       {'record_company': 'ordinary-company'}, {'record_company': 'KTL-\ue007'}):
            with self.subTest(keys=list(values)), self.assertRaises(ValueError):bindings.prepare(source, values)
        result = bindings.prepare(source, {'record_company': 'KTL-explicit-new-company'})
        self.assertEqual(source, original)
        self.assertEqual(len(result['scenario']['steps']), len(source['steps']))
        self.assertEqual([m['source_order'] for m in result['source_mapping']], [s['order'] for s in source['steps']])
        self.assertEqual([m['source_target'] for m in result['source_mapping']], [s['target'] for s in source['steps']])
        self.assertTrue(all(m['historical_target_identity_verified'] is False for m in result['source_mapping']))
        selected = result['scenario']['steps'][0]
        self.assertEqual(selected['row_match'], dict(rows='table.business-card-table tbody tr',
                         cell='td:nth-child(3)', expected='KTL-explicit-new-company'))
        self.assertNotIn('match_text', selected)
        checks = result['contract']['steps'][0]['checks']
        self.assertTrue(any(c['kind'] == 'text_equals' and c['expected'] == 'KTL-explicit-new-company' for c in checks))
        self.assertTrue(any(c['kind'] == 'text_count' and c['count'] == 1 for c in checks))
        self.assertEqual(result['scenario']['steps'][-1]['match_text'], '확인')
        self.assertTrue(any(c['kind'] == 'visible' and c['expected'] is False for c in result['contract']['steps'][-1]['checks']))
        self.assertIn('동일한 인물·레코드', result['notice'])

    def test_pure_prepare_has_no_network_or_source_write(self):
        with patch('socket.socket',side_effect=AssertionError('No network')), \
                patch.object(Path,'write_bytes',side_effect=AssertionError('No source write')):
            result=bindings.prepare(self.source('BU01'),{})
        self.assertEqual(len(result['source_mapping']),2)
        self.assertEqual(result['remediation_provenance']['original_m03_step_count'],2)


if __name__ == '__main__':
    unittest.main()
