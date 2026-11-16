"""Event-level view of the existing rule engine. No learned classifier or GT input.

Input events: {id, features:{case_id, activity, ts}}. Activity is the existing
CSV adapter's standardized token, not a label. Batch must retain full sequence
context; evaluate selected held-out events only AFTER inference on that context.
No sequence-length filtering/truncation: those are model batching, not cleaning.
"""
import ast
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

VERSION = 'existing-dataset-cleaning-event-adapter-v1'
ALLOWED_FEATURES = {'case_id', 'activity', 'ts'}


def load_rules(config_path):
    config_path = Path(config_path).resolve()
    config = json.loads(config_path.read_text())
    source = (config_path.parent / config['cleaning_source']['path']).resolve()
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != config['cleaning_source']['sha256']:
        raise ValueError('Cleaning source hash mismatch')
    tree = ast.parse(data, filename=str(source))
    wanted = {'DROP_EXACT', 'DROP_PREFIX', 'should_drop_activity', 'rle_dedupe_rows', 'parse_ts'}
    selected = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name in wanted) or
                (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in wanted for t in n.targets))]
    names = {n.name if isinstance(n, ast.FunctionDef) else n.targets[0].id for n in selected}
    if names != wanted:
        raise ValueError('Original cleaning definitions missing')
    # Compile original nodes unchanged, without loading unrelated torch Dataset.
    ns = {'datetime': datetime}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), ns)
    return ns, config


def predict(events, rules):
    if not isinstance(events, list):
        raise ValueError('events must be a list')
    ids = set(); grouped = {}; rows = []
    for index, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != {'id', 'features'}:
            raise ValueError('Only id/features accepted; no labels')
        eid = event['id']; f = event['features']
        if not isinstance(eid, str) or not eid.strip() or eid in ids:
            raise ValueError('Missing or duplicate event ID')
        ids.add(eid)
        if not isinstance(f, dict) or set(f) != ALLOWED_FEATURES:
            raise ValueError('Exactly case_id/activity/ts features required')
        if not isinstance(f['case_id'], (str, int)) or isinstance(f['case_id'], bool) or not str(f['case_id']).strip():
            raise ValueError('Explicit case_id required')
        if f['activity'] is not None and not isinstance(f['activity'], str):
            raise ValueError('activity must be string or null')
        if f['ts'] is not None and not isinstance(f['ts'], str):
            raise ValueError('ts must be string or null')
        row = dict(f, source_event_pk=eid, _row_index=index)
        rows.append(row)
        # Preserve case identity types, do not hash or merge unrelated cases.
        grouped.setdefault((type(f['case_id']).__name__, f['case_id']), []).append(row)
    def sort_key(row):
        parsed = rules['parse_ts'](row['ts'])
        if parsed is None:
            return True, float(row['_row_index']), row['_row_index']
        try:
            stamp = parsed.timestamp()
        except (OverflowError, OSError, ValueError):
            stamp = float(row['_row_index'])
        return False, stamp, row['_row_index']
    survivors = set(); evidence = {}
    for case in grouped.values():
        case.sort(key=sort_key)
        kept = rules['rle_dedupe_rows'](case)
        kept_ids = {r['source_event_pk'] for r in kept}
        survivors.update(kept_ids)
        previous = None
        for row in case:
            eid = row['source_event_pk']; act = row['activity']
            if eid in kept_ids:
                previous = eid
                evidence[eid] = ('kept', None)
            elif rules['should_drop_activity'](act):
                reason = 'empty_activity' if not act else ('drop_exact' if act in rules['DROP_EXACT'] else 'drop_prefix')
                evidence[eid] = (reason, None)
            else:
                evidence[eid] = ('consecutive_same_activity', previous)
    return {'model_version': VERSION, 'engine_type': 'existing_deterministic_rules',
            'predictions': [{'id':r['source_event_pk'], 'label':'KEEP' if r['source_event_pk'] in survivors else 'REMOVE',
              'remove_reason':None if r['source_event_pk'] in survivors else evidence[r['source_event_pk']][0],
              'duplicate_of_event_id':evidence[r['source_event_pk']][1],
              'activity':r['activity'], 'case_id':r['case_id'], 'source_row_index':r['_row_index']}
             for r in rows]}


def main():
    if len(sys.argv) != 3 or sys.argv[1] != '--model':
        raise SystemExit('usage: m05_baseline_adapter.py --model CONFIG.json')
    rules, config = load_rules(sys.argv[2])
    if config.get('rule_version') != VERSION:
        raise ValueError('Rule version mismatch')
    payload = json.load(sys.stdin)
    if set(payload) != {'events'}:
        raise ValueError('Only events input accepted')
    print(json.dumps(predict(payload['events'], rules), ensure_ascii=False, sort_keys=True))

if __name__ == '__main__':
    main()
