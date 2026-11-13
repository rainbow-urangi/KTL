"""CU02 원본과 실제 Chrome의 로컬 폼 제출 연결. 명시적으로 켠 경우만 실행한다."""
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend.m04 import cu02, runner


PAGE = r'''<!doctype html><meta charset="utf-8"><title>Synthetic CU02</title>
<style>.monthly-calendar__grid{display:grid;grid-template-columns:repeat(7,90px)}
.monthly-calendar__cell{min-height:50px}form{padding:20px;border:1px solid black}textarea{height:40px}</style>
<div class="schedule-page"><div class="calendar-toolbar__month">2026.11</div>
<div class="schedule-viewer-bar__copy"><strong>내 일정</strong></div>
<div class="monthly-calendar"><div class="monthly-calendar__grid"></div></div></div>
<script>
const grid=document.querySelector('.monthly-calendar__grid');
for(let i=1;i<=30;i++){
  const cell=document.createElement('div');cell.className='monthly-calendar__cell';
  cell.innerHTML='<button class="monthly-calendar__date-number">'+i+'</button>';
  cell.firstChild.addEventListener('click',()=>openForm(null));grid.appendChild(cell);
}
function openForm(saved){
  const form=document.createElement('form');form.className='schedule-modal__panel';
  form.innerHTML='<h2>'+(saved?'업무 내용':'업무 등록')+'</h2>'+
    '<input id="schedule-title"><textarea id="schedule-description"></textarea>'+
    '<div class="schedule-modal__actions"><button type="submit">'+(saved?'확인':'등록')+'</button></div>'+
    '<button type="button" aria-label="닫기">닫기</button>';
  form.querySelector('[aria-label="닫기"]').onclick=()=>form.remove();
  form.querySelector('#schedule-title').value=saved?saved.title:'';
  form.querySelector('#schedule-description').value=saved?saved.description:'';
  form.syntheticState={title:saved?saved.title:'',description:saved?saved.description:''};
  form.dataset.existing=saved?'true':'false';
  for(const name of ['title','description']){
    const control=form.querySelector('#schedule-'+name);
    control.addEventListener('input',()=>{form.syntheticState[name]=control.value;});
  }
  document.body.appendChild(form);
}
// 제출 이벤트의 bubbling과 입력 이벤트로 갱신한 상태를 검사한다. React 자체는 아니다.
document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.matches('form.schedule-modal__panel'))return;
  event.preventDefault();
  if(form.dataset.existing==='true')throw new Error('Synthetic fixture forbids editing existing data');
  for(const name of ['title','description']){
    if(form.querySelector('#schedule-'+name).value!==form.syntheticState[name])throw new Error('Synthetic state mismatch');
  }
  const value={...form.syntheticState,startDate:'2026-11-13'};
  const response=await fetch('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
  if(response.status!==201)throw new Error('Synthetic wrong HTTP status');
  await response.json();form.remove();await render();
});
async function render(){
  const response=await fetch('/api/schedules'),value=await response.json();
  for(const button of document.querySelectorAll('.schedule-event__title'))button.remove();
  for(const row of value.schedules){
    const button=document.createElement('button');button.className='schedule-event__title';
    button.textContent=row.title;button.onclick=()=>openForm(row);grid.children[12].appendChild(button);
  }
}
render();
</script>'''


@unittest.skipUnless(os.environ.get('KTL_TEST_LOCAL_CHROME') == '1',
                     '명시적인 로컬 Chrome 합성 시험에서만 실행')
class CU02LocalBrowserTests(unittest.TestCase):
    def test_generated_original_native_submit_reaches_post_201_finish_and_reload(self):
        driver_path = Path(os.environ.get('KTL_TEST_CHROMEDRIVER', ''))
        self.assertTrue(driver_path.is_file(), '기존 로컬 chromedriver 절대경로가 필요합니다.')
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        records, requests = [], []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, status, value, content_type='application/json'):
                raw = value.encode('utf-8') if isinstance(value, str) else json.dumps(value).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', content_type + '; charset=utf-8')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                requests.append(('GET', self.path))
                if self.path == '/mypage/schedule':
                    self.reply(200, PAGE, 'text/html')
                elif self.path == '/api/schedules/viewers':
                    self.reply(200, {'viewers': [dict(id=1, relation='self')]})
                elif self.path.split('?')[0] == '/api/schedules':
                    self.reply(200, {'schedules': list(records)})
                else:
                    self.reply(404, {})

            def do_POST(self):
                requests.append(('POST', self.path))
                value = json.loads(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                if self.path == '/api/auth/login':
                    self.reply(200, dict(success=True, token='SYNTHETIC_CU02_LOCAL_ONLY'))
                elif self.path == '/api/schedules':
                    records.append(value)
                    self.reply(201, dict(success=True))
                else:
                    self.reply(404, {})

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        origin = 'http://127.0.0.1:' + str(server.server_port)
        original_chrome = webdriver.Chrome

        def local_chrome(*, options):
            options.add_argument('--headless=new')
            options.add_argument('--disable-background-networking')
            options.add_argument('--disable-sync')
            options.add_argument('--no-proxy-server')
            options.add_argument('--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1')
            return original_chrome(options=options, service=Service(executable_path=str(driver_path)))

        try:
            with patch.object(cu02, 'TARGET_ORIGIN', origin), \
                    patch.object(cu02, 'TARGET_URL', origin + '/mypage/schedule'):
                prepared = cu02.prepare(dict(date='2026-11-13', title='SYNTHETIC LOCAL CU02',
                    description='Only local fixture data.', browser='chrome'))
            output = io.StringIO()
            with tempfile.TemporaryDirectory(prefix='ktl-cu02-local-chrome-') as folder:
                script = Path(folder) / 'original.py'
                script.write_bytes(prepared['code'].encode('utf-8'))
                original = script.read_bytes()
                with patch.object(runner, 'load_login_settings', return_value={}), \
                        patch.dict(os.environ, KTL_M04_RBEM_USERNAME='SYNTHETIC_LOCAL',
                                   KTL_M04_RBEM_PASSWORD='SYNTHETIC_LOCAL'), \
                        patch.object(webdriver, 'Chrome', side_effect=local_chrome), redirect_stdout(output):
                    code = runner.execute(script, prepared['scenario'], required=True, contract=prepared['contract'])
                self.assertEqual(script.read_bytes(), original)
                events = [json.loads(line) for line in output.getvalue().splitlines()]
                result = events[-1]
                self.assertEqual(code, 0, result)
                self.assertTrue(result['business_step_complete'])
                self.assertTrue(result['independent_checks_passed'])
                self.assertEqual(len(result['business_steps']), 5)
                registration = result['business_steps'][3]
                self.assertIn('submit', registration['observed_actions'])
                evidence = next(item for item in registration['check_results'] if item['kind'] == 'native_submit_response')
                self.assertEqual(evidence['status'], 'PASS')
                self.assertEqual(evidence['network']['http_status'], 201)
                self.assertFalse(evidence['network']['direct_causal_id_proven'])
                self.assertEqual(requests.count(('POST', '/api/schedules')), 1)
                self.assertEqual(records, [dict(title='SYNTHETIC LOCAL CU02',
                    description='Only local fixture data.', startDate='2026-11-13')])
                self.assertGreaterEqual(requests.count(('GET', '/mypage/schedule')), 2)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
