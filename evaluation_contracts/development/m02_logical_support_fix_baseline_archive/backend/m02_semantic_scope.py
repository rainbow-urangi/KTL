"""Post-generation execution ownership. No GT procedure content accepted."""
import copy
from collections import Counter

def scope_steps(snapshot, executions, target_units):
    raw = snapshot['raw_evidence_ledger']
    positions = {r['event_id']: i for i, r in enumerate(raw)}
    if len(positions) != len(raw):
        raise ValueError('Duplicate raw identity')
    owners = {}
    execution_ids = set()
    for execution in executions:
        xid = execution['execution_id']
        if xid in execution_ids:
            raise ValueError('Duplicate execution identity')
        execution_ids.add(xid)
        start = positions.get(execution['start_event_id'])
        end = positions.get(execution.get('end_event_id'))
        if start is None or (end is not None and end < start):
            raise ValueError('Invalid execution anchors')
        # A missing end is not silently inferred from the next BU. Only its
        # explicit start event is certain. Remaining events stay unassigned.
        for i in range(start, (end if end is not None else start) + 1):
            event = raw[i]
            if event['session_id'] != execution['session_id']:
                raise ValueError('Execution crosses session')
            owners.setdefault(event['event_id'], set()).add((xid, execution['business_unit_id']))
    buckets = {bu: [] for bu in target_units}
    audit, mixed, unassigned, outside = [], [], [], []
    seen = set()
    for process in snapshot['processes']:
        for original in process['business_steps']:
            step = copy.deepcopy(original)
            sid = step['generated_step_id']
            if sid in seen:
                raise ValueError('Duplicate generated step')
            seen.add(sid)
            event_owners = [owners.get(eid, set()) for eid in step['source_event_ids']]
            all_owners = set().union(*event_owners)
            units = sorted({bu for _, bu in all_owners})
            xids = sorted({xid for xid, _ in all_owners})
            status = ('CROSS_EXECUTION_MIXED' if len(units) > 1 else
                'ASSIGNED' if len(xids) == 1 and all(event_owners) else 'UNASSIGNED')
            step.update(business_unit_ownership=status, business_unit_ids=units,
                business_unit_id=units[0] if status == 'ASSIGNED' else None,
                execution_ids=xids, matching_eligible=status == 'ASSIGNED' and step['resolution_status'] == 'RESOLVED',
                in_m02_denominator=bool(set(units) & set(target_units)) and status != 'UNASSIGNED')
            audit.append(step)
            if status == 'UNASSIGNED':
                unassigned.append(step)
            elif status == 'CROSS_EXECUTION_MIXED':
                if step['in_m02_denominator']:
                    mixed.append(step)
                else:
                    outside.append(step)
            elif units[0] in buckets:
                buckets[units[0]].append(step)
            else:
                outside.append(step)
    for bu in buckets:
        buckets[bu].sort(key=lambda step: min(positions[eid] for eid in step['source_event_ids']))
        for order, step in enumerate(buckets[bu], 1):
            step['comparison_order'] = order
    for order, step in enumerate(mixed, 1):
        step['comparison_order'] = order
    processes = [{'id': bu, 'source_process_id': 'EXECUTION_OWNERSHIP',
        'canonical_instance_id': 'ALL_FROZEN_SPLIT_FRAGMENTS',
        'procedures': [dict(s, id=s['generated_step_id'], comparison_order=order, label=s['target_field_label'],
            evidence_type='direct' if s['matching_eligible'] else 'unresolved',
            node_id=s['source_node_ids'][0]) for order, s in enumerate(buckets[bu], 1)],
        'unlinked_technical_evidence': []} for bu in target_units]
    if mixed:
        processes.append({'id': 'CROSS_EXECUTION_MIXED', 'source_process_id': 'MIXED',
            'canonical_instance_id': 'MIXED', 'procedures': [dict(s, id=s['generated_step_id'], comparison_order=order,
            label=s['target_field_label'], evidence_type='mixed', node_id=s['source_node_ids'][0]) for order, s in enumerate(mixed, 1)],
            'unlinked_technical_evidence': []})
    return {'processes': processes, 'serializer_version': snapshot['serializer_version'],
        'serializer_rules_hash': snapshot['serializer_rules_hash'], 'ownership_ledger': audit,
        'unassigned_steps': unassigned, 'out_of_scope_steps': outside, 'mixed_steps': mixed,
        'scope_summary': {'target_units': list(target_units),
            'per_business_unit': {bu: len(buckets[bu]) for bu in target_units},
            'mixed_count': len(mixed), 'unassigned_count': len(unassigned),
            'out_of_scope_count': len(outside),
            'total_generated_steps': sum(len(p['procedures']) for p in processes),
            'all_generated_steps': len(audit),
            'ownership_counts': dict(Counter(s['business_unit_ownership'] for s in audit)),
            'policy': 'EXPLICIT_START_END_ANCHORS; MISSING_END_NOT_INFERRED; MIXED_COUNT_ONCE_INELIGIBLE'}}
