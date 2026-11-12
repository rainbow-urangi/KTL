"""Learned medoids and capture execution views have distinct scope identities."""
from model.workflow_candidate_v1_2.src.adapter import canonical_for_generator as base_canonical


def canonical_for_generator(tables, model_id):
    model = next(row for row in tables['process_models'] if row['process_model_id'] == model_id)
    if model['canonical_instance_id'] is None:
        return None
    result = base_canonical(tables, model_id)
    result['canonical_kind'] = 'LEARNED_PROCESS_MEDOID'
    result['canonical_instance_id'] = model['canonical_instance_id']
    return result
