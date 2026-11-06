"""M03 원본에 연결한 개발용 실행 조건. 개정본과 실행 입력을 별도로 보존한다."""
import copy
import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .evaluators import EvaluationError, require
from .m04.checks import prepare_contract, _safe_literal, _target


_LOCK = threading.RLock()
_RUN = re.compile(r'DEV-M03-\d{8}T\d{6}-[a-f0-9]{12}')
_HASH = re.compile(r'[a-f0-9]{64}')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _safe(root, path):
    root, path = Path(root).resolve(), Path(path).absolute()
    require(path.is_relative_to(root), '실행 조건 저장 경로를 확인하세요.')
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        require(not current.is_symlink() and current.resolve() == current, '연결된 실행 조건 경로는 사용할 수 없습니다.')
    return path


def _directory(root, run_id, scenario_id):
    key = sha((run_id + '\0' + scenario_id).encode('utf-8'))
    return _safe(root, Path(root) / 'data/development/execution_contexts' / key)


def _read(root, run_id, source):
    if not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
        return None
    folder = _directory(root, run_id, source['scenario_id'])
    pointer = _safe(root, folder / 'current.json')
    if not pointer.is_file():
        return None
    current = json.loads(pointer.read_bytes())
    require(isinstance(current, dict) and isinstance(current.get('revision_id'), str)
            and _HASH.fullmatch(current['revision_id']), '실행 조건 개정 포인터가 올바르지 않습니다.')
    raw = _safe(root, folder / (current['revision_id'] + '.json')).read_bytes()
    require(sha(raw) == current.get('sha256'), '실행 조건 개정 SHA-256 불일치')
    record = json.loads(raw)
    content = {key: value for key, value in record.items() if key not in {'revision_id', 'saved_at'}}
    require(sha(encoded(content)) == record.get('revision_id') == current['revision_id']
            and record.get('m03_run_id') == run_id and record.get('scenario_id') == source['scenario_id'],
            '실행 조건 개정 식별 정보가 일치하지 않습니다.')
    return record


def _overlay(source, expected_results):
    steps = source.get('steps', [])
    require(isinstance(expected_results, list) and len(expected_results) == len(steps),
            '모든 단계의 기대 결과를 순서대로 입력하세요.')
    effective = copy.deepcopy(source)
    for index, (step, value) in enumerate(zip(effective['steps'], expected_results), 1):
        require(isinstance(value, dict) and set(value) == {'order', 'expected_result'}
                and type(value.get('order')) is int and value['order'] == index
                and isinstance(value.get('expected_result'), str) and 0 < len(value['expected_result'].strip()) <= 2000,
                '단계별 기대 결과는 순서와 비어 있지 않은 문자열이 필요합니다.')
        try:
            _safe_literal(value['expected_result'])
        except ValueError as exc:
            raise EvaluationError(str(exc), 'NOT_READY') from None
        step['expected_result'] = value['expected_result'].strip()
    return effective


def resolve(root, run_id, source, config):
    """새 작업에 사용할 입력을 결정한다. 원본 dict와 과거 작업은 수정하지 않는다."""
    record = _read(root, run_id, source)
    effective = copy.deepcopy(source)
    if record is not None:
        require(record.get('source_scenario_sha256') == sha(encoded(source)),
                'M03 원본이 저장 조건과 달라졌습니다. 현재 원본으로 실행 조건을 다시 저장하세요.')
        effective = _overlay(source, record['expected_results'])
        effective['execution_contract'] = copy.deepcopy(record['execution_contract'])
    try:
        contract = prepare_contract(effective, config)
    except ValueError as exc:
        raise EvaluationError('실행 준비 필요: ' + str(exc), 'NOT_READY') from None
    return dict(scenario=effective, contract=contract,
                revision_id=record['revision_id'] if record else None)


def editor(root, run_id, source, config):
    record = _read(root, run_id, source)
    expected = [dict(order=index, expected_result=(step.get('expected_result') if isinstance(step.get('expected_result'), str) else ''))
                for index, step in enumerate(source['steps'], 1)]
    contract = None
    if record is not None:
        expected, contract = record['expected_results'], record['execution_contract']
    try:
        prepared = resolve(root, run_id, source, config)
        contract = prepared['contract']
        ready, notice = True, ''
    except EvaluationError as exc:
        ready, notice = False, str(exc)
    if contract is None:
        definitions = []
        for step in source['steps']:
            target = dict(by='css selector', value='')
            if step['action'] in {'open', 'navigate'}:
                target = dict(url='')
                if isinstance(step.get('url'), str):
                    try:
                        target = _target(dict(url=step['url']))
                    except ValueError:
                        pass
            definitions.append(dict(order=step['order'], action=step['action'], target=target, checks=[]))
        contract = dict(version=1, scenario_id=source['scenario_id'], steps=definitions)
    # 편집 시작값에도 인증 문자열을 노출하지 않는다.
    for value in expected:
        try:
            _safe_literal(value['expected_result'])
        except ValueError:
            value['expected_result'] = ''
    return dict(m03_run_id=run_id, scenario_id=source['scenario_id'], source_scenario_sha256=sha(encoded(source)),
                saved_revision_id=record['revision_id'] if record else None, execution_ready=ready,
                execution_notice=notice, execution_contract=copy.deepcopy(contract), expected_results=copy.deepcopy(expected))


def save(root, run_id, source, config, contract, expected_results):
    require(isinstance(run_id, str) and _RUN.fullmatch(run_id), '저장된 M03 실행 ID가 필요합니다.')
    effective = _overlay(source, expected_results)
    effective['execution_contract'] = contract
    try:
        prepared = prepare_contract(effective, config)
    except ValueError as exc:
        raise EvaluationError('실행 조건을 확인하세요: ' + str(exc), 'NOT_READY') from None
    expected = [dict(order=step['order'], expected_result=step['expected_result']) for step in effective['steps']]
    content = dict(version=1, run_mode='DEVELOPMENT', m03_run_id=run_id, scenario_id=source['scenario_id'],
                   source_scenario_sha256=sha(encoded(source)), execution_contract=prepared, expected_results=expected)
    revision = sha(encoded(content))
    folder = _directory(root, run_id, source['scenario_id'])
    with _LOCK:
        folder.mkdir(parents=True, exist_ok=True)
        path = _safe(root, folder / (revision + '.json'))
        if path.exists():
            raw = path.read_bytes()
            existing = json.loads(raw)
            require({k: v for k, v in existing.items() if k not in {'revision_id', 'saved_at'}} == content
                    and existing.get('revision_id') == revision, '기존 실행 조건 개정 내용이 일치하지 않습니다.')
        else:
            raw = encoded(dict(content, revision_id=revision, saved_at=datetime.now(timezone.utc).isoformat()))
            with path.open('xb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
        pointer = _safe(root, folder / 'current.json')
        temporary = _safe(root, folder / (uuid.uuid4().hex + '.tmp'))
        try:
            with temporary.open('xb') as output:
                output.write(encoded(dict(revision_id=revision, sha256=sha(raw))))
                output.flush()
                os.fsync(output.fileno())
            for attempt in range(20):
                try:
                    temporary.replace(pointer)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(.025)
        finally:
            if temporary.exists():
                temporary.unlink()
    return editor(root, run_id, source, config)
