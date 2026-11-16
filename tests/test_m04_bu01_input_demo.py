"""BU01 input-only supplemental execution; no real browser or account writes."""
import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.m04 import bu01_input_demo, m03_bindings
from backend.m04.checks import prepare_contract
from backend.m04.scenario_compiler import compile_code
from backend.m04.store import M04Manager
from backend.session import RuntimeSession
from tests.test_m04_scenario_compiler import FakeDriver, FakeElement, execute_synthetic


FIXTURE = (Path(__file__).resolve().parents[1] /
           'data/runtime/rainbow-m03-frozen-20261112/results/development/m03_menu_enter_20261112/scenarios.json')
# Independently reviewed page order, including the separate address controls.
ORDER = ('#personal-name', '#personal-email-primary', '#personal-email-secondary',
         '#personal-duty', '#personal-office-phone', '#personal-emergency-phone',
         '#personal-postal-code', 'input[placeholder="주소"]', 'input[placeholder="상세주소"]',
         '#personal-gender', '#personal-introduction', '#personal-workplace',
         '#personal-position', '#personal-degree')
FORM = 'form.personal-info-page '


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def sha(value):
    return hashlib.sha256(value).hexdigest()


class DemoDriver(FakeDriver):
    def __init__(self, prepared, values=None):
        super().__init__()
        self.prepared = prepared
        self.add('button.mypage-sidebar__section-button', tag='button', text='일반 정보')
        self.add('button.mypage-sidebar__section-button[aria-expanded="true"]', tag='button')
        menu = self.add('button.mypage-sidebar__submenu-button', tag='button', text='개인정보')
        menu.after_click = lambda: setattr(self, 'current_url', 'https://rainbowlab.ai.kr/mypage/personal-info')
        self.original_values = (list(values) if values is not None else
                                ['' if index % 2 else 'Synthetic preserved field ' + str(index)
                                 for index in range(len(ORDER))])
        for selector, value in zip(ORDER, self.original_values):
            self.add(FORM + selector, value=value,
                     tag='textarea' if selector == '#personal-introduction' else 'input')
        self.add('#personal-name', value='Synthetic initial name')
        self.add(FORM + '#personal-birth-date', value='1999-12-31', attributes={'type': 'date'})
        inventory = ', '.join(FORM + selector for selector in ORDER)
        self.elements[inventory] = [self.elements[FORM + selector][0] for selector in ORDER]
        self.state_before_fill = None
        self.first_fill = next(row['order'] for row in prepared['scenario']['steps']
                               if row['action'] == 'fill_empty')

    def before_step(self, order):
        if order == self.first_fill:
            self.state_before_fill = [self.elements[FORM + selector][0].value for selector in ORDER]


class BU01InputDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = FIXTURE.read_bytes()
        cls.rows = {row['business_unit_id']: row for row in json.loads(cls.raw)}

    def prepare(self):
        return m03_bindings.prepare(deepcopy(self.rows['BU01']), {})

    def execute(self, prepared=None, driver=None):
        prepared = prepared or self.prepare()
        driver = driver or DemoDriver(prepared)
        entered = execute_synthetic(compile_code(prepared['scenario'], prepared['contract']), driver)
        return driver, entered

    def test_original_m03_rows_and_raw_pinned_bytes_are_preserved(self):
        source = deepcopy(self.rows['BU01'])
        original = deepcopy(source)
        fingerprint = m03_bindings.source_fingerprint(source)
        prepared = m03_bindings.prepare(source, {})
        self.assertEqual(source, original)
        self.assertEqual(FIXTURE.read_bytes(), self.raw)
        self.assertEqual(fingerprint, m03_bindings._PINS['BU01'])
        self.assertEqual(prepared['source_fingerprint'], fingerprint)
        self.assertEqual(len(source['steps']), 2)
        self.assertEqual(len(prepared['source_mapping']), 2)
        for observed, mapping in zip(source['steps'], prepared['source_mapping']):
            self.assertEqual(mapping['source_order'], observed['order'])
            self.assertEqual(mapping['source_event_ids'], observed['source_event_ids'])
            self.assertEqual(mapping['source_node_ids'], observed['source_node_ids'])
            self.assertEqual(mapping['effective_orders'], [observed['order']])

    def test_additional_work_is_explicitly_input_only_and_unobserved_in_m03(self):
        prepared = self.prepare()
        provenance = prepared['remediation_provenance']
        self.assertEqual(provenance['input_policy'], 'EMPTY_ONLY_IN_REVIEWED_FORM_ORDER')
        self.assertEqual(provenance['original_m03_step_count'], 2)
        self.assertFalse(provenance['original_m03_modified'])
        self.assertFalse(provenance['persisted_business_writes'])
        self.assertFalse(provenance['submit_included'])
        self.assertEqual(provenance['field_count'], 14)
        self.assertEqual([row['phase'] for row in provenance['supplemental_steps']],
                         ['PREFLIGHT'] + ['FILL_EMPTY'] * 14 + ['FILLED_FORM'])
        for row in provenance['supplemental_steps']:
            self.assertFalse(row['observed_in_m03'])
            self.assertEqual(row['origin'], 'USER_REQUESTED_M04_SUPPLEMENT')
        for step in prepared['scenario']['steps'][2:]:
            self.assertNotIn('source_order', step)
            self.assertEqual(step['execution_origin'], 'USER_REQUESTED_BU01_INPUT_DEMO')

    def test_explicit_targets_follow_the_reviewed_form_order_once(self):
        prepared = self.prepare()
        selected = [row for row in prepared['remediation_provenance']['supplemental_steps']
                    if row['phase'] == 'FILL_EMPTY']
        self.assertEqual([row['target']['value'] for row in selected], [FORM + selector for selector in ORDER])
        self.assertEqual(len(prepared['scenario']['steps']), 18)
        self.assertEqual([row['order'] for row in prepared['scenario']['steps']], list(range(1, 19)))
        self.assertEqual(prepared['binding_version'], 'bu01-text-entry-demo-v2-empty-only')

    def test_contract_checks_empty_only_policy_without_submit(self):
        prepared = self.prepare()
        scenario, contract = prepared['scenario'], prepared['contract']
        self.assertEqual(prepare_contract(dict(scenario, execution_contract=contract)), contract)
        self.assertEqual({row['action'] for row in scenario['steps']}, {'click', 'fill_empty', 'verify'})
        for step, definition in zip(scenario['steps'], contract['steps']):
            if step['action'] == 'fill_empty':
                self.assertTrue(any(check['kind'] == 'fill_empty' and check['expected'] == step['value']
                                    and check['target'] == definition['target'] for check in definition['checks']))
                self.assertFalse(any(char in step['value'] for char in ('\r', '\n', '\ue007')))
        filled = next(row for row in prepared['remediation_provenance']['supplemental_steps']
                      if row['phase'] == 'FILLED_FORM')
        self.assertEqual(sum(check['kind'] == 'fill_empty'
                             for check in contract['steps'][filled['order'] - 1]['checks']), 14)

    def test_compiled_native_execution_fills_only_blank_fields_in_order_and_keeps_date(self):
        prepared = self.prepare()
        driver, entered = self.execute(prepared)
        self.assertEqual(entered, list(range(1, 19)))
        self.assertEqual(driver.state_before_fill, driver.original_values)
        self.assertEqual(driver.elements[FORM + '#personal-birth-date'][0].value, '1999-12-31')
        fills = [step for index, step in enumerate(prepared['scenario']['steps'][3:-1])
                 if driver.original_values[index] == '']
        actual = [(action[1], action[2][0]) for action in driver.actions
                  if action[0] == 'send_keys']
        self.assertEqual(actual, [(step['target'], step['value']) for step in fills])
        self.assertTrue(all(driver.elements[step['target']][0].value == step['value'] for step in fills))
        for selector, previous in zip(ORDER, driver.original_values):
            if previous:
                self.assertEqual(driver.elements[FORM + selector][0].value, previous)
                self.assertFalse(any(action[0] in {'click', 'send_keys', 'clear'} and action[1] == FORM + selector
                                     for action in driver.actions))
        self.assertFalse(any(action[0] == 'submit' for action in driver.actions))
        self.assertFalse(any(action[0] == 'clear' for action in driver.actions))
        self.assertFalse(any(action[0] == 'send_keys' and action[2] in
                             (('ENTER',), ('TAB',), ('CTRL', 'a'), ('BACKSPACE',))
                             for action in driver.actions))
        self.assertEqual(driver.quit_count, 1)

    def test_all_populated_fields_receive_no_clicks_or_keys(self):
        prepared = self.prepare()
        values = ['Synthetic preserved ' + str(index) for index in range(len(ORDER))]
        driver = DemoDriver(prepared, values)
        _, entered = self.execute(prepared, driver)
        self.assertEqual(entered, list(range(1, 19)))
        self.assertEqual([driver.elements[FORM + selector][0].value for selector in ORDER], values)
        self.assertFalse(any(action[0] in {'send_keys', 'clear'} for action in driver.actions))
        self.assertFalse(any(action[0] == 'click' and action[1] in {FORM + selector for selector in ORDER}
                             for action in driver.actions))

    def test_all_blank_fields_receive_exactly_one_value_in_reviewed_order(self):
        prepared = self.prepare()
        driver = DemoDriver(prepared, [''] * len(ORDER))
        self.execute(prepared, driver)
        fills = prepared['scenario']['steps'][3:-1]
        self.assertEqual([action for action in driver.actions if action[0] == 'send_keys'],
                         [('send_keys', step['target'], (step['value'],)) for step in fills])

    def test_whitespace_is_a_current_value_and_is_preserved_exactly(self):
        prepared = self.prepare()
        values = [' \t ' if index % 2 else ' Synthetic populated ' for index in range(len(ORDER))]
        driver = DemoDriver(prepared, values)
        self.execute(prepared, driver)
        self.assertEqual([driver.elements[FORM + selector][0].value for selector in ORDER], values)
        self.assertFalse(any(action[0] in {'send_keys', 'clear'} for action in driver.actions))

    def test_later_mutation_of_a_preserved_value_fails_final_check(self):
        prepared = self.prepare()
        driver = DemoDriver(prepared)
        real_before_step = driver.before_step

        def before_step(order):
            real_before_step(order)
            if order == 18:
                driver.elements[FORM + ORDER[0]][0].value = 'Synthetic unexpected replacement'

        driver.before_step = before_step
        with self.assertRaises(TimeoutError):
            self.execute(prepared, driver)
        self.assertEqual(driver.quit_count, 1)

    def test_missing_reviewed_input_aborts_preflight_before_any_typing(self):
        prepared = self.prepare()
        driver = DemoDriver(prepared)
        driver.elements[FORM + ORDER[-1]] = []
        with self.assertRaises(TimeoutError):
            self.execute(prepared, driver)
        self.assertFalse(any(action[0] == 'send_keys' for action in driver.actions))
        self.assertEqual([driver.elements[FORM + selector][0].value for selector in ORDER[:-1]],
                         driver.original_values[:-1])

    def test_readonly_first_control_never_receives_input(self):
        prepared = self.prepare()
        driver = DemoDriver(prepared, [''] * len(ORDER))
        driver.elements[FORM + ORDER[0]][0].attributes['readOnly'] = True
        with self.assertRaises(RuntimeError):
            self.execute(prepared, driver)
        self.assertFalse(any(action[0] in {'send_keys', 'clear'} for action in driver.actions))
        self.assertEqual(driver.quit_count, 1)

    def test_hidden_or_duplicate_control_aborts_before_any_typing(self):
        prepared = self.prepare()
        for defect in ('hidden', 'duplicate'):
            with self.subTest(defect=defect):
                driver = DemoDriver(prepared, [''] * len(ORDER))
                selector = FORM + ORDER[-1]
                if defect == 'hidden':
                    driver.elements[selector][0].shown = False
                else:
                    driver.elements[selector].append(FakeElement(driver, selector, value=''))
                with self.assertRaises(TimeoutError):
                    self.execute(prepared, driver)
                self.assertFalse(any(action[0] in {'send_keys', 'clear'} for action in driver.actions))
                self.assertEqual(driver.quit_count, 1)

    def test_click_time_value_change_never_overwrites_the_new_value(self):
        prepared = self.prepare()
        driver = DemoDriver(prepared, [''] * len(ORDER))
        first = driver.elements[FORM + ORDER[0]][0]
        first.after_click = lambda: setattr(first, 'value', 'Synthetic concurrent value')
        with self.assertRaises(RuntimeError):
            self.execute(prepared, driver)
        self.assertEqual(first.value, 'Synthetic concurrent value')
        self.assertFalse(any(action[0] in {'send_keys', 'clear'} for action in driver.actions))

    def test_current_private_values_do_not_enter_compiled_source_or_prepared_artifacts(self):
        prepared = self.prepare()
        code = compile_code(prepared['scenario'], prepared['contract'])
        initial_artifacts = encoded(prepared)
        values = ['SYNTHETIC-PRIVATE-EXISTING-' + str(index) for index in range(len(ORDER))]
        driver = DemoDriver(prepared, values)
        self.execute(prepared, driver)
        self.assertEqual(encoded(prepared), initial_artifacts)
        self.assertEqual(compile_code(prepared['scenario'], prepared['contract']), code)
        for private_value in values:
            self.assertNotIn(private_value, code)
            self.assertNotIn(private_value.encode('utf-8'), initial_artifacts)

    def test_recorded_before_and_after_checkpoints_represent_complete_forms(self):
        prepared = self.prepare()
        phases = {row['phase']: row['order'] for row in prepared['remediation_provenance']['supplemental_steps']
                  if row['phase'] in {'PREFLIGHT', 'FILLED_FORM'}}
        self.assertEqual(prepared['scenario']['screenshot_checkpoints'],
                         dict(before=phases['PREFLIGHT'], after=phases['FILLED_FORM']))
        driver, _ = self.execute(prepared)
        captures = [action for action in driver.actions if action[0] == 'capture']
        self.assertEqual(captures, [('capture', 'before'), ('capture', 'after')])

    def test_date_control_has_no_action_or_expectation_that_changes_it(self):
        prepared = self.prepare()
        self.assertEqual(prepared['remediation_provenance']['unchanged_controls'], ['#personal-birth-date'])
        self.assertNotIn('personal-birth-date', json.dumps(prepared['scenario']['steps']))
        self.assertNotIn('personal-birth-date', json.dumps(prepared['contract']))

    def test_other_business_bindings_never_enter_the_supplement(self):
        for name in ('BU05', 'BU07', 'BU09', 'BU12', 'BU13', 'BU14', 'BU17', 'BU20'):
            source = deepcopy(self.rows[name])
            specs = m03_bindings.describe(source)['parameters']
            params = {spec['name']: '문서' if spec['type'] == 'select' else
                      '2026-11-16' if spec['type'] == 'date' else 'KTL-synthetic-new-value' for spec in specs}
            with self.subTest(business_unit_id=name), patch.object(
                    bu01_input_demo, 'extend', side_effect=AssertionError('Only BU01 may enter supplemental input')):
                prepared = m03_bindings.prepare(source, params)
            self.assertNotIn('USER_REQUESTED_BU01_INPUT_DEMO', json.dumps(prepared))
            self.assertEqual(source, self.rows[name])

    def test_compiler_preserves_identity_and_never_calls_llm_or_browser_when_preparing(self):
        with patch('socket.socket', side_effect=AssertionError('No network')), patch(
                'subprocess.Popen', side_effect=AssertionError('No browser or model')):
            prepared = self.prepare()
            code = compile_code(prepared['scenario'], prepared['contract'])
        tree = ast.parse(code)
        constants = {target.id: node.value.value for node in tree.body if isinstance(node, ast.Assign)
                     and isinstance(node.value, ast.Constant) for target in node.targets if isinstance(target, ast.Name)}
        self.assertEqual(constants['SCENARIO_ID'], self.rows['BU01']['scenario_id'])
        self.assertFalse(constants['GENERATED_BY_LLM'])
        self.assertIn('element.send_keys', code)

    def test_registration_archives_supplement_separately_from_original_m03(self):
        with tempfile.TemporaryDirectory(prefix='ktl-bu01-input-demo-') as directory:
            root = Path(directory).resolve()
            config = dict(targets={'M04': 90}, adapters={}, m03={}, m04={}, m07={}, integration_datasets={})
            (root / 'backend').mkdir()
            (root / 'backend/config.json').write_bytes(encoded(config))
            run_id = 'DEV-M03-20261116T000000-0123456789ab'
            source = deepcopy(self.rows['BU01'])
            folder = root / 'results/development' / run_id
            folder.mkdir(parents=True)
            payload = encoded(dict(run_mode='DEVELOPMENT', scenarios=[source]))
            (folder / 'received_payload.json').write_bytes(payload)
            (folder / 'result.json').write_bytes(encoded(dict(run_id=run_id, metric_id='M03',
                run_mode='DEVELOPMENT', status='COMPLETED', score=90, official_pass=None, details={})))
            session = RuntimeSession()
            session.claim('RESULT', run_id)
            manager = M04Manager(root, lambda: config, session=session)
            with patch('subprocess.Popen', side_effect=AssertionError('No execution during preparation')), patch(
                    'urllib.request.urlopen', side_effect=AssertionError('No provider or business HTTP')):
                metadata = manager.prepare_m03(dict(m03_run_id=run_id, scenario_id=source['scenario_id'],
                    source_scenario_sha256=sha(encoded(source)), parameters={}))['script']
                manager._script(metadata['script_id'])
            script_dir = manager.script_directory / metadata['script_id']
            self.assertEqual((folder / 'received_payload.json').read_bytes(), payload)
            self.assertEqual((script_dir / 'source_scenario.json').read_bytes(), encoded(source))
            execution = json.loads((script_dir / 'execution_scenario.json').read_bytes())
            proof_raw = (script_dir / 'm03_compilation.json').read_bytes()
            proof = json.loads(proof_raw)
            self.assertEqual(len(execution['steps']), 18)
            self.assertEqual(proof['remediation_provenance'], self.prepare()['remediation_provenance'])
            self.assertEqual(proof['source_mapping'], self.prepare()['source_mapping'])
            self.assertEqual(metadata['m03_compilation_sha256'], sha(proof_raw))
            self.assertFalse(metadata['generated_by_llm'])


if __name__ == '__main__':
    unittest.main()
