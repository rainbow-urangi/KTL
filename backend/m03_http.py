"""M03 외부 생성기 HTTP JSON 연동."""
import base64
import hashlib
import ipaddress
import json
import os
import re
import socket
import uuid
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from urllib import error, parse, request

from .evaluators import EvaluationError, require


MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
HTTP_KEYS = {'url', 'timeout_seconds', 'max_response_bytes', 'auth_env', 'auth_header', 'auth_prefix'}


def _url(value):
    require(isinstance(value, str) and 0 < len(value) <= 2048, 'M03 HTTP URL을 입력하세요.')
    try:
        parsed = parse.urlsplit(value)
        parsed.port
    except ValueError:
        raise EvaluationError('M03 HTTP URL 형식을 확인하세요.', 'ERROR') from None
    require(parsed.scheme in {'http', 'https'} and bool(parsed.hostname)
            and not parsed.username and not parsed.password and not parsed.fragment
            and not any(ord(char) <= 32 for char in value), 'M03 HTTP(S) URL에는 인증정보나 fragment를 넣을 수 없습니다.')
    require(not any(re.search(r'password|token|secret|api[_-]?key|authorization', key, re.I)
                    for key, _ in parse.parse_qsl(parsed.query)), 'M03 HTTP 인증정보는 URL 대신 환경변수로 지정하세요.')
    host = parsed.hostname.casefold()
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host.rstrip('.') == 'localhost'
    path = parsed.path
    for _ in range(3):
        path = parse.unquote(path)
    if local and (path.rstrip('/') == '/api/m03/generate'
                  or path.startswith('/api/development/m03/')
                  or path.rstrip('/') == '/api/integrations/m03/result'):
        raise EvaluationError('M03 수신 API가 아닌 외부 생성기 URL을 지정하세요. 자기 호출은 허용하지 않습니다.', 'ERROR')
    return value


def http_settings(config, incomplete=False):
    options = config.get('m03', {}).get('http', {})
    require(isinstance(options, dict) and set(options) <= HTTP_KEYS, 'M03 HTTP 설정 항목을 확인하세요. 인증값은 저장하지 않습니다.')
    url = options.get('url', '')
    if url:
        _url(url)
    elif not incomplete:
        raise EvaluationError('M03 외부 생성기 HTTP URL이 설정되지 않았습니다.', 'NOT_CONFIGURED')
    timeout = options.get('timeout_seconds', config.get('adapter_timeout_seconds', 120))
    maximum = options.get('max_response_bytes', MAX_RESPONSE_BYTES)
    require(type(timeout) in (int, float) and 1 <= timeout <= 120, 'M03 HTTP timeout_seconds는 1~120초입니다.')
    require(type(maximum) is int and 1024 <= maximum <= MAX_RESPONSE_BYTES, 'M03 HTTP 응답 상한은 1 KiB~4 MiB입니다.')
    env = options.get('auth_env', '')
    header = options.get('auth_header', 'Authorization')
    prefix = options.get('auth_prefix', 'Bearer ')
    require(isinstance(env, str) and (not env or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', env)), 'M03 auth_env에는 환경변수 이름만 입력하세요.')
    require(isinstance(header, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{0,63}', header)
            and header.casefold() not in {'host', 'content-length', 'content-type', 'x-ktl-m03-adapter'}, 'M03 인증 header 이름을 확인하세요.')
    require(prefix in ('', 'Bearer ', 'Token '), 'M03 auth_prefix는 빈 문자열, Bearer 또는 Token입니다.')
    if env and not incomplete and not os.environ.get(env):
        raise EvaluationError('M03 인증 환경변수 값이 서버에 설정되지 않았습니다.', 'NOT_CONFIGURED')
    if env and not incomplete:
        secret=os.environ[env]
        require(secret.isascii() and len(secret)<=8192 and not any(char in secret for char in '\r\n'), 'M03 인증 환경변수 형식을 확인하세요.')
    return dict(url=url, timeout_seconds=timeout, max_response_bytes=maximum,
                auth_env=env, auth_header=header, auth_prefix=prefix)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _folder(root, identity):
    root = Path(root).resolve()
    path = root / 'data/development/m03_http' / identity
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        require(not current.is_symlink(), 'M03 근거 경로에 심볼릭 링크를 사용할 수 없습니다.')
    path.mkdir(parents=True, exist_ok=False)
    return path


def call_http(root, config, payload):
    """단일 POST 전송과 원본 입력·응답 바이트 보관."""
    settings = http_settings(config)
    from .m03_integration import _project_path
    outgoing = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    files = outgoing['analysis_input']['files']
    total = 0
    for entry in files:
        path = _project_path(Path(root).resolve(), entry['path'])
        total += path.stat().st_size
        require(total <= MAX_REQUEST_BYTES // 2, 'M03 HTTP 분석 입력은 총 4 MiB 이하여야 합니다. 더 큰 입력은 subprocess 어댑터를 사용하세요.')
        with path.open('rb') as source:
            raw = source.read(MAX_REQUEST_BYTES//2+1)
        require(len(raw)<=MAX_REQUEST_BYTES//2,'M03 HTTP 분석 입력 크기가 전송 준비 중 변경되었습니다.')
        require(hashlib.sha256(raw).hexdigest() == entry['sha256'], 'M03 HTTP 전송 전 분석 입력 SHA-256 불일치')
        entry['content_base64'] = base64.b64encode(raw).decode('ascii')
    body = (json.dumps(outgoing, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n').encode('utf-8')
    require(len(body) <= MAX_REQUEST_BYTES, 'M03 HTTP 요청 크기 상한 8 MiB를 초과했습니다.')
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json', 'X-KTL-M03-Adapter': '1'}
    secret = os.environ.get(settings['auth_env'], '') if settings['auth_env'] else ''
    require(secret.isascii() and len(secret)<=8192 and not any(char in secret for char in '\r\n'), 'M03 인증 환경변수 형식을 확인하세요.')
    if secret:
        headers[settings['auth_header']] = settings['auth_prefix'] + secret
    identity = 'M03-HTTP-' + uuid.uuid4().hex
    folder = _folder(root, identity)
    (folder / 'request.json').write_bytes(body)
    endpoint = parse.urlsplit(settings['url'])
    proof = dict(attempt_id=identity, started_at=datetime.now(timezone.utc).isoformat(),
                 request_sha256=hashlib.sha256(body).hexdigest(), request_bytes=len(body),
                 endpoint=parse.urlunsplit((endpoint.scheme, endpoint.netloc, endpoint.path, '', '')),
                 endpoint_sha256=hashlib.sha256(settings['url'].encode('utf-8')).hexdigest(),
                 timeout_seconds=settings['timeout_seconds'],
                 source_module=config['m03']['source_module'],source_version=config['m03']['source_version'],
                 transport='HTTP', response_policy='HASH_ONLY', status='STARTED')
    result = None
    failure = None
    raw = b''
    try:
        opener = request.build_opener(_NoRedirect())
        req = request.Request(settings['url'], data=body, headers=headers, method='POST')
        try:
            with opener.open(req, timeout=settings['timeout_seconds']) as response:
                proof['http_status'] = response.status
                raw = response.read(settings['max_response_bytes'] + 1)
        except error.HTTPError as exc:
            proof['http_status'] = exc.code
            raw = exc.read(settings['max_response_bytes'] + 1)
            raise EvaluationError('M03 외부 생성기가 HTTP 오류를 반환했습니다.', 'ERROR') from None
        proof['response_truncated'] = len(raw) > settings['max_response_bytes']
        require(not proof['response_truncated'], 'M03 외부 생성기 응답 크기 상한을 초과했습니다.')
        if secret and secret.encode('utf-8') in raw:
            raise EvaluationError('M03 외부 생성기 응답에 인증정보가 포함되어 원문 보관을 차단했습니다.', 'ERROR')
        def checked_object(pairs):
            # Check every decoded pair before duplicate keys discard earlier values.
            if secret:
                pending = [item for pair in pairs for item in pair]
                while pending:
                    value = pending.pop()
                    if isinstance(value, str) and secret in value:
                        raise EvaluationError('M03 외부 생성기 응답에 인증정보가 포함되어 원문 보관을 차단했습니다.', 'ERROR')
                    # Child objects were already checked by this parsing hook.
                    if isinstance(value, list):
                        pending.extend(value)
            return dict(pairs)
        try:
            result = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=checked_object,
                                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            raise EvaluationError('M03 외부 생성기는 UTF-8 JSON 객체를 반환해야 합니다.', 'ERROR') from None
        require(isinstance(result, dict), 'M03 외부 생성기는 시나리오 JSON 객체 하나를 반환해야 합니다.')
        (folder / 'response.json').write_bytes(raw)
        proof.update(status='RECEIVED', response_policy='ORIGINAL_JSON')
    except (error.URLError, TimeoutError, socket.timeout, OSError, HTTPException):
        failure = EvaluationError('M03 외부 생성기 연결 실패 또는 응답 시간 초과입니다.', 'ERROR')
    except (ValueError, UnicodeError):
        failure = EvaluationError('M03 HTTP URL 또는 header의 전송 형식을 확인하세요.', 'ERROR')
    except EvaluationError as exc:
        failure = exc
    finally:
        proof.update(completed_at=datetime.now(timezone.utc).isoformat(), response_bytes=len(raw),
                     response_sha256=hashlib.sha256(raw).hexdigest(), response_truncated=len(raw)>settings['max_response_bytes'])
        if failure:
            proof['status'] = 'ERROR'
        (folder / 'evidence.json').write_text(json.dumps(proof, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    if failure:
        raise EvaluationError(str(failure) + ' 근거 ID: ' + identity, failure.status) from None
    return result, proof
