"""CU02 일정 등록을 위한 개발용 고정 Selenium 실행 입력.

업무 정의와 새 시험값으로 코드를 준비한다. 준비 중에는 사이트를 호출하거나
브라우저를 실행하지 않으며 로그인 값은 실행 환경에서만 읽는다.
"""
import hashlib
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..evaluators import require


WORKFLOW_ID = 'CU02'
VERSION = 'cu02-schedule-registration-v3-state-evidence'
TARGET_ORIGIN = 'https://rainbowlab.ai.kr'
TARGET_URL = TARGET_ORIGIN + '/mypage/schedule'
PROCEDURES = ['일정관리', '날짜 선택', '일정 입력', '등록', '종료']
SOURCE_DOCUMENT_SHA256 = '8f0fb27bf28de7d39d221d71781c82fae5456dcdfb0750205024fcf85bcbef72'
CALENDAR = '.schedule-page .monthly-calendar'
MONTH = '.schedule-page .calendar-toolbar__month'
MODAL = 'form.schedule-modal__panel'
TITLE = '#schedule-title'
DESCRIPTION = '#schedule-description'
SUBMIT = 'form.schedule-modal__panel .schedule-modal__actions button[type="submit"]'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def default_browser():
    return 'chrome'


def login_configured(root):
    # 공개 응답과 보관 코드에는 인증값을 반환하지 않는다.
    from .runner import load_login_settings
    values = load_login_settings(Path(root) / '.env.local')
    return all(isinstance(values.get(name), str) and bool(values[name].strip())
               for name in ('KTL_M04_RBEM_USERNAME', 'KTL_M04_RBEM_PASSWORD'))


def workflow(root):
    now = datetime.now(timezone(timedelta(hours=9)))
    browser = default_browser()
    return dict(workflow_id=WORKFLOW_ID, name='일정 등록', steps=list(PROCEDURES), target_url=TARGET_URL,
                run_mode='DEVELOPMENT', login_configured=login_configured(root),
                browser_name='Microsoft Edge' if browser == 'edge' else 'Chrome',
                defaults=dict(date=now.date().isoformat(), title='KTL CU02 ' + now.strftime('%Y%m%d %H%M%S'),
                              description='KTL CU02 일정 등록 자동화 시험', browser=browser))


def parameters(payload):
    require(isinstance(payload, dict) and {'date', 'title', 'description'} <= set(payload)
            and set(payload) <= {'date', 'title', 'description', 'browser'}, '날짜·제목·내용과 실행 브라우저만 지정하세요.')
    day = payload.get('date')
    require(isinstance(day, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', day), '날짜는 YYYY-MM-DD 형식이어야 합니다.')
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        require(False, '실제로 존재하는 날짜를 선택하세요.')
    require(2000 <= parsed.year <= 2100, '시험 날짜는 2000년부터 2100년 사이로 선택하세요.')
    title, description = payload.get('title'), payload.get('description')
    require(isinstance(title, str) and 1 <= len(title.strip()) <= 120
            and not any(ord(char) < 32 or ord(char) == 127 for char in title), '일정 제목은 1~120자로 입력하세요.')
    require(isinstance(description, str) and len(description.strip()) <= 2000
            and not any((ord(char) < 32 and char not in '\n\r\t') or ord(char) == 127 for char in description),
            '일정 내용은 2000자 이내로 입력하세요.')
    browser = payload.get('browser', default_browser())
    require(isinstance(browser, str) and browser in {'chrome', 'edge'}, 'Chrome 또는 Microsoft Edge를 선택하세요.')
    result = dict(date=day, title=title.strip(), description=description.strip().replace('\r\n', '\n').replace('\r', '\n'), browser=browser)
    from .checks import validate_source_data
    try:
        validate_source_data(result, strict_literals=True)
    except ValueError:
        require(False, '시험 입력에는 인증정보나 비밀값을 넣을 수 없습니다.')
    return result


def prepare(payload):
    values = parameters(payload)
    day = date.fromisoformat(values['date'])
    index = (day.replace(day=1).weekday() + 1) % 7 + day.day
    cell = CALENDAR + ' .monthly-calendar__grid > .monthly-calendar__cell:nth-child(' + str(index) + ')'
    date_target = cell + ' .monthly-calendar__date-number'
    event_target = cell + ' button.schedule-event__title'
    identity = hashlib.sha256(encoded(values)).hexdigest()[:12]
    scenario_id = 'CU02-SCHEDULE-' + identity
    definition = dict(workflow_id=WORKFLOW_ID, version=VERSION, procedures=list(PROCEDURES),
                      source_document_sha256=SOURCE_DOCUMENT_SHA256, target_url=TARGET_URL,
                      calendar_cell=cell, date_target=date_target, event_target=event_target,
                      expected_states=dict(
                          before=dict(step_order=2, date=values['date'], modal_heading='업무 등록',
                                      fields={TITLE: '', DESCRIPTION: ''}),
                          after=dict(step_order=5, date=values['date'], reload_required=True,
                                     fields={TITLE: values['title'], DESCRIPTION: values['description']},
                                     matching_schedule_count=1)),
                      ui_sources=[dict(url=TARGET_ORIGIN + '/assets/SchedulePage-w3CoeEPW.js',
                                       sha256='c38b2e7f5f4db88bb827e423570eac523336484683358d56bd3a1127e24ef7da'),
                                  dict(url=TARGET_ORIGIN + '/assets/MyPage-DXxFGEX1.js',
                                       sha256='b58283503c32781c8ad56c02a7b508150de2b64b9c10a5ff72aee0f9daca10fa')])
    actions = [('open', TARGET_URL, '일정관리 화면과 대상 월을 확인한다'),
               ('click', date_target, '선택 날짜의 신규 업무 등록 창에서 제목과 내용이 비어 있는지 확인한다'),
               ('input', TITLE, '새 시험 제목과 내용이 입력되었는지 확인한다'),
               ('submit', SUBMIT, '등록 후 대상 날짜에 새 일정이 표시되는지 확인한다'),
               ('verify', event_target, '재조회 후 저장된 제목과 내용을 확인하고 창을 닫는다')]
    steps = [dict(order=i, action=action, target=target, expected_result=expected,
                  **({'url': target} if action == 'open' else {}))
             for i, (action, target, expected) in enumerate(actions, 1)]
    css = lambda value: dict(by='css selector', value=value)
    exact = lambda count: dict(kind='text_count', target=css(event_target), expected=values['title'], count=count)
    checks = [[dict(kind='url_path', expected='/mypage/schedule'), dict(kind='text_equals', target=css(MONTH), expected=day.strftime('%Y.%m')), exact(0)],
              [dict(kind='visible', target=css(MODAL), expected=True), dict(kind='text_equals', target=css(MODAL + ' h2'), expected='업무 등록'),
               dict(kind='value', target=css(TITLE), expected=''), dict(kind='value', target=css(DESCRIPTION), expected='')],
              [dict(kind='value', target=css(TITLE), expected=values['title']), dict(kind='value', target=css(DESCRIPTION), expected=values['description'])],
              [dict(kind='visible', target=css(MODAL), expected=False), exact(1)],
              [dict(kind='url_path', expected='/mypage/schedule'), dict(kind='visible', target=css(MODAL), expected=False), exact(1)]]
    contract = dict(version=1, scenario_id=scenario_id, steps=[dict(order=step['order'], action=step['action'],
        target={'url': TARGET_URL} if step['action'] == 'open' else css(step['target']), checks=conditions)
        for step, conditions in zip(steps, checks)])
    scenario = dict(scenario_id=scenario_id, scenario_name='CU02 일정 등록', business_unit_id=WORKFLOW_ID,
                    workflow_id=WORKFLOW_ID, status='SUCCESS', steps=steps, execution_contract=contract,
                    screenshot_checkpoints=dict(before=2, after=5),
                    run_mode='DEVELOPMENT', official=False, generated_by_llm=False)
    data = dict(values, scenario_id=scenario_id, target_url=TARGET_URL, auth_url=TARGET_ORIGIN + '/api/auth/login',
                target_origin=TARGET_ORIGIN,
                calendar=CALENDAR, month=MONTH, cell=cell, date_target=date_target, event_target=event_target,
                modal=MODAL, title_target=TITLE, description_target=DESCRIPTION, submit_target=SUBMIT)
    code = ('SCENARIO_ID = ' + repr(scenario_id) + '\nDATA_JSON = ' + repr(json.dumps(data, ensure_ascii=False)) + '\n' + SCRIPT)
    return dict(code=code, scenario=scenario, contract=contract, parameters=values, definition=definition,
                source_files={'cu02_definition.json': encoded(definition), 'cu02_parameters.json': encoded(values)})


SCRIPT = r'''
import json
import os
from datetime import date
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from ktl_runtime import business_step, capture_evidence

DATA = json.loads(DATA_JSON)
driver = None
wait = None


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def preauthenticate():
    account = os.environ.get('KTL_M04_RBEM_USERNAME', '')
    secret = os.environ.get('KTL_M04_RBEM_PASSWORD', '')
    if not account.strip() or not secret:
        raise RuntimeError('시험 계정 연결이 필요합니다.')
    try:
        request = Request(DATA['auth_url'], method='POST',
            data=json.dumps({'loginId': account, 'password': secret}).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        with build_opener(RejectRedirects()).open(request, timeout=30) as response:
            if type(response.status) is not int or response.status != 200 or response.geturl() != DATA['auth_url']:
                raise ValueError('Invalid authentication response')
            raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('Oversized authentication response')
        value = json.loads(raw)
        token = value.get('token') if isinstance(value, dict) else None
        if (not isinstance(value, dict) or value.get('success') is not True
                or not isinstance(token, str) or not 1 <= len(token) <= 16384
                or token != token.strip() or any(ord(char) < 32 or ord(char) == 127 for char in token)):
            raise ValueError('Incomplete authentication response')
        return {'token': token}
    except Exception:
        # HTTP/JSON/transport exceptions may include response data. Only the fixed
        # diagnosis reaches the Runner; the token remains in this worker's memory.
        raise RuntimeError('시험 계정 로그인에 실패했습니다. 계정과 연결 상태를 확인하세요.') from None


def install_session(browser, session):
    try:
        source = ('(()=>{if(window!==window.top||location.origin!==' + json.dumps(DATA['target_origin'])
                  + ')return;const state=' + json.dumps(session, ensure_ascii=True)
                  + ';localStorage.setItem("token",state.token);})();')
        result = browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': source})
        identifier = result.get('identifier') if isinstance(result, dict) else None
        if not isinstance(identifier, str) or not identifier:
            raise ValueError('Missing session bootstrap identifier')
        return identifier
    except Exception:
        # Do not expose a CDP exception that might echo its token-bearing source.
        raise RuntimeError('로그인 세션을 브라우저에 전달하지 못했습니다.') from None


def remove_session_bootstrap(browser, identifier):
    try:
        browser.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument', {'identifier': identifier})
    except Exception:
        raise RuntimeError('로그인 세션 초기화 작업을 정리하지 못했습니다.') from None

def one(selector):
    found = driver.find_elements(By.CSS_SELECTOR, selector)
    return found[0] if len(found) == 1 and found[0].is_displayed() and found[0].is_enabled() else False

def read(selector):
    element = one(selector)
    return element.text.strip() if element else None

def click(selector):
    element = wait.until(lambda _: one(selector))
    driver.execute_script('arguments[0].scrollIntoView({block:"center",inline:"center",behavior:"instant"});', element)
    wait.until(lambda _: driver.execute_script('const e=arguments[0],r=e.getBoundingClientRect(),t=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return !!t&&(t===e||e.contains(t));', element))
    element.click()

def month():
    text = read(DATA['month'])
    if not text:
        return None
    parts = text.split('.')
    return (int(parts[0]), int(parts[1])) if len(parts) == 2 else None

def target_month():
    day = date.fromisoformat(DATA['date'])
    desired = (day.year, day.month)
    current = wait.until(lambda _: month())
    distance = (desired[0]-current[0])*12 + desired[1]-current[1]
    if abs(distance) > 120:
        raise RuntimeError('현재 달력에서 10년 이내의 시험 날짜를 선택하세요.')
    for _ in range(abs(distance)):
        previous = current
        click('.schedule-page button[aria-label="다음 달"]' if distance > 0 else '.schedule-page button[aria-label="이전 달"]')
        current = wait.until(lambda _: month() if month() != previous else False)
    wait.until(lambda _: month() == desired)

def matching_events():
    return [e for e in driver.find_elements(By.CSS_SELECTOR, DATA['event_target'])
            if e.is_displayed() and e.text.strip() == DATA['title']]

def existing_schedule_count():
    # 일정 화면에는 조회 완료 표시가 없다. DOM의 빈 목록을 조회 성공으로
    # 해석하지 않고, 본인 일정의 읽기 전용 응답에서 중복 여부만 반환한다.
    value = driver.execute_async_script(r"""
const done=arguments[arguments.length-1],day=arguments[0],title=arguments[1];
(async()=>{
  const token=localStorage.getItem('token');
  if(!token) return done({ok:false});
  const headers={Authorization:'Bearer '+token};
  const viewers=await fetch('/api/schedules/viewers',{headers});
  if(!viewers.ok) return done({ok:false});
  const own=(await viewers.json()).viewers;
  const self=Array.isArray(own)&&own.find(row=>row.relation==='self');
  if(!self) return done({ok:false});
  const query=new URLSearchParams({year:day.slice(0,4),month:String(Number(day.slice(5,7))),targetUserId:String(self.id)});
  const response=await fetch('/api/schedules?'+query,{headers});
  if(!response.ok) return done({ok:false});
  const rows=(await response.json()).schedules;
  if(!Array.isArray(rows)) return done({ok:false});
  if(rows.some(row=>!row||typeof row.title!=='string'||typeof row.startDate!=='string'||!/^\d{4}-\d{2}-\d{2}/.test(row.startDate)||
     (row.endDate!=null&&(typeof row.endDate!=='string'||!/^\d{4}-\d{2}-\d{2}/.test(row.endDate))))) return done({ok:false});
  done({ok:true,count:rows.filter(row=>row.title===title&&String(row.startDate).slice(0,10)<=day&&String(row.endDate||row.startDate).slice(0,10)>=day).length});
})().catch(()=>done({ok:false}));
""", DATA['date'], DATA['title'])
    if not isinstance(value, dict) or value.get('ok') is not True or type(value.get('count')) is not int or value['count'] < 0:
        raise RuntimeError('본인 일정 조회를 완료하지 못했습니다. 등록은 시작하지 않았습니다.')
    return value['count']

def modal_closed():
    return not any(e.is_displayed() for e in driver.find_elements(By.CSS_SELECTOR, DATA['modal']))

try:
    session = preauthenticate()
    print('로그인을 완료했습니다. 일정관리 화면을 준비합니다.')
    options = webdriver.EdgeOptions() if DATA['browser'] == 'edge' else webdriver.ChromeOptions()
    options.add_argument('--window-size=1440,1100')
    driver = webdriver.Edge(options=options) if DATA['browser'] == 'edge' else webdriver.Chrome(options=options)
    driver.set_page_load_timeout(40)
    wait = WebDriverWait(driver, 25)
    try:
        bootstrap = install_session(driver, session)
    finally:
        session.clear()

    with business_step(1):
        driver.get(DATA['target_url'])
        wait.until(lambda _: one(DATA['calendar']))
        wait.until(lambda _: read('.schedule-viewer-bar__copy strong') == '내 일정')
        remove_session_bootstrap(driver, bootstrap)
        target_month()
        assert urlsplit(driver.current_url).path == '/mypage/schedule'
        assert month() == (int(DATA['date'][:4]), int(DATA['date'][5:7]))
        assert existing_schedule_count() == 0, '같은 제목의 일정이 이미 저장되어 있습니다. 새 시험 제목을 지정하세요.'
        assert not matching_events(), '같은 제목의 일정이 이미 있습니다. 새 시험 제목을 지정하세요.'

    with business_step(2):
        day = date.fromisoformat(DATA['date'])
        assert wait.until(lambda _: read(DATA['date_target']) == str(day.day))
        cell = wait.until(lambda _: one(DATA['cell']))
        assert 'monthly-calendar__cell--outside' not in cell.get_attribute('class').split()
        assert cell.get_attribute('aria-readonly') != 'true'
        click(DATA['date_target'])
        assert wait.until(lambda _: read(DATA['modal'] + ' h2') == '업무 등록')
        assert read(DATA['submit_target']) == '등록', '기존 일정 수정 대신 신규 등록 창이 필요합니다.'
        for selector in (DATA['title_target'], DATA['description_target']):
            element = wait.until(lambda _: one(selector))
            assert element.get_attribute('value') == '', '신규 등록 화면의 제목과 내용이 비어 있어야 합니다.'
        capture_evidence('before')

    with business_step(3):
        for selector, value in ((DATA['title_target'], DATA['title']), (DATA['description_target'], DATA['description'])):
            element = wait.until(lambda _: one(selector))
            element.send_keys(Keys.CONTROL, 'a')
            element.send_keys(Keys.BACKSPACE)
            if value:
                element.send_keys(value)
        assert driver.find_element(By.CSS_SELECTOR, DATA['title_target']).get_attribute('value') == DATA['title']
        assert driver.find_element(By.CSS_SELECTOR, DATA['description_target']).get_attribute('value') == DATA['description']

    with business_step(4):
        assert read(DATA['modal'] + ' h2') == '업무 등록'
        click(DATA['submit_target'])
        assert wait.until(lambda _: modal_closed())
        assert wait.until(lambda _: len(matching_events()) == 1), '등록 후 대상 날짜의 일정이 확인되지 않습니다.'

    with business_step(5):
        driver.refresh()
        wait.until(lambda _: one(DATA['calendar']))
        target_month()
        assert wait.until(lambda _: len(matching_events()) == 1), '재조회 후 저장된 일정이 확인되지 않습니다.'
        event = matching_events()[0]
        event.click()
        assert wait.until(lambda _: one(DATA['title_target']))
        assert wait.until(lambda _: driver.find_element(By.CSS_SELECTOR, DATA['title_target']).get_attribute('value') == DATA['title'])
        assert wait.until(lambda _: driver.find_element(By.CSS_SELECTOR, DATA['description_target']).get_attribute('value') == DATA['description'])
        capture_evidence('after')
        click(DATA['modal'] + ' button[aria-label="닫기"]')
        assert wait.until(lambda _: modal_closed())
        assert len(matching_events()) == 1
finally:
    if driver is not None:
        driver.quit()
'''
