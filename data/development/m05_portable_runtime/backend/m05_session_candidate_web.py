"""Loopback DEVELOPMENT candidate UI; old baseline service is left intact.
Run: python3 -m backend.m05_session_candidate_web (port 8769).
"""
import json
import re
from http.server import HTTPServer
from . import m05_readiness_web as old
from .m05_session_candidate import prepare,evaluate,CONFIG_PATH
from scripts.recalculate_m05_full_context_csv import verify

class Handler(old.Handler):
    def do_GET(self):
        if self.path=='/':
            return self.send(old.PAGE.replace('frozen engine','versioned candidate engine').replace('<h1>','<p>후보 v2: 독립 검증 후 freeze. baseline은 보존됩니다.</p><h1>'),'text/html')
        match=re.fullmatch(r'/runs/([0-9a-f]{64})/evidence\.csv',self.path)
        if match:
            out=old.ROOT/'results/development/m05_full_context'/match[1]
            try:
                verify(out)
                return self.send((out/'evidence.csv').read_bytes().decode('utf-8'),'text/csv')
            except Exception:
                return self.send({'status':'BLOCKED','reason':'No verified evidence'},status=404)
        return super().do_GET()
    def do_POST(self):
        if self.path not in {'/validate','/measure'}:return self.send({'status':'NOT_FOUND'},status=404)
        try:
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=4096:raise ValueError('Invalid length')
            body=json.loads(self.rfile.read(length))
            manifest,_=old.load_dataset(old.ROOT,body['dataset'])
            config=json.loads((old.ROOT/CONFIG_PATH).read_text())
            p=prepare(old.ROOT,manifest,config);out=old.ROOT/'results/development/m05_full_context'/p['bundle_sha256']
            if self.path=='/validate':
                if out.exists():
                    verify(out);return self.send(json.loads((out/'result.json').read_text()))
                return self.send(dict(status='READY',score=None,full_event_count=len(p['events']),target_event_count=20,context_event_count=len(p['events'])-20,target=.79,run_mode='DEVELOPMENT',official_pass=None))
            result,_=evaluate(old.ROOT,manifest,config);return self.send(result)
        except Exception as exc:return self.send({'status':'BLOCKED','score':None,'f1':None,'reason':str(exc)},status=422)
if __name__=='__main__':HTTPServer(('127.0.0.1',8769),Handler).serve_forever()
