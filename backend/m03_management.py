"""M03 저장 시나리오 관리."""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .evaluators import EvaluationError, require


RUN_ID = re.compile(r'DEV-M03-\d{8}T\d{6}-[0-9a-f]{12}')


def _decode(raw):
    try:
        value = json.loads(raw.decode('utf-8'))
    except (ValueError, UnicodeError) as exc:
        raise EvaluationError('M03 저장 기록의 UTF-8 JSON 형식을 확인하세요.', 'ERROR') from exc
    require(isinstance(value, dict), 'M03 저장 기록은 JSON 객체여야 합니다.')
    return value


def _safe(root, path):
    root = Path(root).resolve()
    path = Path(path)
    require(path.is_relative_to(root) and '..' not in path.parts, 'M03 경로 범위를 확인하세요.')
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        require(not current.is_symlink(), 'M03 심볼릭 링크는 사용할 수 없습니다.')
    return path


def _folder(root, run_id):
    require(isinstance(run_id, str) and RUN_ID.fullmatch(run_id), 'DEVELOPMENT M03 실행 ID가 필요합니다.')
    return _safe(root, Path(root).resolve() / 'results/development' / run_id)


def _source(root, run_id, session=None):
    folder = _folder(root, run_id)
    if session is not None:
        session.check('RESULT', run_id)
    source = _safe(root, folder / 'received_payload.json')
    result_path = _safe(root, folder / 'result.json')
    if not source.is_file() or not result_path.is_file():
        raise EvaluationError('저장된 M03 시나리오를 찾을 수 없습니다.', 'NOT_FOUND')
    raw = source.read_bytes()
    payload = _decode(raw)
    result = _decode(result_path.read_bytes())
    require(isinstance(payload, dict) and isinstance(payload.get('scenarios'), list), 'M03 원본 시나리오 형식을 확인하세요.')
    require(result.get('run_id') == run_id and result.get('run_mode') == 'DEVELOPMENT' and result.get('metric_id') == 'M03', 'M03 저장 결과를 확인하세요.')
    return folder, raw, payload, result


def _marker(root, run_id, scenario_id):
    require(isinstance(scenario_id, str) and bool(scenario_id.strip()) and len(scenario_id) <= 256, '시나리오 ID가 필요합니다.')
    digest = hashlib.sha256(scenario_id.encode('utf-8')).hexdigest()
    return _safe(root, _folder(root, run_id) / 'scenario_management' / (digest + '.deleted.json'))


def scenario_deleted(root, run_id, scenario_id, session=None):
    if session is not None:
        session.check('RESULT', run_id)
    marker = _marker(root, run_id, scenario_id)
    if not marker.exists():
        return False
    record = _decode(marker.read_bytes())
    require(record.get('run_id') == run_id and record.get('scenario_id') == scenario_id and record.get('deleted') is True, 'M03 삭제 기록을 확인하세요.')
    return True


def scenario_state(root, run_id, session=None):
    _, _, payload, _ = _source(root, run_id, session)
    active, deleted = [], []
    for row in payload['scenarios']:
        require(isinstance(row, dict), 'M03 원본 시나리오 형식을 확인하세요.')
        identity = row.get('scenario_id')
        if identity and scenario_deleted(root, run_id, identity, session):
            deleted.append(identity)
        else:
            active.append(row)
    return dict(run_mode='DEVELOPMENT', run_id=run_id, scenarios=active, deleted_scenario_ids=deleted)


def list_runs(root, session=None):
    directory = _safe(root, Path(root).resolve() / 'results/development')
    runs = []
    for folder in sorted(directory.glob('DEV-M03-*'), reverse=True):
        if not RUN_ID.fullmatch(folder.name):
            continue
        if session is not None and not session.has('RESULT', folder.name):
            continue
        if not _safe(root, folder / 'received_payload.json').is_file():
            continue
        _, _, payload, result = _source(root, folder.name, session)
        state = scenario_state(root, folder.name, session)
        runs.append(dict(run_id=folder.name, completed_at=result.get('completed_at'), status=result.get('status'),
                         score=result.get('score'), scenario_count=len(payload['scenarios']),
                         active_scenario_count=len(state['scenarios']), deleted_scenario_count=len(state['deleted_scenario_ids']),
                         synthetic=result.get('details', {}).get('external_details', {}).get('synthetic') is True))
    return dict(run_mode='DEVELOPMENT', runs=runs)


def execution_results(root, run_id, session=None):
    _source(root, run_id, session)
    directory = _safe(root, Path(root).resolve() / 'data/development/m04_runner/executions')
    executions = []
    for file in directory.glob('M04-RUN-*/execution.json'):
        if session is not None and not session.has('M04', file.parent.name):
            continue
        file = _safe(root, file)
        job = _decode(file.read_bytes())
        if not re.fullmatch(r'M04-RUN-[0-9a-f]{32}', str(job.get('execution_id', ''))):
            continue
        for case in job.get('cases', []):
            if case.get('source_m03_run_id') != run_id:
                continue
            executions.append(dict(execution_id=job['execution_id'], scenario_id=case.get('scenario_id'),
                                   case_id=case.get('case_id'), status=case.get('status'), execution_status=job.get('status'),
                                   started_at=case.get('started_at') or job.get('started_at'), completed_at=case.get('completed_at'),
                                   duration_ms=case.get('duration_ms'), error=case.get('error')))
    executions.sort(key=lambda row: row.get('started_at') or '', reverse=True)
    return dict(run_mode='DEVELOPMENT', run_id=run_id, executions=executions)


def delete_scenario(root, run_id, payload, session=None):
    require(isinstance(payload, dict) and set(payload) == {'scenario_id'}, '삭제할 scenario_id만 지정하세요.')
    identity = payload['scenario_id']
    folder, raw, source, _ = _source(root, run_id, session)
    if not any(isinstance(row, dict) and row.get('scenario_id') == identity for row in source['scenarios']):
        raise EvaluationError('삭제할 시나리오를 찾을 수 없습니다.', 'NOT_FOUND')
    marker = _marker(root, run_id, identity)
    marker.parent.mkdir(exist_ok=True)
    # 원본 평가 근거 보존
    record = dict(run_id=run_id, scenario_id=identity, deleted=True,
                  deleted_at=datetime.now(timezone.utc).isoformat(), source_sha256=hashlib.sha256(raw).hexdigest())
    if marker.exists():
        require(scenario_deleted(root, run_id, identity, session), 'M03 삭제 기록을 확인하세요.')
        return scenario_state(root, run_id, session)
    temporary = marker.with_name(marker.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as output:
            json.dump(record, output, ensure_ascii=False, indent=2, allow_nan=False)
        try:
            temporary.replace(marker)
        except PermissionError:
            if not marker.exists():
                raise
            require(scenario_deleted(root, run_id, identity, session), 'M03 삭제 기록을 확인하세요.')
    finally:
        if temporary.exists():
            temporary.unlink()
    return scenario_state(root, run_id, session)
