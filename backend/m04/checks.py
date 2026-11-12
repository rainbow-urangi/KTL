"""사전 승인 실행 계약과 생성 코드와 독립된 브라우저 결과 검사.

자연어 기대 결과를 추론하지 않는다. 명시한 locator/typed condition 또는
정확히 일치하는 BU14 개발 계약만 실행하며 응답 본문/개인정보는 기록하지 않는다.
"""
import base64
import copy
import hashlib
import json
import math
import re
import time
from urllib.parse import parse_qs, urlsplit


VERSION = 1
_ACTIONS = {'open', 'navigate', 'click', 'input', 'type', 'clear', 'submit',
            'select', 'back', 'forward', 'refresh', 'verify'}
_KINDS = {'visible', 'focus', 'value', 'text_equals', 'text_contains', 'url_path',
          'count', 'text_count', 'cards_search', 'cards_state', 'text_equals_target', 'nonempty', 'native_submit_response'}
_RELATIONAL_CHECK_SCRIPT = r"""const qa=s=>[...document.querySelectorAll(s)];
const shown=e=>!!e && e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
const attr=(e,name)=>String(e.getAttribute(name)||'');
const permitted=(e,p)=>{
  const tag=String(e.tagName||'').toLowerCase();
  const types=[attr(e,'type'),String(e.type||'')].map(v=>v.toLowerCase());
  const identity=attr(e,'id')+' '+attr(e,'name');
  const autocomplete=(attr(e,'autocomplete')+' '+String(e.autocomplete||'')).toLowerCase().split(/\s+/);
  if(types.some(v=>v==='password'||v==='hidden') ||
     /password|passwd|pwd|secret|token|auth|cookie|login[\W_]*id|user[\W_]*name|비밀번호|비번|아이디/i.test(identity) ||
     autocomplete.some(v=>['username','current-password','new-password','one-time-code'].includes(v))) return false;
  return p==='text' || (p==='value' && ['input','textarea'].includes(tag));
};
const useful=s=>typeof s==='string' && !!s.trim() &&
  !/^(?:[-–—]+|n\/a|null|undefined)$/i.test(s.trim()) &&
  !/\[\s*(?:masked|redacted|hidden|숨김|마스킹|비공개)[^\]]*\]|<\s*(?:masked|redacted|hidden)[^>]*>/iu.test(s) &&
  !/^[*＊⋆★☆✱✳✴✻✼❋\s]+$/u.test(s);
const read=(e,p)=>p==='value'?e.value:e.innerText;
const left=qa(arguments[0]);
if(left.length!==1 || !shown(left[0]) || !permitted(left[0],arguments[1])) return false;
const a=read(left[0],arguments[1]);
if(!useful(a)) return false;
if(arguments[4]==='nonempty') return true;
const right=qa(arguments[2]);
if(right.length!==1 || left[0]===right[0] || !shown(right[0]) || !permitted(right[0],arguments[3])) return false;
const b=read(right[0],arguments[3]);
return useful(b) && a.trim()===b.trim();"""
_EMPTY_TEXT = ['표시할 명함 정보가 없습니다.', '검색 결과가 없습니다', '조회된 명함이 없습니다',
               '등록된 명함이 없습니다', '데이터가 없습니다']
_AUTH_TARGET = re.compile(r'password|passwd|pwd|secret|token|auth|cookie|login[\W_]*id|user[\W_]*name|비밀번호|비번|아이디', re.I)
_ATTRIBUTE_COMPARE = re.compile(r'\[\s*(?:[\w*-]*\|)?([\w:-]+)\s*[~|^$*]?=', re.I)
_URL_LITERAL = re.compile(r'(?:https?|file)://[^\s\x22\x27<>]+|(?<![\w:/])/(?!/)[^\s\x22\x27<>]*[?#][^\s\x22\x27<>]*', re.I)
_CREDENTIAL_LITERAL = re.compile(r'\bBearer\s+\S|\b(?:password|passwd|pwd|secret|(?:access[_-]?|refresh[_-]?)?token|authorization|cookie|api[_-]?key)\s*[:=]\s*\S', re.I)
_TRUTH_KEYS = {'ground_truth', 'groundtruth', 'expected_events', 'expected_label', 'gt_steps',
               'gt_label', 'evaluation_pairing', 'match_result', 'official_pass'}
_CREDENTIAL_KEY = re.compile(r'(?:password|passwd|pwd|secret|(?:access[_-]?|refresh[_-]?)?token|authorization|cookie|api[_-]?key)', re.I)


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _css_text(value):
    # 이스케이프된 CSS 속성명도 동일한 정책을 적용한다.
    def decode(match):
        try:
            return chr(int(match.group(1), 16))
        except (ValueError, OverflowError):
            return '\ufffd'
    value = re.sub(r'\\([0-9a-fA-F]{1,6})\s?', decode, str(value))
    return re.sub(r'\\(.)', r'\1', value)


def _auth_target(value):
    if isinstance(value, dict):
        value = value.get('value', '')
    return _AUTH_TARGET.search(_css_text(value)) is not None


def _safe_url(value):
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise ValueError('실행 계약 URL 형식을 확인하세요.') from None
    _require(not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
             and '?' not in value and '#' not in value,
             '실행 계약 URL에는 인증정보, query 또는 fragment를 넣을 수 없습니다.')
    return parsed


def _safe_literal(value):
    if isinstance(value, str):
        _require(_CREDENTIAL_LITERAL.search(value) is None,
                 '실행 계약의 literal 조건에는 인증정보를 넣을 수 없습니다.')
        for match in _URL_LITERAL.finditer(value):
            _safe_url(match.group())


def validate_source_data(value, strict_literals=False):
    """시나리오 입력의 재귀 인증정보·평가 정답 검사."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower().replace('-', '_')
            # 비공식 결과의 빈 공식 판정 표시
            neutral_official_marker = normalized == 'official_pass' and item is None
            _require(normalized not in _TRUTH_KEYS or neutral_official_marker,
                     '시나리오 실행 입력에 평가 정답 키를 넣을 수 없습니다.')
            _require(not (_CREDENTIAL_KEY.fullmatch(normalized) and item not in (None, '', [], {})),
                     '시나리오 실행 입력에 인증정보를 넣을 수 없습니다.')
            validate_source_data(str(key), strict_literals)
            validate_source_data(item, strict_literals)
    elif isinstance(value, list):
        for item in value:
            validate_source_data(item, strict_literals)
    elif isinstance(value, str):
        _require(_CREDENTIAL_LITERAL.search(value) is None, '시나리오 실행 입력에 인증정보를 넣을 수 없습니다.')
        if strict_literals:
            _safe_literal(value)


def _locator(value):
    _require(isinstance(value, dict) and set(value) == {'by', 'value'}
             and value.get('by') == 'css selector' and isinstance(value.get('value'), str)
             and bool(value['value'].strip()) and len(value['value']) <= 2048,
             '실행 계약에 유효한 CSS locator {by, value}가 필요합니다.')
    css = _css_text(value['value'])
    _require(not any(name.casefold() == 'value' or _AUTH_TARGET.search(name)
                     for name in _ATTRIBUTE_COMPARE.findall(css)),
             '실행 계약 CSS에는 value 또는 인증 속성의 비교값을 넣을 수 없습니다.')
    _safe_literal(css)
    return {'by': 'css selector', 'value': value['value'].strip()}


def _target(value):
    if isinstance(value, dict) and set(value) == {'url'}:
        parsed = _safe_url(value['url']) if isinstance(value.get('url'), str) else None
        _require(parsed is not None and parsed.scheme in {'http', 'https', 'file'}
                 and (parsed.scheme == 'file' or bool(parsed.hostname))
                 and not parsed.username and not parsed.password,
                 '실행 계약 URL 형식 또는 인증정보 포함 여부를 확인하세요.')
        return {'url': value['url']}
    return _locator(value)


def _condition(value, target, sensitive=False):
    _require(isinstance(value, dict) and isinstance(value.get('kind'), str) and value['kind'] in _KINDS,
             '지원하는 typed condition이 필요합니다: ' + ', '.join(sorted(_KINDS)))
    kind = value['kind']
    if kind == 'text_count':
        _require(set(value) == {'kind', 'target', 'expected', 'count'}
                 and isinstance(value.get('expected'), str) and len(value['expected']) <= 2000
                 and type(value.get('count')) is int and value['count'] >= 0,
                 'text_count에는 2000자 이내 expected와 0 이상 정수 count가 필요합니다.')
        result = dict(kind=kind, target=_locator(value['target']), expected=value['expected'], count=value['count'])
        _require(not (sensitive or _auth_target(target) or _auth_target(result['target'])),
                 '인증 입력은 text_count 검사 대상이 아닙니다.')
        _safe_literal(result['expected'])
        return result
    if kind == 'native_submit_response':
        _require(set(value) == {'kind', 'method', 'api_origin', 'api_path', 'expected_status'}
                 and isinstance(value.get('method'), str) and value['method'] in {'POST', 'PUT', 'PATCH', 'DELETE'}
                 and type(value.get('expected_status')) is int and 200 <= value['expected_status'] <= 299,
                 'native submit 검사에는 명시적인 method/origin/path/성공 status가 필요합니다.')
        origin = _safe_url(value['api_origin']) if isinstance(value.get('api_origin'), str) else None
        path = _safe_url(value['api_path']) if isinstance(value.get('api_path'), str) else None
        _require(origin is not None and origin.scheme in {'http', 'https'} and bool(origin.hostname)
                 and not origin.username and not origin.password and origin.path in {'', '/'}
                 and not origin.query and not origin.fragment
                 and value['api_origin'].rstrip('/') == origin.scheme + '://' + origin.netloc,
                 'native submit API origin 형식 오류')
        _require(path is not None and value['api_path'].startswith('/') and not value['api_path'].startswith('//')
                 and not path.scheme and not path.netloc and not path.query and not path.fragment
                 and path.path == value['api_path'], 'native submit API path에는 query/fragment를 넣을 수 없습니다.')
        _require(not sensitive and not _auth_target(target), '인증 입력은 native submit 업무 검사 대상이 아닙니다.')
        return dict(kind=kind, method=value['method'], api_origin=value['api_origin'].rstrip('/'),
                    api_path=value['api_path'], expected_status=value['expected_status'])
    if kind in {'text_equals_target', 'nonempty'}:
        fields = {'kind', 'target', 'property'}
        if kind == 'text_equals_target':
            fields |= {'other_target', 'other_property'}
        _require(set(value) == fields and isinstance(value.get('property'), str)
                 and value['property'] in {'text', 'value'},
                 'DOM 비교 검사에는 명시적인 target과 text/value property가 필요합니다.')
        result = dict(kind=kind, target=_locator(value['target']), property=value['property'])
        _require(not sensitive and not _auth_target(result['target']),
                 'DOM 비교 검사로 인증 입력을 읽을 수 없습니다.')
        if kind == 'text_equals_target':
            _require(isinstance(value.get('other_property'), str) and value['other_property'] in {'text', 'value'},
                     '비교 DOM의 text/value property가 필요합니다.')
            result.update(other_target=_locator(value['other_target']), other_property=value['other_property'])
            _require(result['target'] != result['other_target'] and not _auth_target(result['other_target']),
                     'DOM 비교에는 인증 입력이 아닌 서로 다른 두 locator가 필요합니다.')
        return result
    if kind in {'cards_search', 'cards_state'}:
        fields = {'kind', 'keyword', 'api_path', 'api_origin', 'search_type', 'search_type_query',
                  'search_input', 'search_type_target', 'table', 'rows', 'category_cells', 'empty_state', 'empty_text'}
        _require(set(value) <= fields and isinstance(value.get('keyword'), str)
                 and isinstance(value.get('api_path'), str) and value['api_path'].startswith('/')
                 and isinstance(value.get('search_type'), str) and bool(value['search_type']),
                 '명함 검사에 keyword/api_path/search_type이 필요합니다.')
        result = dict(kind=kind, keyword=value['keyword'], api_path=value['api_path'], search_type=value['search_type'])
        for name in ('search_input', 'search_type_target', 'table', 'rows', 'category_cells', 'empty_state'):
            result[name] = _locator(value.get(name))
        _require(not (sensitive or _auth_target(target) or _auth_target(result['search_input'])),
                 '인증 입력은 명함 검색 계약으로 검사할 수 없습니다. 기존 로그인 환경변수를 사용하세요.')
        _safe_url(value['api_path'])
        _safe_literal(value['keyword'])
        _safe_literal(value['search_type'])
        if 'api_origin' in value:
            parsed = _safe_url(value['api_origin']) if isinstance(value['api_origin'], str) else None
            _require(parsed is not None and parsed.scheme in {'http', 'https'} and bool(parsed.hostname)
                     and not parsed.username and not parsed.password and parsed.path in {'', '/'}
                     and not parsed.query and not parsed.fragment, '명함 API origin 형식이 올바르지 않습니다.')
            result['api_origin'] = value['api_origin'].rstrip('/')
        if 'search_type_query' in value:
            _require(isinstance(value['search_type_query'], str) and bool(value['search_type_query']),
                     'search_type_query는 비어 있지 않은 문자열이어야 합니다.')
            result['search_type_query'] = value['search_type_query']
        empty_text = value.get('empty_text', _EMPTY_TEXT)
        _require(isinstance(empty_text, list) and bool(empty_text)
                 and all(isinstance(item, str) and item for item in empty_text), '빈 목록 문구 계약이 필요합니다.')
        result['empty_text'] = list(empty_text)
        for text in empty_text:
            _safe_literal(text)
        return result
    _require(set(value) <= {'kind', 'target', 'expected'}, 'typed condition에 지원하지 않는 필드가 있습니다.')
    result = {'kind': kind}
    if kind == 'url_path':
        _require(isinstance(value.get('expected'), str) and value['expected'].startswith('/'),
                 'url_path 검사에 절대 경로 expected가 필요합니다.')
        parsed = _safe_url(value['expected'])
        _require(not parsed.scheme and not parsed.netloc, 'url_path에는 URL host 또는 인증정보를 넣을 수 없습니다.')
        result['expected'] = value['expected']
        return result
    result['target'] = _locator(value.get('target', target))
    expected = value.get('expected', True) if kind in {'visible', 'focus'} else value.get('expected')
    if kind in {'visible', 'focus'}:
        _require(type(expected) is bool, kind + ' expected는 boolean이어야 합니다.')
    elif kind == 'count':
        _require(type(expected) is int and expected >= 0, 'count expected는 0 이상 정수여야 합니다.')
    else:
        _require(isinstance(expected, str) and (kind != 'text_contains' or bool(expected)),
                 kind + ' expected는 문자열이어야 합니다.')
        _require(not (expected and (sensitive or _auth_target(target) or _auth_target(result['target']))),
                 '인증 입력의 고정 value/text 기대값은 허용하지 않습니다. 기존 로그인 환경변수를 사용하세요.')
        _safe_literal(expected)
    result['expected'] = expected
    return result


def _bu14_contract(scenario):
    """기존 승인 개발 업무의 정확한 8단계만 명시적 선택자로 대응한다."""
    expected = [
        ('open', '명함 목록 화면', '명함 목록 화면 표시'),
        ('click', '명함 검색어 입력란', '검색어 입력 가능'),
        ('input', '명함 검색어 입력란', '테스트 검색어 입력'),
        ('click', '명함 검색 버튼', '테스트 검색어에 해당하는 명함 목록 표시'),
        ('click', '명함 검색어 입력란', '검색어 수정 가능'),
        ('clear', '명함 검색어 입력란', '검색어가 비워짐'),
        ('click', '명함 검색 버튼', '전체 명함 목록 조회'),
        ('verify', '명함 목록 화면', '검색어가 비워지고 전체 명함 목록 확인'),
    ]
    steps = scenario.get('steps', [])
    if (scenario.get('business_unit_id') != 'BU14' or len(steps) != 8
            or any((step.get('action'), step.get('target'), step.get('expected_result')) != definition
                   for step, definition in zip(steps, expected))
            or steps[0].get('url') != 'https://rainbowlab.ai.kr/mypage/cards'
            or steps[2].get('value') != '테스트'):
        return None
    loc = lambda value: dict(by='css selector', value=value)
    field = loc('.business-card-toolbar__actions input')
    button = loc('.business-card-toolbar__actions > button')
    table = loc('.business-card-page .business-card-table')
    def condition(kind, keyword):
        return dict(kind=kind, keyword=keyword, api_path='/api/business-cards', api_origin='https://rainbowlab.ai.kr',
                    search_type='category', search_input=field,
                    search_type_target=loc('.business-card-toolbar__actions select[aria-label]'), table=table,
                    rows=loc('.business-card-page .business-card-table tbody tr:not(:has(td[colspan]))'),
                    category_cells=loc('.business-card-page .business-card-table tbody tr td:first-child:not([colspan])'),
                    empty_state=loc('.business-card-page .business-card-table tbody td[colspan]'))
    targets = [dict(url=steps[0]['url']), field, field, button, field, field, button, table]
    checks = [[dict(kind='url_path', expected='/mypage/cards'), dict(kind='visible', target=table)],
              [dict(kind='focus')], [dict(kind='value', expected='테스트')], [condition('cards_search', '테스트')],
              [dict(kind='focus')], [dict(kind='value', expected='')], [condition('cards_search', '')],
              [dict(kind='value', target=field, expected=''), condition('cards_state', '')]]
    return dict(version=1, scenario_id=scenario['scenario_id'], steps=[
        dict(order=index, action=step['action'], target=target, checks=outcomes)
        for index, (step, target, outcomes) in enumerate(zip(steps, targets, checks), 1)])


def prepare_contract(scenario, config=None):
    """사전 실행 조건을 검증한다. 불충분한 입력을 자연어로 보충하지 않는다."""
    _require(isinstance(scenario, dict) and isinstance(scenario.get('scenario_id'), str)
             and bool(scenario['scenario_id'].strip()), '실행 계약에 scenario_id가 필요합니다.')
    validate_source_data(scenario, strict_literals=True)
    steps = scenario.get('steps')
    _require(isinstance(steps, list) and bool(steps), '실행할 시나리오 단계가 필요합니다.')
    for index, step in enumerate(steps, 1):
        _require(isinstance(step, dict) and type(step.get('order')) is int and step['order'] == index
                 and isinstance(step.get('action'), str) and step['action'] in _ACTIONS
                 and bool(step.get('target')), '시나리오 단계 순서/action/target을 확인하세요.')
        _require(isinstance(step.get('expected_result'), (str, dict, list)) and bool(step['expected_result']),
                 '단계 ' + str(index) + '의 expected_result가 없습니다. 실행 기대 결과를 먼저 확정하세요.')
        validate_source_data(step['expected_result'], strict_literals=True)
        validate_source_data(step.get('value'), strict_literals=True)
        if step['action'] in {'open', 'navigate'} and isinstance(step.get('url'), str):
            _safe_url(step['url'])
        _safe_literal(_css_text(step['target']))
        if _auth_target(step['target']):
            _require(step.get('value') is None or step.get('value') == '',
                     '인증 입력의 고정값은 실행 계약에 넣을 수 없습니다. 기존 로그인 환경변수를 사용하세요.')
    contract = scenario.get('execution_contract')
    if contract is None:
        options = (config or {}).get('m07', {})
        contexts = options.get('execution_contexts', {}) if isinstance(options, dict) else {}
        context = contexts.get(scenario.get('business_unit_id'), {}) if isinstance(contexts, dict) else {}
        contract = context.get('execution_contract') if isinstance(context, dict) else None
    if contract is None:
        contract = _bu14_contract(scenario)
    _require(isinstance(contract, dict), '명시적인 execution_contract의 locator와 typed condition이 필요합니다.')
    _require(set(contract) <= {'version', 'scenario_id', 'steps'} and type(contract.get('version')) is int
             and contract['version'] == VERSION and contract.get('scenario_id') == scenario['scenario_id'],
             '실행 계약 version/scenario_id가 시나리오와 일치해야 합니다.')
    definitions = contract.get('steps')
    _require(isinstance(definitions, list) and len(definitions) == len(steps), '실행 계약은 모든 시나리오 단계를 포함해야 합니다.')
    result = dict(version=VERSION, scenario_id=scenario['scenario_id'], steps=[])
    for index, (step, definition) in enumerate(zip(steps, definitions), 1):
        _require(isinstance(definition, dict) and set(definition) == {'order', 'action', 'target', 'checks'}
                 and type(definition.get('order')) is int and definition['order'] == index
                 and definition.get('action') == step['action'], '실행 계약의 단계 순서/action이 시나리오와 일치해야 합니다.')
        target = _target(definition['target'])
        _require(('url' in target) == (step['action'] in {'open', 'navigate'}),
                 'open/navigate에는 URL, 나머지 동작에는 CSS target이 필요합니다.')
        values = definition['checks']
        _require(isinstance(values, list) and bool(values), '단계 ' + str(index) + '의 typed condition이 없습니다.')
        conditions = [_condition(value, target, sensitive=_auth_target(step['target'])) for value in values]
        native = [value for value in conditions if value['kind'] == 'native_submit_response']
        _require(not native or (step['action'] == 'submit' and len(native) == 1
                 and not any(value['kind'] == 'cards_search' for value in conditions)),
                 'native_submit_response는 submit 단계에 하나만 지정할 수 있습니다.')
        result['steps'].append(dict(order=index, action=step['action'], target=target, checks=conditions))
    return copy.deepcopy(result)


class _NativeSubmitResponse:
    """현재 native submit window의 CDP 메타데이터만 유지한다. body/header는 읽지 않는다."""
    def __init__(self, condition):
        self.condition = condition
        self.prior, self.seen, self.invalid = set(), set(), set()
        self.requests = {}
        self.since = None
        self.succeeded = False
        self.error = None

    @staticmethod
    def finite(value):
        try:
            return type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            return False

    def exact_url(self, value):
        if not isinstance(value, str) or value != self.condition['api_origin'] + self.condition['api_path']:
            return False
        try:
            url = urlsplit(value)
            return (not url.username and not url.password and not url.query and not url.fragment
                    and url.scheme + '://' + url.netloc == self.condition['api_origin']
                    and url.path == self.condition['api_path'])
        except ValueError:
            return False

    def same_endpoint(self, value):
        if not isinstance(value, str):
            return False
        try:
            url = urlsplit(value)
            return url.scheme + '://' + url.netloc == self.condition['api_origin'] and url.path == self.condition['api_path']
        except ValueError:
            return False

    def arm(self):
        if self.since is not None:
            # The public Selenium submit can internally issue submitElement too.
            if self.succeeded:
                self.error = '동일 단계의 native submit 중복 실행'
            return
        self.since = time.time()

    def consume(self, entries):
        for entry in entries:
            try:
                event = json.loads(entry['message'])['message']
                if not isinstance(event, dict) or not isinstance(event.get('params', {}), dict):
                    raise ValueError('Invalid network metadata')
                method, params = event.get('method'), event.get('params', {})
                if method not in {'Network.requestWillBeSent', 'Network.responseReceived',
                                  'Network.loadingFinished', 'Network.loadingFailed'}:
                    continue
                identity = params.get('requestId')
                if not isinstance(identity, str) or not identity or len(identity) > 512:
                    self.error = '네트워크 관측 request ID 형식 오류'
                    continue
                if self.since is None:
                    self.prior.add(identity)
                    continue
                stamp = params.get('timestamp')
                if method == 'Network.requestWillBeSent':
                    duplicate = identity in self.seen or identity in self.prior or 'redirectResponse' in params
                    self.seen.add(identity)
                    if duplicate:
                        self.invalid.add(identity)
                    request = params.get('request', {})
                    if not isinstance(request, dict) or not self.same_endpoint(request.get('url')):
                        continue
                    if request.get('method') != self.condition['method']:
                        self.invalid.add(identity)
                        continue
                    wall = params.get('wallTime')
                    if not self.finite(stamp) or not self.finite(wall) or wall < self.since:
                        self.invalid.add(identity)
                    if not self.exact_url(request.get('url')):
                        self.invalid.add(identity)
                    # Rejected matching requests remain counted: a later valid request cannot hide them.
                    self.requests[identity] = dict(phase='REQUEST', request_timestamp=stamp, request_wall=wall)
                elif identity in self.requests and identity not in self.invalid:
                    record = self.requests[identity]
                    if method == 'Network.loadingFailed':
                        self.invalid.add(identity)
                    elif method == 'Network.responseReceived':
                        response = params.get('response', {})
                        status = response.get('status') if isinstance(response, dict) else None
                        if self.finite(status) and 100 <= status <= 599:
                            record['http_status'] = status
                        if (record['phase'] != 'REQUEST' or not self.finite(stamp)
                                or stamp < record['request_timestamp'] or not isinstance(response, dict)
                                or not self.exact_url(response.get('url'))
                                or type(response.get('status')) not in (int, float)
                                or response['status'] != self.condition['expected_status']):
                            self.invalid.add(identity)
                        else:
                            record.update(phase='RESPONSE', response_timestamp=stamp)
                    elif method == 'Network.loadingFinished':
                        if record['phase'] != 'RESPONSE' or not self.finite(stamp) or stamp < record['request_timestamp']:
                            self.invalid.add(identity)
                        else:
                            record.update(phase='FINISHED', finish_timestamp=stamp)
                elif method != 'Network.requestWillBeSent':
                    # An out-of-order phase must never recover through a later request with the same ID.
                    self.invalid.add(identity)
            except (KeyError, TypeError, ValueError):
                self.error = '네트워크 관측 메타데이터 형식 오류'

    def receipt(self):
        if self.error or not self.succeeded or len(self.requests) != 1:
            return None
        identity, record = next(iter(self.requests.items()))
        if identity in self.invalid or record['phase'] != 'FINISHED':
            return None
        return dict(method=self.condition['method'], path=self.condition['api_path'],
                    http_status=self.condition['expected_status'], request_id_sha256=hashlib.sha256(identity.encode()).hexdigest(),
                    request_after_submit_ms=round(1000 * (record['request_wall'] - self.since), 3),
                    response_after_request_ms=round(1000 * (record['response_timestamp'] - record['request_timestamp']), 3),
                    finish_after_request_ms=round(1000 * (record['finish_timestamp'] - record['request_timestamp']), 3),
                    association='EXACT_NATIVE_SUBMIT_OBSERVATION_WINDOW', direct_causal_id_proven=False)

    def diagnostic(self):
        return dict(method=self.condition['method'], path=self.condition['api_path'],
                    expected_http_status=self.condition['expected_status'], native_submit_succeeded=self.succeeded,
                    matching_request_count=len(self.requests), capture_error=self.error,
                    requests=[dict(request_id_sha256=hashlib.sha256(identity.encode()).hexdigest(),
                                   phase=record['phase'], rejected=identity in self.invalid,
                                   http_status=record.get('http_status'))
                              for identity, record in list(self.requests.items())[:20]])


class RuntimeChecks:
    """원본 WebDriver.execute로 생성 코드의 assert와 독립적으로 검사한다."""
    def __init__(self, contract):
        self.contract = contract
        self.raw_execute = None
        self.current = None
        self.driver = None
        self.target_action = False
        self.network = None
        self.summaries = {}

    def _raw(self, driver, name, params=None):
        return self.raw_execute(driver, name, params or {}).get('value')

    def _js(self, driver, script, *args):
        return self._raw(driver, 'w3cExecuteScript', dict(script=script, args=list(args)))

    def _matches(self, driver, identity, selector):
        if not identity:
            return False
        try:
            return self._js(driver, 'return !!arguments[0] && arguments[0].matches(arguments[1]);',
                            {'element-6066-11e4-a52e-4f735466cecf': identity}, selector) is True
        except Exception:
            return False

    def _drain(self, driver):
        try:
            entries = self._raw(driver, 'getLog', {'type': 'performance'})
            if self.network is not None and 'native' in self.network and not isinstance(entries, list):
                raise ValueError('Missing performance log')
            self._consume(entries or [])
        except Exception:
            if self.network is not None:
                self.network['error'] = '독립 네트워크 관측에 Chrome performance logging이 필요합니다.'

    def begin(self, order, drivers):
        self.current = self.contract['steps'][order - 1]
        self.driver = drivers[-1] if drivers else None
        self.target_action = False
        self.network = None
        conditions = [value for value in self.current['checks'] if value['kind'] == 'cards_search']
        native = [value for value in self.current['checks'] if value['kind'] == 'native_submit_response']
        if native:
            self.network = dict(native=_NativeSubmitResponse(native[0]), armed=False, error=None)
            if self.driver:
                self._drain(self.driver)
        elif conditions:
            self.network = dict(requests={}, condition=conditions[0], armed=False, error=None)
            if self.driver:
                self._drain(self.driver)

    def before_command(self, driver, name, params):
        if not self.current:
            return
        action = {'get': 'open', 'clickElement': 'click', 'sendKeysToElement': 'input',
                  'clearElement': 'clear', 'submitElement': 'submit', 'goBack': 'back',
                  'goForward': 'forward', 'refresh': 'refresh'}.get(name)
        allowed = {'open': {'open'}, 'navigate': {'open'}, 'click': {'click'}, 'input': {'input'},
                   'type': {'input'}, 'clear': {'clear', 'input'}, 'submit': {'submit', 'click'},
                   'select': {'click', 'input'}, 'back': {'back'}, 'forward': {'forward'}, 'refresh': {'refresh'}}
        if action not in allowed.get(self.current['action'], set()):
            return
        target = self.current['target']
        if 'url' in target:
            actual, expected = urlsplit(str(params.get('url', ''))), urlsplit(target['url'])
            matched = (actual.scheme, actual.netloc, actual.path.rstrip('/'), actual.query, actual.fragment) == (
                expected.scheme, expected.netloc, expected.path.rstrip('/'), expected.query, expected.fragment)
        elif action in {'back', 'forward', 'refresh'}:
            matched = self._js(driver, 'return !!document.querySelector(arguments[0]);', target['value']) is True
        else:
            matched = self._matches(driver, params.get('id'), target['value'])
        if self.network is not None and 'native' in self.network and name == 'submitElement' and not matched:
            raise RuntimeError('native submit의 실제 target이 계약과 일치하지 않습니다.')
        if matched:
            self.driver = driver
            if self.network is not None and 'native' in self.network and name == 'submitElement':
                self._drain(driver)
                if self.network['error']:
                    raise RuntimeError(self.network['error'])
                self.network['native'].arm()
                self.network['armed'] = True
                if self.network['native'].error:
                    raise RuntimeError(self.network['native'].error)
            elif self.network is not None and 'native' not in self.network and not self.network['armed']:
                self._drain(driver)
                self.network['requests'].clear()
                self.network['armed'] = True
            self.target_action = True

    def observe(self, driver, name, params, response):
        if self.current and name == 'getLog' and params.get('type') == 'performance':
            if self.network is not None and 'native' in self.network and driver is not self.driver:
                return
            self._consume(response.get('value') if isinstance(response, dict) else [])

    def native_submit_completed(self, driver, succeeded):
        if self.network is not None and 'native' in self.network and driver is self.driver:
            native = self.network['native']
            if succeeded and native.since is not None:
                native.succeeded = True
            else:
                native.error = 'native submit 실행 실패'

    def _consume(self, entries):
        if self.network is not None and 'native' in self.network:
            if isinstance(entries, list):
                self.network['native'].consume(entries)
            return
        if not self.network or not self.network['armed'] or not isinstance(entries, list):
            return
        condition = self.network['condition']
        for entry in entries:
            try:
                event = json.loads(entry['message'])['message']
                method, params = event.get('method'), event.get('params', {})
                identity = params.get('requestId')
                if method == 'Network.requestWillBeSent':
                    request = params.get('request', {})
                    url = urlsplit(request.get('url', ''))
                    query = parse_qs(url.query, keep_blank_values=True)
                    origin = condition.get('api_origin')
                    if origin is None and self.driver:
                        current = urlsplit(self._raw(self.driver, 'getCurrentUrl'))
                        origin = current.scheme + '://' + current.netloc
                    if (request.get('method') == 'GET' and url.scheme + '://' + url.netloc == origin
                            and url.path == condition['api_path'] and query.get('keyword', [''])[0] == condition['keyword']
                            and (not condition.get('search_type_query') or
                                 query.get(condition['search_type_query'], [''])[0] == condition['search_type'])):
                        self.network['requests'][identity] = dict(status=None, complete=False, failed=False)
                elif identity in self.network['requests']:
                    record = self.network['requests'][identity]
                    if method == 'Network.responseReceived':
                        record['status'] = params.get('response', {}).get('status')
                    elif method == 'Network.loadingFinished':
                        record['complete'] = True
                    elif method == 'Network.loadingFailed':
                        record['failed'] = True
            except (KeyError, TypeError, ValueError):
                continue

    def _simple(self, driver, condition):
        kind = condition['kind']
        if kind in {'text_equals_target', 'nonempty'}:
            return self._js(driver, _RELATIONAL_CHECK_SCRIPT, condition['target']['value'], condition['property'],
                            condition.get('other_target', {}).get('value'), condition.get('other_property'), kind) is True
        if kind == 'url_path':
            return urlsplit(self._raw(driver, 'getCurrentUrl')).path == condition['expected']
        selector, expected = condition['target']['value'], condition['expected']
        script = """const items=[...document.querySelectorAll(arguments[0])], expected=arguments[1];
const e=items[0], visible=x=>{
  if(!x || !x.getClientRects().length || ['hidden','collapse'].includes(getComputedStyle(x).visibility)) return false;
  for(let ancestor=x;ancestor;ancestor=ancestor.parentElement){
    if(Number(getComputedStyle(ancestor).opacity)===0) return false;
  }
  return true;
};
switch(arguments[2]) {
case 'visible': return expected ? items.length===1 && visible(e) : !items.some(visible);
case 'focus': return (!!e && document.activeElement===e)===expected;
case 'value': return !!e && e.value===expected;
case 'text_equals': return !!e && e.innerText.trim()===expected;
case 'text_contains': return !!e && e.innerText.includes(expected);
case 'count': return items.length===expected;
case 'text_count': return items.filter(x=>visible(x) && typeof x.innerText==='string' && x.innerText.trim()===expected).length===arguments[3];
} return false;"""
        if kind == 'text_count':
            return self._js(driver, script, selector, expected, kind, condition['count']) is True
        return self._js(driver, script, selector, expected, kind) is True

    def _cards_state(self, driver, condition, summary):
        state = self._js(driver, """const q=s=>document.querySelector(s), qa=s=>[...document.querySelectorAll(s)];
const visible=e=>!!e && e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
const input=q(arguments[0]), type=q(arguments[1]), table=q(arguments[2]);
return {keyword:input?input.value:null, type:type?type.value:null, visible:visible(table),
loading:!!table && table.innerText.includes('불러오는 중입니다.'),
rows:qa(arguments[3]).length, categories:qa(arguments[4]).map(e=>e.innerText.trim()),
empty:qa(arguments[5]).some(e=>visible(e) && arguments[6].some(t=>e.innerText.includes(t)))};""",
                         condition['search_input']['value'], condition['search_type_target']['value'],
                         condition['table']['value'], condition['rows']['value'],
                         condition['category_cells']['value'], condition['empty_state']['value'], condition['empty_text'])
        if (not isinstance(state, dict) or state.get('keyword') != condition['keyword']
                or state.get('type') != condition['search_type'] or state.get('visible') is not True
                or state.get('loading') is True or state.get('rows') != len(summary['categories'])
                or state.get('categories') != summary['categories']):
            return False
        return bool(summary['categories']) or summary['total'] == 0 and state.get('empty') is True

    def _cards(self, driver, condition):
        key = (condition.get('api_origin'), condition['api_path'], condition['keyword'])
        if condition['kind'] == 'cards_state':
            summary = self.summaries.get(key)
            return summary is not None and self._cards_state(driver, condition, summary)
        if not self.network or not self.network['armed'] or self.network.get('error'):
            return False
        self._drain(driver)
        for identity, record in self.network['requests'].items():
            if not record['complete'] or record['failed'] or record['status'] != 200:
                continue
            try:
                result = self._raw(driver, 'executeCdpCommand', {'cmd': 'Network.getResponseBody', 'params': {'requestId': identity}})
                body = result.get('body', '')
                if result.get('base64Encoded'):
                    body = base64.b64decode(body)
                data = json.loads(body)
                cards, pagination = data.get('cards'), data.get('pagination')
                if (not isinstance(cards, list) or not isinstance(pagination, dict)
                        or type(pagination.get('total')) is not int or pagination['total'] < len(cards)
                        or not all(isinstance(card, dict) and isinstance(card.get('category'), str) for card in cards)):
                    continue
                categories = [card['category'].strip() for card in cards]
                if condition['keyword'] and not all(condition['keyword'].casefold() in category.casefold() for category in categories):
                    continue
                summary = dict(categories=categories, total=pagination['total'])
                if self._cards_state(driver, condition, summary):
                    self.summaries[key] = summary
                    return True
            except Exception:
                # 본문과 개인정보를 오류 문자열이나 evidence에 포함하지 않는다.
                continue
        return False

    def finish(self, drivers):
        definition = self.current
        driver = self.driver or (drivers[-1] if drivers else None)
        evidence = []
        try:
            if driver is None or self.raw_execute is None:
                return False, '독립 실행 검사에 브라우저 세션이 없습니다.', evidence
            if definition['action'] != 'verify' and not self.target_action:
                return False, '계약 target에 대응하는 실제 브라우저 동작이 없습니다.', evidence
            for index, condition in enumerate(definition['checks'], 1):
                passed = False
                limit = time.monotonic() + 2
                while True:
                    try:
                        if condition['kind'] == 'native_submit_response':
                            self._drain(driver)
                            passed = not self.network['error'] and self.network['native'].receipt() is not None
                        else:
                            passed = (self._cards(driver, condition) if condition['kind'] in {'cards_search', 'cards_state'}
                                      else self._simple(driver, condition))
                    except Exception:
                        passed = False
                    if passed or time.monotonic() >= limit:
                        break
                    time.sleep(.05)
                item = dict(check_index=index, kind=condition['kind'], status='PASS' if passed else 'FAIL')
                if condition['kind'] == 'native_submit_response' and passed:
                    item['network'] = self.network['native'].receipt()
                elif condition['kind'] == 'native_submit_response':
                    item['network'] = self.network['native'].diagnostic()
                    if self.network['error']:
                        item['network']['capture_error'] = self.network['error']
                evidence.append(item)
                if not passed:
                    return False, '독립 기대 결과 검사 실패: ' + condition['kind'], evidence
            return True, None, evidence
        finally:
            self.current = None
            self.network = None
