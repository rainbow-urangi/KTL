"""고정 Python 스크립트 실행과 Selenium 관측."""
import argparse
import ast
import base64
import contextlib
import hashlib
import io
import importlib.util
import json
import os
import re
import runpy
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


# -I 작업 프로세스에서도 동일한 검사 모듈을 사용한다.
_checks_spec = importlib.util.spec_from_file_location('ktl_execution_checks', Path(__file__).with_name('checks.py'))
checks = importlib.util.module_from_spec(_checks_spec)
_checks_spec.loader.exec_module(checks)


def now():
    return datetime.now(timezone.utc).isoformat()


def load_login_settings(settings_path=None):
    # 로컬 시험 계정 설정
    names = ('KTL_M04_RBEM_USERNAME', 'KTL_M04_RBEM_PASSWORD')
    path = Path(settings_path) if settings_path is not None else Path(__file__).resolve().parents[2] / '.env.local'
    if path.is_file():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            name, separator, value = line.strip().partition('=')
            name = name.strip()
            if separator and name in names and name not in os.environ:
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    value = value[1:-1]
                os.environ[name] = value
    return {name: os.environ[name] for name in names if name in os.environ}


def _redact(value):
    text = str(value)
    password = os.environ.get('KTL_M04_RBEM_PASSWORD', '')
    username = os.environ.get('KTL_M04_RBEM_USERNAME', '')
    if password:
        text = text.replace(password, '[숨김]')
    if username:
        text = re.sub(r'(?<!\w)' + re.escape(username) + r'(?!\w)', '[숨김]', text)
    def url(match):
        try:
            parsed = urlsplit(match.group())
            host = parsed.hostname or ''
            if parsed.port:
                host += ':' + str(parsed.port)
            return urlunsplit((parsed.scheme, host, parsed.path, '', ''))
        except ValueError:
            return '[URL 숨김]'
    text = re.sub(r'https?://[^\s\x22\x27<>]+', url, text)
    text = re.sub(r'(?i)\bBearer\s+\S+', 'Bearer [숨김]', text)
    text = re.sub(r'(?i)(\b(?:password|passwd|authorization|cookie|set-cookie|access[_-]?token|refresh[_-]?token|api[_-]?key|secret)\b[\x22\x27]?\s*[:=]\s*)(?:\x22[^\x22]*\x22|\x27[^\x27]*\x27|[^\s,;}]+)', r'\1[숨김]', text)
    return text


def mask(value):
    return _redact(value)[:4000]


SCREENSHOT_POLICY = 'text-and-images-masked-v1'
_SCREENSHOT_MASK = r'''
const token=arguments[0], mode=arguments[1];
if(window!==window.top) return {ok:false,reason:'not_top_frame'};
if(mode==='remove'){document.getElementById(token)?.remove();return {ok:!document.getElementById(token)}}
if(mode==='apply'){
  if(document.getElementById(token)) return {ok:false,reason:'mask_collision'};
  const style=document.createElement('style');style.id=token;
  const selector='html:not(#'+token+'):not(#'+token+'-unused)';
  style.textContent=selector+','+selector+' *{color:transparent!important;-webkit-text-fill-color:transparent!important;-webkit-text-stroke:0 transparent!important;text-shadow:none!important;caret-color:transparent!important;background-image:none!important;border-image-source:none!important;list-style-image:none!important;content:none!important;box-shadow:none!important}'+
    selector+' *::before,'+selector+' *::after,'+selector+' *::marker{content:none!important;color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;background-image:none!important}'+
    selector+' input,'+selector+' textarea,'+selector+' select,'+selector+' option{opacity:0!important}'+
    selector+' img,'+selector+' picture,'+selector+' video,'+selector+' audio,'+selector+' canvas,'+selector+' svg,'+selector+' iframe,'+selector+' object,'+selector+' embed,'+selector+' fencedframe{visibility:hidden!important}';
  (document.head||document.documentElement).append(style);
}
if(!document.getElementById(token)) return {ok:false,reason:'mask_missing'};
const elements=[document.documentElement,...document.querySelectorAll('*')];
if(elements.length>20000) return {ok:false,reason:'document_too_large'};
const transparent=value=>value==='transparent'||value==='rgba(0, 0, 0, 0)';
for(const element of elements){
  if(element.shadowRoot) return {ok:false,reason:'shadow_dom_unsupported'};
  const style=getComputedStyle(element);
  if(style.display==='none'||style.visibility==='hidden'||Number(style.opacity)===0) continue;
  if(/^(INPUT|TEXTAREA|SELECT|OPTION|IMG|PICTURE|VIDEO|AUDIO|CANVAS|SVG|IFRAME|OBJECT|EMBED|FENCEDFRAME)$/.test(element.tagName)) return {ok:false,reason:'media_or_input_mask_failed'};
  if(!transparent(style.color)||!transparent(style.webkitTextFillColor)||style.textShadow!=='none'||style.backgroundImage!=='none'||style.borderImageSource!=='none'||style.listStyleImage!=='none'||!['none','normal'].includes(style.content)) return {ok:false,reason:'computed_mask_failed'};
  for(const pseudo of ['::before','::after']){
    const decoration=getComputedStyle(element,pseudo);
    if(!['none','normal','""'].includes(decoration.content)||decoration.backgroundImage!=='none') return {ok:false,reason:'pseudo_mask_failed'};
  }
}
return {ok:true};
'''


class Observer:
    def __init__(self, script, output, scenario=None, required=False, contract=None, contract_sha256=None):
        self.script = script
        self.filename = os.path.normcase(str(script))
        self.output = output
        self.sequence = 0
        self.actions = 0
        self.assertions = 0
        self.passed = 0
        self.failed = False
        self.drivers = []
        self.pending = {}
        self.assert_lines = {}
        self.dynamic_assertions = set()
        self.business_steps = []
        self.current_step = None
        self.business_errors = []
        self.required = required
        self.used_hooks = False
        self.reads = 0
        self.elements = {}
        self.last_failed_target = None
        self.raw_execute = None
        self.screenshots = {}
        self.scenario = scenario if isinstance(scenario, dict) else {}
        self.expected_steps = self.scenario.get('steps', [])
        if not isinstance(self.expected_steps, list):
            self.expected_steps = []
        self.contract_checker = None
        self.contract_error = None
        self.execution_contract_sha256 = contract_sha256
        if contract is not None:
            if self.execution_contract_sha256 is None:
                encoded = (json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
                self.execution_contract_sha256 = hashlib.sha256(encoded).hexdigest()
            try:
                source = dict(self.scenario, execution_contract=contract)
                self.contract_checker = checks.RuntimeChecks(checks.prepare_contract(source))
            except ValueError as exc:
                self.contract_error = str(exc)
        elif required:
            self.contract_error = '사전 확정한 실행 계약이 없습니다. 독립 기대 결과 검사를 수행할 수 없습니다.'
        tree = ast.parse(script.read_bytes(), filename=str(script))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                self.assert_lines[node.lineno] = node.end_lineno or node.lineno
                if any(isinstance(child, (ast.Name, ast.Attribute, ast.Call, ast.Subscript)) for child in ast.walk(node.test)):
                    self.dynamic_assertions.add(node.lineno)

    def capture_screen(self, phase, driver=None, final=False):
        if phase in self.screenshots:
            return
        driver = driver or (self.drivers[-1] if self.drivers else None)
        if driver is None and not final:
            return
        record = dict(phase=phase, file=None, sha256=None, policy=SCREENSHOT_POLICY,
                      captured_at=now(), status='NOT_CAPTURED', reason='no_browser')
        self.screenshots[phase] = record
        if driver is None or self.raw_execute is None:
            return
        token = 'ktl-evidence-mask-' + os.urandom(10).hex()
        frozen, applied, raw = False, False, None
        try:
            def command(name, params):
                return self.raw_execute(driver, name, params).get('value')

            def cdp(name, params=None):
                return command('executeCdpCommand', dict(cmd=name, params=params or {}))

            def safe_tree():
                tree = cdp('DOM.getDocument', dict(depth=-1, pierce=True))
                if not isinstance(tree, dict) or not isinstance(tree.get('root'), dict):
                    raise RuntimeError('shadow_dom_unverified')
                pending = [tree['root']]
                while pending:
                    node = pending.pop()
                    if node.get('shadowRootType') in {'open', 'closed'}:
                        raise RuntimeError('shadow_dom_unsupported')
                    pending.extend(node.get('children', []))
                    pending.extend(node.get('shadowRoots', []))
                    if isinstance(node.get('contentDocument'), dict):
                        pending.append(node['contentDocument'])

            safe_tree()
            applied = True
            state = command('w3cExecuteScript', dict(script=_SCREENSHOT_MASK, args=[token, 'apply']))
            if not isinstance(state, dict) or state.get('ok') is not True:
                raise RuntimeError((state or {}).get('reason', 'mask_unverified'))
            cdp('Page.setWebLifecycleState', dict(state='frozen'))
            frozen = True
            safe_tree()
            encoded = command('screenshot', {})
            raw = base64.b64decode(encoded, validate=True)
            state = command('w3cExecuteScript', dict(script=_SCREENSHOT_MASK, args=[token, 'check']))
            if not isinstance(state, dict) or state.get('ok') is not True:
                raise RuntimeError((state or {}).get('reason', 'mask_unverified'))
            if not raw.startswith(b'\x89PNG\r\n\x1a\n') or len(raw) > 10 * 1024 * 1024:
                raise RuntimeError('invalid_png')
            record['reason'] = None
        except BaseException as exc:
            reason = str(exc)
            record['reason'] = reason if re.fullmatch(r'[a-z_]{1,60}', reason) else 'capture_or_mask_unavailable'
            raw = None
        finally:
            try:
                if frozen:
                    self.raw_execute(driver, 'executeCdpCommand', dict(cmd='Page.setWebLifecycleState', params=dict(state='active')))
                if applied:
                    cleaned = self.raw_execute(driver, 'w3cExecuteScript', dict(script=_SCREENSHOT_MASK, args=[token, 'remove'])).get('value')
                    if not isinstance(cleaned, dict) or cleaned.get('ok') is not True:
                        raise RuntimeError('mask_cleanup_unverified')
            except BaseException:
                raw = None
                record['reason'] = 'mask_cleanup_unverified'
        if raw is not None:
            target = self.script.parent / (phase + '.png')
            try:
                with target.open('xb') as output:
                    output.write(raw)
                record.update(file=target.name, sha256=hashlib.sha256(raw).hexdigest(), status='CAPTURED', reason=None)
            except OSError:
                record['reason'] = 'screenshot_storage_unavailable'
        self.emit('screenshot', screenshot=dict(record))

    def screenshot_result(self):
        for phase in ('before', 'after'):
            self.capture_screen(phase, final=True)
        return [self.screenshots[phase] for phase in ('before', 'after')]

    def fail_business(self, message):
        self.business_errors.append(message)
        if self.current_step:
            self.current_step['error'] = message

    @contextlib.contextmanager
    def business_step(self, order):
        # 시나리오 업무 단계 실행 근거
        self.used_hooks = True
        position = len(self.business_steps) + 1
        if self.current_step is not None:
            self.fail_business('업무 단계는 중첩할 수 없습니다.')
            raise RuntimeError('업무 단계 중첩')
        definition = self.expected_steps[position - 1] if position <= len(self.expected_steps) else {}
        if type(order) is not int or order != position or definition.get('order') != order:
            self.fail_business('시나리오 단계 순서가 일치하지 않습니다.')
            raise RuntimeError('시나리오 단계 순서 불일치')
        expected = definition.get('expected_result')
        if not isinstance(expected, (str, dict, list)) or not expected:
            self.fail_business('단계의 기대 결과가 없습니다.')
            raise RuntimeError('단계 기대 결과 누락')
        if self.contract_error:
            self.fail_business(self.contract_error)
            raise RuntimeError(self.contract_error)
        started = time.monotonic()
        step = dict(sequence=order, step_id=definition.get('step_id') or str(order),
                    action=mask(definition.get('action', '')), target=mask(definition.get('target', '')),
                    expected_result=mask(expected), status='RUNNING', started_at=now(),
                    action_count=0, browser_read_count=0, assertion_count=0, passed_assertion_count=0,
                    dynamic_assertion_count=0, observed_actions=[], error=None, failure_selector=None,
                    independent_checks_passed=False if self.contract_checker else None, check_results=[])
        if not step['action'] or not step['target']:
            self.fail_business('단계 action 또는 target이 없습니다.')
            raise RuntimeError('단계 실행 정보 누락')
        self.current_step = step
        self.last_failed_target = None
        if position == 1:
            self.capture_screen('before')
        if self.contract_checker:
            self.contract_checker.begin(order, self.drivers)
        self.emit('business_step_started', step=dict(step))
        try:
            yield
        except BaseException as exc:
            step['error'] = step['error'] or type(exc).__name__
            step['failure_selector'] = step['failure_selector'] or self.last_failed_target or step.get('actual_selector')
            raise
        finally:
            if not step['error']:
                if not step['assertion_count'] or step['assertion_count'] != step['passed_assertion_count']:
                    step['error'] = '기대 결과 assert 성공 근거가 없습니다.'
                elif not step['dynamic_assertion_count']:
                    step['error'] = '상수 assert만으로 기대 결과를 확인할 수 없습니다.'
                elif not step['action_count'] and not step['browser_read_count']:
                    step['error'] = '해당 단계의 실제 브라우저 동작 또는 조회 근거가 없습니다.'
                else:
                    required_actions = {'open': {'open'}, 'navigate': {'open'}, 'click': {'click'},
                                        'input': {'input'}, 'type': {'input'}, 'clear': {'clear', 'input'},
                                        'submit': {'submit', 'click'}, 'select': {'click', 'input'},
                                        'back': {'back'}, 'forward': {'forward'}, 'refresh': {'refresh'}}
                    allowed = required_actions.get(str(definition.get('action', '')).lower())
                    if allowed and not allowed.intersection(step['observed_actions']):
                        step['error'] = '시나리오 action에 대응하는 브라우저 동작 근거가 없습니다.'
            if self.contract_checker:
                if not step['error']:
                    passed, failure, evidence = self.contract_checker.finish(self.drivers)
                    step['independent_checks_passed'] = passed
                    step['check_results'] = evidence
                    if not passed:
                        step['error'] = failure
                        step['failure_selector'] = self.contract_checker.contract['steps'][order - 1]['target'].get('value')
                else:
                    self.contract_checker.current = None
                    self.contract_checker.network = None
            step.update(status='FAIL' if step['error'] else 'PASS', completed_at=now(),
                        duration_ms=round((time.monotonic() - started) * 1000))
            self.business_steps.append(step)
            self.current_step = None
            if step['error'] or len(self.business_steps) == len(self.expected_steps):
                self.capture_screen('after')
            self.emit('business_step', step=step)

    def business_result(self):
        # 미실행 필수 단계 포함
        strict = self.required or self.used_hooks
        if strict:
            for position in range(len(self.business_steps) + 1, len(self.expected_steps) + 1):
                definition = self.expected_steps[position - 1]
                self.business_steps.append(dict(sequence=position, step_id=definition.get('step_id') or str(position),
                                                action=mask(definition.get('action', '')), target=mask(definition.get('target', '')),
                                                expected_result=mask(definition.get('expected_result', '')), status='SKIPPED',
                                                error='필수 단계가 실행되지 않았습니다.', started_at=None, completed_at=None,
                                                duration_ms=None, failure_selector=None))
        passed = sum(step['status'] == 'PASS' for step in self.business_steps)
        complete = bool(strict and self.expected_steps and len(self.business_steps) == len(self.expected_steps)
                        and passed == len(self.expected_steps) and not self.business_errors)
        independent = bool(self.contract_checker and complete
                           and all(step.get('independent_checks_passed') is True for step in self.business_steps))
        if self.required and not independent:
            complete = False
        failed = next((step for step in self.business_steps if step['status'] != 'PASS'), None)
        return dict(step_evidence_mode='BUSINESS_STEPS' if strict else 'LEGACY_TRACE',
                    business_step_complete=complete if strict else None,
                    required_step_count=len(self.expected_steps) if strict else None,
                    success_step_count=passed if strict else None,
                    failed_step=failed['sequence'] if failed else None,
                    error_message=(failed or {}).get('error') or (self.business_errors[0] if self.business_errors else None),
                    failure_selector=(failed or {}).get('failure_selector'), business_steps=self.business_steps,
                    independent_checks_passed=independent if strict else None,
                    execution_contract_sha256=self.execution_contract_sha256)

    def emit(self, event, **data):
        self.output.write(json.dumps(dict(event=event, **data), ensure_ascii=False, allow_nan=False) + '\n')
        self.output.flush()

    def step(self, action, line, status, started, stamp, error=None):
        self.sequence += 1
        value = dict(sequence=self.sequence, action=action, target=f'{self.script.name}:{line}',
                     status=status, started_at=stamp, completed_at=now(),
                     duration_ms=round((time.monotonic() - started) * 1000))
        if error:
            value['error'] = mask(error)
        if self.current_step:
            value['business_step_order'] = self.current_step['sequence']
            value['selector'] = self.current_step.get('actual_selector')
        self.emit('step', step=value)

    def finish_assertion(self, key, status, error=None):
        pending = self.pending.pop(key, None)
        if pending is None:
            return
        self.assertions += 1
        self.passed += status == 'PASS'
        self.failed |= status != 'PASS'
        line, _, started, stamp = pending
        if self.current_step:
            self.current_step['assertion_count'] += 1
            self.current_step['passed_assertion_count'] += status == 'PASS'
            self.current_step['dynamic_assertion_count'] += status == 'PASS' and line in self.dynamic_assertions
            if status != 'PASS':
                self.current_step['error'] = error or 'assert 실패'
                self.current_step['failure_selector'] = self.current_step.get('actual_selector')
        self.step('assert', line, status, started, stamp, error)

    def trace(self, frame, event, argument):
        if (os.path.normcase(frame.f_code.co_filename) != self.filename
                or frame.f_code.co_name in {'<lambda>', '<listcomp>', '<dictcomp>', '<setcomp>', '<genexpr>'}):
            return None
        key = id(frame)
        if event == 'exception':
            self.finish_assertion(key, 'FAIL' if isinstance(argument[1], AssertionError) else 'ERROR', argument[0].__name__)
        elif event == 'return':
            self.finish_assertion(key, 'PASS')
        elif event == 'line':
            pending = self.pending.get(key)
            if pending and not pending[0] <= frame.f_lineno <= pending[1]:
                self.finish_assertion(key, 'PASS')
            if frame.f_lineno in self.assert_lines and key not in self.pending:
                self.pending[key] = (frame.f_lineno, self.assert_lines[frame.f_lineno], time.monotonic(), now())
        return self.trace

    def source_line(self):
        frame = sys._getframe(1)
        while frame:
            if os.path.normcase(frame.f_code.co_filename) == self.filename:
                return frame.f_lineno
            frame = frame.f_back
        return 0


class ScriptOutput(io.TextIOBase):
    def __init__(self, observer):
        self.observer = observer
        self.buffered = ''
        self.lines = 0

    def write(self, text):
        self.buffered += str(text)
        reserve = max(1, *(len(os.environ.get(name, '')) for name in ('KTL_M04_RBEM_USERNAME', 'KTL_M04_RBEM_PASSWORD')))
        while '\n' in self.buffered or len(self.buffered) > 4000 + reserve:
            self.buffered = _redact(self.buffered)
            if '\n' in self.buffered:
                line, self.buffered = self.buffered.split('\n', 1)
            else:
                line, self.buffered = self.buffered[:4000], self.buffered[4000:]
            if self.lines < 1000:
                self.observer.emit('log', message=mask(line))
                self.lines += 1
        return len(text)

    def flush(self):
        if self.buffered and self.lines < 1000:
            self.observer.emit('log', message=mask(self.buffered))
            self.lines += 1
        self.buffered = ''


def execute(script, scenario=None, required=False, contract=None, contract_sha256=None):
    load_login_settings()
    observer = Observer(script, sys.stdout, scenario, required, contract=contract, contract_sha256=contract_sha256)
    runtime = types.ModuleType('ktl_runtime')
    runtime.business_step = observer.business_step
    previous_runtime = sys.modules.get('ktl_runtime')
    sys.modules['ktl_runtime'] = runtime
    sink = ScriptOutput(observer)
    status, error, browser_version = 'ERROR', None, None
    try:
        from importlib.metadata import version
        from selenium.webdriver.remote.webdriver import WebDriver
        original_session, original_execute = WebDriver.start_session, WebDriver.execute
        observer.raw_execute = original_execute
        if observer.contract_checker:
            observer.contract_checker.raw_execute = original_execute
        actions = {'get': 'open', 'goBack': 'back', 'goForward': 'forward', 'refresh': 'refresh',
                   'clickElement': 'click', 'sendKeysToElement': 'input', 'clearElement': 'clear',
                   'submitElement': 'submit', 'switchToWindow': 'window', 'newWindow': 'window',
                   'switchToFrame': 'frame', 'switchToParentFrame': 'frame',
                   'w3cExecuteScript': 'script', 'w3cExecuteScriptAsync': 'script'}

        def start_session(driver, *args, **kwargs):
            nonlocal browser_version
            result = original_session(driver, *args, **kwargs)
            observer.drivers.append(driver)
            browser_version = driver.capabilities.get('browserVersion')
            observer.emit('log', message='Selenium 브라우저 세션 시작')
            return result

        def command(driver, name, params=None):
            line = observer.source_line()
            if name == 'quit':
                observer.capture_screen('after', driver)
            elif name in actions and line and (observer.current_step or not observer.expected_steps):
                observer.capture_screen('before', driver)
            lookup = name in {'findElement', 'findElements', 'findChildElement', 'findChildElements'}
            parameters = params if isinstance(params, dict) else {}
            if observer.contract_checker:
                observer.contract_checker.before_command(driver, name, parameters)
            selector = None
            if lookup:
                selector = mask(str(parameters.get('using', '')) + ': ' + str(parameters.get('value', '')))
                selector = re.sub(r'(?i)(\[\s*(?:value|data-token|data-secret|password)\s*=)[^\]]+', r'\1[숨김]', selector)
                selector = re.sub(r'(?:text\(\)|contains\([^)]*)\s*=\s*[\x22\x27][^\x22\x27]*[\x22\x27]', '[텍스트 조건 숨김]', selector)
            elif parameters.get('id') in observer.elements:
                selector = observer.elements[parameters['id']]
            if lookup:
                try:
                    value = original_execute(driver, name, params)
                except Exception:
                    observer.last_failed_target = selector
                    raise
                items = value.get('value') if isinstance(value, dict) else None
                for item in items if isinstance(items, list) else [items]:
                    if isinstance(item, dict):
                        identity = item.get('element-6066-11e4-a52e-4f735466cecf') or item.get('ELEMENT')
                    else:
                        identity = getattr(item, 'id', None)
                    if isinstance(identity, str) and identity:
                        observer.elements[identity] = selector
                if observer.current_step:
                    observer.current_step['browser_read_count'] += 1
                    observer.current_step['actual_selector'] = selector
                observer.last_failed_target = None
                return value
            if name not in actions or not line:
                try:
                    value = original_execute(driver, name, params)
                except Exception:
                    observer.last_failed_target = selector
                    raise
                if observer.current_step and name != 'quit':
                    observer.current_step['browser_read_count'] += 1
                    if selector:
                        observer.current_step['actual_selector'] = selector
                if observer.contract_checker:
                    observer.contract_checker.observe(driver, name, parameters, value)
                return value
            started, stamp = time.monotonic(), now()
            try:
                value = original_execute(driver, name, params)
            except Exception as exc:
                observer.capture_screen('after', driver)
                observer.last_failed_target = selector
                if observer.current_step:
                    observer.current_step.update(error=type(exc).__name__, failure_selector=selector)
                observer.step(actions[name], line, 'ERROR', started, stamp, type(exc).__name__)
                raise
            observer.actions += 1
            if observer.current_step:
                observer.current_step['action_count'] += 1
                observer.current_step['observed_actions'].append(actions[name])
                if selector:
                    observer.current_step['actual_selector'] = selector
            observer.step(actions[name], line, 'PASS', started, stamp)
            return value

        WebDriver.start_session, WebDriver.execute = start_session, command
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                previous_trace = sys.gettrace()
                try:
                    sys.settrace(observer.trace)
                    runpy.run_path(str(script), run_name='__main__')
                finally:
                    sys.settrace(previous_trace)
            if observer.failed:
                status, error = 'FAIL', '실행 중 실패한 assert가 있습니다.'
            elif not observer.drivers or not observer.actions:
                status, error = 'ERROR', '실제 Selenium 브라우저 동작 근거가 없습니다.'
            elif not observer.assertions or observer.passed != observer.assertions:
                status, error = 'ERROR', '기대 결과 assert의 성공 근거가 없습니다.'
            else:
                status = 'PASS'
        finally:
            WebDriver.start_session, WebDriver.execute = original_session, original_execute
    except AssertionError as exc:
        status, error = 'FAIL', mask(str(exc) or '기대 결과 assert 실패')
    except SystemExit as exc:
        status, error = 'ERROR', '스크립트가 실행을 조기 종료했습니다: ' + mask(exc.code)
    except BaseException as exc:
        status, error = 'ERROR', type(exc).__name__ + ': ' + mask(exc)
    finally:
        sys.settrace(None)
        if previous_runtime is None:
            sys.modules.pop('ktl_runtime', None)
        else:
            sys.modules['ktl_runtime'] = previous_runtime
        sink.flush()
        for driver in observer.drivers:
            try:
                observer.capture_screen('after', driver)
                driver.quit()
            except Exception:
                observer.emit('log', message='브라우저 세션 종료 확인 실패')
    try:
        selenium_version = version('selenium')
    except Exception:
        selenium_version = None
    evidence = observer.business_result()
    if (observer.required or observer.used_hooks) and evidence['business_step_complete'] is not True:
        if status == 'PASS' or observer.used_hooks:
            status = 'FAIL'
        error = error or evidence['error_message'] or '필수 업무 단계 완료 근거가 없습니다.'
    if error:
        evidence['error_message'] = error
    observer.emit('result', status=status, error=error, browser_started=bool(observer.drivers), **evidence,
                  action_count=observer.actions, assertion_count=observer.assertions,
                  passed_assertion_count=observer.passed, browser_version=browser_version,
                  selenium_version=selenium_version, code_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
                  screenshots=observer.screenshot_result())
    return {'PASS': 0, 'FAIL': 1, 'ERROR': 2}[status]


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='strict')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--script', required=True)
    parser.add_argument('--scenario')
    parser.add_argument('--contract')
    parser.add_argument('--require-business-steps', action='store_true')
    args = parser.parse_args()
    scenario = json.loads(Path(args.scenario).read_text(encoding='utf-8-sig')) if args.scenario else None
    contract_raw = Path(args.contract).read_bytes() if args.contract else None
    contract = json.loads(contract_raw.decode('utf-8-sig')) if contract_raw is not None else None
    contract_sha = hashlib.sha256(contract_raw).hexdigest() if contract_raw is not None else None
    sys.exit(execute(Path(args.script).resolve(strict=True), scenario, args.require_business_steps,
                     contract=contract, contract_sha256=contract_sha))
