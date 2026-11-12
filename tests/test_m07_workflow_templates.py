"""Synthetic template execution; no real browser, business API or LLM is called."""
import ast
from contextlib import contextmanager
from copy import deepcopy
import unittest
from unittest.mock import patch

from backend.m04.checks import prepare_contract
from backend.m07 import workflow_templates as templates


VALUES = dict(date='2028-02-29', title='SYNTHETIC UNIQUE REPORT', description='SYNTHETIC saved content',
              contact_name='SYNTHETIC Person', company='SYNTHETIC Unique Company',
              phone='010-1234-5678', email='synthetic@example.invalid', lookup_title='')
WORKFLOWS = ['CU03', 'CU04', 'CU05', 'CU06', 'CU07', 'CU08', 'CU09', 'CU10']


class Element:
    def __init__(self, driver, kind, value=None):
        self.driver, self.kind, self.value = driver, kind, value

    @property
    def text(self):
        if self.kind == 'report-button':
            return self.driver.display_title
        if self.kind == 'table':
            return 'SYNTHETIC TABLE'
        return self.value or ''

    def get_attribute(self, name):
        if name == 'aria-busy':
            return 'false'
        if name == 'value':
            return self.value
        raise AssertionError('Unexpected synthetic attribute')

    def is_displayed(self):
        return True

    def find_elements(self, by, selector):
        return [Element(self.driver, 'card-button')] if selector == '.business-card-table__title button' else []

    def find_element(self, by, selector):
        if selector == '.business-card-table__title button':
            return Element(self.driver, 'card-button')
        if selector == 'td:nth-of-type(3)':
            return Element(self.driver, 'text', self.driver.saved['company'])
        raise AssertionError('Unexpected synthetic row field')

    def click(self):
        if self.kind not in {'report-button', 'card-button'}:
            raise AssertionError('Unexpected synthetic native click')
        self.driver.actions.append('open-detail')
        self.driver.modal = 'detail'


class Driver:
    def __init__(self, values, data, *, empty=False, prefilled=False, wrong_saved=None, delayed=False):
        self.values, self.data = dict(values), data
        self.has_record = not empty
        self.saved = dict(values)
        self.fields = {}
        self.prefilled, self.wrong_saved, self.delayed = prefilled, wrong_saved, delayed
        self.modal, self.message = None, False
        self.actions, self.captures, self.steps = [], [], []
        self.reads = {}
        self.current_step = None

    @property
    def display_title(self):
        return '[' + self.saved['date'] + '] ' + self.saved['title']

    def get(self, url):
        assert url == self.data['target_url']
        self.actions.append('open-page')

    def refresh(self):
        self.actions.append('refresh')
        self.modal = None

    def find_elements(self, by, selector):
        if selector == self.data.get('report_buttons'):
            return [Element(self, 'report-button')] if self.has_record else []
        if selector == self.data.get('card_rows'):
            return [Element(self, 'card-row')] if self.has_record else []
        raise AssertionError('Unexpected synthetic find_elements: ' + selector)

    def one(self, selector):
        if selector == self.data['list_selector']:
            if self.delayed and not self.reads.get('table'):
                self.reads['table'] = 1
                return False
            return Element(self, 'table')
        inputs = {'title_input': 'title', 'content_input': 'description', 'company_input': 'company',
                  'name_input': 'contact_name', 'phone_input': 'phone', 'email_input': 'email', 'note_input': 'description'}
        for key, value in inputs.items():
            if selector == self.data.get(key):
                return Element(self, 'input', self.fields.get(value, '')) if self.modal == 'create' else False
        if selector == self.data.get('category_input'):
            return Element(self, 'input', 'IT / 정보통신')
        if selector == self.data.get('form_heading'):
            return Element(self, 'text', self.data.get('form_heading_text', '명함 등록')) if self.modal == 'create' else False
        if selector == self.data.get('first_button'):
            return Element(self, 'report-button' if 'report_buttons' in self.data else 'card-button') if self.has_record else False
        if selector == self.data.get('first_company'):
            return Element(self, 'text', self.saved['company']) if self.has_record else False
        if selector == self.data.get('date_button'):
            return Element(self, 'text', self.fields.get('date', self.values['date']).replace('-', '.') + ' (화)')
        if selector == self.data.get('detail_heading'):
            return Element(self, 'text', self.data.get('detail_heading_text', '명함 정보 상세')) if self.modal == 'detail' else False
        if selector == self.data.get('message_text'):
            if not self.message:
                return False
            if self.delayed and not self.reads.get('message'):
                self.reads['message'] = 1
                return False
            return Element(self, 'text', self.data.get('success_message', '명함 정보가 등록되었습니다.'))
        outputs = {'saved_title': 'title', 'saved_content': 'description', 'saved_date': 'date',
                   'saved_company': 'company', 'saved_name': 'contact_name', 'saved_phone': 'phone',
                   'saved_email': 'email', 'saved_note': 'description'}
        for key, value in outputs.items():
            if selector != self.data.get(key):
                continue
            if self.modal != 'detail':
                return False
            if self.delayed and not self.reads.get(key):
                self.reads[key] = 1
                return False
            observed = 'SYNTHETIC WRONG SAVED VALUE' if value == self.wrong_saved else self.saved[value]
            if key == 'saved_title':
                observed = self.display_title
            if key in {'saved_email', 'saved_note'}:
                observed = observed or '-'
            return Element(self, 'text', observed)
        raise AssertionError('Unexpected synthetic one: ' + selector)

    def read(self, selector):
        element = self.one(selector)
        return element.text.strip() if element else None

    def click(self, selector):
        if selector == self.data['register']:
            self.actions.append('new-form')
            self.modal = 'create'
            self.fields = {'title': 'SYNTHETIC PREFILLED', 'company': 'SYNTHETIC PREFILLED'} if self.prefilled else {}
        elif selector == self.data['save']:
            self.actions.append('save')
            self.saved.update(self.fields)
            self.has_record, self.message, self.modal = True, True, None
        elif selector == self.data['message_confirm']:
            self.actions.append('confirm-message')
            self.message = False
        elif selector == self.data['detail_close']:
            self.actions.append('close-detail')
            self.modal = None
        elif selector == self.data['first_button']:
            self.one(selector).click()
        else:
            raise AssertionError('Unexpected synthetic click')

    def fill(self, selector, value):
        for key, field in {'title_input': 'title', 'content_input': 'description', 'company_input': 'company',
                           'name_input': 'contact_name', 'phone_input': 'phone', 'email_input': 'email',
                           'note_input': 'description'}.items():
            if selector == self.data.get(key):
                self.fields[field] = value
                self.actions.append('input-' + field)
                return
        raise AssertionError('Unexpected synthetic fill')

    def closed(self, selector):
        return ((selector == self.data['form_modal'] and self.modal != 'create')
                or (selector == self.data['detail_modal'] and self.modal != 'detail')
                or (selector == self.data['message_modal'] and not self.message))

    def select_date(self, selector, value):
        assert selector == self.data['date_button'] and self.modal == 'create'
        self.fields['date'] = value
        self.actions.append('select-date')

    @contextmanager
    def business_step(self, order):
        self.current_step = order
        self.steps.append(order)
        try:
            yield
        finally:
            self.current_step = None

    def capture(self, phase):
        self.captures.append(dict(phase=phase, order=self.current_step, modal=self.modal, fields=dict(self.fields)))


class Wait:
    def until(self, predicate):
        for _ in range(4):
            value = predicate(None)
            if value:
                return value
        raise TimeoutError('Synthetic state did not become ready')


class PreparedWorkflowTemplateTests(unittest.TestCase):
    def run_body(self, identity, values=None, **options):
        values = VALUES if values is None else values
        template = templates.build(identity, values, 'SYNTHETIC-' + identity)
        data = dict(values, **template['data'])
        driver = Driver(values, data, **options)
        namespace = dict(DATA=data, driver=driver, wait=Wait(), bootstrap=object(), one=driver.one,
                         read=driver.read, click=driver.click, native=lambda element: element.click(),
                         fill=driver.fill, closed=driver.closed, select_date=driver.select_date,
                         business_step=driver.business_step, capture_evidence=driver.capture,
                         remove_session_bootstrap=lambda *_: driver.actions.append('remove-bootstrap'))
        failure = None
        try:
            exec(compile(template['body'], '<synthetic-workflow>', 'exec'), namespace)
        except Exception as error:
            failure = error
        return template, driver, failure

    def test_each_template_is_pure_compiles_and_has_a_complete_typed_contract(self):
        original = deepcopy(VALUES)
        with patch('socket.create_connection', side_effect=AssertionError('No template network')), \
                patch('subprocess.Popen', side_effect=AssertionError('No template browser')):
            for identity in WORKFLOWS:
                with self.subTest(workflow=identity):
                    template = templates.build(identity, VALUES, 'SYNTHETIC-' + identity)
                    tree = ast.parse(template['body'])
                    scenario = dict(scenario_id='SYNTHETIC-' + identity, steps=template['steps'],
                                    execution_contract=template['contract'])
                    self.assertEqual(prepare_contract(scenario), template['contract'])
                    blocks = [node for node in tree.body if isinstance(node, ast.With)]
                    self.assertEqual([ast.literal_eval(node.items[0].context_expr.args[0]) for node in blocks],
                                     list(range(1, len(template['steps']) + 1)))
                    self.assertTrue(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))
                    self.assertNotIn('.post(', template['body'])
                    self.assertNotIn('openai', template['body'].lower())
                    self.assertEqual(template['body'].count('remove_session_bootstrap(driver, bootstrap)'), 1)
        self.assertEqual(VALUES, original)

    def test_all_eight_bodies_execute_their_real_action_and_verification_paths(self):
        for identity in WORKFLOWS:
            with self.subTest(workflow=identity):
                template, driver, failure = self.run_body(identity)
                self.assertIsNone(failure, repr(failure))
                self.assertEqual(driver.steps, list(range(1, len(template['steps']) + 1)))
                self.assertEqual([(record['phase'], record['order']) for record in driver.captures],
                                 list(template['checkpoints'].items()))
                self.assertEqual(driver.actions.count('remove-bootstrap'), 1)
                self.assertEqual(driver.actions.count('open-detail'), 1)
                self.assertIsNone(driver.modal)
                if identity in {'CU04', 'CU06', 'CU08', 'CU10'}:
                    self.assertEqual(driver.actions.count('save'), 1)
                    self.assertEqual(driver.actions.count('refresh'), 1)
                    self.assertEqual(driver.captures[0]['modal'], 'create')
                    self.assertEqual(driver.captures[0]['fields'], {})
                    self.assertEqual(driver.captures[1]['modal'], 'detail')
                else:
                    self.assertNotIn('save', driver.actions)
                    self.assertNotIn('new-form', driver.actions)

    def test_empty_lookup_never_passes_or_silently_creates_a_record(self):
        for identity in ('CU03', 'CU05', 'CU07', 'CU09'):
            with self.subTest(workflow=identity):
                _, driver, failure = self.run_body(identity, empty=True)
                self.assertIsInstance(failure, TimeoutError)
                self.assertNotIn('save', driver.actions)
                self.assertNotIn('open-detail', driver.actions)
                self.assertEqual(driver.captures, [])

    def test_prefilled_new_forms_fail_before_clearing_or_saving(self):
        for identity in ('CU04', 'CU06', 'CU08', 'CU10'):
            with self.subTest(workflow=identity):
                _, driver, failure = self.run_body(identity, prefilled=True)
                self.assertIsInstance(failure, AssertionError)
                self.assertNotIn('save', driver.actions)
                self.assertFalse(any(action.startswith('input-') for action in driver.actions))
                self.assertEqual(driver.captures, [])

    def test_changed_persisted_content_or_name_cannot_be_reported_as_success(self):
        for identity, wrong in (('CU04', 'description'), ('CU06', 'date'), ('CU08', 'description'),
                                ('CU10', 'contact_name'), ('CU10', 'phone'), ('CU10', 'email')):
            with self.subTest(workflow=identity, field=wrong):
                _, driver, failure = self.run_body(identity, wrong_saved=wrong)
                self.assertIsInstance(failure, TimeoutError)
                self.assertEqual(driver.actions.count('save'), 1)
                self.assertEqual([record['phase'] for record in driver.captures], ['before'])

    def test_late_table_message_and_detail_mounts_are_polled(self):
        for identity in WORKFLOWS:
            with self.subTest(workflow=identity):
                _, driver, failure = self.run_body(identity, delayed=True)
                self.assertIsNone(failure, repr(failure))
                self.assertEqual(driver.reads['table'], 1)

    def test_optional_lookup_expectation_never_falls_back_to_a_different_record(self):
        for identity in ('CU03', 'CU05', 'CU07', 'CU09'):
            with self.subTest(workflow=identity):
                _, driver, failure = self.run_body(identity, dict(VALUES, lookup_title='SYNTHETIC DIFFERENT EXPECTATION'))
                self.assertIsInstance(failure, AssertionError)
                self.assertNotIn('open-detail', driver.actions)

    def test_unsupported_workflow_fails_instead_of_inventing_a_template(self):
        with self.assertRaises(ValueError):
            templates.build('CU99', VALUES, 'SYNTHETIC-CU99')


if __name__ == '__main__':
    unittest.main()
