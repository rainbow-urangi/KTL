"""M02 main-web transport for the preserved evaluator, not a new evaluator.
The isolated snapshot re-evaluates frozen process maps; it does not rerun ML.
"""
import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path
from .evaluators import digest, read_json, require, EvaluationError
from .run_storage import save_run, now

DATASET = 'm02_recovery_data_05_exact_five'
FREEZE = 'evaluation_contracts/development/m02_baseline_77_29_preserved'
FREEZE_HASH = 'd81d503c2dc78e08d571b3552fb57096e9f5c7f9489277143a1569f9b3436674'
OUTPUT = 'results/recovery-validation/m02_recovery_data_05'
ROUTING_MANIFEST = 'evaluation_contracts/development/m02_recovery_rules_v1/manifest.json'
ROUTING_HASH = '9ac54d36753d1a78c767bab54280203ba332062ec2d46b8e3ff0d93734c89a72'
METHOD = '동결 프로세스맵을 기존 evaluator로 재평가합니다. 모델 재추론은 하지 않습니다.'


def verify(root):
    folder = Path(root) / FREEZE
    require(digest(folder/'manifest.json') == FREEZE_HASH, 'M02 preserved manifest changed')
    manifest = read_json(folder/'manifest.json')
    for item in manifest['artifacts']:
        require(digest(folder/item['snapshot_path']) == item['sha256'],
                'M02 preserved artifact changed: ' + item['source_path'])
    require(digest(Path(root)/ROUTING_MANIFEST) == ROUTING_HASH, 'M02 input routing manifest changed')
    return folder/'snapshot'


def readiness(root):
    try:
        verify(root)
        return dict(status='READY', dataset_id=DATASET, details=dict(ground_truth_count=5,
            model_version='workflow_candidate_v1_2_1', config_path=FREEZE+'/manifest.json',
            config_sha256=FREEZE_HASH, measurement_method=METHOD))
    except (EvaluationError, OSError, ValueError, KeyError) as exc:
        return dict(status='BLOCKED', dataset_id=DATASET, details={'missing':[str(exc)]}, error=str(exc))


def measure(snapshot):
    # The historical preservation snapshot omitted this routing-only manifest.
    # Reconstitute a disposable workspace, never modify the preserved snapshot.
    with tempfile.TemporaryDirectory(prefix='m02-frozen-evaluation-') as tmp:
        workspace = Path(tmp)/'snapshot'
        shutil.copytree(snapshot, workspace)
        routing = workspace/ROUTING_MANIFEST
        routing.parent.mkdir(parents=True, exist_ok=True)
        routing.write_bytes((snapshot.parents[3]/ROUTING_MANIFEST).read_bytes())
        require(digest(routing) == ROUTING_HASH, 'M02 routing manifest copy mismatch')
        # Isolated imports prevent editable main-web modules replacing frozen dependencies.
        command = "import importlib.util,json;from pathlib import Path;p=Path(%r);s=importlib.util.spec_from_file_location('frozen_m02_web',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);print(json.dumps(m.measure(),ensure_ascii=False))" % str(workspace/OUTPUT/'web_ready/server.py')
        try:
            proc = subprocess.run([sys.executable, '-B', '-c', command], cwd=workspace,
                env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'), capture_output=True, text=True, timeout=120)
            require(proc.returncode == 0, 'Frozen M02 evaluator failed: '+proc.stderr[-2000:])
            return json.loads(proc.stdout)
        except (subprocess.TimeoutExpired, ValueError) as exc:
            raise EvaluationError('Frozen M02 evaluator response unavailable: '+str(exc)) from exc


def run(root, config):
    root = Path(root); snapshot = verify(root); started = now()
    result = measure(snapshot)
    verify(root)
    values = result['overall']
    require(config['targets']['M02'] == values['target'], 'M02 target configuration changed')
    source = snapshot/OUTPUT/'evidence.csv'
    require(digest(source) == result['evidence_sha256'], 'M02 evaluator evidence binding mismatch')
    rows = list(csv.DictReader(io.StringIO(source.read_text(encoding='utf-8-sig'))))
    # Existing evidence is the frozen evaluator's verified evidence, not new UI math.
    per_bu = []
    for summary in result['per_business_unit']:
        bu = summary['business_unit_id']
        per_bu.append(dict(summary,
            generated_process=[r for r in rows if r['row_type']=='generated_step' and r.get('business_unit_id')==bu],
            required_steps=[r for r in rows if r['row_type']=='required_step' and r.get('process_id')==bu]))
    details = dict(accuracy=values['accuracy'], completeness=values['completeness'],
        evaluated_procedures=values['generated'], correctly_mapped=values['matched'],
        included_required=values['satisfied'], defined_required=values['required'],
        ground_truth_count=result['execution_count'], per_business_unit=per_bu,
        measurement_method=METHOD, model_version='workflow_candidate_v1_2_1',
        config_sha256=FREEZE_HASH, source_evidence_sha256=result['evidence_sha256'])
    saved = save_run(root, 'M02', 'DEVELOPMENT', config, dict(status='COMPLETED',
        score=values['score'], sample_count=result['execution_count'], dataset_id=DATASET,
        source_type='DEVELOPMENT', details=details, started_at=started,
        evaluator_version='preserved-m02-web-ready', input_sha256={FREEZE+'/manifest.json':FREEZE_HASH, ROUTING_MANIFEST:ROUTING_HASH},
        measurement_method=METHOD, evidence_sha256=result['evidence_sha256']), rows)
    # Keep exact bytes, including field encodings/provenance, in this new run only.
    run_dir = root/'results/development'/saved['run_id']
    (run_dir/'evidence.csv').write_bytes(source.read_bytes())
    require(digest(run_dir/'evidence.csv') == saved['evidence_sha256'], 'M02 run evidence mismatch')
    return saved
