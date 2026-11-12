"""브라우저 표시 전 인증과 Chrome 세션 전달만 제공한다.

업무 페이지 이동, 요소 조작, 기대 결과 판정은 생성된 스크립트가 수행한다.
인증 응답과 토큰은 파일이나 로그에 남기지 않는다.
"""
import json
import os
from urllib.request import HTTPRedirectHandler, Request, build_opener
from weakref import WeakKeyDictionary


TARGET_ORIGIN = 'https://rainbowlab.ai.kr'
AUTH_URL = TARGET_ORIGIN + '/api/auth/login'
_BOOTSTRAPS = WeakKeyDictionary()
_SESSION_PRESENT = ('return window === window.top && location.origin === '
                    + json.dumps(TARGET_ORIGIN)
                    + ' && typeof localStorage.getItem("token") === "string"'
                    + ' && localStorage.getItem("token").length > 0;')


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _preauthenticate():
    account = os.environ.get('KTL_M04_RBEM_USERNAME', '')
    secret = os.environ.get('KTL_M04_RBEM_PASSWORD', '')
    if not account.strip() or not secret:
        raise RuntimeError('시험 계정 연결이 필요합니다.')
    raw = value = request = None
    try:
        request = Request(AUTH_URL, method='POST',
                          data=json.dumps({'loginId': account, 'password': secret}).encode('utf-8'),
                          headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        with build_opener(_RejectRedirects()).open(request, timeout=30) as response:
            if type(response.status) is not int or response.status != 200 or response.geturl() != AUTH_URL:
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
        raise RuntimeError('시험 계정 로그인에 실패했습니다. 계정과 연결 상태를 확인하세요.') from None
    finally:
        # Python 문자열 자체를 덮어쓴다고 보장하지 않으며, 작업용 참조만 해제한다.
        account = secret = raw = value = request = None


def _quit_silently(driver):
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass


def authenticated_chrome():
    """인증에 성공한 다음 Chrome을 생성하고 첫 문서용 세션을 준비한다."""
    session = _preauthenticate()
    driver = source = result = None
    try:
        from selenium import webdriver

        options = webdriver.ChromeOptions()
        options.add_argument('--window-size=1440,1100')
        if os.environ.get('KTL_M04_HEADLESS') != '0':
            options.add_argument('--headless=new')
        driver = webdriver.Chrome(options=options)
        source = ('(()=>{if(window!==window.top||location.origin!==' + json.dumps(TARGET_ORIGIN)
                  + ')return;const state=' + json.dumps(session, ensure_ascii=True)
                  + ';localStorage.setItem("token",state.token);})();')
        result = driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': source})
        identifier = result.get('identifier') if isinstance(result, dict) else None
        if not isinstance(identifier, str) or not identifier:
            raise ValueError('Missing session bootstrap identifier')
        _BOOTSTRAPS[driver] = identifier
        return driver
    except Exception:
        _quit_silently(driver)
        raise RuntimeError('로그인 세션을 Chrome에 준비하지 못했습니다.') from None
    finally:
        session.clear()
        source = result = None


def complete_authentication(driver):
    """첫 업무 이동 후 세션 존재를 확인하고 일회성 초기화 스크립트를 제거한다."""
    try:
        identifier = _BOOTSTRAPS.pop(driver, None)
    except (TypeError, ValueError):
        identifier = None
    if identifier is None:
        raise RuntimeError('초기화할 Chrome 로그인 세션이 없습니다.')
    try:
        try:
            present = driver.execute_script(_SESSION_PRESENT)
        finally:
            driver.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument', {'identifier': identifier})
        if present is not True:
            raise ValueError('Authenticated origin session required')
    except Exception:
        _quit_silently(driver)
        raise RuntimeError('Chrome 로그인 세션 초기화를 완료하지 못했습니다.') from None
