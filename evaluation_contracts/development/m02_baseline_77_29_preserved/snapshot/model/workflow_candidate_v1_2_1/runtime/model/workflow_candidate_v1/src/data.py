"""검증된 논리 선택과 학습/평가 metadata를 분리합니다."""
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

RAW_FIELDS = ('event_id', 'session_id', 'event_time', 'event_type', 'interaction_type',
              'element_tag', 'api_method', 'api_status_code', 'api_path', 'page_url',
              'page_title', 'target_selector')

def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def time_of(e):
    return datetime.fromisoformat(e['event_time'].replace('Z', '+00:00')).timestamp()

def stream_key(e):
    return (e['source_dataset'], e['session_id'])

def sanitize_raw(row, source):
    out = {k: row.get(k, '') for k in RAW_FIELDS}
    out['source_dataset'] = source
    return out

def load_logical(root, directory):
    """Membership는 데이터 구성에만 사용하고 execution metadata는 별도로 반환합니다."""
    root, directory = Path(root), Path(directory)
    manifest = json.loads((directory/'dataset_manifest.json').read_text())
    if manifest.get('official') is not False:
        raise ValueError('DEVELOPMENT dataset required')
    for entry in manifest['files']:
        if sha(directory/entry['path']) != entry['sha256']:
            raise ValueError('Logical artifact hash mismatch: '+entry['path'])
    raw = {}
    for source, spec in manifest['sources'].items():
        for f in spec['files']:
            p = (root/f['path']).resolve()
            if not p.is_relative_to(root.resolve()) or sha(p) != f['sha256']:
                raise ValueError('Source path/hash mismatch')
            rows = read_csv(p)
            if len(rows) != f['row_count']:
                raise ValueError('Row count mismatch')
            if p.name == 'events.csv':
                for row in rows:
                    k = (source, row['event_id'])
                    if k in raw:
                        raise ValueError('Duplicate event ID')
                    raw[k] = sanitize_raw(row, source)
    executions = read_csv(directory/'execution_manifest.csv')
    active = {r['execution_id']: r for r in executions if r['active'].lower() == 'true'}
    metadata, selected = {}, []
    for item in read_csv(directory/'execution_event_index.csv'):
        if item['execution_id'] not in active:
            raise ValueError('Inactive membership')
        k = (item['source_dataset'], item['event_id'])
        e = raw[k]
        if k in metadata or e['session_id'] != item['source_session_id']:
            raise ValueError('Overlap or session mismatch')
        metadata[k] = active[item['execution_id']]
        selected.append(e)
    selected.sort(key=lambda e: (*stream_key(e), time_of(e), e['event_id']))
    grouped = defaultdict(list)
    for e in selected:
        grouped[metadata[(e['source_dataset'],e['event_id'])]['execution_id']].append(e)
    for eid, row in active.items():
        ev = grouped[eid]
        if (len(ev) != int(row['event_count']) or ev[0]['event_id'] != row['start_event_id']
            or ev[-1]['event_id'] != row['end_event_id'] or ev[0]['event_time'] != row['start_time']
            or ev[-1]['event_time'] != row['end_time']):
            raise ValueError('Execution provenance mismatch: '+eid)
    # Session boundaries alone reset inference state; execution boundaries do not.
    streams = defaultdict(list)
    for e in selected:
        streams[stream_key(e)].append(e)
    return list(streams.values()), metadata, manifest

def boundary_labels(stream, metadata):
    labels = []
    previous = None
    for e in stream:
        owner = metadata[(e['source_dataset'], e['event_id'])]['execution_id']
        labels.append(int(previous is not None and owner != previous))
        previous = owner
    return labels
