"""Pure compilation of an already resolved M03 execution scenario; no I/O or LLM."""
import ast
from copy import deepcopy
import json
from urllib.parse import urlsplit

from ..evaluators import EvaluationError
from .checks import _RELATIONAL_CHECK_SCRIPT, _auth_target, _target, prepare_contract


VERSION = 'm03-selenium-compiler-v3-empty-input'
SUPPORTED_ACTIONS = frozenset({'open', 'navigate', 'click', 'input', 'type', 'fill_empty', 'clear', 'submit',
                               'select', 'back', 'forward', 'refresh', 'verify'})
SUPPORTED_CHECKS = frozenset({'visible', 'focus', 'value', 'fill_empty', 'text_equals', 'text_contains', 'count',
                              'text_count', 'url_path', 'nonempty', 'text_equals_target'})
TRUSTED_ORIGIN = 'https://rainbowlab.ai.kr'
_MAX_CODE_BYTES = 262144


def _not_ready(message):
    raise EvaluationError(message, 'NOT_READY')


def _trusted(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname == 'rainbowlab.ai.kr'
            and parsed.port in {None, 443})


def compile_code(scenario, contract):
    """Return fixed Selenium source, keeping all resolved steps and conditions.

    Caller archives the original M03 source, resolved scenario/contract/revision
    and this source together before registration. Compilation never resolves a
    different context, reads credentials, launches a browser or invokes GPT.
    Complex API/card checks require their dedicated implementation and are
    deliberately NOT_READY here.
    """
    try:
        source = deepcopy(scenario)
        if not isinstance(source, dict):
            _not_ready('실행 시나리오 객체가 필요합니다.')
        identity = source.get('scenario_id')
        if (not isinstance(identity, str) or not identity.strip() or identity != identity.strip() or len(identity) > 256
                or any(ord(char) < 32 for char in identity)):
            _not_ready('유효한 실행 시나리오 ID가 필요합니다.')
        source['execution_contract'] = deepcopy(contract)
        normalized = prepare_contract(source)
        for step, definition in zip(source['steps'], normalized['steps']):
            if step['action'] not in SUPPORTED_ACTIONS:
                _not_ready('준비 코드가 지원하지 않는 브라우저 동작입니다.')
            if _auth_target(definition['target']):
                _not_ready('인증 입력은 업무 단계로 컴파일하지 않습니다. 기존 인증 초기화를 사용하세요.')
            if any(item['kind'] not in SUPPORTED_CHECKS for item in definition['checks']):
                _not_ready('전용 관측이 필요한 API·명함 검사는 이 준비 코드에서 지원하지 않습니다.')
            if step['action'] in {'input', 'type', 'select', 'fill_empty'}:
                value = step.get('value')
                if (not isinstance(value, str) or '\x00' in value or '\t' in value
                        or any('\ue000' <= char <= '\ue05d' for char in value)):
                    _not_ready('입력·선택 단계에는 예약 키가 아닌 명시적인 문자열 value가 필요합니다.')
            if step['action'] == 'fill_empty' and ('match_text' in step or 'row_match' in step):
                _not_ready('빈 입력란 전용 동작에는 고유한 입력 대상만 지정하세요.')
            if 'match_text' in step:
                text = step['match_text']
                if (not isinstance(text, str) or not ' '.join(text.split()) or len(text) > 2000
                        or step['action'] in {'open', 'navigate', 'back', 'forward', 'refresh', 'verify'}):
                    _not_ready('match_text는 조작 대상의 비어 있지 않은 정확한 표시 문구여야 합니다.')
            if 'row_match' in step:
                scope = step['row_match']
                if (step['action'] != 'click' or 'match_text' in step or not isinstance(scope, dict)
                        or set(scope) != {'rows', 'cell', 'expected'}):
                    _not_ready('row_match는 click에 정확한 rows·cell·expected만 지정해야 합니다.')
                for key in ('rows', 'cell'):
                    selector = scope[key]
                    if (not isinstance(selector, str) or selector != selector.strip()
                            or selector.lower().startswith(('http://', 'https://', 'file:', 'javascript:'))):
                        _not_ready('row_match에는 명시적인 CSS 선택자가 필요합니다.')
                    locator = _target(dict(by='css selector', value=selector))
                    if _auth_target(locator):
                        _not_ready('인증 대상을 row_match로 사용할 수 없습니다.')
                expected = scope['expected']
                if not isinstance(expected, str) or not ' '.join(expected.split()) or len(expected) > 2000:
                    _not_ready('row_match에는 비어 있지 않은 정확한 셀 문구가 필요합니다.')
        start_url = source.get('start_url')
        if start_url is not None:
            start_url = _target(dict(url=start_url))['url']
            if not _trusted(start_url):
                _not_ready('업무 단계 밖 start_url 초기화는 신뢰한 업무 origin에서만 허용합니다.')
        first = source['steps'][0]
        first_url = normalized['steps'][0]['target'].get('url')
        if first['action'] not in {'open', 'navigate'} and start_url is None:
            _not_ready('이동 없이 시작하는 시나리오에는 명시적인 start_url이 필요합니다.')
        initial_url = start_url or first_url
        authenticated = _trusted(initial_url)
        points = source.get('screenshot_checkpoints')
        if points is not None and (not isinstance(points, dict) or set(points) != {'before', 'after'}
                or any(type(value) is not int or not 1 <= value <= len(source['steps']) for value in points.values())
                or points['before'] > points['after']):
            _not_ready('화면 기록 시점은 유효한 전·후 실행 단계로 고정해야 합니다.')
        source['execution_contract'] = normalized
        data = json.dumps(dict(scenario=source, contract=normalized, start_url=start_url,
                               authenticated=authenticated, checkpoints=points),
                          ensure_ascii=False, sort_keys=True, allow_nan=False)
        code = ('# PREPARED M03 Selenium source; generated_by_llm=False; requires the KTL M04 runner.\n'
                'import json\nfrom urllib.parse import urlsplit\n'
                'from selenium import webdriver\n'
                'from selenium.webdriver.common.by import By\n'
                'from selenium.webdriver.common.keys import Keys\n'
                'from selenium.webdriver.support.ui import WebDriverWait, Select\n'
                'from ktl_runtime import business_step, capture_evidence, authenticated_chrome, complete_authentication\n\n'
                'SCENARIO_ID = ' + repr(identity) + '\n'
                'COMPILER_VERSION = ' + repr(VERSION) + '\n'
                'GENERATED_BY_LLM = False\n'
                'DATA = json.loads(' + repr(data) + ')\n'
                'RELATIONAL_CHECK_SCRIPT = ' + repr(_RELATIONAL_CHECK_SCRIPT) + '\n'
                'SIMPLE_CHECK_SCRIPT = ' + repr(_SIMPLE_CHECK_SCRIPT) + '\n' + _PROGRAM)
        ast.parse(code)
        if len(code.encode('utf-8')) > _MAX_CODE_BYTES:
            _not_ready('준비 코드가 고정 스크립트의 256 KiB 한도를 초과합니다.')
        return code
    except EvaluationError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, SyntaxError):
        _not_ready('원 시나리오·실행 계약·명시적인 입력값을 확인하세요.')


_SIMPLE_CHECK_SCRIPT = r"""// M03_PREPARED_TYPED_CHECK: return booleans only, never DOM values.
const items=[...document.querySelectorAll(arguments[0])],e=items[0];
const kind=arguments[1],expected=arguments[2],wanted=arguments[3];
const visible=x=>{
  if(!x||!x.getClientRects().length||['hidden','collapse'].includes(getComputedStyle(x).visibility))return false;
  for(let p=x;p;p=p.parentElement)if(Number(getComputedStyle(p).opacity)===0)return false;
  return true;
};
switch(kind){
case 'visible':return expected?items.length===1&&visible(e):!items.some(visible);
case 'focus':return (!!e&&document.activeElement===e)===expected;
case 'value':return !!e&&e.value===expected;
case 'text_equals':return !!e&&e.innerText.trim()===expected;
case 'text_contains':return !!e&&e.innerText.includes(expected);
case 'count':return items.length===expected;
case 'text_count':return items.filter(x=>visible(x)&&typeof x.innerText==='string'&&x.innerText.trim()===expected).length===wanted;
}return false;"""


_PROGRAM = r'''
driver = None
wait = None
authentication_pending = DATA['authenticated']
empty_input_values = {}


def normalized_text(value):
    return ' '.join(value.split())


def safe_control(element):
    import re
    identity = (element.get_attribute('id') or '') + ' ' + (element.get_attribute('name') or '')
    kind = (element.get_attribute('type') or '').lower()
    autocomplete = (element.get_attribute('autocomplete') or '').lower().split()
    if (kind in {'password', 'hidden'}
            or any(value in autocomplete for value in ('username', 'current-password', 'new-password', 'one-time-code'))
            or re.search(r'password|passwd|pwd|secret|token|auth|cookie|login[\W_]*id|user[\W_]*name|비밀번호|비번|아이디', identity, re.I)):
        raise RuntimeError('Authentication controls are not business actions')
    return element


def interaction_target(target, match_text=None, row_match=None):
    def unique(_):
        if row_match is not None:
            matches = []
            expected = normalized_text(row_match['expected'])
            for row in driver.find_elements(By.CSS_SELECTOR, row_match['rows']):
                if not row.is_displayed() or not row.is_enabled():
                    continue
                cells = row.find_elements(By.CSS_SELECTOR, row_match['cell'])
                if len(cells) == 1 and cells[0].is_displayed():
                    cell = safe_control(cells[0])
                    if normalized_text(cell.text) == expected:
                        matches.append(row)
            if len(matches) != 1:
                return False
            items = matches[0].find_elements(By.CSS_SELECTOR, target['value'])
        else:
            items = driver.find_elements(By.CSS_SELECTOR, target['value'])
        if match_text is not None:
            expected = normalized_text(match_text)
            items = [item for item in items if normalized_text(item.text) == expected]
        if len(items) != 1 or not items[0].is_displayed() or not items[0].is_enabled():
            return False
        if row_match is not None and items[0].tag_name.lower() != 'button':
            return False
        return safe_control(items[0])
    node = wait.until(unique)
    driver.execute_script('arguments[0].scrollIntoView({block:"center",inline:"center",behavior:"instant"});', node)
    def hit(_):
        current = unique(driver)
        if current is False:
            return False
        passed = driver.execute_script('const e=arguments[0],r=e.getBoundingClientRect(),h=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return !!h&&(h===e||e.contains(h));', current)
        return current if passed is True else False
    return wait.until(hit)


def condition(check):
    kind = check['kind']
    if kind == 'fill_empty':
        selector = check['target']['value']
        if selector not in empty_input_values:
            return False
        items = driver.find_elements(By.CSS_SELECTOR, selector)
        return (len(items) == 1 and items[0].is_displayed() and items[0].is_enabled()
                and safe_control(items[0]).get_property('value') == empty_input_values[selector])
    if kind == 'url_path':
        return urlsplit(driver.current_url).path == check['expected']
    if kind in {'text_equals_target', 'nonempty'}:
        return driver.execute_script(RELATIONAL_CHECK_SCRIPT, check['target']['value'], check['property'],
                                     check.get('other_target', {}).get('value'),
                                     check.get('other_property'), kind) is True
    return driver.execute_script(SIMPLE_CHECK_SCRIPT, check['target']['value'], kind,
                                 check.get('expected'), check.get('count')) is True


def initialize_authentication():
    global authentication_pending
    if authentication_pending:
        wait.until(lambda _: driver.execute_script('return document.readyState;') == 'complete')
        complete_authentication(driver)
        authentication_pending = False


def perform(step, definition):
    action, target = step['action'], definition['target']
    if action in {'open', 'navigate'}:
        driver.get(target['url'])
        initialize_authentication()
    elif action in {'click', 'input', 'type', 'fill_empty', 'clear', 'submit', 'select'}:
        element = interaction_target(target, step.get('match_text'), step.get('row_match'))
        if action == 'click':
            element.click()
        elif action == 'fill_empty':
            tag = element.tag_name.lower()
            kind = (element.get_attribute('type') or 'text').lower()
            if (tag not in {'input', 'textarea'}
                    or tag == 'input' and kind not in {'text', 'email', 'tel', 'url', 'search'}
                    or element.get_property('readOnly')):
                raise RuntimeError('Empty-only input requires an editable text control')
            original = element.get_property('value')
            if not isinstance(original, str):
                raise RuntimeError('Empty-only input value could not be read')
            selector = target['value']
            if selector in empty_input_values:
                raise RuntimeError('Empty-only input target was already handled')
            empty_input_values[selector] = original if original != '' else step['value']
            if original != '':
                return
            if any(value in step['value'] for value in ('\r', '\n')) and tag != 'textarea':
                raise RuntimeError('Multiline values require an explicit textarea target')
            element.click()
            if element.get_property('value') != '':
                raise RuntimeError('Input changed before empty-only typing')
            element.send_keys(step['value'])
        elif action in {'input', 'type'}:
            if any(value in step['value'] for value in ('\r', '\n')) and element.tag_name.lower() != 'textarea':
                raise RuntimeError('Multiline values require an explicit textarea target')
            element.click()
            element.send_keys(Keys.CONTROL, 'a')
            element.send_keys(Keys.BACKSPACE)
            if step['value']:
                element.send_keys(step['value'])
        elif action == 'clear':
            element.clear()
        elif action == 'select':
            if element.tag_name.lower() != 'select':
                raise RuntimeError('Selection requires a native select element')
            element.click()
            Select(element).select_by_value(step['value'])
        elif element.tag_name.lower() == 'form':
            element.submit()
        elif (element.tag_name.lower() == 'button'
              and (element.get_attribute('type') or '').lower() in {'', 'button', 'submit'}):
            element.click()
        elif (element.tag_name.lower() == 'input'
              and (element.get_attribute('type') or '').lower() in {'button', 'submit', 'image'}):
            element.click()
        else:
            raise RuntimeError('Submit requires a native form or button target')
    elif action == 'back':
        driver.back()
    elif action == 'forward':
        driver.forward()
    elif action == 'refresh':
        driver.refresh()
    elif action != 'verify':
        raise RuntimeError('Unsupported fixed browser action')


try:
    if DATA['authenticated']:
        driver = authenticated_chrome()
    else:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1440,1100')
        driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    wait = WebDriverWait(driver, 20)
    if DATA['start_url'] is not None:
        driver.get(DATA['start_url'])
        initialize_authentication()
    for step, definition in zip(DATA['scenario']['steps'], DATA['contract']['steps']):
        with business_step(step['order']):
            perform(step, definition)
            for check in definition['checks']:
                wait.until(lambda _, current=check: condition(current))
                assert condition(check), 'Fixed typed expectation failed'
            for phase in ('before', 'after'):
                if DATA['checkpoints'] is not None and DATA['checkpoints'][phase] == step['order']:
                    capture_evidence(phase)
finally:
    if driver is not None:
        driver.quit()
'''
