"""명시적인 PREPARED 출처를 갖는 CU01~CU10 개발용 Chrome 코드."""
import ast
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import uuid

from ..evaluators import require
from ..m04 import cu02
from ..m04.checks import prepare_contract, validate_source_data


VERSION = 'rbem-prepared-workflows-v1'
WORKFLOWS = [
    ('CU01', '일정 조회', '조회', ['일정관리', '일정이 존재하는 날짜 선택', '일정 내용 확인', '종료']),
    ('CU02', '일정 등록', '등록', list(cu02.PROCEDURES)),
    ('CU03', '일일보고 조회', '조회', ['업무관리', '일일보고', '기존 보고 조회', '종료']),
    ('CU04', '일일보고 작성', '등록', ['일일보고', '등록', '내용 입력', '저장', '완료 확인', '종료']),
    ('CU05', '주간보고 조회', '조회', ['업무관리', '주간보고', '기존 주간보고 선택/조회', '종료']),
    ('CU06', '주간보고 작성', '등록', ['주간보고', '등록', '대상 주차 선택', '내용 입력', '저장', '완료 확인']),
    ('CU07', '월간보고 조회', '조회', ['업무관리', '월간보고', '기존 월간보고 선택/조회', '종료']),
    ('CU08', '월간보고 작성', '등록', ['월간보고', '등록', '대상 월 선택', '내용 입력', '저장', '완료 확인']),
    ('CU09', '명함 상세조회', '조회', ['명함관리', '기존 명함 1건 선택', '상세 내용 확인', '종료']),
    ('CU10', '명함 등록', '등록', ['명함관리', '등록', '테스트 명함 정보 입력', '저장', '종료']),
]
FIELDS = [dict(name='date', label='시험 날짜', type='date', required=True),
          dict(name='title', label='신규 일정·보고 제목', type='text', required=True),
          dict(name='description', label='일정·보고 내용', type='textarea', required=True),
          dict(name='contact_name', label='명함 이름', type='text', required=True),
          dict(name='company', label='명함 회사명', type='text', required=True),
          dict(name='phone', label='명함 전화번호', type='text', required=True),
          dict(name='email', label='명함 이메일', type='email', required=False),
          dict(name='lookup_title', label='조회 첫 항목의 기대 제목·회사명 (선택)', type='text', required=False),
          dict(name='cases_per_workflow', label='업무당 코드 수', type='number', required=True)]


def defaults():
    now = datetime.now(timezone(timedelta(hours=9)))
    return dict(date=now.date().isoformat(), title='KTL 시험 ' + now.strftime('%m%d %H%M'),
                description='KTL 업무 자동화 개발 시험', contact_name='KTL 테스트', company='KTL 테스트 회사',
                phone='010-0000-0000', email='ktl-test@example.com', lookup_title='', cases_per_workflow=2)


def catalog(root):
    return dict(run_mode='DEVELOPMENT', browser='chrome', code_source='PREPARED', generated_by_llm=False,
                login_configured=cu02.login_configured(root), defaults=defaults(), parameter_fields=deepcopy(FIELDS),
                workflows=[dict(workflow_id=identity, name=name, type=kind, steps=list(steps), available=True,
                                notice='기존 첫 항목이 있어야 조회할 수 있습니다.' if kind == '조회'
                                else '검사 시 실제 시험 데이터가 등록됩니다.')
                           for identity, name, kind, steps in WORKFLOWS])


def parameters(value):
    require(isinstance(value, dict) and set(value) <= {field['name'] for field in FIELDS}, '지원하는 업무 입력값만 지정하세요.')
    result = dict(defaults(), **value)
    normalized = cu02.parameters({key: result[key] for key in ('date', 'title', 'description')} | {'browser': 'chrome'})
    result.update({key: normalized[key] for key in ('date', 'title', 'description')})
    require(len(result['title']) <= 90 and bool(result['description']), '신규 제목은 90자 이내, 업무 내용은 빈 값 없이 입력하세요.')
    for key, limit, required in [('contact_name', 45, True), ('company', 90, True), ('phone', 30, True),
                                  ('email', 120, False), ('lookup_title', 160, False)]:
        text = result[key]
        require(isinstance(text, str) and len(text.strip()) <= limit and (bool(text.strip()) or not required)
                and not any(ord(char) < 32 or ord(char) == 127 for char in text), '업무별 입력값의 형식과 길이를 확인하세요.')
        result[key] = text.strip()
    digits = re.sub(r'\D', '', result['phone'])
    require(len(digits) in {10, 11} and re.fullmatch(r'[0-9+() -]+', result['phone']), '전화번호는 숫자 10~11자리로 입력하세요.')
    lead = 2 if digits.startswith('02') else 3
    result['phone'] = digits[:lead] + '-' + digits[lead:-4] + '-' + digits[-4:]
    require(not result['email'] or re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', result['email']), '이메일 형식을 확인하세요.')
    require(type(result['cases_per_workflow']) is int and result['cases_per_workflow'] in {1, 2}, '업무당 코드 수는 1 또는 2입니다.')
    try:
        validate_source_data(result, strict_literals=True)
    except ValueError:
        require(False, '업무 입력에 인증정보나 비밀값을 넣을 수 없습니다.')
    return result


def shared_source():
    # Reuse the already tested login/bootstrap/native-action helpers in standalone
    # source. The final business try block is replaced, never executed at prepare.
    tree = ast.parse(cu02.SCRIPT)
    entry = next(node for node in tree.body if isinstance(node, ast.Try))
    source = '\n'.join(cu02.SCRIPT.splitlines()[:entry.lineno - 1]) + '\n' + HELPERS
    return source.replace("Authorization:'Bearer '+token", "Authorization:['Bearer',token].join(' ')")


def prepared(workflow_id, values):
    if workflow_id == 'CU02':
        item = cu02.prepare({key: values[key] for key in ('date', 'title', 'description')} | {'browser': 'chrome'})
        item['code'] = item['code'].replace("webdriver.EdgeOptions() if DATA['browser'] == 'edge' else webdriver.ChromeOptions()", 'webdriver.ChromeOptions()')
        item['code'] = item['code'].replace("webdriver.Edge(options=options) if DATA['browser'] == 'edge' else webdriver.Chrome(options=options)", 'webdriver.Chrome(options=options)')
        item['code'] = item['code'].replace("Authorization:'Bearer '+token", "Authorization:['Bearer',token].join(' ')")
        item['scenario'].update(code_source='PREPARED', generated_by_llm=False)
        return item
    identity = workflow_id + '-PREPARED-' + hashlib.sha256(cu02.encoded(values)).hexdigest()[:12]
    if workflow_id == 'CU01':
        template = schedule_query(values, identity)
    else:
        from .workflow_templates import build
        template = build(workflow_id, values, identity)
    name = next(name for code, name, _, _ in WORKFLOWS if code == workflow_id)
    scenario = dict(scenario_id=identity, scenario_name=name, workflow_id=workflow_id, business_unit_id=workflow_id,
                    steps=template['steps'], execution_contract=template['contract'], status='SUCCESS',
                    screenshot_checkpoints=template['checkpoints'], run_mode='DEVELOPMENT', official=False,
                    code_source='PREPARED', generated_by_llm=False)
    contract = prepare_contract(scenario)
    scenario['execution_contract'] = contract
    data = dict(values, browser='chrome', auth_url=cu02.TARGET_ORIGIN + '/api/auth/login', target_origin=cu02.TARGET_ORIGIN,
                **template['data'])
    code = 'SCENARIO_ID = ' + repr(identity) + '\nDATA_JSON = ' + repr(json.dumps(data, ensure_ascii=False)) + '\n'
    code += shared_source() + '\ntry:\n' + LAUNCHER
    code += '\n'.join('    ' + line if line else '' for line in template['body'].splitlines())
    code += '\nfinally:\n    if driver is not None:\n        driver.quit()\n'
    ast.parse(code)
    return dict(code=code, scenario=scenario, contract=contract, parameters=deepcopy(values),
                definition=dict(workflow_id=workflow_id, version=VERSION, target_url=data['target_url']))


def prepare_batch(payload):
    require(isinstance(payload, dict) and set(payload) == {'workflow_ids', 'parameters'}, '업무 목록과 시험 입력값이 필요합니다.')
    ids = payload['workflow_ids']
    require(isinstance(ids, list) and 1 <= len(ids) <= 10 and all(isinstance(value, str) for value in ids)
            and len(set(ids)) == len(ids) and set(ids) <= {row[0] for row in WORKFLOWS}, 'CU01~CU10에서 서로 다른 업무를 선택하세요.')
    values = parameters(payload['parameters'])
    suffix = uuid.uuid4().hex[:8]
    output = []
    for workflow_id in ids:
        for number in range(1, values['cases_per_workflow'] + 1):
            item_values = deepcopy(values)
            for key in ('title', 'company'):
                item_values[key] += f' [{suffix}-{workflow_id}-{number}]'
            item = prepared(workflow_id, item_values)
            definition = dict(item['definition'], version=VERSION, code_source='PREPARED', generated_by_llm=False,
                              source_document_sha256=cu02.SOURCE_DOCUMENT_SHA256,
                              procedures=next(list(steps) for code, _, _, steps in WORKFLOWS if code == workflow_id),
                              screenshot_checkpoints=item['scenario'].get('screenshot_checkpoints'))
            item.update(case_number=number, source_files={'workflow_definition.json': cu02.encoded(definition),
                                                         'workflow_parameters.json': cu02.encoded(item_values)})
            output.append(item)
    return output


def schedule_query(values, identity):
    day = date.fromisoformat(values['date'])
    index = (day.replace(day=1).weekday() + 1) % 7 + day.day
    cell = cu02.CALENDAR + ' .monthly-calendar__grid > .monthly-calendar__cell:nth-child(' + str(index) + ')'
    event = cell + ' li.schedule-event:nth-child(1 of .schedule-event:not(.schedule-event--holiday)) button.schedule-event__title'
    css = lambda target: dict(by='css selector', value=target)
    same_title = dict(kind='text_equals_target', target=css(cu02.TITLE), property='value', other_target=css(event), other_property='text')
    definitions = [('open', cu02.TARGET_URL, '대상 날짜에 실제 일정이 있는지 확인',
                    [dict(kind='url_path', expected='/mypage/schedule'), dict(kind='nonempty', target=css(event), property='text')]),
                   ('click', event, '선택한 기존 일정의 상세창을 열기',
                    [dict(kind='visible', target=css(cu02.MODAL), expected=True), same_title]),
                   ('verify', cu02.TITLE, '목록 제목과 상세 제목이 같은지 확인', [same_title]),
                   ('click', cu02.MODAL + ' button[aria-label="닫기"]', '상세창 닫기',
                    [dict(kind='visible', target=css(cu02.MODAL), expected=False)])]
    steps = [dict(order=i, action=action, target=target, expected_result=expected) for i, (action, target, expected, _) in enumerate(definitions, 1)]
    contract = dict(version=1, scenario_id=identity, steps=[dict(order=i, action=action,
                    target={'url': target} if action == 'open' else css(target), checks=checks)
                    for i, (action, target, _, checks) in enumerate(definitions, 1)])
    return dict(steps=steps, contract=contract, checkpoints={'before': 1, 'after': 3},
                data=dict(target_url=cu02.TARGET_URL, calendar=cu02.CALENDAR, month=cu02.MONTH,
                          cell=cell, event_target=event, modal=cu02.MODAL, title_target=cu02.TITLE,
                          description_target=cu02.DESCRIPTION), body=SCHEDULE_QUERY)


HELPERS = r'''
import re

def native(element):
    driver.execute_script('arguments[0].scrollIntoView({block:"center",inline:"center",behavior:"instant"});', element)
    wait.until(lambda _: driver.execute_script('const e=arguments[0],r=e.getBoundingClientRect(),t=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return !!t&&(t===e||e.contains(t));', element))
    element.click()

def fill(selector, value):
    element = wait.until(lambda _: one(selector))
    native(element)
    element.send_keys(Keys.CONTROL, 'a')
    element.send_keys(Keys.BACKSPACE)
    if value:
        element.send_keys(value)
    assert wait.until(lambda _: one(selector).get_attribute('value') == value if one(selector) else False), '입력한 값이 일치하지 않습니다.'

def closed(selector):
    return not any(element.is_displayed() for element in driver.find_elements(By.CSS_SELECTOR, selector))

def select_date(button, desired):
    click(button)
    stamp = date.fromisoformat(desired)
    selector = '.work-date-calendar__month'
    def calendar_month():
        text = read(selector)
        numbers = re.findall(r'\d+', text or '')
        return (int(numbers[0]), int(numbers[1])) if len(numbers) == 2 else None
    current = wait.until(lambda _: calendar_month())
    distance = (stamp.year-current[0])*12 + stamp.month-current[1]
    assert abs(distance) <= 120, '현재 달력에서 10년 이내의 날짜를 선택하세요.'
    for _ in range(abs(distance)):
        previous = current
        click('.work-date-calendar button[aria-label="다음 달"]' if distance > 0 else '.work-date-calendar button[aria-label="이전 달"]')
        current = wait.until(lambda _: calendar_month() if calendar_month() != previous else False)
    click('.work-date-calendar button[aria-label="' + desired + '"]')
    assert wait.until(lambda _: closed('.work-date-calendar'))
    numbers = re.findall(r'\d+', read(button) or '')
    assert [int(part) for part in numbers] == [stamp.year, stamp.month, stamp.day], '선택한 날짜가 일치하지 않습니다.'
'''

LAUNCHER = '''    session = preauthenticate()
    print('시험 계정 인증 완료. 준비 코드를 Chrome에서 실행합니다.')
    options = webdriver.ChromeOptions()
    options.add_argument('--window-size=1440,1100')
    if os.environ.get('KTL_M04_HEADLESS', '1') != '0':
        options.add_argument('--headless=new')
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(40)
    wait = WebDriverWait(driver, 25)
    try:
        bootstrap = install_session(driver, session)
    finally:
        session.clear()
'''

SCHEDULE_QUERY = '''with business_step(1):
    driver.get(DATA['target_url'])
    wait.until(lambda _: one(DATA['calendar']))
    remove_session_bootstrap(driver, bootstrap)
    target_month()
    event = wait.until(lambda _: one(DATA['event_target']))
    assert event.text.strip(), '선택 날짜에 조회할 기존 일정이 필요합니다.'
    if DATA['lookup_title']:
        assert event.text.strip() == DATA['lookup_title'], '첫 기존 일정이 기대 제목과 다릅니다.'
    capture_evidence('before')
with business_step(2):
    click(DATA['event_target'])
    assert wait.until(lambda _: read(DATA['modal'] + ' h2') == '업무 내용')
    assert wait.until(lambda _: one(DATA['title_target']).get_attribute('value') == read(DATA['event_target']) if one(DATA['title_target']) else False)
with business_step(3):
    assert one(DATA['title_target']).get_attribute('value') == read(DATA['event_target'])
    assert isinstance(one(DATA['description_target']).get_attribute('value'), str)
    capture_evidence('after')
with business_step(4):
    click(DATA['modal'] + ' button[aria-label="닫기"]')
    assert wait.until(lambda _: closed(DATA['modal']))
'''
