"""M02 공식 비교는 사전 process ID 또는 선택적 GT 독립 pairing을 사용합니다."""
from datetime import datetime
from .evaluators import require, object_list, unique_ids


def validate_fixed_at(value, cutoff, label):
    require(isinstance(value, str), label + ' fixed timestamp required')
    try:
        fixed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        require(False, label + ' invalid timestamp')
    require(fixed.tzinfo is not None and fixed <= cutoff, label + ' must be fixed before evaluation starts')


def official_m02_inputs(process_result, ground_truth, pairing, cutoff):
    instances = object_list(process_result.get('processes'), 'process maps')
    unique_ids(instances, 'process maps')
    gt = object_list(ground_truth.get('processes'), 'Ground Truth')
    require(len(unique_ids(gt, 'Ground Truth')) == 5, 'Official M02 requires 5 GT processes')
    if pairing is None:
        # 사전에 부여된 process ID로만 비교하며 모든 생성 절차를 분모에 유지합니다.
        return process_result, ground_truth
    require(isinstance(pairing, dict) and pairing.get('version') == '1.0', 'Pairing version 1.0 required')
    require(pairing.get('ground_truth_independent') is True, 'GT-independent pairing required')
    validate_fixed_at(pairing.get('fixed_at'), cutoff, 'Pairing')
    pairs = object_list(pairing.get('pairs'), 'pairing pairs')
    instances = object_list(process_result.get('processes'), 'process instances')
    unique_ids(instances, 'process instances')
    gt = object_list(ground_truth.get('processes'), 'Ground Truth')
    scenario_ids = unique_ids(gt, 'Ground Truth')
    require(len(gt) == 5, 'Official M02 requires 5 GT processes')
    for pair in pairs:
        require(all(isinstance(pair.get(k), str) and pair[k].strip() for k in
                    ('scenario_id', 'execution_id', 'process_instance_id', 'selection_method')), 'Pairing fields required')
        require(pair['selection_method'] in {'execution_linked', 'predeclared'}, 'GT-based best-instance selection is prohibited')
    require(len(pairs) == len(scenario_ids) and {p['scenario_id'] for p in pairs} == scenario_ids,
            'Exactly one explicit pairing per GT scenario required')
    by_id = {p['id']: p for p in instances}
    actual = []
    selected = set()
    for pair in pairs:
        require(pair['process_instance_id'] in by_id, 'Invalid paired process instance ID')
        require(pair['process_instance_id'] not in selected, 'A process map cannot be paired twice')
        selected.add(pair['process_instance_id'])
        instance = by_id[pair['process_instance_id']]
        require(instance.get('execution_id') == pair['execution_id'], 'Paired execution ID mismatch')
        # ID lookup only. GT procedure labels never participate in instance selection.
        actual.append({'id': pair['scenario_id'], 'procedures': instance.get('procedures')})
    actual.extend(p for p in instances if p['id'] not in selected)
    unique_ids(actual, 'Mapped process maps')
    return {'processes': actual}, ground_truth
