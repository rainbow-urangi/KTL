"""사용자 명시 저장 기반 M03 연결 설정."""
import copy
import json
import uuid
from pathlib import Path

from .evaluators import EvaluationError, require
from .m03_http import http_settings


KEYS = {'generator_mode', 'transport', 'http', 'input_manifest', 'source_module', 'source_version', 'business_units'}


def _path(root):
    root = Path(root).resolve()
    path = root / 'data/development/m03_connection.json'
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        require(not current.is_symlink(), 'M03 연결 설정 경로에 심볼릭 링크를 사용할 수 없습니다.')
    return path


def _validate(settings, root):
    require(isinstance(settings, dict) and set(settings) <= KEYS, 'M03 연결 설정 항목을 확인하세요.')
    require(settings.get('generator_mode', 'MOCK') in {'MOCK', 'REAL'}, 'M03 generator_mode는 MOCK 또는 REAL입니다.')
    require(settings.get('transport', 'SUBPROCESS') in {'HTTP', 'SUBPROCESS'}, 'M03 transport는 HTTP 또는 SUBPROCESS입니다.')
    from .m03_integration import _no_truth, _project_path, nonempty
    _no_truth(settings)
    http_settings({'m03': settings}, incomplete=True)
    for name in ('source_module', 'source_version'):
        require(name not in settings or settings[name] == '' or nonempty(settings[name]), 'M03 생성기 이름과 버전은 256자 이내 문자열입니다.')
    require('input_manifest' not in settings or isinstance(settings['input_manifest'],str), 'M03 input_manifest는 프로젝트 내부 상대 경로 문자열입니다.')
    if settings.get('input_manifest'):
        _project_path(Path(root).resolve(), settings['input_manifest'])
    if 'business_units' in settings:
        rows = settings['business_units']
        require(isinstance(rows, list) and len(rows) <= 10 and all(isinstance(row, dict) for row in rows), 'M03 business_units는 최대 10개 업무 객체 배열입니다.')
    return copy.deepcopy(settings)


def apply_connection(root, config):
    effective = copy.deepcopy(config)
    path = _path(root)
    if path.exists():
        try:
            require(path.is_file() and path.stat().st_size <= 1024 * 1024, 'M03 연결 설정 파일 상한은 1 MiB입니다.')
            value = json.loads(path.read_text(encoding='utf-8'))
            require(isinstance(value, dict) and set(value) == {'m03'}, 'M03 연결 설정 파일 형식을 확인하세요.')
            effective['m03'] = _validate(value['m03'], root)
        except (ValueError, UnicodeError, OSError):
            raise EvaluationError('저장된 M03 연결 설정을 읽을 수 없습니다.', 'NOT_CONFIGURED') from None
    return effective


def connection_state(root, config):
    settings = config.get('m03', {})
    public = {key: copy.deepcopy(value) for key, value in settings.items() if key in KEYS} if isinstance(settings, dict) else {}
    if isinstance(public.get('http'),dict):
        from .m03_http import HTTP_KEYS
        public['http']={key:value for key,value in public['http'].items() if key in HTTP_KEYS}
        try:
            http_settings({'m03':public},incomplete=True)
        except EvaluationError:
            public['http']={'url':'','auth_env':''}
    missing = []
    transport = public.get('transport', 'SUBPROCESS')
    for key in ('input_manifest', 'source_module', 'source_version', 'business_units'):
        if not public.get(key):
            missing.append('m03.' + key)
    if transport == 'HTTP':
        if not isinstance(public.get('http'), dict) or not public['http'].get('url'):
            missing.append('m03.http.url')
    elif not config.get('adapters', {}).get('scenario_generation'):
        missing.append('adapters.scenario_generation')
    state = dict(m03=public, saved=_path(root).is_file(), configured=False,
                 current_mode=public.get('generator_mode', 'MOCK'), transport=transport, missing=missing)
    try:
        from .m03_integration import _real_input
        definitions, verified = _real_input(Path(root).resolve(), config)
        state.update(configured=True, status='READY', message='실제 생성기 연결 설정과 분석 입력 검증을 완료했습니다. 외부 응답은 생성 요청 때 확인합니다.',
                     business_unit_count=len(definitions), input_dataset_id=verified['dataset_id'])
    except EvaluationError as exc:
        state.update(status='NOT_CONFIGURED' if missing or exc.status == 'NOT_CONFIGURED' else 'NOT_READY', message=str(exc))
    except (OSError, ValueError, TypeError, KeyError):
        state.update(status='NOT_READY', message='분석 입력 manifest와 파일 경로·형식을 확인하세요.')
    return state


def save_connection(root, config, payload):
    require(isinstance(payload, dict) and set(payload) == {'m03'}, '저장할 m03 연결 설정 객체가 필요합니다.')
    settings = _validate(payload['m03'], root)
    raw = (json.dumps({'m03': settings}, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')
    require(len(raw) <= 1024 * 1024, 'M03 연결 설정 파일 상한은 1 MiB입니다.')
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('xb') as output:
            output.write(raw)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    effective = copy.deepcopy(config)
    effective['m03'] = settings
    return connection_state(root, effective)
