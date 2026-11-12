"""Isolated DEVELOPMENT full-context UI. Frozen main web/engine stay unchanged.
Run: python3 -m backend.m05_readiness_web (loopback only).
"""
import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from .m05_full_context import SCHEMA, validate_bundle, evaluate, attempt_path

ROOT = Path(__file__).resolve().parents[1]
PAGE = '''<!doctype html><html lang="ko"><meta charset="utf-8"><title>M05 DEVELOPMENT</title>
<h1>M05 full-context / target 20건</h1>
<p>DEVELOPMENT 전용. 전체 raw sequence를 frozen engine으로 1회 실행하고, 사전 잠금 target 20건(KEEP10/REMOVE10)만 계산합니다. context는 점수 분모에서 제외합니다.</p>
<p>REMOVE 구성: duplicate3 / noise3 / repeated_action2 / irrelevant_action2. 목표 F1 ≥ 0.79. KTL 공식 판정이 아닙니다. 구형 target-only 경로는 stale이며 사용하지 않습니다.</p>
<select id="dataset" aria-label="held-out dataset"></select><button id="validate">근거 검증</button><button id="run" disabled>검증된 전체 sequence 1회 측정</button>
<a id="csv" hidden>target20 evidence CSV 다운로드</a><a id="manifest" hidden>run manifest 다운로드</a>
<pre id="result">BLOCKED: 새 raw 수집 근거·독립 라벨 lock·별도 reviewer 승인이 없으면 점수 미산출.</pre>
<script>
const dataset=document.getElementById('dataset'),validate=document.getElementById('validate'),run=document.getElementById('run'),csv=document.getElementById('csv'),manifest=document.getElementById('manifest'),result=document.getElementById('result');
let busy=false, generation=0;
function clear(){run.disabled=true;csv.hidden=true;manifest.hidden=true;}
async function request(path){if(busy)return;busy=true;const current=++generation;clear();validate.disabled=true;dataset.disabled=true;try{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset:dataset.value})});const data=await response.json();if(current!==generation)return;result.textContent=JSON.stringify(data,null,2);run.disabled=data.status!=='READY';if(data.status==='COMPLETE'){csv.href='/runs/'+data.run_id+'/evidence.csv';csv.download='m05-target20-evidence.csv';csv.hidden=false;manifest.href='/runs/'+data.run_id+'/run_manifest.json';manifest.download='m05-run-manifest.json';manifest.hidden=false;}}catch(error){result.textContent='BLOCKED: '+error.message;}finally{busy=false;validate.disabled=!dataset.options.length;dataset.disabled=false;}}
dataset.onchange=()=>{generation++;clear();result.textContent='근거 검증이 필요합니다.';};validate.onclick=()=>request('/validate');run.onclick=()=>request('/measure');
fetch('/datasets').then(r=>r.json()).then(names=>{for(const name of names){const option=document.createElement('option');option.value=name;option.textContent=name;dataset.append(option)}validate.disabled=!names.length;}).catch(e=>{clear();validate.disabled=true;result.textContent='BLOCKED: '+e.message;});
</script></html>'''


def load_dataset(root, name):
    root = Path(root).resolve()
    if not isinstance(name, str) or name in ('', '.', '..') or Path(name).name != name:
        raise ValueError('Invalid dataset name')
    directory = (root / 'data/held_out/m05' / name).resolve()
    if not directory.is_relative_to((root / 'data/held_out/m05').resolve()):
        raise ValueError('Dataset outside held-out directory')
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('dataset_id') != name or manifest.get('schema_version') != SCHEMA:
        raise ValueError('Full-context manifest required')
    config = json.loads((root / 'evaluation_contracts/m05_engine.json').read_text())
    return manifest, config


class Handler(BaseHTTPRequestHandler):
    def send(self, data, kind='application/json', status=200):
        body = (json.dumps(data, ensure_ascii=False) if kind == 'application/json' else data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', kind + '; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/':
            return self.send(PAGE, 'text/html')
        if self.path == '/datasets':
            names = []
            for path in (ROOT / 'data/held_out/m05').glob('*/manifest.json'):
                try:
                    manifest, _ = load_dataset(ROOT, path.parent.name)
                    names.append(manifest['dataset_id'])
                except (ValueError, OSError, KeyError):
                    continue
            return self.send(sorted(names))
        match = re.fullmatch(r'/runs/([0-9a-f]{64})/(evidence\.csv|run_manifest\.json)', self.path)
        if match:
            directory = ROOT / 'results/development/m05_full_context' / match[1]
            try:
                from scripts.recalculate_m05_full_context_csv import verify
                verify(directory)  # Never download partial/stale/tampered results.
                if match[2] == 'evidence.csv':
                    return self.send((directory / match[2]).read_text(), 'text/csv')
                return self.send(json.loads((directory / match[2]).read_text()))
            except Exception:
                pass
        return self.send({'status': 'BLOCKED', 'score': None, 'reason': 'No verified evidence'}, status=404)

    def do_POST(self):
        if self.path not in ('/validate', '/measure'):
            return self.send({'status': 'NOT_FOUND'}, status=404)
        try:
            # JSON + no CORS blocks cross-site form/fetch triggering an inference.
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ValueError('JSON request required')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
                raise ValueError('Invalid request length')
            body = json.loads(self.rfile.read(length))
            manifest, config = load_dataset(ROOT, body['dataset'])
            if self.path == '/validate':
                prepared = validate_bundle(ROOT, manifest, config)
                attempted = ROOT / 'results/development/m05_full_context' / prepared['bundle_sha256']
                if attempted.exists() or attempt_path(ROOT, prepared).exists():
                    raise ValueError('BUNDLE_ALREADY_ATTEMPTED_NO_AUTOMATIC_RERUN')
                return self.send(dict(status='READY', score=None, f1=None, full_event_count=len(prepared['events']),
                                      target_event_count=20, context_event_count=len(prepared['events']) - 20,
                                      run_mode='DEVELOPMENT', official_pass=None))
            result, _ = evaluate(ROOT, manifest, config)
            return self.send(result)
        except Exception as exc:
            return self.send({'status': 'BLOCKED', 'score': None, 'f1': None, 'official_pass': None, 'target': .79, 'reason': str(exc)}, status=422)


if __name__ == '__main__':
    HTTPServer(('127.0.0.1', 8768), Handler).serve_forever()
