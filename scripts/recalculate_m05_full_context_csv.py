"""Read-only independent verification of one completed M05 run artifact bundle."""
import csv
import hashlib
import io
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.m05_full_context_csv import recalculate_csv


def verify(run_dir):
    run_dir = Path(run_dir).resolve()
    manifest = json.loads((run_dir / 'run_manifest.json').read_text())
    if manifest.get('status') != 'COMPLETE' or manifest.get('target_event_count') != 20 or manifest.get('official_pass') is not None:
        raise ValueError('Not a completed DEVELOPMENT target-20 run')
    required = {'attempt.json', 'engine_input.json', 'full_predictions.json', 'evidence.csv', 'result.json',
                'validated_manifest.json', 'normalization_provenance.json', 'locked_target_snapshot.json'}
    if not required.issubset(manifest.get('files', {})):
        raise ValueError('Run artifact inventory incomplete')
    for name, expected in manifest['files'].items():
        if Path(name).name != name or hashlib.sha256((run_dir / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Run artifact hash mismatch: ' + name)
    def read(name):
        return json.loads((run_dir / name).read_text())
    payload = read('engine_input.json')
    events = payload['events']
    predictions = read('full_predictions.json')['predictions']
    targets = read('locked_target_snapshot.json')['targets']
    evidence = (run_dir / 'evidence.csv').read_text()
    rows = list(csv.DictReader(io.StringIO(evidence)))
    ids = [e['id'] for e in events]
    pred_ids = [p['id'] for p in predictions]
    target_ids = [t['event_id'] for t in targets]
    if (len(ids) != len(set(ids)) or len(pred_ids) != len(set(pred_ids)) or set(ids) != set(pred_ids)
            or len(target_ids) != 20 or len(set(target_ids)) != 20
            or [r['event_id'] for r in rows] != target_ids
            or manifest['full_event_count'] != len(ids) or manifest['context_event_count'] != len(ids) - 20):
        raise ValueError('Full-context/target cardinality mismatch')
    by_id = {p['id']: p for p in predictions}
    provenance = read('normalization_provenance.json')
    for row, target in zip(rows, targets):
        p = by_id[row['event_id']]
        if (row['predicted_label'] != p['label'] or row['expected_label'] != target['expected_label']
                or row['remove_category'] != target['remove_category']
                or row['predictions_sha256'] != manifest['files']['full_predictions.json']
                or any(row[k] != str(value) for k, value in provenance[row['event_id']].items())
                or row['remove_reason'] != (p['remove_reason'] or '')
                or row['duplicate_of_event_id'] != (p['duplicate_of_event_id'] or '')):
            raise ValueError('Evidence differs from locked target/full prediction/provenance')
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    if hashlib.sha256(canonical).hexdigest() != manifest['binding']['normalized_input_sha256']:
        raise ValueError('Engine input binding mismatch')
    result = read('result.json')
    checked = recalculate_csv(evidence)
    if not all(result[k] == value for k, value in checked.items()):
        raise ValueError('Result differs from evidence CSV')
    return dict(status='PASS', run_mode='DEVELOPMENT', official_pass=None, **checked)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 scripts/recalculate_m05_full_context_csv.py RUN_DIRECTORY')
    print(json.dumps(verify(sys.argv[1]), indent=2))
