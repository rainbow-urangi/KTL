"""M03 생성 입력과 분리된 평가 전용 정답 순서. 원본을 수정하거나 추론하지 않는다."""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path, PureWindowsPath

from .evaluators import EvaluationError, require


SCHEMA_VERSION = 'm03-order-reference-v1'
MATCHING_POLICY = 'EXACT_ACTION_TARGET_SEQUENCE'
MAX_REFERENCE_BYTES = 1024 * 1024
MAX_STEPS = 1000


def _text(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and bool(value.strip())


def _timestamp(value, field):
    require(isinstance(value, str) and 0 < len(value) <= 80, field + ' requires an ISO timestamp with timezone')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise EvaluationError(field + ' requires an ISO timestamp with timezone', 'ERROR') from None
    require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
            field + ' requires an ISO timestamp with timezone')
    return stamp


def _valid_steps(steps):
    return (isinstance(steps, list) and 1 <= len(steps) <= MAX_STEPS
            and all(isinstance(step, dict) and type(step.get('order')) is int and step['order'] == index
                    and _text(step.get('action')) and _text(step.get('target'))
                    for index, step in enumerate(steps, 1)))


def _validate_unit(unit):
    require(isinstance(unit, dict) and _text(unit.get('business_unit_id')) and _text(unit.get('workflow_id')),
            'M03 reference unit requires business_unit_id and workflow_id')
    require(_valid_steps(unit.get('steps')), 'M03 reference steps require 1..1000 ordered action/target objects')
    return unit


def validate_reference(reference):
    """검증된 동일 dict를 반환한다. 파일 접근·현재 시각 비교·입력 변경은 하지 않는다."""
    require(isinstance(reference, dict), 'M03 evaluation reference must be an object')
    require(reference.get('schema_version') == SCHEMA_VERSION, 'Unsupported M03 evaluation reference schema')
    require(_text(reference.get('reference_id')), 'M03 evaluation reference_id required')
    require(reference.get('evaluation_only') is True, 'M03 reference must be evaluation-only')
    require(reference.get('matching_policy') == MATCHING_POLICY, 'Unsupported M03 reference matching policy')
    _timestamp(reference.get('fixed_at'), 'M03 reference fixed_at')
    units = reference.get('business_units')
    require(isinstance(units, list) and 1 <= len(units) <= 10, 'M03 reference requires 1..10 business units')
    for unit in units:
        _validate_unit(unit)
    identities = [unit['business_unit_id'] for unit in units]
    require(len(set(identities)) == len(identities), 'M03 reference business_unit_id must be unique')
    return reference


def _safe_path(root, relative):
    require(isinstance(relative, str) and bool(relative) and '\x00' not in relative,
            'M03 reference project-relative path required')
    supplied = Path(relative)
    windows = PureWindowsPath(relative)
    require(not supplied.is_absolute() and not supplied.drive and not windows.drive and not windows.root
            and '..' not in supplied.parts and '..' not in windows.parts,
            'M03 reference must use a project-relative path without parent traversal')
    root = Path(root).resolve()
    path = root / supplied
    require(path.is_relative_to(root / 'data/evaluation'), 'M03 reference must remain under data/evaluation')
    current = root
    for part in path.relative_to(root).parts:
        current = current / part
        require(not current.is_symlink() and current.resolve() == current, 'Linked M03 reference paths are prohibited')
    return path, path.relative_to(root).as_posix()


def _pairs(items):
    value = {}
    for key, item in items:
        require(key not in value, 'Duplicate M03 reference JSON keys are prohibited')
        value[key] = item
    return value


def load_reference(root, config, dataset_id, mode, submitted_at):
    """신뢰 설정에 등록된 원본 bytes만 검증한다. 미등록은 평가 대기이며 오류는 숨기지 않는다."""
    require(isinstance(config, dict) and _text(dataset_id), 'M03 reference configuration and dataset_id required')
    require(isinstance(mode, str) and mode in {'DEVELOPMENT', 'REFERENCE', 'OFFICIAL'}, 'Invalid M03 reference mode')
    registry = config.get('m03_evaluation_references', {})
    require(isinstance(registry, dict), 'm03_evaluation_references must be an object')
    if dataset_id not in registry:
        return None, {}
    registered = registry[dataset_id]
    require(isinstance(registered, dict) and set(registered) == {'path', 'sha256'},
            'M03 reference registration requires path and sha256')
    expected = registered['sha256']
    require(isinstance(expected, str) and re.fullmatch(r'[0-9a-fA-F]{64}', expected) is not None,
            'M03 reference SHA-256 required')
    try:
        path, relative = _safe_path(root, registered['path'])
    except (OSError, RuntimeError, ValueError):
        raise EvaluationError('Registered M03 evaluation reference path is invalid', 'ERROR') from None
    try:
        with path.open('rb') as source:
            raw = source.read(MAX_REFERENCE_BYTES + 1)
    except OSError:
        raise EvaluationError('Registered M03 evaluation reference cannot be read', 'ERROR') from None
    require(0 < len(raw) <= MAX_REFERENCE_BYTES, 'M03 evaluation reference must be at most 1 MiB')
    actual = hashlib.sha256(raw).hexdigest()
    require(actual == expected.lower(), 'M03 evaluation reference SHA-256 mismatch')
    try:
        reference = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise EvaluationError('M03 evaluation reference must be UTF-8 JSON', 'ERROR') from None
    validate_reference(reference)
    require(_timestamp(reference['fixed_at'], 'M03 reference fixed_at')
            <= _timestamp(submitted_at, 'M03 submitted_at'), 'M03 evaluation reference must be fixed before submission')
    if mode == 'OFFICIAL':
        require(reference.get('synthetic') is False and reference.get('approved_for_official') is True,
                'Official M03 reference requires synthetic=false and approved_for_official=true')
    return reference, {relative: actual}


def compare_business_order(scenario, reference_unit):
    """같은 단위의 action/target 배열을 순서대로 비교한다. 별칭·재정렬·보완은 하지 않는다."""
    _validate_unit(reference_unit)
    scenario = scenario if isinstance(scenario, dict) else {}
    expected = reference_unit['steps']
    steps = scenario.get('steps')
    valid = _valid_steps(steps)
    actual = steps if isinstance(steps, list) else []
    positions = []
    if valid:
        for index in range(max(len(expected), len(actual))):
            left = expected[index] if index < len(expected) else None
            right = actual[index] if index < len(actual) else None
            if (left is None or right is None
                    or (left['action'], left['target']) != (right['action'], right['target'])):
                positions.append(index + 1)
    business_match = scenario.get('business_unit_id') == reference_unit['business_unit_id']
    workflow_match = scenario.get('workflow_id') == reference_unit['workflow_id']
    if not business_match:
        reason = 'BUSINESS_UNIT_MISMATCH'
    elif not workflow_match:
        reason = 'WORKFLOW_MISMATCH'
    elif not valid:
        reason = 'INVALID_SCENARIO_STEPS'
    elif len(actual) != len(expected):
        reason = 'STEP_COUNT_MISMATCH'
    elif positions:
        reason = 'STEP_SEQUENCE_MISMATCH'
    else:
        reason = 'EXACT_MATCH'
    return dict(semantic_order_valid=reason == 'EXACT_MATCH', reason=reason,
                mismatched_positions=positions, expected_step_count=len(expected), actual_step_count=len(actual),
                business_unit_match=business_match, workflow_match=workflow_match, matching_policy=MATCHING_POLICY)
