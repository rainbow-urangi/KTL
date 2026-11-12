'use strict';
// Run the actual UI functions against synthetic in-memory APIs; no browser or HTTP calls.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.resolve(__dirname,'../frontend/m04.js'),'utf8');
const SERVER='SERVER-'+'f'.repeat(32),SCRIPT='a'.repeat(32),OTHER='b'.repeat(32),EXEC='M04-RUN-'+'c'.repeat(32);
const RESULT='DEV-M04-20261113T120000-'+'d'.repeat(12),HASH='e'.repeat(64);
const EVALUATION='CU02-EVAL-'+'9'.repeat(32);
const clone=value=>JSON.parse(JSON.stringify(value));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const settle=async()=>{for(let i=0;i<18;i++) await new Promise(done=>setImmediate(done));};
function workflow(login=true) {return {workflow_id:'CU02',name:'일정 등록',run_mode:'DEVELOPMENT',
  steps:['일정관리','날짜 선택','일정 입력','등록','종료'],target_url:'https://rainbowlab.ai.kr/mypage/schedule',login_configured:login,
  defaults:{date:'2026-11-13',title:'KTL CU02 synthetic',description:'Synthetic schedule only',browser:'edge'}};}
function script(id=SCRIPT) {return {script_id:id,filename:'cu02-schedule.py',workflow_id:'CU02',scenario_id:'CU02-SCHEDULE-'+'1'.repeat(12),
  sha256:HASH,business_step_required:true,execution_ready:true,generated_by_llm:false,source_kind:'CU02_SCHEDULE_REGISTRATION'};}
function job(status='RUNNING',id=EXEC) {return {execution_id:id,status,cases:[],logs:[],result:status==='COMPLETED'?{score:100}:null,
  counts:{total_execution_count:1,successful_execution_count:status==='COMPLETED'?1:0}};}
function batchJob(status='RUNNING',statuses=[]) {
  const cases=Array.from({length:10},(_unused,index)=>({case_id:'CASE-'+String(index+1).padStart(3,'0'),script_id:(index+1).toString(16).padStart(32,'0'),
    cu02_evaluation_id:EVALUATION,cu02_case_number:index+1,status:statuses[index]||'PENDING'}));
  const passed=cases.filter(row=>row.status==='PASS').length;
  return {...job(status),cases,cu02_evaluation:{evaluation_id:EVALUATION,workflow_id:'CU02',case_count:10,counting_unit:'SCHEDULE_REGISTRATION',
    cases:cases.map(row=>({case_id:row.case_id,script_id:row.script_id,case_number:row.cu02_case_number,expected:{date:'2026-11-13',title:'Synthetic item '+row.cu02_case_number,description:'Synthetic expected contents',browser:'edge'}}))},
    result:status==='COMPLETED'?{score:passed*10,run_id:RESULT}:null,counts:{total_execution_count:10,successful_execution_count:passed}};
}
function harness({login=true,initialScripts=[],jobs=[]}={}) {
  const calls=[],elements=new Map(),timers=new Map();let timerId=0;
  const state={workflow:workflow(login),scripts:clone(initialScripts),jobs:clone(jobs),overrides:new Map(),prepareReply:null,evaluationReply:null};
  const location={pathname:'/metrics/m04',search:'?mode=DEVELOPMENT'};
  const element=id=>{if(!elements.has(id)) elements.set(id,{innerHTML:'',textContent:'',value:'',disabled:false,checked:false,files:[],dataset:{},listeners:{},
    addEventListener(name,fn){this.listeners[name]=fn;}});return elements.get(id);};
  const response=(data,status=200,session=SERVER)=>({ok:status>=200&&status<300,status,headers:{get:()=>session},json:async()=>clone(data)});
  const original={run_mode:'DEVELOPMENT',dataset_id:'synthetic-only',external_run_id:'synthetic-external',source_module:'synthetic',source_version:'v1',submitted_at:'2026-11-13T12:00:00+09:00',
    counts:{total_execution_count:1,successful_execution_count:1},details:{}};
  const external={metric_id:'M04',run_id:RESULT,run_mode:'DEVELOPMENT',status:'COMPLETED',score:100,sample_count:1,dataset_id:original.dataset_id,
    details:{raw_counts:clone(original.counts)},provenance:Object.fromEntries(['external_run_id','source_module','source_version','submitted_at'].map(key=>[key,original[key]]))};
  const context=vm.createContext({URLSearchParams,AbortController,Uint8Array,Date,console,location,
    setTimeout(fn,delay){const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),
    history:{replaceState(_a,_b,url){location.search=url.slice(url.indexOf('?'));}},document:{querySelector:element},app:element('#app'),banner:()=>'',link:value=>value,labels:{M04:'M04'},
    esc:value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),score:value=>value==null?'—':value+'%',
    catalog:{server_session_id:SERVER,metrics:[]},ktlDropQuery(keys){const query=new URLSearchParams(location.search);keys.forEach(key=>query.delete(key));location.search='?'+query;},
    ktlCheckServerSession(reply){if(reply.headers.get()!==SERVER){const error=new Error('synthetic server session changed');error.status='SESSION_EXPIRED';throw error;}},
    fetch:async(url,options)=>{
      const payload=options?.body?JSON.parse(options.body):undefined;calls.push({url,method:options?.method||'GET',payload});
      if(state.overrides.has(url)) return state.overrides.get(url)(payload);
      if(url==='/api/development/m04/cu02') return response(state.workflow);
      if(url==='/api/development/m04/cu02/scripts') {
        const data={script:script(),workflow:state.workflow};
        if(state.prepareReply) return state.prepareReply(payload,data);
        state.scripts.unshift(data.script);return response(data,201);
      }
      if(url==='/api/development/m04/cu02/evaluations') {
        const execution=batchJob(),data={evaluation:execution.cu02_evaluation,execution};
        if(state.evaluationReply) return state.evaluationReply(payload,data);
        state.jobs.unshift(execution);state.scripts.unshift(...execution.cases.map(row=>script(row.script_id)));return response(data,201);
      }
      if(url==='/api/development/m04/scripts') return response({run_mode:'DEVELOPMENT',scripts:state.scripts,readiness:{selenium:true,chrome:true,edge:true}});
      if(url==='/api/development/m04/executions') {
        if(payload){const next=job();state.jobs.unshift(next);return response({execution:next},202);}
        return response({executions:state.jobs});
      }
      if(url==='/api/development/m04/executions/'+EXEC) return response({execution:state.jobs.find(row=>row.execution_id===EXEC)});
      if(url.startsWith('/api/development/m04/executions/')) return response({execution:state.jobs.find(row=>url.endsWith(row.execution_id))});
      if(url==='/api/development/m03/runs') return response({runs:[]});
      if(url==='/api/development/m07/context') return response({run_mode:'DEVELOPMENT',scenarios:[],readiness:{configured:false}});
      if(url==='/api/development/m07/generations') return response({generations:[]});
      if(url==='/api/development/m01/csv') return response({datasets:[]});
      if(url===`/api/evaluations/m04/runs/${RESULT}/result.json`) return response(external);
      if(url===`/api/evaluations/m04/runs/${RESULT}/received_payload.json`) return response(original);
      throw new Error('Unexpected synthetic route '+url);
    }});
  vm.runInContext(source,context);context.renderM04({metric_id:'M04',target:90});
  const evaluate=code=>vm.runInContext(code,context);
  return {context,state,calls,element,response,location,timers,evaluate,
    input(field,value){element('#m04-cu02-'+field).value=value;element('#m04-cu02-'+field).listeners[field==='browser'?'change':'input']({target:{value}});},
    posts:route=>calls.filter(call=>call.url===route&&call.method==='POST'),
    async poll(){const id=evaluate('m04PollTimer'),timer=timers.get(id);assert.ok(timer,'active runner must keep polling');timers.delete(id);await timer.fn();}};
}
const tests=[];const test=(name,run)=>tests.push({name,run});
test('CU02 defaults come from the server and remain ready without GPT configuration or M03 input',async()=>{
  const h=harness();await settle();
  assert.equal(h.element('#m04-cu02-date').value,'2026-11-13');assert.equal(h.element('#m04-cu02-title').value,'KTL CU02 synthetic');
  assert.equal(h.element('#m04-cu02-browser').value,'edge');
  assert.equal(h.element('#m04-cu02-prepare').disabled,false);assert.match(h.element('#m04-cu02-login').textContent,/준비됨/);
  assert.ok(h.calls.every(call=>call.method==='GET'));assert.equal(h.evaluate('m04View.selected.size'),0);
});
test('invalid calendar dates, blank or multiline titles and oversized input cannot prepare',async()=>{
  for(const [field,value] of [['date','2026-02-30'],['date','2026-2-3'],['title','  '],['title','line\nbreak'],['title','a'.repeat(121)],['description','a'.repeat(2001)],['browser','firefox']]) {
    const h=harness();await settle();h.input(field,value);assert.equal(h.element('#m04-cu02-prepare').disabled,true);await h.context.prepareM04Cu02();
    assert.equal(h.posts('/api/development/m04/cu02/scripts').length,0);
  }
});
test('prepare preserves entered content, refreshes scripts, removes M03 scope and requires a separate execution click',async()=>{
  const h=harness({initialScripts:[script(OTHER)]});await settle();
  h.evaluate(`m04View.locked=true;m04View.selected.add('${OTHER}')`);h.location.search+='&m03_run_id=old&scenario_id=old';
  h.input('date','2028-02-29');h.input('title','  Synthetic CU02  ');h.input('description','  first\nsecond  ');
  await h.context.prepareM04Cu02();
  assert.deepEqual(h.posts('/api/development/m04/cu02/scripts')[0].payload,{date:'2028-02-29',title:'Synthetic CU02',description:'first\nsecond',browser:'edge'});
  assert.equal(h.calls.filter(call=>call.url==='/api/development/m04/scripts').length,2);
  assert.deepEqual(clone(h.evaluate('[...m04View.selected]')),[SCRIPT]);assert.equal(h.evaluate('m04View.locked'),false);
  assert.equal(new URLSearchParams(h.location.search).has('scenario_id'),false);assert.equal(h.element('#m04-start').disabled,false);
  assert.equal(h.posts('/api/development/m04/executions').length,0);assert.equal(h.posts('/api/development/m07/generations').length,0);
  assert.match(h.element('#m04-cu02-status').textContent,/선택 스크립트 실행/);
  await h.context.prepareM04Cu02();assert.equal(h.posts('/api/development/m04/cu02/scripts').length,1);
  await h.context.startM04();assert.deepEqual(h.posts('/api/development/m04/executions')[0].payload,{script_ids:[SCRIPT],visible_browser:true,action_delay_ms:700,keep_open_seconds:15});
});
test('Edge-only readiness enables the existing execution action and an explicit browser selection is preserved',async()=>{
  const h=harness();await settle();h.input('browser','chrome');
  await h.context.prepareM04Cu02();assert.equal(h.posts('/api/development/m04/cu02/scripts')[0].payload.browser,'chrome');
  h.evaluate('m04View.readiness={selenium:true,chrome:false,edge:true}');h.context.paintM04();
  assert.equal(h.element('#m04-start').disabled,false);await h.context.startM04();assert.equal(h.posts('/api/development/m04/executions').length,1);
});
test('missing login or unavailable CU02 preparation leaves existing fixed scripts usable',async()=>{
  for(const unavailable of [false,true]) {
    const h=harness({login:false,initialScripts:[script(OTHER)]});
    if(unavailable) h.state.overrides.set('/api/development/m04/cu02',async()=>h.response({error:'synthetic unavailable'},503));
    await settle();assert.equal(h.element('#m04-cu02-prepare').disabled,true);await h.context.prepareM04Cu02();assert.equal(h.posts('/api/development/m04/cu02/scripts').length,0);
    h.evaluate(`m04View.selected.add('${OTHER}')`);h.context.paintM04();assert.equal(h.element('#m04-start').disabled,false);
    assert.equal(h.element('#m04-m01-import').disabled,true);
  }
});
test('double preparation and execution are blocked while preparing and field contents remain intact',async()=>{
  const h=harness();await settle();const gate=deferred();let answer;
  h.input('title','Synthetic pending title');h.state.prepareReply=(_payload,data)=>{answer=data;return gate.promise;};
  const first=h.context.prepareM04Cu02();await h.context.prepareM04Cu02();await h.context.startM04();
  assert.equal(h.posts('/api/development/m04/cu02/scripts').length,1);assert.equal(h.posts('/api/development/m04/executions').length,0);
  assert.equal(h.element('#m04-cu02-title').disabled,true);assert.equal(h.element('#m04-cu02-title').value,'Synthetic pending title');
  h.state.scripts=[answer.script];gate.resolve(h.response(answer,201));await first;
  assert.equal(h.element('#m04-cu02-title').value,'Synthetic pending title');assert.equal(h.element('#m04-cu02-title').disabled,false);
});
test('retired page and changed server session cannot accept prepared scripts',async()=>{
  for(const kind of ['page','session']) {
    const h=harness();await settle();const gate=deferred();let answer;
    h.state.prepareReply=(_payload,data)=>{answer=data;return gate.promise;};const pending=h.context.prepareM04Cu02();
    if(kind==='page') {h.context.renderM04({metric_id:'M04',target:90});await settle();}
    gate.resolve(h.response(answer,201,kind==='session'?'SERVER-changed':SERVER));await pending;
    assert.equal(h.evaluate('m04View.selected.size'),0);assert.equal(h.evaluate('m04View.scripts.length'),0);
  }
});
test('malformed workflow and script source are rejected without selection or execution',async()=>{
  for(const mutate of [data=>data.workflow.workflow_id='CU03',data=>data.script.sha256='bad',data=>data.script.source_kind='other',data=>data.script.generated_by_llm=true]) {
    const h=harness();await settle();h.state.prepareReply=(_payload,data)=>{mutate(data);return h.response(data,201);};
    await h.context.prepareM04Cu02();assert.equal(h.evaluate('m04View.selected.size'),0);assert.equal(h.posts('/api/development/m04/executions').length,0);
    assert.match(h.element('#m04-cu02-status').textContent,/확인/);
  }
});
test('a script-list refresh error preserves the confirmed preparation and prevents duplicate preparation',async()=>{
  const h=harness();await settle();h.state.overrides.set('/api/development/m04/scripts',async()=>h.response({error:'synthetic list unavailable'},503));
  await h.context.prepareM04Cu02();assert.equal(h.evaluate(`m04View.selected.has('${SCRIPT}')`),true);
  assert.match(h.element('#m04-cu02-status').textContent,/새로고침에 실패/);await h.context.prepareM04Cu02();
  assert.equal(h.posts('/api/development/m04/cu02/scripts').length,1);assert.equal(h.element('#m04-start').disabled,false);
});
test('an active runner blocks CU02 preparation and keeps polling while an external result is displayed',async()=>{
  const h=harness({initialScripts:[script()],jobs:[job()]});await settle();
  h.evaluate(`m04View.selected.add('${SCRIPT}')`);h.context.paintM04();await h.context.prepareM04Cu02();
  assert.equal(h.posts('/api/development/m04/cu02/scripts').length,0);assert.equal(h.element('#m04-start').disabled,true);
  await h.context.selectM04Result(RESULT);const message=h.element('#m04-status').textContent;
  h.state.jobs=[job('COMPLETED')];await h.poll();
  assert.equal(h.evaluate('m04View.executions[0].status'),'COMPLETED');assert.equal(h.evaluate('m04View.resultSource'),'external');
  assert.equal(h.evaluate('m04View.externalRunId'),RESULT);assert.equal(h.element('#m04-status').textContent,message);
  assert.equal(h.element('#m04-start').disabled,false);assert.equal(h.element('#m04-cu02-prepare').disabled,false);
});
test('an older in-flight runner response cannot revive RUNNING after a newer completion',async()=>{
  const h=harness({jobs:[job()]});await settle();const gate=deferred();
  h.state.overrides.set('/api/development/m04/executions/'+EXEC,()=>gate.promise);const old=h.poll();
  await h.context.selectM04Result(RESULT);h.state.overrides.delete('/api/development/m04/executions/'+EXEC);h.state.jobs=[job('COMPLETED')];await h.poll();
  gate.resolve(h.response({execution:job()}));await old;
  assert.equal(h.evaluate('m04View.executions[0].status'),'COMPLETED');assert.equal(h.evaluate('m04View.resultSource'),'external');
});
test('viewing a completed local history does not strand a different running execution',async()=>{
  const past='M04-RUN-'+'2'.repeat(32),h=harness({jobs:[job(),job('COMPLETED',past)]});await settle();
  await h.context.selectM04Execution(past);h.state.jobs=[job('COMPLETED'),job('COMPLETED',past)];await h.poll();
  assert.equal(h.evaluate('m04View.execution.execution_id'),past);assert.equal(h.evaluate('m04View.executions.find(row=>row.execution_id==='+JSON.stringify(EXEC)+').status'),'COMPLETED');
});
test('one CU02 evaluation click requests ten executions once and immediately tracks their single job',async()=>{
  const h=harness();await settle();
  assert.equal(h.element('#m04-cu02-evaluate').disabled,false);
  assert.match(h.element('#app').innerHTML,/일정 10건을 실제 등록/);assert.match(h.element('#app').innerHTML,/제목·내용이 비었는지/);
  h.input('title','  Synthetic batch  ');h.input('description','  Synthetic expected\ncontents  ');
  await h.context.evaluateM04Cu02();
  assert.deepEqual(h.posts('/api/development/m04/cu02/evaluations')[0].payload,{date:'2026-11-13',title:'Synthetic batch',description:'Synthetic expected\ncontents',browser:'edge',visible_browser:true,action_delay_ms:700,keep_open_seconds:15});
  assert.equal(h.posts('/api/development/m04/cu02/evaluations').length,1);assert.equal(h.posts('/api/development/m04/executions').length,0);
  assert.equal(h.posts('/api/development/m04/cu02/scripts').length,0);assert.equal(h.posts('/api/development/m07/generations').length,0);
  assert.equal(h.evaluate('m04View.execution.cases.length'),10);assert.equal(h.evaluate('m04View.selected.size'),10);
  assert.match(h.element('#m04-result').innerHTML,/집계 중/);assert.doesNotMatch(h.element('#m04-result').innerHTML,/개발 목표 달성/);
  assert.equal(h.element('#m04-cu02-evaluate').disabled,true);assert.equal(h.element('#m04-cu02-prepare').disabled,true);
  assert.ok(h.timers.has(h.evaluate('m04PollTimer')));
});
test('batch requires a ready chosen browser, login and at most 105 title characters while single preparation retains 120',async()=>{
  const h=harness();await settle();h.input('title','a'.repeat(106));
  assert.equal(h.element('#m04-cu02-evaluate').disabled,true);assert.equal(h.element('#m04-cu02-prepare').disabled,false);
  await h.context.evaluateM04Cu02();assert.equal(h.posts('/api/development/m04/cu02/evaluations').length,0);
  h.input('title','a'.repeat(105));assert.equal(h.element('#m04-cu02-evaluate').disabled,false);
  h.evaluate('m04View.readiness={selenium:true,chrome:true,edge:false}');h.context.paintM04();assert.equal(h.element('#m04-cu02-evaluate').disabled,true);
  h.input('browser','chrome');assert.equal(h.element('#m04-cu02-evaluate').disabled,false);
  h.evaluate('m04View.cu02.workflow.login_configured=false');h.context.paintM04();assert.equal(h.element('#m04-cu02-evaluate').disabled,true);
});
test('batch blocks repeated click, single preparation and normal execution during the creation request',async()=>{
  const h=harness();await settle();const gate=deferred();let answer;
  h.state.evaluationReply=(_payload,data)=>{answer=data;return gate.promise;};
  const pending=h.context.evaluateM04Cu02();await h.context.evaluateM04Cu02();await h.context.prepareM04Cu02();await h.context.startM04();
  assert.equal(h.posts('/api/development/m04/cu02/evaluations').length,1);assert.equal(h.posts('/api/development/m04/cu02/scripts').length,0);
  assert.equal(h.posts('/api/development/m04/executions').length,0);assert.equal(h.element('#m04-cu02-title').disabled,true);
  h.state.jobs=[answer.execution];gate.resolve(h.response(answer,201));await pending;
  assert.equal(h.evaluate('m04View.execution.execution_id'),EXEC);
});
test('ten item results retain errors and skipped cases and only completed matching server results get a goal verdict',async()=>{
  for(const passed of [8,9,10]) {
    const statuses=Array.from({length:10},(_unused,index)=>index<passed?'PASS':index===9?'ERROR':'SKIPPED');
    const h=harness({jobs:[batchJob('COMPLETED',statuses)]});await settle();
    const html=h.element('#m04-result').innerHTML;
    assert.match(html,new RegExp('최종 성공률 '+passed*10+'%'));
    assert.match(html,passed>=9?/개발 목표 달성/:/개발 목표 미달/);
    assert.match(html,new RegExp('실패·오류·미실행</label><strong>'+String(10-passed)+'건'));
    assert.match(html,/전체<\/label><strong>10건/);
  }
  for(const mutate of [record=>record.result.score=100,record=>record.counts.total_execution_count=9,record=>record.cases[0].cu02_evaluation_id='bad']) {
    const record=batchJob('COMPLETED',Array.from({length:10},(_unused,index)=>index===9?'FAIL':'PASS'));mutate(record);
    const h=harness({jobs:[record]});await settle();const html=h.element('#m04-result').innerHTML;
    assert.doesNotMatch(html,/개발 목표 달성/);assert.match(html,/판정.*확인|연결을 확인/);
  }
});
test('batch progress distinguishes pending from failure and does not expose a premature final score',async()=>{
  const h=harness({jobs:[batchJob('RUNNING',['PASS','FAIL','RUNNING'])]});await settle();
  const html=h.element('#m04-result').innerHTML;
  assert.match(html,/성공<\/label><strong>1건/);assert.match(html,/실패·오류·미실행<\/label><strong>1건/);
  assert.match(html,/실행 중<\/label><strong>1건/);assert.match(html,/대기·확인 필요<\/label><strong>7건/);
  assert.doesNotMatch(html,/최종 성공률|개발 목표 달성/);
});
test('case expected values are escaped and before/after comparison comes from recorded business steps',async()=>{
  const record=batchJob('RUNNING',['PASS','FAIL']);
  record.cu02_evaluation.cases[0].expected.title='<img src=x onerror=bad()> & synthetic';
  record.cu02_evaluation.cases[0].expected.description='First\n<script>bad()</script>';
  record.cases[0].steps=[{sequence:2,status:'PASS'},{sequence:5,status:'PASS'}];
  record.cases[1].steps=[{sequence:2,status:'FAIL'}];
  const h=harness({jobs:[record]});await settle();const html=h.element('#m04-cases').innerHTML;
  assert.match(html,/&lt;img src=x onerror=bad\(\)&gt; &amp; synthetic/);assert.doesNotMatch(html,/<script>bad/);
  assert.match(html,/실행 전 빈 제목·내용: 빈 상태 확인/);assert.match(html,/저장 후 재조회: 기대 제목·내용과 일치/);
  assert.match(html,/실행 전 빈 제목·내용: 확인 실패/);assert.match(html,/저장 후 재조회: 확인 대기/);
});
test('CU02 screenshot captions describe only captured matching explicit checkpoints',async()=>{
  const h=harness();await settle();
  const row={execution_id:EXEC,case_id:'CASE-001',source_kind:'CU02_SCHEDULE_REGISTRATION',workflow_id:'CU02',
    screenshots:['before','after'].map((phase,index)=>({phase,status:'CAPTURED',file:phase+'.png',policy:'text-and-images-masked-v1',
      capture_mode:'EXPLICIT_BUSINESS_CHECKPOINT',business_step_order:index?5:2}))};
  h.context.syntheticRow=row;
  const html=h.evaluate('m04ScreenDetails(syntheticRow)');
  assert.match(html,/실행 전 · 빈 신규등록 화면/);assert.match(html,/실행 후 · 저장값 재조회 화면/);
  for(const mutate of [value=>value.source_kind='UPLOADED_FIXED_SCRIPT',value=>value.screenshots.forEach(record=>record.capture_mode='other'),
    value=>value.screenshots.forEach(record=>record.business_step_order=3),value=>value.screenshots.forEach(record=>record.status='SKIPPED')]) {
    const generic=clone(row);mutate(generic);h.context.syntheticRow=generic;
    const result=h.evaluate('m04ScreenDetails(syntheticRow)');
    assert.doesNotMatch(result,/빈 신규등록 화면|저장값 재조회 화면/);assert.match(result,/실행 전/);assert.match(result,/실행 후/);
  }
});
test('malformed batch linkage cannot be accepted and never triggers a replacement execution request',async()=>{
  for(const mutate of [data=>data.evaluation.case_count=9,data=>data.execution.cases.pop(),data=>data.execution.cases[1].script_id=data.execution.cases[0].script_id,
    data=>data.execution.cases[1].cu02_case_number=1,data=>data.execution.cu02_evaluation={...data.evaluation,evaluation_id:'CU02-EVAL-'+'8'.repeat(32)}]) {
    const h=harness();await settle();h.state.evaluationReply=(_payload,data)=>{mutate(data);return h.response(data,201);};
    await h.context.evaluateM04Cu02();assert.equal(h.evaluate('m04View.execution'),null);
    assert.match(h.element('#m04-cu02-status').textContent,/연결을 확인/);assert.equal(h.posts('/api/development/m04/executions').length,0);
  }
});
test('retired pages and changed server sessions cannot accept a pending batch response',async()=>{
  for(const kind of ['page','session']) {
    const h=harness();await settle();const gate=deferred();let answer;
    h.state.evaluationReply=(_payload,data)=>{answer=data;return gate.promise;};const pending=h.context.evaluateM04Cu02();
    if(kind==='page') {h.context.renderM04({metric_id:'M04',target:90});await settle();}
    gate.resolve(h.response(answer,201,kind==='session'?'SERVER-other':SERVER));await pending;
    assert.equal(h.evaluate('m04View.execution'),null);assert.equal(h.posts('/api/development/m04/cu02/evaluations').length,1);
  }
});
(async()=>{for(const item of tests){await item.run();console.log('PASS '+item.name);}console.log(tests.length+' M04 CU02 and background runner UI groups passed');})().catch(error=>{console.error(error);process.exitCode=1;});
