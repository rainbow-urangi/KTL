// Synthetic UI/API fixtures only. Never contact an LLM or run business automation.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {webcrypto,createHash}=require('node:crypto');
const source=fs.readFileSync('frontend/m07.js','utf8');
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const clone=value=>JSON.parse(JSON.stringify(value));
const hash=value=>createHash('sha256').update(value).digest('hex');
const fixture={run_mode:'DEVELOPMENT',browser:'chrome',login_configured:true,readiness:{selenium:true,chrome:true},
  workflows:[{workflow_id:'CU01',name:'일정 조회',type:'조회',steps:['일정관리','날짜 선택','일정 확인'],available:true},
    {workflow_id:'CU02',name:'일정 등록',type:'등록',steps:['일정관리','날짜 선택','입력','등록','종료'],available:true},
    {workflow_id:'CU03',name:'준비 필요',type:'조회',steps:['조회'],available:false,notice:'원본 확인 필요'}],
  defaults:{date:'2028-02-29',title:'SYNTHETIC UI',description:'SYNTHETIC CONTENT',contact_name:'SYNTHETIC NAME',company:'SYNTHETIC COMPANY',phone:'010-0000-0000',email:'synthetic@example.invalid',lookup_title:'',cases_per_workflow:2},
  parameter_fields:[{name:'contact_name',label:'명함 이름',type:'text'},{name:'cases_per_workflow',label:'업무당 코드 수',type:'number'}]};
const meetingContext={run_mode:'DEVELOPMENT',required_count:20,target_percent:80,readiness:{configured:false,selenium:true,chrome:true,model_display_name:'GPT 루나'}};
function meetingItems() {
  return Array.from({length:20},(_,index)=>{
    const scenario_id='SYNTHETIC-MEETING-'+(index+1);
    return {input_id:'SYNTHETIC-INPUT-'+(index+1),scenario:{scenario_id,scenario_name:'SYNTHETIC CASE '+(index+1),business_unit_id:'SYNTHETIC-BUSINESS',workflow_id:'SYNTHETIC-WORKFLOW',
      steps:[{order:1,action:'input',target:'#synthetic-field',input_value:'SYNTHETIC '+index,expected_result:'SYNTHETIC '+index}],
      execution_contract:{version:1,scenario_id,steps:[{order:1,target:{by:'css selector',value:'#synthetic-field'},checks:[{kind:'value',expected:'SYNTHETIC '+index}]}]}}};
  });
}
function meetingJob(items=meetingItems(),status='QUEUED') {
  const cases=items.map((item,index)=>{
    const code=`SCENARIO_ID = '${item.scenario.scenario_id}'\nassert True\n`;
    return {case_id:'CASE-'+String(index+1).padStart(3,'0'),input_id:item.input_id,...item.scenario,code_source:'LLM',generated_by_llm:true,
      generation_status:status==='QUEUED'?'PENDING':'PASS',syntax_status:'PENDING',execution_status:'PENDING',final_status:'PENDING',code_sha256:hash(code),_code:code,execution_contract_sha256:'b'.repeat(64)};
  });
  return {generation_id:'M07-GEN-'+'d'.repeat(32),meeting_protocol:true,required_count:20,measurement_protocol:'M07_MEETING_20_V1',code_source:'LLM',source_kind:'MEETING_LLM_BATCH',generated_by_llm:true,status,cases,
    counts:{generation_request_count:20,generated_code_count:status==='QUEUED'?0:20,syntax_pass_count:0,execution_pass_count:0,both_pass_count:0},logs:[],
    measurement:{version:1,evaluation_status:'NOT_READY',registered_count:20,provider_http_attempt_count:status==='QUEUED'?0:20,provider_http_unknown_count:0}};
}
function preparedJob(ids=['CU02'],each=2) {
  const cases=[];
  for(const workflow_id of ids)for(let number=1;number<=each;number++) {
    const case_id='CASE-'+String(cases.length+1).padStart(3,'0'),scenario_id='SYNTHETIC-'+workflow_id+'-'+number;
    const code=`SCENARIO_ID = '${scenario_id}'\nassert True\n`,sha=hash(code);
    cases.push({case_id,scenario_id,scenario_name:workflow_id+' synthetic case '+number,workflow_id,workflow_case_number:number,
      browser:'chrome',code_source:'PREPARED',generated_by_llm:false,generation_status:'PASS',syntax_status:'PENDING',execution_status:'PENDING',final_status:'PENDING',
      source_file_sha256:sha,code_sha256:sha,execution_contract_sha256:'b'.repeat(64),source_filename:workflow_id+'.py',_code:code});
  }
  return {generation_id:'M07-GEN-'+'a'.repeat(32),status:'GENERATED',code_source:'PREPARED',source_kind:'RBEM_PREPARED_WORKFLOW',generated_by_llm:false,workflow_ids:ids,cases,
    counts:{generation_request_count:cases.length,generated_code_count:cases.length,syntax_pass_count:0,execution_pass_count:0,both_pass_count:0},logs:[]};
}
function harness(options={}) {
  const elements=new Map(),calls=[],timers=new Map();let nextTimer=0;
  function node(id) {
    if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',disabled:false,hidden:false,attrs:{},listeners:{},
      addEventListener(name,callback){this.listeners[name]=callback;},setAttribute(name,value){this.attrs[name]=value;},insertAdjacentHTML(position,value){this.innerHTML+=value;}});
    return elements.get(id);
  }
  const response=value=>({ok:true,json:async()=>value});
  const context=vm.createContext({URLSearchParams,URL,TextEncoder,TextDecoder,AbortController,crypto:webcrypto,console,Date,Number,Set,Map,
    location:{pathname:'/metrics/m07',search:'?mode=DEVELOPMENT'},history:{replaceState(){}},catalog:{server_session_id:'SERVER-'+'f'.repeat(32)},
    document:{title:'',querySelector:node},app:node('#app'),labels:{M07:'LLM 코드 유효성 및 정확성'},esc,
    score:value=>value==null?'—':Number(value).toFixed(2)+'%',banner:()=>'<p>DEVELOPMENT</p>',link:value=>value,
    setTimeout(callback,delay){const id=++nextTimer;timers.set(id,{callback,delay});return id;},clearTimeout(id){timers.delete(id);},
    fetch:async(url,init={})=>{
      const call={url,method:init.method||'GET',body:init.body?JSON.parse(init.body):null};calls.push(call);
      if(options.fetch){const result=await options.fetch(call);if(result!==undefined)return response(result);}
      if(url==='/api/development/m07/workflows')return response(clone(options.catalog||fixture));
      if(url==='/api/development/m07/meeting-context')return response(clone(options.meetingContext||meetingContext));
      if(url==='/api/development/m07/meeting-generations')return response({generation:meetingJob(call.body.items)});
      if(url==='/api/development/m07/context')return response({run_mode:'DEVELOPMENT',scenarios:[],readiness:{configured:false,selenium:true,chrome:true},target_url:'https://example.invalid'});
      if(url==='/api/development/m07/generations')return response({generations:[]});
      if(url==='/api/development/m07/workflows/prepare') {
        const job=preparedJob(call.body.workflow_ids,call.body.parameters.cases_per_workflow);
        if(options.mutateJob)options.mutateJob(job);
        return response({generation:job,workflows:[]});
      }
      const match=url.match(/\/codes\/(CASE-\d{3})$/);
      if(match) {
        const job=vm.runInContext('m07View.generation',context),row=job.cases.find(item=>item.case_id===match[1]);
        return response({code:row._code,case:row,identity_verification:{verified:true,source_sha256:row.code_sha256,display_sha256:row.code_sha256}});
      }
      if(url.endsWith('/validate')) {
        const job=clone(vm.runInContext('m07View.generation',context));job.status='VALIDATING';return response({generation:job});
      }
      throw new Error('Unexpected synthetic request '+url);
    }});
  vm.runInContext(source,context);
  return {node,calls,context,evaluate:value=>vm.runInContext(value,context),async start(){vm.runInContext('renderM07({target:80})',context);await tick();},
    posts:path=>calls.filter(row=>row.method==='POST'&&(!path||row.url===path)),
    async poll(){const entry=[...timers].find(([,value])=>value.delay===1500);assert.ok(entry,'An active job should remain polled');timers.delete(entry[0]);await entry[1].callback();}};
}
async function tick(){for(let index=0;index<8;index++)await new Promise(resolve=>setImmediate(resolve));}
const tests=[];function test(name,run){tests.push([name,run]);}

test('default entry shows the twenty input LLM meeting flow and keeps prepared workflows auxiliary',async()=>{
  const h=harness();await h.start();assert.equal(h.evaluate('m07View.mode'),'meeting');
  assert.equal(h.node('#m07-meeting-panel').hidden,false);assert.equal(h.node('#m07-workflow-panel').hidden,true);assert.equal(h.node('#m07-llm-panel').hidden,true);
  assert.match(h.node('#m07-workflows').innerHTML,/CU01/);assert.match(h.node('#m07-workflows').innerHTML,/CU02/);
  assert.match(h.node('#m07-workflows').innerHTML,/原本確認|원본 확인 필요/);
  assert.equal(h.node('#m07-workflow-prepare').disabled,false);assert.equal(h.node('#m07-generate').disabled,true);
  assert.equal(h.posts().length,0);assert.match(h.node('#app').innerHTML,/Chrome/);assert.match(h.node('#m07-result').innerHTML,/실행 결과가 이곳/);
  assert.equal((h.node('#m07-cases').innerHTML.match(/data-m07-result-row=/g)||[]).length,20);assert.match(h.node('#m07-meeting-ready').textContent,/GPT 루나.*업무 PC 연결 필요/);
  assert.match(h.node('#app').innerHTML,/<details id="m07-auxiliary"[^>]*>\s*<summary>M03 연결/);
});
test('one preparation request saves prepared provenance and previews exact hashed code without running it',async()=>{
  const h=harness();await h.start();await h.evaluate('prepareM07Workflows()');
  assert.equal(h.posts('/api/development/m07/workflows/prepare').length,1);
  assert.equal(h.posts('/api/development/m07/generations').length,0);assert.equal(h.posts().filter(row=>row.url.endsWith('/validate')).length,0);
  assert.equal(h.evaluate('m07View.generation.code_source'),'PREPARED');assert.equal(h.evaluate('m07View.generation.generated_by_llm'),false);
  assert.equal(h.evaluate('m07View.codeProof.size'),1);assert.match(h.node('#m07-cases').innerHTML,/SCENARIO_ID/);
  assert.match(h.node('#m07-current-source').textContent,/준비한 원본 코드 · LLM 호출 없음/);
  assert.match(h.node('#m07-result').innerHTML,/LLM 생성 성능 집계에서 제외/);assert.ok(!h.node('#m07-export').innerHTML.includes('M04에 고정 등록'));
  assert.equal(h.node('#m07-workflow-prepare').disabled,true);assert.equal(h.node('#m07-validate').disabled,false);
});
test('actual browser validation needs a separate click and does not make another generation request',async()=>{
  const h=harness();await h.start();await h.evaluate('prepareM07Workflows()');await h.evaluate('validateM07()');
  assert.equal(h.posts().filter(row=>row.url.endsWith('/validate')).length,1);
  assert.equal(h.posts('/api/development/m07/workflows/prepare').length,1);assert.equal(h.posts('/api/development/m07/generations').length,0);
  assert.equal(h.evaluate('m07View.generation.status'),'VALIDATING');assert.equal(h.node('#m07-workflow-prepare').disabled,true);
});
test('mode changes preserve the current prepared source and never relabel it as actual LLM output',async()=>{
  const h=harness();await h.start();await h.evaluate('prepareM07Workflows()');h.evaluate("selectM07Mode('llm')");
  assert.equal(h.node('#m07-workflow-panel').hidden,true);assert.equal(h.node('#m07-llm-panel').hidden,false);
  assert.match(h.node('#m07-current-source').textContent,/LLM 호출 없음/);assert.match(h.node('#m07-result').innerHTML,/준비 코드 검사 결과/);
  assert.equal(h.posts('/api/development/m07/generations').length,0);
});
test('workflow selection and numeric case count make two prepared cases per chosen business',async()=>{
  const h=harness();await h.start();h.node('#m07-workflow-all').listeners.click();h.node('#m07-workflow-all').listeners.click();
  assert.match(h.node('#m07-workflow-count').textContent,/2개 업무 · 4개 코드/);await h.evaluate('prepareM07Workflows()');
  const request=h.posts('/api/development/m07/workflows/prepare')[0];assert.deepEqual(request.body.workflow_ids,['CU01','CU02']);
  assert.equal(request.body.parameters.cases_per_workflow,2);assert.equal(h.evaluate('m07View.generation.cases.length'),4);
});
test('missing login, invalid date and invalid case count block preparation while preserving inspection',async()=>{
  const h=harness({catalog:{...clone(fixture),login_configured:false}});await h.start();assert.equal(h.node('#m07-workflow-prepare').disabled,true);
  await h.evaluate('prepareM07Workflows()');assert.equal(h.posts().length,0);
  const good=harness();await good.start();
  for(const value of [0,3,true,'2']) {good.evaluate('m07View.workflows.parameters.cases_per_workflow='+JSON.stringify(value));assert.equal(good.evaluate('m07WorkflowCanPrepare()'),false);}
  good.evaluate("m07View.workflows.parameters.cases_per_workflow=2;m07View.workflows.parameters.date='2027-02-29'");
  assert.equal(good.evaluate('m07WorkflowCanPrepare()'),false);assert.match(good.node('#m07-workflows').innerHTML,/일정 조회/);
});
test('duplicate prepare clicks cannot create simultaneous jobs',async()=>{
  let release;const wait=new Promise(resolve=>release=resolve);
  const h=harness({fetch:async call=>{if(call.url.endsWith('/workflows/prepare')){await wait;return {generation:preparedJob(['CU01','CU02'])};}}});
  await h.start();const first=h.evaluate('prepareM07Workflows()');await tick();await h.evaluate('prepareM07Workflows()');
  assert.equal(h.posts('/api/development/m07/workflows/prepare').length,1);assert.equal(h.node('#m07-workflow-prepare').disabled,true);
  release();await first;
});
test('inconsistent workflow identities and fabricated LLM provenance are rejected without execution',async()=>{
  for(const mutateJob of [job=>job.generated_by_llm=true,job=>job.cases[0].workflow_id='CU10',job=>job.cases[0].browser='edge',job=>job.workflow_ids=['CU01'],job=>job.cases[1].workflow_case_number=1]) {
    const h=harness({mutateJob});await h.start();await h.evaluate('prepareM07Workflows()');
    assert.equal(h.evaluate('m07View.generation'),null);assert.match(h.node('#m07-status').textContent,/출처와 실행 기록/);
    assert.equal(h.posts().filter(row=>row.url.endsWith('/validate')).length,0);
  }
});
test('prepared workflow jobs cannot be exported as M03 based generated scripts',async()=>{
  const h=harness();await h.start();await h.evaluate('prepareM07Workflows()');await h.evaluate('exportM07ToM04()');
  assert.equal(h.posts().filter(row=>row.url.endsWith('/export-m04')).length,0);
  assert.ok(!h.node('#m07-cases').innerHTML.includes('data-m07-export'));
});
test('catalog and input text are escaped and unavailable cards remain disabled',async()=>{
  const catalog=clone(fixture);catalog.workflows[0].name='<img src=x onerror=alert(1)>';catalog.defaults.company='" autofocus onfocus="x';
  const h=harness({catalog});await h.start();assert.ok(h.node('#m07-workflows').innerHTML.includes('&lt;img'));
  assert.ok(!h.node('#m07-workflows').innerHTML.includes('<img'));assert.ok(h.node('#m07-workflow-extra-fields').innerHTML.includes('&quot; autofocus'));
  assert.match(h.node('#m07-workflows').innerHTML,/data-workflow-id="CU03"\s+disabled/);
});
test('late preparation cannot repopulate a retired page',async()=>{
  let release;const wait=new Promise(resolve=>release=resolve);
  const h=harness({fetch:async call=>{if(call.url.endsWith('/workflows/prepare')){await wait;return {generation:preparedJob(['CU01','CU02'])};}}});
  await h.start();const pending=h.evaluate('prepareM07Workflows()');await tick();h.context.location.pathname='/metrics/m01';release();await pending;
  assert.equal(h.evaluate('m07View.generation'),null);
});
test('viewing older history keeps a different active job polled without replacing the chosen result',async()=>{
  const old=preparedJob(['CU01','CU02']);old.generation_id='M07-GEN-'+'b'.repeat(32);old.status='COMPLETED';
  const active=preparedJob(['CU01','CU02']);active.status='COMPLETED';active.cases.forEach(row=>Object.assign(row,{syntax_status:'PASS',execution_status:'PASS',final_status:'PASS'}));
  active.counts.syntax_pass_count=active.counts.execution_pass_count=active.counts.both_pass_count=active.cases.length;
  active.result={score:100,run_id:active.generation_id};
  const h=harness({fetch:async call=>{
    if(call.url==='/api/development/m07/generations/'+old.generation_id)return {generation:old};
    if(call.url==='/api/development/m07/generations/'+active.generation_id)return {generation:active};
  }});
  await h.start();await h.evaluate('prepareM07Workflows()');await h.evaluate('validateM07()');
  await h.evaluate(`selectM07Generation('${old.generation_id}')`);await h.poll();
  assert.equal(h.evaluate('m07View.generation.generation_id'),old.generation_id);
  assert.equal(h.evaluate('m07View.generations.find(row=>row.generation_id===\''+active.generation_id+'\').status'),'COMPLETED');
  assert.equal(h.evaluate('m07View.generations.some(m07Running)'),false);
  h.evaluate("m07View.workflows.parameters.title='SYNTHETIC NEXT RUN'");assert.equal(h.evaluate('m07WorkflowCanPrepare()'),true);
});
test('an old in flight poll cannot revive a running state after a newer history selection',async()=>{
  let release,started=false;const wait=new Promise(resolve=>release=resolve);
  const completed=preparedJob(['CU01','CU02']);completed.status='COMPLETED';
  const running=clone(completed);running.status='VALIDATING';
  const identity=completed.generation_id;
  const h=harness({fetch:async call=>{
    if(call.url==='/api/development/m07/generations/'+identity) {
      if(!started){started=true;await wait;return {generation:running};}
      return {generation:completed};
    }
  }});
  await h.start();await h.evaluate('prepareM07Workflows()');await h.evaluate('validateM07()');
  const pending=h.poll();await tick();await h.evaluate(`selectM07Generation('${identity}')`);release();await pending;
  assert.equal(h.evaluate('m07View.generation.status'),'COMPLETED');assert.equal(h.evaluate('m07View.generations.some(m07Running)'),false);
});
test('real LLM generation remains a separate explicit action with original M03 references',async()=>{
  const run='DEV-M03-20261113T000000-'+'c'.repeat(12),scenario='SYNTHETIC-M03-SCENARIO';
  const h=harness({fetch:async call=>{
    if(call.url==='/api/development/m07/generations'&&call.method==='POST') {
      const job=preparedJob(['CU01'],1);delete job.code_source;delete job.source_kind;delete job.generated_by_llm;job.status='QUEUED';return {generation:job};
    }
  }});
  await h.start();h.evaluate(`m07View.context.readiness.configured=true;m07View.context.scenarios=[{m03_run_id:'${run}',scenario_id:'${scenario}',execution_ready:true}];m07View.selected=new Set(['${scenario}']);selectM07Mode('llm')`);
  await h.evaluate('startM07()');const requests=h.posts('/api/development/m07/generations');assert.equal(requests.length,1);
  assert.deepEqual(requests[0].body,{scenario_refs:[{m03_run_id:run,scenario_id:scenario}]});
  assert.equal(h.posts('/api/development/m07/workflows/prepare').length,0);assert.equal(h.node('#m07-workflow-panel').hidden,true);
});
test('all ten available business workflows form twenty prepared code cases by default',async()=>{
  const catalog=clone(fixture);catalog.workflows=Array.from({length:10},(_,index)=>({workflow_id:'CU'+String(index+1).padStart(2,'0'),name:'SYNTHETIC WORKFLOW '+(index+1),type:'synthetic',steps:['synthetic step'],available:true}));
  const h=harness({catalog});await h.start();assert.match(h.node('#m07-workflow-count').textContent,/10개 업무 · 20개 코드/);
  await h.evaluate('prepareM07Workflows()');assert.equal(h.evaluate('m07View.generation.cases.length'),20);
  assert.equal(h.evaluate('m07View.codeProof.size'),1);assert.equal((h.node('#m07-cases').innerHTML.match(/data-m07-case=/g)||[]).length,20);
  assert.equal((h.node('#m07-cases').innerHTML.match(/data-m07-case="[^"]+" open/g)||[]).length,1);
});
test('prepared workflow readiness stays usable when LLM context is unavailable',async()=>{
  const h=harness();await h.start();await h.evaluate('prepareM07Workflows()');h.evaluate('m07View.context=null;paintM07()');
  assert.equal(h.node('#m07-validate').disabled,false);assert.match(h.node('#m07-current-source').textContent,/Chrome 실행 검사 준비됨/);
  await h.evaluate('validateM07()');assert.equal(h.posts().filter(row=>row.url.endsWith('/validate')).length,1);
});
test('a queued prepared job opens the first original once when polling reaches GENERATED',async()=>{
  const completed=preparedJob(['CU01','CU02']),queued=clone(completed);queued.status='QUEUED';queued.cases.forEach(row=>row.generation_status='PENDING');
  const h=harness({fetch:async call=>{
    if(call.url.endsWith('/workflows/prepare'))return {generation:queued};
    if(call.url==='/api/development/m07/generations/'+completed.generation_id)return {generation:completed};
  }});
  await h.start();await h.evaluate('prepareM07Workflows()');
  assert.equal(h.calls.filter(row=>/\/codes\//.test(row.url)).length,0);assert.match(h.node('#m07-workflow-status').textContent,/준비 중/);
  await h.poll();await tick();assert.equal(h.calls.filter(row=>/\/codes\//.test(row.url)).length,1);
  assert.equal(h.evaluate('m07View.codeProof.size'),1);assert.match(h.node('#m07-cases').innerHTML,/SCENARIO_ID/);
  assert.match(h.node('#m07-workflow-status').textContent,/원본 코드를 준비했습니다/);
  await h.evaluate("readM07Code('CASE-001')");assert.equal(h.evaluate("m07View.openCode.has('CASE-001')"),false);
  await h.evaluate('acceptM07Generation(m07View.generation)');
  assert.equal(h.calls.filter(row=>/\/codes\//.test(row.url)).length,1);assert.equal(h.evaluate("m07View.openCode.has('CASE-001')"),false);
});
test('a late automatic preview cannot replace code or expand cases in a different selected history',async()=>{
  const completed=preparedJob(['CU01','CU02']),queued=clone(completed);queued.status='QUEUED';queued.cases.forEach(row=>row.generation_status='PENDING');
  const old=preparedJob(['CU01','CU02']);old.generation_id='M07-GEN-'+'b'.repeat(32);old.status='COMPLETED';
  let release,started=false;const wait=new Promise(resolve=>release=resolve);
  const h=harness({fetch:async call=>{
    if(call.url.endsWith('/workflows/prepare'))return {generation:queued};
    if(call.url==='/api/development/m07/generations/'+completed.generation_id)return {generation:completed};
    if(call.url==='/api/development/m07/generations/'+old.generation_id)return {generation:old};
    if(/\/codes\//.test(call.url)){
      started=true;await wait;const row=completed.cases[0];
      return {code:row._code,case:row,identity_verification:{verified:true,source_sha256:row.code_sha256,display_sha256:row.code_sha256}};
    }
  }});
  await h.start();await h.evaluate('prepareM07Workflows()');await h.poll();await tick();assert.equal(started,true);
  await h.evaluate(`selectM07Generation('${old.generation_id}')`);release();await tick();
  assert.equal(h.evaluate('m07View.generation.generation_id'),old.generation_id);assert.equal(h.evaluate('m07View.code.size'),0);
  assert.equal(h.evaluate('m07View.openCode.size'),0);assert.ok(!h.node('#m07-cases').innerHTML.includes('<div class="m07-code"'));
});
test('prepared title and description validation follows the ninety character nonempty backend contract',async()=>{
  const h=harness();await h.start();h.evaluate("m07View.workflows.parameters.title='x'.repeat(91)");
  assert.equal(h.evaluate('m07WorkflowCanPrepare()'),false);h.evaluate("m07View.workflows.parameters.title='x'.repeat(90)");
  assert.equal(h.evaluate('m07WorkflowCanPrepare()'),true);h.evaluate("m07View.workflows.parameters.description='   '");
  assert.equal(h.evaluate('m07WorkflowCanPrepare()'),false);assert.match(h.node('#app').innerHTML,/id="m07-workflow-title"[^>]*maxlength="90"/);
});
test('automatic preview hash failures remain visible instead of being overwritten by preparation success',async()=>{
  const job=preparedJob(['CU01','CU02']),row=job.cases[0];
  const h=harness({fetch:async call=>{
    if(/\/codes\//.test(call.url))return {code:row._code,case:row,identity_verification:{verified:true,source_sha256:'0'.repeat(64),display_sha256:row.code_sha256}};
  }});
  await h.start();await h.evaluate('prepareM07Workflows()');assert.equal(h.evaluate('m07View.codeProof.size'),0);
  assert.match(h.node('#m07-status').textContent,/SHA-256/);assert.match(h.node('#m07-workflow-status').textContent,/다시 확인/);
  assert.equal(h.evaluate("m07View.openCode.has('CASE-001')"),false);
});
function setMeetingInput(h,items=meetingItems()) {h.node('#m07-meeting-input').value=JSON.stringify({items});return h.evaluate('checkM07MeetingInput()');}
const configuredMeeting=()=>({...clone(meetingContext),readiness:{...meetingContext.readiness,configured:true,model:'synthetic-model-id'}});
function completedMeeting(passed=16) {
  const job=meetingJob(meetingItems(),'COMPLETED');
  job.cases.forEach((row,index)=>Object.assign(row,{syntax_status:index<passed?'PASS':'FAIL',execution_status:index<passed?'PASS':'SKIPPED',final_status:index<passed?'PASS':'FAIL'}));
  Object.assign(job.counts,{syntax_pass_count:passed,execution_pass_count:passed,both_pass_count:passed});
  Object.assign(job.measurement,{evaluation_status:'COMPLETED',integrated_percent:100,both_pass_count:20});
  job.result={score:100,run_id:job.generation_id};return job;
}
test('twenty structured inputs produce one explicit batch request and never trigger validation automatically',async()=>{
  const h=harness({meetingContext:configuredMeeting()});await h.start();assert.equal(setMeetingInput(h),true);
  assert.equal(h.node('#m07-meeting-generate').disabled,false);assert.equal(h.posts().length,0);
  await h.evaluate('startM07Meeting()');assert.equal(h.posts('/api/development/m07/meeting-generations').length,1);
  assert.deepEqual(h.posts('/api/development/m07/meeting-generations')[0].body,{items:meetingItems()});
  assert.equal(h.posts().filter(row=>row.url.endsWith('/validate')).length,0);assert.equal(h.posts('/api/development/m07/workflows/prepare').length,0);
  assert.equal(h.evaluate('m07View.generation.meeting_protocol'),true);assert.equal((h.node('#m07-cases').innerHTML.match(/data-m07-result-row=/g)||[]).length,20);
  assert.match(h.node('#m07-result').innerHTML,/최종 성공률|완료되면/);
});
test('meeting input count, duplicate identity, duplicate content and missing execution conditions are rejected',async()=>{
  const h=harness({meetingContext:configuredMeeting()});await h.start();
  const invalid=[meetingItems().slice(1),[...meetingItems(),meetingItems()[0]]];
  let items=meetingItems();items[1].input_id=items[0].input_id;invalid.push(items);
  items=meetingItems();items[1].scenario.scenario_id=items[0].scenario.scenario_id;invalid.push(items);
  items=meetingItems();const second=items[1];second.scenario=clone(items[0].scenario);second.scenario.scenario_id='DIFFERENT-ID';second.scenario.scenario_name='DIFFERENT NAME';second.scenario.execution_contract.scenario_id='DIFFERENT-ID';invalid.push(items);
  items=meetingItems();delete items[0].scenario.execution_contract;invalid.push(items);
  for(const input of invalid){assert.equal(setMeetingInput(h,input),false);await h.evaluate('startM07Meeting()');assert.equal(h.node('#m07-meeting-generate').disabled,true);}
  assert.equal(h.posts().length,0);
});
test('missing actual model configuration blocks LLM generation with an explicit work computer connection notice',async()=>{
  const h=harness();await h.start();assert.equal(setMeetingInput(h),true);await h.evaluate('startM07Meeting()');
  assert.equal(h.node('#m07-meeting-generate').disabled,true);assert.equal(h.posts().length,0);
  assert.match(h.node('#m07-meeting-ready').textContent,/GPT 루나.*업무 PC 연결 필요/);assert.match(h.node('#m07-status').textContent,/실제 LLM API 키와 모델/);
  assert.ok(!h.node('#m07-result').innerHTML.includes('100.00%'));
});
test('changing the textarea after confirmation invalidates the batch and oversized files cannot reuse old confirmation',async()=>{
  const h=harness({meetingContext:configuredMeeting()});await h.start();setMeetingInput(h);
  h.node('#m07-meeting-input').value='[]';h.node('#m07-meeting-input').listeners.input();
  assert.equal(h.node('#m07-meeting-generate').disabled,true);await h.evaluate('startM07Meeting()');assert.equal(h.posts().length,0);
  setMeetingInput(h);await h.node('#m07-meeting-file').listeners.change({target:{files:[{size:262145,text:async()=>{throw new Error('must not read');}}]}});
  assert.equal(h.evaluate('m07View.meeting.items.length'),0);assert.equal(h.node('#m07-meeting-generate').disabled,true);assert.match(h.node('#m07-meeting-status').textContent,/256 KiB/);
});
test('a reviewed draft is loaded only by an explicit request and never generates code or claims a completed trial',async()=>{
  const h=harness({meetingContext:configuredMeeting(),fetch:async call=>{if(call.url.endsWith('/meeting-input-draft'))return {draft:true,description:'SYNTHETIC 검토용 초안 · 시험 입력 확정 아님',items:meetingItems()};}});
  await h.start();assert.equal(h.calls.filter(row=>row.url.endsWith('/meeting-input-draft')).length,0);
  await h.evaluate('loadM07MeetingDraft()');assert.equal(h.evaluate('m07View.meeting.items.length'),20);
  assert.match(h.node('#m07-meeting-status').textContent,/검토용 초안.*시험 입력 확정 아님/);assert.equal(h.posts().length,0);assert.equal(h.evaluate('m07View.generation'),null);
});
test('duplicate generation clicks make only one request and prepared provenance cannot replace a meeting result',async()=>{
  let release;const wait=new Promise(resolve=>release=resolve);
  const h=harness({meetingContext:configuredMeeting(),fetch:async call=>{if(call.url.endsWith('/meeting-generations')){await wait;return {generation:preparedJob(['CU01'])};}}});
  await h.start();setMeetingInput(h);const pending=h.evaluate('startM07Meeting()');await tick();await h.evaluate('startM07Meeting()');
  assert.equal(h.posts('/api/development/m07/meeting-generations').length,1);release();await pending;
  assert.equal(h.evaluate('m07View.generation'),null);assert.match(h.node('#m07-status').textContent,/출처/);
});
test('meeting generation response identities must match all twenty submitted inputs',async()=>{
  const job=meetingJob();job.cases[19].scenario_id='DIFFERENT-INPUT';
  const h=harness({meetingContext:configuredMeeting(),fetch:async call=>{if(call.url.endsWith('/meeting-generations'))return {generation:job};}});
  await h.start();setMeetingInput(h);await h.evaluate('startM07Meeting()');assert.equal(h.evaluate('m07View.generation'),null);assert.match(h.node('#m07-status').textContent,/입력과 출처/);
});
test('completed meeting score is fixed at sixteen of twenty and fifteen passes fails the eighty percent target',async()=>{
  for(const [passed,expected,verdict]of [[16,'80.00%','기준 충족'],[15,'75.00%','기준 미달']]){
    const h=harness({meetingContext:configuredMeeting()});await h.start();h.context.syntheticJob=completedMeeting(passed);h.evaluate('acceptM07Generation(syntheticJob)');
    assert.match(h.node('#m07-result').innerHTML,new RegExp('class="large-score">'+expected));assert.match(h.node('#m07-result').innerHTML,new RegExp(verdict));
    assert.match(h.node('#m07-result').innerHTML,/실패도 분모 20건에 포함/);assert.equal((h.node('#m07-cases').innerHTML.match(/data-m07-result-row=/g)||[]).length,20);
    assert.ok(!h.node('#m07-export').innerHTML.includes('M04에 고정 등록'));assert.equal(h.node('#m07-cases').innerHTML.includes('data-m07-export'),false);
  }
});
test('generation failures remain in the twenty case denominator and syntax PASS alone cannot produce a final PASS',async()=>{
  const h=harness({meetingContext:configuredMeeting()});await h.start();const job=completedMeeting(16);
  Object.assign(job.cases[19],{generation_status:'FAIL',syntax_status:'SKIPPED',execution_status:'SKIPPED',final_status:'FAIL'});job.counts.generated_code_count=19;
  h.context.syntheticJob=job;h.evaluate('acceptM07Generation(syntheticJob)');assert.match(h.node('#m07-result').innerHTML,/class="large-score">80.00%/);
  Object.assign(job.cases[15],{syntax_status:'PASS',execution_status:'FAIL',final_status:'PASS'});h.context.syntheticJob=job;h.evaluate('acceptM07Generation(syntheticJob)');
  assert.match(h.node('#m07-result').innerHTML,/class="large-score">75.00%/);
});
test('incomplete work or missing HTTP attempt evidence keeps the final score pending even with a stored success percentage',async()=>{
  for(const mutate of [job=>job.status='VALIDATING',job=>job.measurement.provider_http_attempt_count=19,job=>job.measurement.provider_http_unknown_count=1,job=>job.cases[19].execution_status='PENDING']){
    const h=harness({meetingContext:configuredMeeting()});await h.start();const job=completedMeeting(20);mutate(job);h.context.syntheticJob=job;h.evaluate('acceptM07Generation(syntheticJob)');
    assert.match(h.node('#m07-result').innerHTML,/class="large-score">—/);assert.ok(!h.node('#m07-result').innerHTML.includes('100.00%'));assert.match(h.node('#m07-result').innerHTML,/검사 대기/);
  }
});
test('actual meeting code uses exact hash verification and separate validation with meeting readiness',async()=>{
  const h=harness({meetingContext:configuredMeeting()});await h.start();h.context.syntheticJob=meetingJob(meetingItems(),'GENERATED');h.evaluate('acceptM07Generation(syntheticJob);m07View.context=null;paintM07()');
  assert.equal(h.node('#m07-validate').disabled,false);await h.evaluate("readM07Code('CASE-001')");assert.equal(h.evaluate('m07View.codeProof.size'),1);
  await h.evaluate('validateM07()');assert.equal(h.posts().filter(row=>row.url.endsWith('/validate')).length,1);assert.equal(h.posts('/api/development/m07/meeting-generations').length,0);
  const bad=harness({meetingContext:configuredMeeting(),fetch:async call=>{if(/\/codes\//.test(call.url)){const row=meetingJob(meetingItems(),'GENERATED').cases[0];return {code:row._code+'# changed',case:row,identity_verification:{verified:true,source_sha256:row.code_sha256,display_sha256:row.code_sha256}};}}});
  await bad.start();bad.context.syntheticJob=meetingJob(meetingItems(),'GENERATED');bad.evaluate('acceptM07Generation(syntheticJob)');await bad.evaluate("readM07Code('CASE-001')");
  assert.equal(bad.evaluate('m07View.codeProof.size'),0);assert.equal(bad.evaluate('m07View.code.size'),0);assert.match(bad.node('#m07-status').textContent,/실제 LLM 생성 원본.*SHA-256/);
});
test('late file or batch replies cannot modify a retired page and all twenty table labels remain escaped',async()=>{
  let release;const wait=new Promise(resolve=>release=resolve);const h=harness({meetingContext:configuredMeeting()});await h.start();
  const pending=h.node('#m07-meeting-file').listeners.change({target:{files:[{size:1,text:async()=>{await wait;return JSON.stringify(meetingItems());}}]}});
  await tick();h.context.location.pathname='/metrics/m01';release();await pending;assert.equal(h.evaluate('m07View.meeting.items.length'),0);
  const safe=harness();await safe.start();const job=meetingJob(meetingItems(),'GENERATED');job.cases[0].scenario_name='<img src=x onerror=x>';safe.context.syntheticJob=job;safe.evaluate('acceptM07Generation(syntheticJob)');
  assert.ok(!safe.node('#m07-cases').innerHTML.includes('<img'));assert.match(safe.node('#m07-cases').innerHTML,/&lt;img/);
});
(async()=>{for(const [name,run]of tests){await run();console.log('PASS '+name);}console.log(tests.length+' M07 meeting and prepared workflow UI groups passed');})().catch(error=>{console.error(error);process.exitCode=1;});
