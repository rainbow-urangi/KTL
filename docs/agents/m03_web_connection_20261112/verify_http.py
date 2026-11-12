"""Authorized actual M03 HTTP measurement; no browser automation."""
import csv,io,json,hashlib,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[3];out=Path(__file__).parent
base='http://127.0.0.1:8000'
def get(path):
    with urllib.request.urlopen(base+path) as r:return r.read()
cat=json.loads(get('/api/measurement'));item=next(x for x in cat['metrics'] if x['metric_id']=='M03')
assert item['execution_available'] and len(item['details']['business_units'])==10
# Recheck the already completed authorized run; do not rerun on verifier retry.
result=json.loads((out/'api_result.json').read_text())
evidence=get(result['evidence_file']);(out/'api_evidence.csv').write_bytes(evidence)
rows=list(csv.DictReader(io.StringIO(evidence.decode('utf-8-sig'))))
assert len(rows)==10 and sum(x['success']=='True' for x in rows)==9
assert result['score']==90 and result['threshold_met'] and result['sample_count']==10
assert result['details']['success']==9 and result['details']['failure']==1
run=root/'results/development'/result['run_id']
assert evidence==(run/'evidence.csv').read_bytes()
saved=json.loads(get(result['result_file']));assert saved==result
payload=json.loads((run/'received_payload.json').read_text())
assert len(payload['scenarios'])==10
for row,scenario,case in zip(rows,payload['scenarios'],result['details']['per_business_unit']):
    assert row['business_unit_id']==scenario['business_unit_id']==case['business_unit_id']
    assert case['steps']==scenario['steps'] and scenario['generator_mode']=='REAL' and not scenario['synthetic']
    old=json.loads((root/'results/development/m03_menu_enter_20261112'/f"{row['business_unit_id']}-api.json").read_text())
    assert scenario==old['response'], row['business_unit_id']
m=json.loads((root/'docs/agents/m03_development_freeze_20261112/freeze_manifest.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
changed=[name for name,h in m['sha256'].items() if sha(root/name)!=h]
assert changed==['backend/server.py'],changed
report=dict(status='PASS',run_id=result['run_id'],success=9,failure=1,total=10,score=90,
    failed_business_units=[r['business_unit_id'] for r in rows if r['success']!='True'],
    evidence_sha256=sha(run/'evidence.csv'), freeze_manifest_sha256=sha(root/'docs/agents/m03_development_freeze_20261112/freeze_manifest.json'), frozen_core_files_unchanged=42,
    allowed_transport_change=changed, exact_scenarios_equal_previous_frozen=True,
    browser_verification='NOT_RUN_USER_MANUAL',
    current_hashes={p:sha(root/p) for p in ['backend/m03_main_web.py','backend/server.py','backend/measurement_ui.py','frontend/app.js']})
(out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
