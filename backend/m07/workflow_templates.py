"""Prepared report/card UI automation, based on the deployed RBEM components.

Preparation is pure: these builders neither call an LLM nor contact the target.
The caller supplies a Chrome/login launcher and records PREPARED provenance.
"""
from copy import deepcopy


ORIGIN = 'https://rainbowlab.ai.kr'
REPORT_TABLE = '.work-report-page .work-report-table'
REPORT_FIRST = REPORT_TABLE + ' tbody tr:first-child .work-report-table__title button'
REPORT_MODAL = '.work-report-form-modal__panel'
REPORT_TITLE = '#daily-report-create-title-input'
REPORT_CONTENT = '#daily-report-create-content-input'
REPORT_DETAIL = '.work-report-detail-modal__panel'
REPORT_DETAIL_TITLE = REPORT_DETAIL + ' .work-report-detail-modal__meta dd:nth-of-type(5)'
REPORT_DETAIL_DATE = REPORT_DETAIL + ' .work-report-detail-modal__meta dd:nth-of-type(1)'
REPORT_DETAIL_CONTENT = REPORT_DETAIL + ' .work-report-detail-modal__content'
REGISTER = '.work-report-page__register'
DATE_BUTTON = '.work-report-form-modal__date-button'
SAVE = '.work-report-form-modal__submit'
MESSAGE = '.work-report-message-modal'
MESSAGE_CONFIRM = '.work-report-message-modal__button'
CARD_TABLE = '.business-card-page .business-card-table'
CARD_FIRST = CARD_TABLE + ' tbody tr:first-child .business-card-table__title button'
CARD_FIRST_COMPANY = CARD_TABLE + ' tbody tr:first-child td:nth-of-type(3)'
CARD_MODAL = '.business-card-form-modal'
CARD_DETAIL = '.business-card-detail-modal'
CARD_CATEGORY = CARD_MODAL + ' .business-card-form-modal__section:nth-of-type(1) select'


def _card_input(section, label):
    return (CARD_MODAL + f' .business-card-form-modal__section:nth-of-type({section})'
            + f' label:nth-of-type({label}) input')


CARD_COMPANY = _card_input(1, 2)
CARD_NAME = _card_input(1, 3)
CARD_PHONE = _card_input(2, 1)
CARD_EMAIL = _card_input(2, 2)
CARD_NOTE = CARD_MODAL + ' .business-card-form-modal__section:nth-of-type(3) textarea'


def _card_detail(section, field):
    return (CARD_DETAIL + f' .business-card-detail-modal__section:nth-of-type({section})'
            + f' .business-card-detail-modal__grid > div:nth-of-type({field}) > span')


CARD_SAVED_COMPANY = _card_detail(1, 1)
CARD_SAVED_NAME = _card_detail(1, 3)
CARD_SAVED_PHONE = _card_detail(2, 1)
CARD_SAVED_EMAIL = _card_detail(2, 2)
CARD_SAVED_NOTE = _card_detail(3, 1)
UI_SOURCES = [
    dict(url=ORIGIN + '/assets/MyPage-DXxFGEX1.js',
         sha256='b58283503c32781c8ad56c02a7b508150de2b64b9c10a5ff72aee0f9daca10fa'),
    dict(url=ORIGIN + '/assets/DailyReportCreateModal-DftckkI5.js',
         sha256='e7f7dd9e4c074c2c8eaecd1ced040491f3a9e3988d5e83a315a9460b52b47f82'),
    dict(url=ORIGIN + '/assets/BusinessCardManagementPage-DLuhJlYc.js',
         sha256='54746d297ca155a58e0ee9cf4e1393d50bb93cd591e35e2746828d798046beed'),
]


def _css(selector):
    return dict(by='css selector', value=selector)


def _check(kind, selector, expected=None):
    result = dict(kind=kind, target=_css(selector))
    if kind == 'nonempty':
        result['property'] = 'text'
    else:
        result['expected'] = expected
    return result


def _pack(scenario_id, definitions, body, data, checkpoints):
    steps, checks = [], []
    for order, (action, target, expected, conditions) in enumerate(definitions, 1):
        step = dict(order=order, action=action, target=target, expected_result=expected)
        if action == 'open':
            step['url'] = target
        steps.append(step)
        checks.append(dict(order=order, action=action,
                           target=dict(url=target) if action == 'open' else _css(target),
                           checks=conditions))
    return dict(steps=steps, contract=dict(version=1, scenario_id=scenario_id, steps=checks),
                body=body.strip() + '\n', data=dict(data, ui_sources=deepcopy(UI_SOURCES)),
                checkpoints=checkpoints)


REPORT_COMMON = r'''
def report_ready():
    table = one(DATA['list_selector'])
    return table if table and table.get_attribute('aria-busy') == 'false' else False


def report_buttons():
    return [item for item in driver.find_elements('css selector', DATA['report_buttons']) if item.is_displayed()]


def assert_no_report_message():
    assert closed(DATA['message_modal']), '보고서 요청의 오류 또는 미확인 메시지가 있습니다.'
'''


REPORT_LOOKUP = r'''
with business_step(1):
    driver.get(DATA['target_url'])
    assert wait.until(lambda _: report_ready())
    remove_session_bootstrap(driver, bootstrap)
    assert_no_report_message()
    assert wait.until(lambda _: report_buttons()), '조회할 기존 보고서가 없습니다.'
    capture_evidence('before')

with business_step(2):
    selected_title = wait.until(lambda _: read(DATA['first_button']))
    assert selected_title.strip(), '기존 보고서 제목이 비어 있습니다.'
    if DATA['lookup_title']:
        assert DATA['lookup_title'] in selected_title, '첫 보고서가 지정한 조회 기대 제목과 다릅니다.'
    click(DATA['first_button'])
    assert wait.until(lambda _: read(DATA['detail_heading']) == DATA['detail_heading_text'])
    assert wait.until(lambda _: read(DATA['saved_title']) == selected_title)

with business_step(3):
    assert read(DATA['saved_title']) == selected_title
    assert wait.until(lambda _: (read(DATA['saved_content']) or '').strip()), '기존 보고서 상세 내용이 비어 있습니다.'
    assert wait.until(lambda _: (read(DATA['saved_date']) or '').strip()), '기존 보고서 업무일자가 비어 있습니다.'
    capture_evidence('after')

with business_step(4):
    click(DATA['detail_close'])
    assert wait.until(lambda _: closed(DATA['detail_modal']))
    assert one(DATA['list_selector'])
'''


REPORT_CREATE = r'''
with business_step(1):
    driver.get(DATA['target_url'])
    assert wait.until(lambda _: report_ready())
    remove_session_bootstrap(driver, bootstrap)
    assert_no_report_message()

with business_step(2):
    click(DATA['register'])
    assert wait.until(lambda _: read(DATA['form_heading']) == DATA['form_heading_text'])
    assert one(DATA['title_input']).get_attribute('value') == ''
    assert one(DATA['content_input']).get_attribute('value') == ''
    capture_evidence('before')

with business_step(3):
    select_date(DATA['date_button'], DATA['date'])
    assert DATA['date'].replace('-', '.') in (read(DATA['date_button']) or '')

with business_step(4):
    fill(DATA['title_input'], DATA['title'])
    fill(DATA['content_input'], DATA['description'])
    assert one(DATA['title_input']).get_attribute('value') == DATA['title']
    assert one(DATA['content_input']).get_attribute('value') == DATA['description']

with business_step(5):
    click(DATA['save'])
    assert wait.until(lambda _: closed(DATA['form_modal']))
    assert wait.until(lambda _: DATA['success_message'] in (read(DATA['message_text']) or ''))

with business_step(6):
    click(DATA['message_confirm'])
    assert wait.until(lambda _: closed(DATA['message_modal']))
    driver.refresh()
    assert wait.until(lambda _: report_ready())
    assert_no_report_message()
    matches = wait.until(lambda _: [item for item in report_buttons() if DATA['title'] in item.text])
    assert len(matches) == 1, '등록한 보고서를 재조회하여 하나로 구별할 수 없습니다.'
    saved_title = matches[0].text.strip()
    native(matches[0])
    assert wait.until(lambda _: read(DATA['detail_heading']) == DATA['detail_heading_text'])
    assert wait.until(lambda _: read(DATA['saved_title']) == saved_title)
    assert wait.until(lambda _: read(DATA['saved_content']) == DATA['description'])
    assert wait.until(lambda _: read(DATA['saved_date']) == DATA['date'])
    capture_evidence('after')

with business_step(7):
    click(DATA['detail_close'])
    assert wait.until(lambda _: closed(DATA['detail_modal']))
    assert one(DATA['list_selector'])
'''


CARD_COMMON = r'''
def card_ready():
    table = one(DATA['list_selector'])
    return table if table and '불러오는 중입니다.' not in table.text else False


def card_rows():
    return [row for row in driver.find_elements('css selector', DATA['card_rows'])
            if row.is_displayed() and row.find_elements('css selector', '.business-card-table__title button')]


def assert_no_card_message():
    assert closed(DATA['message_modal']), '명함 요청의 오류 또는 미확인 메시지가 있습니다.'
'''


CARD_LOOKUP = r'''
with business_step(1):
    driver.get(DATA['target_url'])
    assert wait.until(lambda _: card_ready())
    remove_session_bootstrap(driver, bootstrap)
    assert_no_card_message()
    assert wait.until(lambda _: card_rows()), '조회할 기존 명함이 없습니다.'
    capture_evidence('before')

with business_step(2):
    selected_company = wait.until(lambda _: read(DATA['first_company']))
    assert selected_company.strip(), '기존 명함의 회사명이 비어 있습니다.'
    if DATA['lookup_title']:
        assert selected_company == DATA['lookup_title'], '첫 명함이 지정한 조회 기대 회사와 다릅니다.'
    click(DATA['first_button'])
    assert wait.until(lambda _: read(DATA['detail_heading']) == '명함 정보 상세')
    assert wait.until(lambda _: read(DATA['saved_company']) == selected_company)

with business_step(3):
    assert read(DATA['saved_company']) == selected_company
    assert wait.until(lambda _: (read(DATA['saved_name']) or '').strip()), '기존 명함의 상세 이름이 비어 있습니다.'
    assert wait.until(lambda _: (read(DATA['saved_phone']) or '').strip()), '기존 명함의 상세 전화번호가 비어 있습니다.'
    capture_evidence('after')

with business_step(4):
    click(DATA['detail_close'])
    assert wait.until(lambda _: closed(DATA['detail_modal']))
    assert one(DATA['list_selector'])
'''


CARD_CREATE = r'''
with business_step(1):
    driver.get(DATA['target_url'])
    assert wait.until(lambda _: card_ready())
    remove_session_bootstrap(driver, bootstrap)
    assert_no_card_message()

with business_step(2):
    click(DATA['register'])
    assert wait.until(lambda _: read(DATA['form_heading']) == '명함 등록')
    assert one(DATA['category_input']).get_attribute('value') == 'IT / 정보통신'
    for selector in (DATA['company_input'], DATA['name_input'], DATA['phone_input'], DATA['email_input'], DATA['note_input']):
        assert one(selector).get_attribute('value') == '', '명함 신규등록 필드가 비어 있어야 합니다.'
    capture_evidence('before')

with business_step(3):
    select_date(DATA['date_button'], DATA['date'])
    assert DATA['date'].replace('-', '.') in (read(DATA['date_button']) or '')

with business_step(4):
    for key, value in (('company_input', 'company'), ('name_input', 'contact_name'), ('phone_input', 'phone'),
                       ('email_input', 'email'), ('note_input', 'description')):
        fill(DATA[key], DATA[value])
        assert one(DATA[key]).get_attribute('value') == DATA[value]

with business_step(5):
    click(DATA['save'])
    assert wait.until(lambda _: closed(DATA['form_modal']))
    assert wait.until(lambda _: '명함 정보가 등록되었습니다.' in (read(DATA['message_text']) or ''))

with business_step(6):
    click(DATA['message_confirm'])
    assert wait.until(lambda _: closed(DATA['message_modal']))
    driver.refresh()
    assert wait.until(lambda _: card_ready())
    assert_no_card_message()
    matches = wait.until(lambda _: [row for row in card_rows()
                                    if row.find_element('css selector', 'td:nth-of-type(3)').text.strip() == DATA['company']])
    assert len(matches) == 1, '등록한 명함을 고유 회사명으로 구별할 수 없습니다.'
    native(matches[0].find_element('css selector', '.business-card-table__title button'))
    assert wait.until(lambda _: read(DATA['detail_heading']) == '명함 정보 상세')
    for key, value in (('saved_company', 'company'), ('saved_name', 'contact_name'), ('saved_phone', 'phone')):
        assert wait.until(lambda _: read(DATA[key]) == DATA[value])
    assert wait.until(lambda _: read(DATA['saved_email']) == (DATA['email'] or '-'))
    assert wait.until(lambda _: read(DATA['saved_note']) == (DATA['description'] or '-'))
    capture_evidence('after')

with business_step(7):
    click(DATA['detail_close'])
    assert wait.until(lambda _: closed(DATA['detail_modal']))
    assert one(DATA['list_selector'])
'''


def _report(workflow_id, values, scenario_id):
    create = workflow_id in {'CU04', 'CU06', 'CU08'}
    suffix = {'CU03': 'daily', 'CU04': 'daily', 'CU05': 'weekly', 'CU06': 'weekly',
              'CU07': 'monthly', 'CU08': 'monthly'}[workflow_id]
    label = {'daily': '일일업무', 'weekly': '주간업무', 'monthly': '월간업무'}[suffix]
    path = '/mypage/work/' + suffix
    data = dict(target_url=ORIGIN + path, list_selector=REPORT_TABLE,
                report_buttons=REPORT_TABLE + ' .work-report-table__title button', first_button=REPORT_FIRST,
                form_modal=REPORT_MODAL, form_heading='#daily-report-create-title', form_heading_text=label + ' 등록',
                title_input=REPORT_TITLE, content_input=REPORT_CONTENT, register=REGISTER,
                date_button=REPORT_MODAL + ' ' + DATE_BUTTON, save=REPORT_MODAL + ' ' + SAVE,
                detail_modal=REPORT_DETAIL, detail_heading='#work-report-detail-title', detail_heading_text=label + ' 내용',
                saved_title=REPORT_DETAIL_TITLE, saved_content=REPORT_DETAIL_CONTENT, saved_date=REPORT_DETAIL_DATE,
                detail_close=REPORT_DETAIL + ' button[aria-label="상세 닫기"]',
                message_modal=MESSAGE, message_text='#work-report-message', message_confirm=MESSAGE_CONFIRM,
                success_message=label + '가 저장되었습니다.', lookup_title=values.get('lookup_title', ''))
    visible = lambda target, expected=True: _check('visible', target, expected)
    start = ('open', data['target_url'], '업무 보고 목록을 정상 조회한다',
             [dict(kind='url_path', expected=path), visible(REPORT_TABLE), visible(MESSAGE, False)])
    if not create:
        definitions = [start,
            ('click', REPORT_FIRST, '첫 기존 보고서의 실제 상세창을 연다',
             [visible(REPORT_DETAIL), _check('text_equals', data['detail_heading'], data['detail_heading_text'])]),
            ('verify', REPORT_DETAIL, '선택한 보고서의 제목·업무일자·내용을 확인한다',
             [_check('nonempty', REPORT_DETAIL_TITLE), _check('nonempty', REPORT_DETAIL_DATE),
              _check('nonempty', REPORT_DETAIL_CONTENT)]),
            ('click', data['detail_close'], '상세창을 닫고 목록으로 돌아간다', [visible(REPORT_DETAIL, False), visible(REPORT_TABLE)])]
        return _pack(scenario_id, definitions, REPORT_COMMON + REPORT_LOOKUP, data, dict(before=1, after=3))
    definitions = [start,
        ('click', REGISTER, '빈 신규 업무 등록 화면을 확인한다',
         [visible(REPORT_MODAL), _check('text_equals', data['form_heading'], data['form_heading_text']),
          _check('value', REPORT_TITLE, ''), _check('value', REPORT_CONTENT, '')]),
        ('select', data['date_button'], '지정한 업무일자를 실제 달력에서 선택한다',
         [_check('text_contains', data['date_button'], values['date'].replace('-', '.'))]),
        ('input', REPORT_TITLE, '시험 제목과 내용을 실제 필드에 입력한다',
         [_check('value', REPORT_TITLE, values['title']), _check('value', REPORT_CONTENT, values['description'])]),
        ('submit', data['save'], '저장 버튼을 누르고 저장 성공 메시지를 확인한다',
         [visible(REPORT_MODAL, False), _check('text_contains', data['message_text'], data['success_message'])]),
        ('verify', REPORT_DETAIL, '새로고침 후 저장된 업무일자·제목·내용을 재조회한다',
         [_check('text_equals', REPORT_DETAIL_DATE, values['date']),
          _check('text_contains', REPORT_DETAIL_TITLE, values['title']),
          _check('text_equals', REPORT_DETAIL_CONTENT, values['description'])]),
        ('click', data['detail_close'], '저장된 상세창을 닫고 목록으로 돌아간다', [visible(REPORT_DETAIL, False), visible(REPORT_TABLE)])]
    return _pack(scenario_id, definitions, REPORT_COMMON + REPORT_CREATE, data, dict(before=2, after=6))


def _card(workflow_id, values, scenario_id):
    create = workflow_id == 'CU10'
    path = '/mypage/cards'
    data = dict(target_url=ORIGIN + path, list_selector=CARD_TABLE,
                card_rows=CARD_TABLE + ' tbody tr', first_button=CARD_FIRST, first_company=CARD_FIRST_COMPANY,
                form_modal=CARD_MODAL, form_heading='#business-card-form-title', register=REGISTER,
                category_input=CARD_CATEGORY, company_input=CARD_COMPANY, name_input=CARD_NAME,
                phone_input=CARD_PHONE, email_input=CARD_EMAIL, note_input=CARD_NOTE,
                date_button=CARD_MODAL + ' ' + DATE_BUTTON, save=CARD_MODAL + ' ' + SAVE,
                detail_modal=CARD_DETAIL, detail_heading='#business-card-detail-title',
                saved_company=CARD_SAVED_COMPANY, saved_name=CARD_SAVED_NAME, saved_phone=CARD_SAVED_PHONE,
                saved_email=CARD_SAVED_EMAIL, saved_note=CARD_SAVED_NOTE,
                detail_close=CARD_DETAIL + ' button[aria-label="명함 상세 닫기"]',
                message_modal=MESSAGE, message_text='#business-card-message', message_confirm=MESSAGE_CONFIRM,
                lookup_title=values.get('lookup_title', ''))
    visible = lambda target, expected=True: _check('visible', target, expected)
    start = ('open', data['target_url'], '명함 목록의 실제 조회 상태를 확인한다',
             [dict(kind='url_path', expected=path), visible(CARD_TABLE), visible(MESSAGE, False)])
    if not create:
        definitions = [start,
            ('click', CARD_FIRST, '첫 기존 명함의 상세창을 연다',
             [visible(CARD_DETAIL), _check('text_equals', data['detail_heading'], '명함 정보 상세')]),
            ('verify', CARD_DETAIL, '선택한 명함의 실제 회사명·이름·전화번호를 확인한다',
             [_check('nonempty', CARD_SAVED_COMPANY), _check('nonempty', CARD_SAVED_NAME), _check('nonempty', CARD_SAVED_PHONE)]),
            ('click', data['detail_close'], '명함 상세창을 닫고 목록으로 돌아간다', [visible(CARD_DETAIL, False), visible(CARD_TABLE)])]
        return _pack(scenario_id, definitions, CARD_COMMON + CARD_LOOKUP, data, dict(before=1, after=3))
    definitions = [start,
        ('click', REGISTER, '빈 명함 신규등록 필드와 기본 구분을 확인한다',
         [visible(CARD_MODAL), _check('text_equals', data['form_heading'], '명함 등록'),
          _check('value', CARD_CATEGORY, 'IT / 정보통신'), _check('value', CARD_COMPANY, ''),
          _check('value', CARD_NAME, ''), _check('value', CARD_PHONE, '')]),
        ('select', data['date_button'], '등록일을 실제 달력에서 선택한다',
         [_check('text_contains', data['date_button'], values['date'].replace('-', '.'))]),
        ('input', CARD_COMPANY, '시험 명함의 실제 필수 입력값을 채운다',
         [_check('value', selector, values[key]) for selector, key in
          ((CARD_COMPANY, 'company'), (CARD_NAME, 'contact_name'), (CARD_PHONE, 'phone'), (CARD_EMAIL, 'email'), (CARD_NOTE, 'description'))]),
        ('submit', data['save'], '저장 버튼을 누르고 명함 등록 성공 메시지를 확인한다',
         [visible(CARD_MODAL, False), _check('text_contains', data['message_text'], '명함 정보가 등록되었습니다.')]),
        ('verify', CARD_DETAIL, '새로고침 후 회사명·이름·전화번호·이메일·메모를 다시 확인한다',
         [_check('text_equals', selector, expected) for selector, expected in
          ((CARD_SAVED_COMPANY, values['company']), (CARD_SAVED_NAME, values['contact_name']),
           (CARD_SAVED_PHONE, values['phone']), (CARD_SAVED_EMAIL, values['email'] or '-'),
           (CARD_SAVED_NOTE, values['description'] or '-'))]),
        ('click', data['detail_close'], '등록된 명함의 상세창을 닫고 목록으로 돌아간다', [visible(CARD_DETAIL, False), visible(CARD_TABLE)])]
    return _pack(scenario_id, definitions, CARD_COMMON + CARD_CREATE, data, dict(before=2, after=6))


def build(workflow_id, values, scenario_id):
    if workflow_id in {'CU03', 'CU04', 'CU05', 'CU06', 'CU07', 'CU08'}:
        return _report(workflow_id, values, scenario_id)
    if workflow_id in {'CU09', 'CU10'}:
        return _card(workflow_id, values, scenario_id)
    raise ValueError('지원하는 보고서·명함 업무 ID가 필요합니다.')
