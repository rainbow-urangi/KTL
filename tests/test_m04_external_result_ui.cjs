'use strict';
// Synthetic VM responses only. No HTTP service, model, browser, registration or execution.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../frontend/m04.js'),'utf8');
const RUN='DEV-M04-20261112T120000-'+'a'.repeat(12);
const NEXT='DEV-M04-20261112T120001-'+'b'.repeat(12);
const EXECUTION='M04-RUN-'+'c'.repeat(32);
const clone=value=>JSON.parse(JSON.stringify(value));
const settle=async()=>{for(let i=0;i<18;i++)await new Promise(resolve=>setImmediate(resolve));};
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
function fixture(id=RUN,{cases=true,logs=true}={}) {
  const payload={run_mode:'DEVELOPMENT',dataset_id:'synthetic-fixed-scripts',external_run_id:'synthetic-external-run',
    source_module:'synthetic-api-engine',source_version:'fixture-v1',submitted_at:'2026-11-12T12:00:00+00:00',
    dataset_manifest_sha256:'e'.repeat(64),counts:{total_execution_count:2,successful_execution_count:1,failed_execution_count:1},
    details:{},evidence:{artifact:'<img src=x onerror=bad>',scope:'SYNTHETIC'}};
  if(cases) payload.cases=[{case_id:'CASE-001',scenario_id:'SCN-1',status:'PASS'},
    {case_id:'CASE-002',scenario_id:'SCN-2',status:'FAIL',failed_step:4,error_message:'<script>bad</script>',
      steps:[{sequence:4,status:'FAIL',action:'click',target:'#synthetic'}]}];
  if(logs) payload.details.logs=[{time:'synthetic',case_id:'CASE-002',message:'<script>log</script>'}];
  const result={metric_id:'M04',run_mode:'DEVELOPMENT',run_id:id,status:'COMPLETED',score:37.5,sample_count:2,
    dataset_id:payload.dataset_id,details:{raw_counts:clone(payload.counts)},
    provenance:Object.fromEntries(['external_run_id','source_module','source_version','submitted_at'].map(key=>[key,payload[key]])),
    evidence_file:'https://invalid.example/never-follow'};
  return {result,payload};
}
function harness({latest=fixture().result,query='',jobs=[],records=[fixture()],session='SERVER-current'}={}) {
  const elements=new Map(),calls=[],timers=new Map();let timerId=0;
  const element=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',disabled:false,hidden:false,files:[],dataset:{},listeners:{},
    addEventListener(name,callback){this.listeners[name]=callback;},classList:{toggle(){}},click(){return this.listeners.click?.({target:this});}});return elements.get(id);};
  const metric={metric_id:'M04',target:90,latest};
  const state={metric,records:new Map(records.map(row=>[row.result.run_id,row])),jobs,overrides:new Map(),session,url:'',sessionChecks:0};
  const location={pathname:'/metrics/m04',search:'?mode=DEVELOPMENT'+query};
  const context=vm.createContext({URLSearchParams,AbortController,Uint8Array,Date,console,location,
    setTimeout(callback,delay){const id=++timerId;timers.set(id,{callback,delay});return id;},clearTimeout(id){timers.delete(id);},
    history:{replaceState(_a,_b,url){state.url=url;location.search=url.slice(url.indexOf('?'));}},
    document:{querySelector:element},app:element('#app'),banner:()=>'',link:value=>value,labels:{M04:'자동 실행 성공률'},
    catalog:{server_session_id:session,metrics:[metric]},
    ktlCheckServerSession(_response,_data,requested){state.sessionChecks++;if(requested!==state.session){const error=new Error('session changed');error.status='SESSION_EXPIRED';throw error;}},
    esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    score:value=>value==null?'—':Number(value).toFixed(2)+'%',
    fetch:async(url,options)=>{
      calls.push({url,method:options?.method||'GET'});
      if(state.overrides.has(url))return state.overrides.get(url)(options);
      if(url==='/api/evaluations?mode=DEVELOPMENT')return response({server_session_id:state.session,metrics:[state.metric]});
      if(url==='/api/development/m04/scripts')return response({run_mode:'DEVELOPMENT',scripts:[],readiness:{selenium:false,chrome:false}});
      if(url==='/api/development/m04/executions')return response({executions:state.jobs});
      if(url==='/api/development/m03/runs')return response({runs:[]});
      if(url==='/api/development/m07/context')return response({run_mode:'DEVELOPMENT',scenarios:[]});
      if(url==='/api/development/m07/generations')return response({generations:[]});
      if(url.startsWith('/api/development/m04/executions/'))return response({execution:state.jobs.find(job=>url.endsWith(job.execution_id))});
      const match=/^\/api\/evaluations\/m04\/runs\/([^/]+)\/(result.json|received_payload.json)$/.exec(url);
      if(match){const record=state.records.get(match[1]);return record?response(match[2]==='result.json'?record.result:record.payload):response({error:'not found'},404);}
      throw new Error('Unexpected request '+url);
    }});
  vm.runInContext(source,context);context.renderM04(metric);
  return {context,state,calls,element,location,timers,click:id=>element(id).click(),
    noMutations(){assert.deepEqual(calls.filter(call=>call.method!=='GET'),[],'viewing/refreshing/selecting never executes, registers or ingests');}};
}
const results=[];
async function test(name,fn){await fn();results.push(name);console.log('PASS '+name);}
(async()=>{
  await test('latest API result uses server score and submitted denominator without Runner job',async()=>{
    const h=harness();await settle();
    assert.match(h.element('#m04-result').innerHTML,/37\.50%/);
    assert.match(h.element('#m04-result').innerHTML,/外部|외부 API 접수/);
    assert.match(h.element('#m04-result').innerHTML,/전체 실행 테스트<\/label><strong>2/);
    assert.equal(vm.runInContext('m04View.execution',h.context),null);
    assert.equal(h.element('#m04-start').disabled,true);
    assert.ok(h.state.sessionChecks>0);h.noMutations();
  });
  await test('only supplied cases, failure step and escaped evidence are rendered',async()=>{
    const h=harness();await settle();const html=h.element('#m04-cases').innerHTML;
    assert.match(html,/CASE-002/);assert.match(html,/<td>4<\/td>/);assert.match(html,/미제공/);
    assert.match(html,/&lt;script&gt;bad&lt;\/script&gt;/);assert.ok(!html.includes('<script>bad'));
    assert.ok(h.element('#m04-logs').textContent.includes('<script>log</script>'));
    assert.ok(!html.includes('실행 전·후 화면'),'no fabricated screenshot or business step evidence');
    assert.match(h.element('#m04-downloads').innerHTML,/&lt;img src=x onerror=bad&gt;/);h.noMutations();
  });
  await test('counts-only result does not invent cases, failed steps or logs',async()=>{
    const data=fixture(RUN,{cases:false,logs:false}),h=harness({latest:data.result,records:[data]});await settle();
    assert.match(h.element('#m04-cases').innerHTML,/개별 케이스는 제공되지/);
    assert.ok(!h.element('#m04-cases').innerHTML.includes('CASE-'));
    assert.equal(h.element('#m04-logs').textContent,'실행 로그 미제공');h.noMutations();
  });
  await test('download URLs are fixed local stored evidence, not payload-provided URLs',async()=>{
    const h=harness();await settle();const html=h.element('#m04-downloads').innerHTML;
    for(const name of ['result.json','evidence.csv','received_payload.json','run_manifest.json'])assert.ok(html.includes(`/api/evaluations/m04/runs/${RUN}/${name}`));
    assert.ok(!html.includes('invalid.example'));assert.equal(h.context.m04ResultArtifact('../bad','evidence.csv'),null);
    assert.equal(h.context.m04ResultArtifact(RUN,'../secret'),null);h.noMutations();
  });
  await test('reload restores external run with GET only even when a newer latest exists',async()=>{
    const next=fixture(NEXT),h=harness({latest:next.result,query:'&run_id='+RUN,records:[fixture(),next]});await settle();
    assert.match(h.element('#m04-result').innerHTML,new RegExp(RUN));assert.ok(h.state.url.includes('run_id='+RUN));h.noMutations();
  });
  await test('refresh reads current catalog and selects newly accepted external result',async()=>{
    const next=fixture(NEXT),h=harness({records:[fixture(),next]});await settle();h.state.metric={...h.state.metric,latest:next.result};
    await h.click('#m04-refresh');await settle();
    assert.match(h.element('#m04-result').innerHTML,new RegExp(NEXT));
    assert.equal(h.calls.filter(call=>call.url==='/api/evaluations?mode=DEVELOPMENT').length,1);h.noMutations();
  });
  const job={execution_id:EXECUTION,status:'COMPLETED',cases:[{case_id:'LOCAL',status:'PASS'}],counts:{total_execution_count:1,successful_execution_count:1},logs:[],result:{run_id:'local-synthetic',score:88}};
  await test('explicit execution keeps Runner details and external result remains selectable',async()=>{
    const h=harness({query:'&execution_id='+EXECUTION,jobs:[job]});await settle();
    assert.match(h.element('#m04-result').innerHTML,/88\.00%/);assert.match(h.element('#m04-history').innerHTML,/result:DEV-M04/);
    await h.element('#m04-history').listeners.change({target:{value:'result:'+RUN}});await settle();
    assert.match(h.element('#m04-result').innerHTML,/37\.50%/);assert.ok(!h.state.url.includes('execution_id='));
    await h.context.selectM04Execution(EXECUTION);assert.match(h.element('#m04-result').innerHTML,/88\.00%/);
    assert.ok(!h.state.url.includes('run_id='));h.noMutations();
  });
  await test('new external latest is not hidden by an older local execution',async()=>{
    const h=harness({jobs:[job]});await settle();assert.match(h.element('#m04-result').innerHTML,/37\.50%/);h.noMutations();
  });
  await test('active Runner remains the default and cannot be started twice',async()=>{
    const h=harness({jobs:[{...job,status:'RUNNING',result:null}]});await settle();
    assert.match(h.element('#m04-result').innerHTML,/large-score">—/);assert.equal(h.element('#m04-start').disabled,true);
    assert.equal(h.calls.some(call=>call.url===h.context.m04ResultArtifact(RUN)),false);h.noMutations();
  });
  await test('wrong result identity and nonnumeric score do not display success',async()=>{
    for(const update of [{run_id:NEXT},{metric_id:'M07'},{run_mode:'OFFICIAL'},{score:'100'},{score:Infinity}]){
      const data=fixture();Object.assign(data.result,update);const h=harness({latest:fixture().result,records:[{...data,result:{...data.result,run_id:RUN}}]});
      if(update.run_id)h.state.overrides.set(h.context.m04ResultArtifact(RUN),async()=>response(data.result));
      await settle();assert.ok(!h.element('#m04-result').innerHTML.includes('37.50%'));assert.ok(!h.element('#m04-result').innerHTML.includes('100.00%'));h.noMutations();
    }
  });
  await test('wrong original provenance/counts/case shape is rejected',async()=>{
    for(const mutate of [row=>row.payload.dataset_id='other',row=>row.payload.source_module='other',row=>row.payload.counts.total_execution_count=9,row=>row.payload.cases=[null]]){
      const data=fixture();mutate(data);const h=harness({records:[data]});await settle();assert.ok(!h.element('#m04-result').innerHTML.includes('37.50%'));h.noMutations();
    }
  });
  await test('invalid external URL never sends a path traversal request',async()=>{
    const h=harness({latest:null,query:'&run_id=../../secret'});await settle();
    assert.equal(h.calls.some(call=>call.url.includes('secret')),false);h.noMutations();
  });
  await test('older external GET cannot overwrite an explicitly selected Runner job',async()=>{
    const h=harness({latest:null,jobs:[job]});await settle();const late=deferred();
    h.state.overrides.set(h.context.m04ResultArtifact(RUN),()=>late.promise);
    const old=h.context.selectM04Result(RUN);await settle();await h.context.selectM04Execution(EXECUTION);
    late.resolve(response(fixture().result));await old;assert.match(h.element('#m04-result').innerHTML,/88\.00%/);h.noMutations();
  });
  await test('a newly accepted execution invalidates pending external URL and status updates',async()=>{
    const h=harness({latest:null}),late=deferred();await settle();
    h.state.overrides.set(h.context.m04ResultArtifact(RUN),()=>late.promise);
    const old=h.context.selectM04Result(RUN);await settle();
    h.context.acceptM04Execution({...job,status:'RUNNING',result:null});
    const url=h.state.url,status=h.element('#m04-status').textContent;
    late.resolve(response(fixture().result));await old;
    assert.equal(h.state.url,url);assert.ok(h.state.url.includes('execution_id='+EXECUTION));
    assert.equal(h.element('#m04-status').textContent,status);
    assert.equal(vm.runInContext('m04View.resultSource',h.context),'execution');h.noMutations();
  });
  await test('old page and server-session responses cannot paint external result',async()=>{
    const h=harness({latest:null}),late=deferred();await settle();
    h.state.overrides.set(h.context.m04ResultArtifact(RUN),()=>late.promise);
    const old=h.context.selectM04Result(RUN);await settle();h.context.renderM04({metric_id:'M04',target:90});await settle();
    late.resolve(response(fixture().result));await old;assert.ok(!h.element('#m04-result').innerHTML.includes('37.50%'));
    h.state.session='SERVER-new';await h.context.selectM04Result(RUN);assert.ok(!h.element('#m04-result').innerHTML.includes('37.50%'));h.noMutations();
  });
  await test('missing stored original and failed catalog refresh preserve an honest empty/error state',async()=>{
    const h=harness();await settle();h.state.overrides.set(h.context.m04ResultArtifact(RUN,'received_payload.json'),async()=>response({error:'original missing'},404));
    await h.context.selectM04Result(RUN);assert.match(h.element('#m04-status').textContent,/original missing/);
    assert.ok(!h.element('#m04-result').innerHTML.includes('37.50%'));
    h.state.overrides.set('/api/evaluations?mode=DEVELOPMENT',async()=>response({error:'catalog unavailable'},503));
    await h.click('#m04-refresh');assert.match(h.element('#m04-status').textContent,/catalog unavailable/);h.noMutations();
  });
  console.log(`M04 external result UI: ${results.length}/${results.length} synthetic groups passed`);
})().catch(error=>{console.error(error);process.exitCode=1;});
