"""M01 원 CSV에서 직접 준비하는 제한된 관측 동작 재생. 모델·GT·GPT를 사용하지 않는다."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

from ..evaluators import EvaluationError, require
from ..m01 import M01CsvStore, parse_csv
from .checks import _auth_target, _locator, _safe_literal, _safe_url, prepare_contract, validate_source_data


NOTICE = ('M01 원 CSV의 관측 순서를 재생합니다. 원래 입력값을 복원하지 않고 사용자가 명시한 새 업무값을 사용합니다. '
          '동작·화면 상태 재생 완료는 업무 목적 달성이나 독립 정답 검증을 뜻하지 않습니다. '
          '로그인 리다이렉트는 원 URL 검사에서 실패하며 인증정보를 코드에 넣지 않습니다.')
_REFERENCE = {'collector_boot', 'api_transaction', 'api_transaction_error', 'api_transaction_timeout',
              'fetch_request', 'fetch_response', 'fetch_error', 'xhr_request', 'xhr_response', 'xhr_error',
              'network_request', 'network_response', 'popup_structure', 'screen_change', 'ui_outcome',
              'value_reflection', 'grid_context_enrichment',
              'visibility_change', 'page_close', 'tab_close', 'beforeunload', 'pagehide', 'focus', 'blur'}
_TEXT = {'text', 'textarea', 'search', 'email', 'tel', 'url', 'number'}
_TRUTH = {'expected_event_id', 'expected_events', 'ground_truth', 'groundtruth', 'gt_steps', 'gt_label',
          'evaluation_pairing', 'match_result', 'evaluation_only'}


def _error(message):
    raise EvaluationError(message, 'NOT_READY')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _path(root, relative):
    path = root / relative
    require(path.is_relative_to(root) and '..' not in path.parts, 'M01 원본 경로 범위를 확인하세요.')
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        require(not current.is_symlink(), 'M01 재생 원본에 심볼릭 링크를 사용할 수 없습니다.')
    return path


def _load(root, dataset_id, session, selected):
    root = Path(root).resolve()
    require(isinstance(dataset_id, str) and re.fullmatch(r'[0-9a-f]{32}', dataset_id), 'M01 dataset_id를 확인하세요.')
    folder = _path(root, Path('data/development/m01_uploads') / dataset_id)
    csv_path, manifest_path = _path(root, folder.relative_to(root) / 'source.csv'), _path(root, folder.relative_to(root) / 'manifest.json')
    report = M01CsvStore(root, session=session).read(dataset_id, offset=0, limit=1)
    raw, manifest_raw = csv_path.read_bytes(), manifest_path.read_bytes()
    require(_sha(raw) == report['dataset']['sha256'], '조회 중 M01 원 CSV의 SHA-256이 변경됐습니다.')
    manifest = json.loads(manifest_raw.decode('utf-8'))
    require(manifest.get('dataset_id') == dataset_id and manifest.get('sha256') == _sha(raw),
            'M01 CSV와 업로드 manifest가 다릅니다.')
    headers, rows = parse_csv(raw)
    require(not _TRUTH.intersection(name.lower().replace('-', '_') for name in headers),
            '평가 정답이 포함된 CSV는 재생 입력으로 사용할 수 없습니다.')
    sessions = list(dict.fromkeys(row.get('session_id', '').strip() for row in rows))
    require(isinstance(selected, str) or selected is None, '선택한 수집 session_id를 확인하세요.')
    if selected is None and len(sessions) == 1:
        selected = sessions[0]
    require(bool(selected) and selected in sessions, '단일 수집 session_id를 명시적으로 선택하세요.')
    indexed = [(number, row) for number, row in enumerate(rows, 1) if row.get('session_id', '').strip() == selected]
    require(bool(indexed), '선택한 수집 세션의 원본 행이 없습니다.')
    return root, raw, manifest_raw, manifest, selected, indexed


def _url(value):
    require(isinstance(value, str) and bool(value), '원본 page_url이 없습니다.')
    parsed = _safe_url(value)
    require(parsed.scheme in {'http', 'https'} and bool(parsed.hostname), '원본 HTTP/HTTPS 페이지 URL이 필요합니다.')
    return parsed


def _target(row):
    target = row.get('target_selector', '').strip()
    require(bool(target), '원본 target_selector가 없습니다.')
    _locator(dict(by='css selector', value=target))
    require(not _auth_target(target), '인증 입력 또는 인증 control은 자동 재생하지 않습니다.')
    require(row.get('input_control_type', '').lower() not in {'password', 'hidden'},
            'password 또는 hidden control은 자동 재생하지 않습니다.')
    if row.get('target_key'):
        require(row['target_key'] == 'css:' + target, '원본 selector와 target_key가 다릅니다.')
    locators = json.loads(row['locators_json']) if row.get('locators_json') else {}
    require(isinstance(locators, dict), '원본 locator 객체 형식을 확인하세요.')
    require(not locators.get('selector_css') or locators['selector_css'] == target, '원본 CSS locator가 서로 다릅니다.')
    require(not locators.get('element_tag') or locators['element_tag'].lower() == row.get('element_tag', '').lower(),
            '원본 element_tag가 locator와 다릅니다.')
    return target, locators


def _inspect(root, dataset_id, session, session_id):
    root, raw, manifest_raw, manifest, selected, indexed = _load(root, dataset_id, session, session_id)
    blockers, steps, missing = [], [], []
    known_ids, opened = set(), False
    tabs = {row.get('capture_tab_id') for _, row in indexed if row.get('capture_tab_id')}
    if len(tabs) > 1:
        blockers.append(dict(row=None, reason='여러 탭의 기록은 단일 새 Chrome 창으로 재구성하지 않습니다.'))
    for position, (number, row) in enumerate(indexed):
        kind = row.get('interaction_type', '').strip().lower()
        item = dict(row=number, event_id=row.get('event_id', ''), interaction_type=kind,
                    kind='reference', action=None, target=None, reason='원본 관측 참조')
        steps.append(item)
        try:
            event_id = row.get('event_id', '').strip()
            require(bool(event_id) and event_id not in known_ids, '원본 event_id가 없거나 중복됐습니다.')
            known_ids.add(event_id)
            stamp = datetime.fromisoformat(row.get('event_time', '').replace('Z', '+00:00'))
            require(stamp.tzinfo is not None, '원본 event_time에 timezone이 없습니다.')
            require(row.get('capture_frame_id', '') in {'', '0'}, 'iframe 기록은 자동 재생하지 않습니다.')
            if row.get('capture_root_tab_id') and row.get('capture_tab_id'):
                require(row['capture_root_tab_id'] == row['capture_tab_id'], '자식 탭 기록은 자동 재생하지 않습니다.')
            if kind in {'page_view', 'route_change'}:
                parsed = _url(row.get('page_url'))
                if not opened:
                    require(kind == 'page_view', '첫 페이지 이동 관측 없이 route_change를 재구성할 수 없습니다.')
                    item.update(kind='execute', action='open', target=row['page_url'], url=row['page_url'])
                    opened = True
                else:
                    target = row.get('target_selector') or 'html'
                    # html is permitted only when it is literally the recorded selector.
                    require(bool(row.get('target_selector')), '화면 관측의 원본 selector가 없습니다.')
                    _locator(dict(by='css selector', value=target))
                    item.update(kind='check', action='verify', target=target)
                item['checks'] = [dict(kind='url_path', expected=parsed.path or '/')]
            elif kind in {'click', 'change', 'input', 'popup_open', 'popup_close'}:
                require(opened, '첫 page_view 이전의 동작은 새 창에서 재현할 수 없습니다.')
                target, locators = _target(row)
                tag = row.get('element_tag', '').lower()
                if kind == 'click':
                    # A broad calendar cell does not prove its native child or click coordinates.
                    tail = re.split(r'\s+>\s+|\s+', target.strip())[-1]
                    require(tag not in {'canvas', 'svg', 'path'} and '.monthly-calendar__cell' not in tail,
                            '실제 native 하위 대상 또는 포인터 위치가 없어 등록/수정 동작을 구분할 수 없습니다.')
                    parsed = _url(row.get('page_url'))
                    following = []
                    for _, after in indexed[position + 1:]:
                        if after.get('interaction_type') in {'click', 'change', 'input', 'submit'}:
                            break
                        if after.get('interaction_type') in {'route_change', 'page_view'}:
                            following.append(_url(after.get('page_url')).path or '/')
                    require(len(set(following)) <= 1, '한 조작 뒤 여러 화면 이동을 임의로 선택하지 않습니다.')
                    checks = [dict(kind='focus', target=dict(by='css selector', value=target), expected=True)] if tag in {'input', 'textarea'} else [dict(kind='url_path', expected=following[-1] if following else parsed.path or '/')]
                    item.update(kind='execute', action='click', target=target, checks=checks)
                elif kind in {'change', 'input'}:
                    control = row.get('input_control_type', '').lower()
                    require((tag == 'textarea' and control in {'', 'textarea'}) or (tag == 'input' and control in _TEXT),
                            '원본 text/textarea 입력 형태를 확인할 수 없습니다. 선택·체크 값은 추정하지 않습니다.')
                    name = f'row_{number}_value'
                    field = dict(name=name, row=number, target=target, element_tag=tag,
                                 input_control_type=control or 'textarea', reason='원 입력값은 복원하지 않습니다. 새 비민감 업무값을 명시하세요.')
                    missing.append(field)
                    item.update(kind='execute', action='input', target=target, value_param=name,
                                checks=[dict(kind='value', target=dict(by='css selector', value=target), parameter=name)])
                else:
                    item.update(kind='check', action='verify', target=target,
                                checks=[dict(kind='visible', target=dict(by='css selector', value=target), expected=kind == 'popup_open')])
            elif kind == 'submit':
                _, locators = _target(row)
                previous = indexed[position - 1] if position else None
                require(previous is not None and previous[0] == number - 1
                        and previous[1].get('interaction_type') == 'click'
                        and previous[1].get('element_tag', '').lower() in {'button', 'input'},
                        'submit의 원래 조작을 복원할 수 없습니다. 임의 제출이나 중복 제출을 만들지 않습니다.')
                _, previous_locator = _target(previous[1])
                form_xpath, button_xpath = locators.get('selector_xpath'), previous_locator.get('selector_xpath')
                require(row.get('element_tag', '').lower() == 'form' and isinstance(form_xpath, str)
                        and bool(form_xpath) and isinstance(button_xpath, str) and button_xpath.startswith(form_xpath + '/'),
                        '직전 클릭과 form submit의 원본 DOM 포함 관계를 확인할 수 없습니다.')
                item['reason'] = '직전 form 내부 클릭 뒤의 DOM submit 관측입니다. 독립 조작으로 중복 실행하지 않습니다.'
            else:
                require(kind in _REFERENCE, '지원하지 않거나 원본 조작 정보가 부족한 이벤트입니다. 임의 동작으로 변환하지 않습니다.')
                item['reason'] = '사용자 native 조작이 아닌 원본 lifecycle/API/구조 관측입니다. 별도 조작하지 않습니다.'
        except (EvaluationError, ValueError, TypeError, KeyError) as exc:
            # Use fixed diagnoses only; never echo raw input values or decoder exceptions.
            reason = '행의 원본 selector·URL·입력형태·조작 근거가 부족하거나 지원되지 않습니다.'
            if isinstance(exc, EvaluationError):
                reason = str(exc)
            if kind == 'click' and '.monthly-calendar__cell' in (row.get('target_selector') or ''):
                reason = 'native 하위 대상·포인터 위치가 없어 일정 신규 등록과 기존 수정 클릭을 구분할 수 없습니다.'
            elif kind == 'submit':
                reason = '직전 클릭과 form submit의 원본 포함 관계가 없어 중복 없는 제출을 복원할 수 없습니다.'
            blockers.append(dict(row=number, reason=reason))
            item.update(kind='blocked', reason=reason)
    if not opened:
        blockers.append(dict(row=None, reason='원본 page_view와 초기 페이지 URL이 필요합니다.'))
    if not any(item['kind'] == 'execute' and item['action'] != 'open' for item in steps):
        blockers.append(dict(row=None, reason='재생할 실제 사용자 조작이 없습니다.'))
    return dict(dataset_id=dataset_id, filename=manifest['filename'], source_sha256=_sha(raw),
                session_id=selected, event_count=len(indexed), steps=steps, missing_inputs=missing,
                blockers=blockers, status='NOT_READY' if blockers else 'NEEDS_INPUT' if missing else 'READY', notice=NOTICE), (raw, manifest_raw)


def inspect_source(root, dataset_id, session=None, *, session_id=None, allow_archived=False):
    """현재 서버 세션에 속한 M01 원본을 검사한다. 코드/파일/브라우저를 만들지 않는다."""
    require(allow_archived is False, '이전 서버 세션의 CSV는 M01에서 다시 업로드하세요.')
    return _inspect(root, dataset_id, session, session_id)[0]


def _script(scenario, contract):
    # Safe JSON/Python literals only. Never interpolate strings as executable code.
    data = repr(json.dumps(dict(scenario=scenario, contract=contract), ensure_ascii=False, allow_nan=False))
    return '''# M01_OBSERVED_REPLAY: deterministic CSV replay; no model/GPT/GT.
import json
from urllib.parse import urlsplit
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from ktl_runtime import business_step

SCENARIO_ID = ''' + repr(scenario['scenario_id']) + '''
DATA = json.loads(''' + data + ''')
options = webdriver.ChromeOptions()
options.add_argument('--window-size=1440,1100')
driver = webdriver.Chrome(options=options)
wait = WebDriverWait(driver, 20)

def exact(selector):
    found = driver.find_elements(By.CSS_SELECTOR, selector)
    if len(found) != 1 or not found[0].is_displayed() or not found[0].is_enabled():
        return False
    element = found[0]
    identity = (element.get_attribute('id') or '') + ' ' + (element.get_attribute('name') or '')
    control = (element.get_attribute('type') or '').lower()
    autocomplete = (element.get_attribute('autocomplete') or '').lower().split()
    if control in {'password', 'hidden'} or any(value in autocomplete for value in ('username', 'current-password', 'new-password', 'one-time-code')):
        raise RuntimeError('Authentication control cannot be replayed')
    if __import__('re').search(r'password|passwd|pwd|secret|token|auth|cookie|login[\\W_]*id|user[\\W_]*name|비밀번호|비번|아이디', identity, __import__('re').I):
        raise RuntimeError('Authentication control cannot be replayed')
    return element

def condition(check):
    if check['kind'] == 'url_path':
        return urlsplit(driver.current_url).path == check['expected']
    found = driver.find_elements(By.CSS_SELECTOR, check['target']['value'])
    if check['kind'] == 'visible' and check['expected'] is False:
        return not any(element.is_displayed() for element in found)
    if len(found) != 1 or not found[0].is_displayed():
        return False
    element = found[0]
    if check['kind'] == 'visible':
        return True
    if check['kind'] == 'value':
        return element.get_attribute('value') == check['expected']
    if check['kind'] == 'focus':
        return driver.switch_to.active_element == element
    return False

try:
    for step, definition in zip(DATA['scenario']['steps'], DATA['contract']['steps']):
        with business_step(step['order']):
            if step['action'] == 'open':
                driver.get(step['url'])
            elif step['action'] in {'click', 'input'}:
                selector = definition['target']['value']
                element = wait.until(lambda _: exact(selector))
                driver.execute_script('arguments[0].scrollIntoView({block:"center",inline:"center",behavior:"instant"});', element)
                if step['action'] == 'click':
                    element.click()
                else:
                    element.send_keys(Keys.CONTROL, 'a')
                    element.send_keys(Keys.BACKSPACE)
                    if step['value']:
                        element.send_keys(step['value'])
            for check in definition['checks']:
                assert wait.until(lambda _, expected=check: condition(expected)), 'Recorded replay condition failed'
finally:
    driver.quit()
'''


def prepare_replay(root, dataset_id, parameters=None, session=None, *, session_id=None):
    """새 입력값을 명시했을 때만 M04 strict 계약과 원본 Python을 반환한다. 저장·실행하지 않는다."""
    inspection, (raw, manifest_raw) = _inspect(root, dataset_id, session, session_id)
    if inspection['blockers']:
        _error('재생할 수 없는 원본 행이 있습니다. M01 수집 동작 준비 상태를 확인하세요.')
    parameters = {} if parameters is None else parameters
    require(isinstance(parameters, dict), '새 재생 입력값 객체가 필요합니다.')
    names = {field['name'] for field in inspection['missing_inputs']}
    require(set(parameters) == names, '모든 입력 행에 새 값을 명시해야 합니다. 원 입력값을 복원하거나 다른 값을 추정하지 않습니다.')
    for value in parameters.values():
        require(isinstance(value, str) and len(value) <= 1000 and not any(ord(char) < 32 for char in value),
                '재생 입력은 1000자 이내 비민감 단일 행 업무값이어야 합니다.')
        require(not any('\ue000' <= char <= '\ue05d' for char in value),
                'Selenium 예약 키 문자는 업무 입력값으로 사용할 수 없습니다.')
        require(not re.search(r'\[\s*(?:masked|redacted|숨김|마스킹)|<\s*(?:masked|redacted)', value, re.I),
                '마스킹된 원본값을 새 입력값으로 사용할 수 없습니다.')
        try:
            _safe_literal(value)
            validate_source_data(value, strict_literals=True)
        except ValueError:
            _error('인증정보 또는 비밀값을 재생 입력값에 넣을 수 없습니다.')
    scenario = dict(scenario_id='M01-REPLAY-' + inspection['source_sha256'][:20],
                    scenario_name='M01 관측 동작 재생', source_kind='M01_OBSERVED_REPLAY',
                    official=False, generated_by_llm=False, model_inference=False, steps=[], notice=NOTICE)
    definitions = []
    for item in inspection['steps']:
        if item['kind'] not in {'execute', 'check'}:
            continue
        order = len(scenario['steps']) + 1
        step = dict(order=order, action=item['action'], target=item['target'],
                    expected_result='원본 관측 행의 동작 대상과 화면 상태 재생 확인',
                    source_csv_row=item['row'], evidence=[item['event_id']])
        target = dict(url=item['url']) if item['action'] == 'open' else dict(by='css selector', value=item['target'])
        if item['action'] == 'open':
            step['url'] = item['url']
        conditions = deepcopy(item['checks'])
        if item.get('value_param'):
            step['value'] = parameters[item['value_param']]
            for condition in conditions:
                if 'parameter' in condition:
                    condition['expected'] = parameters[condition.pop('parameter')]
        scenario['steps'].append(step)
        definitions.append(dict(order=order, action=item['action'], target=target, checks=conditions))
    scenario['execution_contract'] = dict(version=1, scenario_id=scenario['scenario_id'], steps=definitions)
    try:
        contract = prepare_contract(scenario)
    except ValueError:
        _error('원본 동작에서 기존 M04 strict 실행 계약을 준비할 수 없습니다.')
    source = dict(dataset_id=dataset_id, session_id=inspection['session_id'], source_sha256=_sha(raw),
                  source_manifest_sha256=_sha(manifest_raw), filename=inspection['filename'],
                  event_count=inspection['event_count'],
                  row_ids=[dict(row=item['row'], event_id=item['event_id']) for item in inspection['steps']],
                  source_kind='M01_OBSERVED_REPLAY', original_input_values_recovered=False,
                  parameter_source='USER_PROVIDED_NON_SENSITIVE_REPLAY_VALUES', notice=NOTICE)
    files = {'m01_source.csv': raw, 'm01_manifest.json': manifest_raw,
             'm01_replay_source.json': _encoded(source), 'm01_parameters.json': _encoded(parameters)}
    return dict(code=_script(scenario, contract), scenario=scenario, contract=contract, source=source, source_files=files)
