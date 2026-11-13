"""M07 사전 회차 정책과 원본 해시 설명. 네트워크ㆍ생성ㆍ실행을 하지 않는다."""
from copy import deepcopy
import hashlib
import json

from ..evaluators import EvaluationError, require


REQUIRED_COUNT = 20
MAX_BYTES = 256 * 1024
POLICY_SCHEMA = 'm07-trial-policy-v1'
DESCRIPTION_SCHEMA = 'm07-trial-description-v1'
LEGACY_BATCH_ID = 'LEGACY-20'


def _text(value, label):
    require(isinstance(value, str) and 0 < len(value) <= 256 and value == value.strip()
            and not any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
                        for char in value), label + '은 공백ㆍ제어 문자 없는 256자 이내 문자열이어야 합니다.')
    return value


def _encoded(value):
    try:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                           allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise EvaluationError('시험 정책과 원본은 유한한 UTF-8 JSON이어야 합니다.', 'ERROR') from None


def _sha(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def normalize_policy(payload):
    """입력 20건의 사전 회차를 검증한다. 원본과 실행 순서를 바꾸지 않는다.

    시나리오ㆍ실행 계약의 유효성은 meeting.prepare_batch가 별도로 검사한다.
    정책이 없으면 기존 전역 중복 금지 계약을 나타내는 한 회차를 반환한다.
    """
    require(isinstance(payload, dict) and {'items'} <= set(payload) <= {'items', 'trial_policy'},
            'M07 일괄 입력에는 items와 선택적인 trial_policy만 지정하세요.')
    rows = payload['items']
    require(isinstance(rows, list) and len(rows) == REQUIRED_COUNT, '시험 입력을 정확히 20건 지정하세요.')
    input_ids = []
    for row in rows:
        require(isinstance(row, dict) and set(row) == {'input_id', 'scenario'}
                and isinstance(row['scenario'], dict), '각 시험 입력에는 input_id와 scenario 객체만 지정하세요.')
        input_ids.append(_text(row['input_id'], 'input_id'))
    require(len(set(input_ids)) == REQUIRED_COUNT, 'input_id는 회차 전체에서 서로 달라야 합니다.')
    # Keep the existing wire-size rule. Canonical indentation is used for hashes,
    # not for deciding whether an otherwise valid compact payload fits the API.
    try:
        size = len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise EvaluationError('시험 정책과 원본은 유한한 UTF-8 JSON이어야 합니다.', 'ERROR') from None
    require(size <= MAX_BYTES, 'M07 일괄 입력은 256 KiB 이내여야 합니다.')
    if 'trial_policy' not in payload:
        return dict(schema_version=POLICY_SCHEMA, mode='LEGACY_UNIQUE_SCENARIOS',
                    batches=[dict(batch_id=LEGACY_BATCH_ID, input_ids=input_ids)])
    policy = payload['trial_policy']
    require(isinstance(policy, dict) and set(policy) == {'batches'},
            'trial_policy에는 batches만 지정하세요. 재시도ㆍ모델ㆍ판정 정책은 입력에서 바꾸지 않습니다.')
    batches = policy['batches']
    require(isinstance(batches, list) and 1 <= len(batches) <= REQUIRED_COUNT,
            '시험 회차는 비어 있지 않은 1~20개 배열이어야 합니다.')
    batch_ids, flattened, normalized = set(), [], []
    for batch in batches:
        require(isinstance(batch, dict) and set(batch) == {'batch_id', 'input_ids'},
                '각 회차에는 batch_id와 input_ids만 지정하세요.')
        batch_id = _text(batch['batch_id'], 'batch_id')
        require(batch_id not in batch_ids, 'batch_id는 서로 달라야 합니다.')
        batch_ids.add(batch_id)
        selected = batch['input_ids']
        require(isinstance(selected, list) and 1 <= len(selected) <= REQUIRED_COUNT,
                '각 회차의 input_ids는 비어 있지 않은 1~20개 배열이어야 합니다.')
        selected = [_text(identity, '회차 input_id') for identity in selected]
        require(len(selected) == len(set(selected)), '같은 회차에 input_id를 중복 지정하지 마세요.')
        flattened.extend(selected)
        normalized.append(dict(batch_id=batch_id, input_ids=selected))
    require(len(flattened) == REQUIRED_COUNT and len(set(flattened)) == REQUIRED_COUNT
            and set(flattened) == set(input_ids), '모든 input_id를 회차 전체에 정확히 한 번씩 지정하세요.')
    require(flattened == input_ids, '회차 input_ids 순서는 원본 items 순서와 같아야 합니다. 임의 재정렬하지 않습니다.')
    return dict(schema_version=POLICY_SCHEMA, mode='EXPLICIT_BATCHES', batches=normalized)


def describe_trial(payload, items, model, prompt_version):
    """검증된 원본과 사전 정책을 해시 고정 가능한 설명으로 만든다.

    items는 prepare_batch의 반환 list이다. 원본 행을 추가ㆍ정규화하거나
    시나리오 내용을 설명에 복사하지 않으며 성공률ㆍ공식 판정을 만들지 않는다.
    """
    policy = normalize_policy(payload)
    model, prompt_version = _text(model, 'model'), _text(prompt_version, 'prompt_version')
    require(isinstance(items, list) and len(items) == REQUIRED_COUNT, '검증된 시험 입력 20건이 필요합니다.')
    assignment = {identity: batch['batch_id'] for batch in policy['batches'] for identity in batch['input_ids']}
    inputs, businesses = [], {}
    for position, (row, prepared) in enumerate(zip(payload['items'], items), 1):
        require(isinstance(prepared, dict) and set(prepared) == {'input_id', 'scenario', 'source_raw'}
                and prepared['input_id'] == row['input_id']
                and _encoded(prepared['source_raw']) == _encoded(row)
                and _encoded(prepared['scenario']) == _encoded(row['scenario']),
                '검증된 시험 입력과 원본 행이 다르거나 순서가 변경됐습니다.')
        scenario = prepared['scenario']
        for key in ('scenario_id', 'business_unit_id', 'workflow_id'):
            _text(scenario.get(key), key)
        batch_id = assignment[row['input_id']]
        inputs.append(dict(position=position, input_id=row['input_id'], batch_id=batch_id,
                           scenario_id=scenario['scenario_id'], business_unit_id=scenario['business_unit_id'],
                           workflow_id=scenario['workflow_id'], source_sha256=_sha(row),
                           scenario_sha256=_sha(scenario)))
        business = businesses.setdefault(scenario['business_unit_id'], dict(
            business_unit_id=scenario['business_unit_id'], input_count=0, batch_ids=[], scenario_ids=[]))
        business['input_count'] += 1
        for key, identity in (('batch_ids', batch_id), ('scenario_ids', scenario['scenario_id'])):
            if identity not in business[key]:
                business[key].append(identity)
    batches = []
    for batch in policy['batches']:
        members = [row for row in inputs if row['batch_id'] == batch['batch_id']]
        batches.append(dict(batch_id=batch['batch_id'], input_ids=deepcopy(batch['input_ids']),
                            input_count=len(members), distinct_scenario_count=len({row['scenario_id'] for row in members}),
                            business_unit_count=len({row['business_unit_id'] for row in members})))
    return dict(schema_version=DESCRIPTION_SCHEMA, policy=policy, model=model, prompt_version=prompt_version,
                input_payload_sha256=_sha(payload), input_count=REQUIRED_COUNT, denominator=REQUIRED_COUNT,
                distinct_scenario_count=len({row['scenario_id'] for row in inputs}),
                business_unit_count=len(businesses), batch_count=len(batches), inputs=inputs,
                batches=batches, business_units=list(businesses.values()),
                max_attempts_per_input=1, automatic_retry_count=0, stop_remaining_on_http_429=True,
                run_mode='DEVELOPMENT', official_pass=None)
