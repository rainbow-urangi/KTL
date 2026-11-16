'use strict';
// Synthetic VM/API bridge only. No HTTP, browser, model, provider or business call.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.resolve(__dirname,'../frontend/m04.js'),'utf8');
const SERVER='SERVER-'+'a'.repeat(32),RUN='DEV-M03-20261113T120000-'+'b'.repeat(12),RUN2='DEV-M03-20261113T120001-'+'c'.repeat(12);
const ID='SYNTHETIC-M03-ONE',ID2='SYNTHETIC-M03-TWO',SHA='d'.repeat(64),SHA2='e'.repeat(64),CODE='f'.repeat(64);
const SCRIPT='1'.repeat(32),OLD='2'.repeat(32),EXEC='M04-RUN-'+'3'.repeat(32);
const LIST='/api/development/m04/m03-scenarios',PREPARE='/api/development/m04/prepare-m03',EXECUTE='/api/development/m04/executions';
const clone=value=>JSON.parse(JSON.stringify(value));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const settle=async()=>{for(let i=0;i<18;i++)await new Promise(done=>setImmediate(done));};
function descriptor(id=ID,run=RUN){return {scenario_id:id,m03_run_id:run,source_scenario_sha256:id===ID?SHA:SHA2,
  business_unit_id:'SYNTHETIC-BU',workflow_id:'SYNTHETIC-WF',scenario_name:'Synthetic scenario '+id,
  source_status:'SUCCESS',source_step_count:3,ready:true,status:'READY',requires_login:true,message:'Synthetic ready',
  parameters:[{name:'title',label:'Synthetic title',type:'text',default:'Synthetic default',required:true}]};}
function listing(run=RUN,rows=[descriptor(ID,run),descriptor(ID2,run)]){return {run_mode:'DEVELOPMENT',m03_run_id:run,
  runs:[RUN,RUN2].map(id=>({run_id:id,completed_at:'2026-11-13T12:00:00+09:00',scenario_count:2})),scenarios:rows,
  readiness:{selenium:true,chrome:true,login_configured:true},generated_by_llm:false};}
function script(payload,id=SCRIPT){return {script_id:id,filename:'synthetic-m03.py',sha256:CODE,execution_ready:true,
  source_kind:'M03_COMPILED_SCRIPT',generated_by_llm:false,business_step_required:true,
  scenario_id:payload.scenario_id,source_m03_run_id:payload.m03_run_id,source_scenario_sha256:payload.source_scenario_sha256};}
function execution(prepared){return {execution_id:EXEC,status:'RUNNING',logs:[],result:null,
  cases:[{case_id:'CASE-001',script_id:prepared.script_id,scenario_id:prepared.scenario_id,
    source_m03_run_id:prepared.source_m03_run_id,status:'PENDING'}],counts:{total_execution_count:1,successful_execution_count:0}};}
function detailAncestors(html,id){
  const offset=html.indexOf(`id="${id}"`);assert.notEqual(offset,-1,'Missing UI contract '+id);const stack=[];
  for(const match of html.slice(0,offset).matchAll(/<\/?details\b[^>]*>/gi)){
    if(/^<\//.test(match[0]))stack.pop();else stack.push(match[0]);
  }return stack;
}
function harness({data=listing(),query='',initialScripts=[],jobs=[]}={}){
  const calls=[],elements=new Map(),timers=new Map();let timerId=0;
  const state={data:clone(data),contexts:new Map(),contextReply:null,prepareReply:null,executeReply:null,
    scripts:clone(initialScripts),jobs:clone(jobs),lastScript:null};
  const location={pathname:'/metrics/m04',search:'?mode=DEVELOPMENT'+query};
  const element=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',value:'',disabled:false,
    hidden:false,checked:false,files:[],dataset:{},listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},querySelectorAll(){return [];}});return elements.get(id);};
  const reply=(body,status=200,session=SERVER)=>({ok:status>=200&&status<300,status,headers:{get:()=>session},json:async()=>clone(body)});
  const context=vm.createContext({URLSearchParams,AbortController,Uint8Array,Date,console,location,
    setTimeout(fn,delay){const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),
    history:{replaceState(_a,_b,url){location.search=url.includes('?')?url.slice(url.indexOf('?')):'';}},
    document:{querySelector:element},app:element('#app'),banner:()=>'',link:value=>value,labels:{M04:'M04'},
    esc:value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),
    score:value=>value==null?'—':value+'%',catalog:{server_session_id:SERVER,metrics:[]},
    ktlDropQuery(keys){const q=new URLSearchParams(location.search);keys.forEach(key=>q.delete(key));location.search='?'+q;},
    m03ResultPath:(id,name='result.json')=>`/api/evaluations/m03/runs/${id}/${name}`,
    ktlCheckServerSession(response){if(response.headers.get()!==SERVER){const error=new Error('Synthetic server session changed');error.status='SESSION_EXPIRED';throw error;}},
    fetch:async(url,options)=>{
      const payload=options?.body?JSON.parse(options.body):undefined;calls.push({url,method:options?.method||'GET',payload});
      if(url===LIST||url.startsWith(LIST+'?')){
        const run=new URLSearchParams(url.split('?')[1]||'').get('m03_run_id');
        const data=clone(state.contexts.get(run)||state.data);
        return state.contextReply?state.contextReply(url,data):reply(data);
      }
      if(url===PREPARE){
        const result={script:script(payload),generated_by_llm:false};
        if(state.prepareReply)return state.prepareReply(payload,result);
        state.lastScript=result.script;state.scripts.unshift(result.script);return reply(result,201);
      }
      if(url===EXECUTE){
        if(!payload)return reply({executions:state.jobs});
        const next=execution(state.lastScript||state.scripts.find(row=>row.script_id===payload.script_ids[0]));
        if(state.executeReply)return state.executeReply(payload,next);
        state.jobs.unshift(next);return reply({execution:next},202);
      }
      if(url==='/api/development/m04/scripts')return reply({run_mode:'DEVELOPMENT',scripts:state.scripts,readiness:{selenium:true,chrome:true}});
      if(url==='/api/development/m03/runs')return reply({runs:query.includes('m03_run_id=')?[{run_id:RUN}]:[]});
      if(url===`/api/evaluations/m03/runs/${RUN}/result.json`)return reply({metric_id:'M03',run_mode:'DEVELOPMENT',run_id:RUN});
      if(url===`/api/evaluations/m03/runs/${RUN}/received_payload.json`)return reply({scenarios:[{scenario_id:ID,scenario_name:'Synthetic source',steps:[]}]});
      if(url==='/api/development/m04/cu02')return reply({error:'Synthetic optional CU02 not configured'},503);
      if(url==='/api/development/m07/context')return reply({run_mode:'DEVELOPMENT',scenarios:[],readiness:{configured:false}});
      if(url==='/api/development/m07/generations')return reply({generations:[]});
      if(url==='/api/development/m01/csv')return reply({datasets:[]});
      throw new Error('Unexpected synthetic API '+url);
    }});
  vm.runInContext(source,context);context.renderM04({metric_id:'M04',target:90});
  const evaluate=code=>vm.runInContext(code,context);
  return {context,state,calls,element,reply,evaluate,location,timers,
    quick:()=>element('#m04-quick-start').listeners.click(),
    select:id=>element('#m04-m03-scenario').listeners.change({target:{value:id}}),
    field(name,value){element('#m04-m03-parameters').listeners.input({target:{dataset:{m03Parameter:name},value}});},
    posts:route=>calls.filter(call=>call.method==='POST'&&(!route||call.url===route))};
}
const tests=[];const test=(name,run)=>tests.push({name,run});
test('entry shows one M03 test choice and runner action while history and fixed scripts stay in closed settings with GET only',async()=>{
  const h=harness();await settle();assert.equal(h.evaluate('m04View.m03.selectedId'),ID);
  assert.equal(h.element('#m04-quick-start').disabled,false);assert.equal(h.posts().length,0);
  assert.match(h.element('#m04-m03-scenario').innerHTML,/SYNTHETIC-M03-ONE/);
  const html=h.element('#app').innerHTML;
  assert.doesNotMatch(html,/id="m04-input-mode"/);
  for(const id of ['m04-quick-panel','m04-m03-scenario','m04-m03-parameters','m04-quick-start'])assert.deepEqual(detailAncestors(html,id),[]);
  const primary=html.match(/<section class="evaluation-panel m04-panel m04-main-panel">([\s\S]*?)<\/section>/)[1];
  assert.equal((primary.match(/<select\b/g)||[]).length,1,'one test choice in the primary flow');
  assert.match(primary,/id="m04-m03-scenario"/);assert.doesNotMatch(primary,/id="m04-m03-run"|id="m04-file"/);
  for(const id of ['m04-m03-run','m04-fixed-panel','m04-register','m04-start','m04-cu02-quick-start']) {
    const settings=detailAncestors(html,id).find(tag=>tag.includes('id="m04-code-preparation"'));
    assert.ok(settings,id);assert.doesNotMatch(settings,/\sopen(?:\s|=|>)/);
  }
  assert.equal(h.element('#m04-result').hidden,true);assert.equal(h.element('#m04-result').innerHTML,'');
  assert.equal(h.element('#m04-result-empty').hidden,false);
});
test('opening optional settings and repainting preserve exact source parameters and fixed-script selection without requests',async()=>{
  const h=harness({initialScripts:[script({m03_run_id:RUN,scenario_id:ID,source_scenario_sha256:SHA},OLD)]});await settle();
  h.field('title','Synthetic unchanged input');h.evaluate(`m04View.selected.add('${OLD}')`);const before=h.calls.length;
  h.element('#m04-code-preparation').open=true;h.context.paintM04();
  assert.equal(h.element('#m04-start').disabled,false);
  h.element('#m04-code-preparation').open=false;h.context.paintM04();
  assert.equal(h.element('#m04-start').disabled,false);assert.notEqual(h.element('#m04-fixed-panel').hidden,true);
  assert.equal(h.evaluate('m04View.m03.selectedId'),ID);assert.equal(h.evaluate('m04View.m03.parameters.title'),'Synthetic unchanged input');
  assert.deepEqual(clone(h.evaluate('[...m04View.selected]')),[OLD]);assert.equal(h.calls.length,before);assert.equal(h.posts().length,0);
});
test('active work locks primary M03 and optional fixed execution without starting or replacing an execution',async()=>{
  for(const state of ['busy','preparation','runner']){
    const h=harness({initialScripts:[script({m03_run_id:RUN,scenario_id:ID,source_scenario_sha256:SHA},OLD)]});await settle();
    h.evaluate(`m04View.selected.add('${OLD}')`);
    if(state==='busy')h.evaluate('m04View.busy=true');
    if(state==='preparation')h.evaluate('m04View.preparation.busy=true');
    if(state==='runner')h.evaluate(`m04View.executions=[{execution_id:'${EXEC}',status:'RUNNING'}]`);
    h.context.paintM04();assert.equal(h.element('#m04-start').disabled,true,state);
    assert.equal(h.element('#m04-quick-start').disabled,true,state);
    await h.context.startM04();await h.quick();
    assert.deepEqual(clone(h.evaluate('[...m04View.selected]')),[OLD]);assert.equal(h.posts().length,0);
  }
});
test('final goal badge uses the server verdict and keeps partial or missing evaluation neutral',async()=>{
  for(const [rate,verdict,total,status,label] of [[90,true,10,'COMPLETED','기준 충족'],[80,false,10,'COMPLETED','기준 미달'],
    [80,true,10,'COMPLETED','기준 충족'],[100,true,1,'COMPLETED','부분 검증'],[null,true,10,'COMPLETED','판정 대기'],
    [100,true,10,'INTERRUPTED','판정 대기'],[90,null,10,'COMPLETED','판정 대기']]){
    const h=harness();await settle();
    h.evaluate(`m04View.execution=${JSON.stringify({execution_id:EXEC,status,cases:[],logs:[],counts:{total_execution_count:total},result:{score:rate,threshold_met:verdict}})};paintM04Execution()`);
    assert.match(h.element('#m04-result').innerHTML,new RegExp(label));
    if(label==='부분 검증'||label==='판정 대기')assert.doesNotMatch(h.element('#m04-result').innerHTML,/기준 충족|기준 미달/);
    assert.equal(h.posts().length,0);
  }
});
test('an explicit selected source alone is prepared and executed with pinned IDs SHA and visible mode',async()=>{
  const h=harness({initialScripts:[script({m03_run_id:RUN,scenario_id:ID,source_scenario_sha256:SHA},OLD)]});await settle();
  h.select(ID2);h.field('title','Synthetic explicit input');h.evaluate(`m04View.selected.add('${OLD}');m04View.visibleBrowser=false`);
  await h.quick();assert.equal(h.posts(PREPARE).length,1);assert.equal(h.posts(EXECUTE).length,1);
  assert.deepEqual(h.posts(PREPARE)[0].payload,{m03_run_id:RUN,scenario_id:ID2,source_scenario_sha256:SHA2,parameters:{title:'Synthetic explicit input'}});
  assert.deepEqual(h.posts(EXECUTE)[0].payload,{script_ids:[SCRIPT],visible_browser:true,action_delay_ms:1500,keep_open_seconds:15});
  assert.deepEqual(clone(h.evaluate('[...m04View.selected]')),[SCRIPT]);assert.equal(h.evaluate('m04View.execution.cases[0].source_m03_run_id'),RUN);
  assert.ok(h.calls.findIndex(row=>row.url===PREPARE)<h.calls.findIndex(row=>row.url===EXECUTE&&row.method==='POST'));
  assert.equal(h.calls.some(row=>row.method==='POST'&&/m07|cu02|validate/.test(row.url)),false);
});
test('empty lists and unready or failed M03 sources never fall back to the CU02 example',async()=>{
  for(const rows of [[],[{...descriptor(),ready:false,status:'NOT_READY',message:'Synthetic target needs review'}],
                     [{...descriptor(),ready:false,source_status:'FAILED',message:'Synthetic original generation failed'}]]){
    const h=harness({data:listing(RUN,rows)});await settle();await h.quick();
    assert.equal(h.element('#m04-quick-start').disabled,true);assert.ok(h.element('#m04-quick-reason').textContent);
    assert.equal(h.posts().length,0);assert.equal(h.element('#m04-result').hidden,true);
    if(rows[0]?.source_status==='FAILED')assert.match(h.element('#m04-m03-summary').textContent,/원생성 실패/);
  }
});
test('source choice resets parameters and required input changes preserve the input DOM',async()=>{
  const data=listing();data.scenarios[0].parameters[0].default='';const h=harness({data});await settle();
  assert.equal(h.element('#m04-quick-start').disabled,true);const before=h.element('#m04-m03-parameters').innerHTML;
  h.field('title','Synthetic user value');assert.equal(h.element('#m04-m03-parameters').innerHTML,before);
  assert.equal(h.element('#m04-quick-start').disabled,false);h.select(ID2);
  assert.deepEqual(clone(h.evaluate('m04View.m03.parameters')),{title:'Synthetic default'});
  assert.equal(h.posts().length,0);
});
test('a select change without an input event preserves its value through preparation and starts only explicitly',async()=>{
  const data=listing();data.scenarios[0].parameters=[{name:'category',label:'Synthetic category',type:'select',choices:['문서','장비'],default:'',required:true}];
  const h=harness({data});await settle();const container=h.element('#m04-m03-parameters'),before=container.innerHTML;
  assert.equal(h.element('#m04-quick-start').disabled,true);
  assert.equal(typeof container.listeners.change,'function','native option clicks may emit change without input');
  container.listeners.change({target:{dataset:{m03Parameter:'category'},value:'문서'}});
  assert.equal(h.evaluate('m04View.m03.parameters.category'),'문서');
  assert.equal(container.innerHTML,before,'editing must preserve the live select DOM');
  assert.equal(h.element('#m04-quick-start').disabled,false);assert.equal(h.posts().length,0);
  await h.quick();assert.deepEqual(h.posts(PREPARE)[0].payload.parameters,{category:'문서'});
  assert.equal(h.posts(PREPARE).length,1);assert.equal(h.posts(EXECUTE).length,1);
});
test('input plus change is idempotent and locked or unknown parameter changes cannot mutate the selected source',async()=>{
  const data=listing();data.scenarios[0].parameters[0].default='';const h=harness({data});await settle();
  const container=h.element('#m04-m03-parameters');
  assert.equal(typeof container.listeners.change,'function');
  const event={target:{dataset:{m03Parameter:'title'},value:'Synthetic keyboard choice'}};
  container.listeners.input(event);container.listeners.change(event);
  assert.equal(h.evaluate('m04View.m03.parameters.title'),'Synthetic keyboard choice');assert.equal(h.posts().length,0);
  container.listeners.change({target:{dataset:{m03Parameter:'unrelated'},value:'Synthetic ignored'}});
  assert.deepEqual(clone(h.evaluate('m04View.m03.parameters')),{title:'Synthetic keyboard choice'});
  for(const lock of ['busy','preparation','runner']){
    if(lock==='busy')h.evaluate('m04View.busy=true');
    if(lock==='preparation')h.evaluate('m04View.preparation.busy=true');
    if(lock==='runner')h.evaluate(`m04View.executions=[{execution_id:'${EXEC}',status:'RUNNING'}]`);
    container.listeners.change({target:{dataset:{m03Parameter:'title'},value:'Synthetic forbidden replacement'}});
    assert.equal(h.evaluate('m04View.m03.parameters.title'),'Synthetic keyboard choice',lock);
    h.evaluate('m04View.busy=false;m04View.preparation.busy=false;m04View.executions=[]');
  }
  await h.quick();assert.equal(h.posts(PREPARE).length,1);assert.equal(h.posts(EXECUTE).length,1);
  assert.equal(h.posts(PREPARE)[0].payload.parameters.title,'Synthetic keyboard choice');
});
test('runtime login loading and active-work requirements block both UI and direct handler calls',async()=>{
  for(const variant of ['selenium','chrome','login','source-loading','prep-loading','prep-busy','runner','busy']){
    const h=harness();await settle();
    if(['selenium','chrome','login'].includes(variant))h.evaluate('m04View.m03.readiness.'+(variant==='login'?'login_configured':variant)+'=false');
    if(variant==='source-loading')h.evaluate('m04View.m03.loading=true');
    if(variant==='prep-loading')h.evaluate('m04View.preparation.loading=true');
    if(variant==='prep-busy')h.evaluate('m04View.preparation.busy=true');
    if(variant==='runner')h.evaluate(`m04View.executions=[{execution_id:'${EXEC}',status:'RUNNING'}]`);
    if(variant==='busy')h.evaluate('m04View.busy=true');
    h.context.paintM04();await h.quick();assert.equal(h.element('#m04-quick-start').disabled,true,variant);
    assert.equal(h.posts().length,0);assert.ok(h.element('#m04-quick-reason').textContent);
  }
  const local=listing();local.scenarios[0].requires_login=false;local.readiness.login_configured=false;
  const h=harness({data:local});await settle();assert.equal(h.element('#m04-quick-start').disabled,false,'explicit unauthenticated scenario does not need an unrelated account');
});
test('one busy guard covers recheck preparation and execution and blocks double-clicks and manual starts',async()=>{
  const h=harness();await settle();const checked=deferred(),prepared=deferred(),started=deferred();let prepareData,executionData;
  h.state.contextReply=(_url,data)=>checked.promise;
  h.state.prepareReply=(_payload,data)=>{prepareData=data;return prepared.promise;};
  h.state.executeReply=(_payload,data)=>{executionData=data;return started.promise;};
  const pending=h.quick();await h.quick();await h.context.startM04();assert.equal(h.posts().length,0);assert.equal(h.evaluate('m04View.busy'),true);
  checked.resolve(h.reply(h.state.data));await settle();assert.equal(h.posts(PREPARE).length,1);await h.quick();
  h.state.lastScript=prepareData.script;prepared.resolve(h.reply(prepareData,201));await settle();
  assert.equal(h.posts(EXECUTE).length,1);await h.quick();await h.context.startM04();assert.equal(h.posts(EXECUTE).length,1);
  started.resolve(h.reply({execution:executionData},202));await pending;
  assert.equal(h.element('#m04-quick-start').disabled,true);assert.equal(h.evaluate('m04View.busy'),false);
});
test('a fresh source must retain exact run SHA readiness and parameter definitions before preparation',async()=>{
  for(const variant of ['http','mode','run','foreign-row','missing','hash','ready-string','ready-false','parameters','duplicate-parameter','parameter-type','required','default-type']){
    const h=harness();await settle();h.state.contextReply=(_url,data)=>{
      if(variant==='http')return h.reply({error:'Synthetic source unavailable'},503);
      if(variant==='mode')data.run_mode='OFFICIAL';if(variant==='run')data.m03_run_id=RUN2;
      if(variant==='foreign-row')data.scenarios[0].m03_run_id=RUN2;if(variant==='missing')data.scenarios.shift();
      if(variant==='hash')data.scenarios[0].source_scenario_sha256=SHA2;
      if(variant==='ready-string')data.scenarios[0].ready='true';if(variant==='ready-false')data.scenarios[0].ready=false;
      if(variant==='parameters')data.scenarios[0].parameters=[];
      if(variant==='duplicate-parameter')data.scenarios[0].parameters.push(clone(data.scenarios[0].parameters[0]));
      if(variant==='parameter-type')data.scenarios[0].parameters[0].type='date';
      if(variant==='required')data.scenarios[0].parameters[0].required=false;
      if(variant==='default-type')data.scenarios[0].parameters[0].default={};
      return h.reply(data);
    };await h.quick();assert.equal(h.posts(PREPARE).length,0,variant);assert.equal(h.posts(EXECUTE).length,0);
    assert.equal(h.evaluate('m04View.execution'),null);assert.equal(h.evaluate('m04View.busy'),false);
  }
});
test('new defaults refresh only untouched inputs while explicit custom inputs stay byte-for-byte',async()=>{
  for(const custom of [false,true]){
    const h=harness();await settle();if(custom)h.field('title','Synthetic explicit custom');
    h.state.contextReply=(_url,data)=>{data.scenarios[0].parameters[0].default='Synthetic fresh unique';return h.reply(data);};
    await h.quick();assert.equal(h.posts(PREPARE)[0].payload.parameters.title,custom?'Synthetic explicit custom':'Synthetic fresh unique');
  }
});
test('tampered or reused prepared scripts cannot execute an earlier selection as fallback',async()=>{
  for(const variant of ['http','script-id','reused','sha','ready','kind','llm','required','scenario','run','source-sha']){
    const h=harness({initialScripts:[script({m03_run_id:RUN,scenario_id:ID,source_scenario_sha256:SHA},OLD)]});await settle();h.evaluate(`m04View.selected.add('${OLD}')`);
    h.state.prepareReply=(_payload,data)=>{
      if(variant==='http')return h.reply({error:'Synthetic prepare rejected'},422);
      const row=data.script;if(variant==='script-id')row.script_id='bad';if(variant==='reused')row.script_id=OLD;
      if(variant==='sha')row.sha256='bad';if(variant==='ready')row.execution_ready=false;
      if(variant==='kind')row.source_kind='CU02_SCHEDULE_REGISTRATION';if(variant==='llm')row.generated_by_llm=true;
      if(variant==='required')row.business_step_required=false;if(variant==='scenario')row.scenario_id=ID2;
      if(variant==='run')row.source_m03_run_id=RUN2;if(variant==='source-sha')row.source_scenario_sha256=SHA2;
      return h.reply(data,201);
    };await h.quick();assert.equal(h.posts(PREPARE).length,1);assert.equal(h.posts(EXECUTE).length,0,variant);
    assert.equal(h.evaluate('m04View.execution'),null);assert.equal(h.element('#m04-result').hidden,true);
  }
});
test('retired page navigation and server-session responses stop the chain before execution',async()=>{
  for(const stage of ['recheck','prepare'])for(const variant of ['page','navigation','session']){
    const h=harness();await settle();const gate=deferred();let data;
    if(stage==='recheck')h.state.contextReply=(_url,body)=>{data=body;return gate.promise;};
    else h.state.prepareReply=(_payload,body)=>{data=body;return gate.promise;};
    const pending=h.quick();await settle();
    if(variant==='page')h.evaluate('++m04RequestNumber');if(variant==='navigation')h.location.pathname='/metrics/m03';
    gate.resolve(h.reply(data,stage==='prepare'?201:200,variant==='session'?'SERVER-foreign':SERVER));await pending;
    assert.equal(h.posts(EXECUTE).length,0,stage+'/'+variant);assert.equal(h.evaluate('m04View.execution'),null);
    if(stage==='recheck')assert.equal(h.posts(PREPARE).length,0);
  }
});
test('an active job discovered during preparation retains the new code but never starts execution',async()=>{
  for(const kind of ['runner','prep']){
    const h=harness();await settle();const gate=deferred();let data;
    h.state.prepareReply=(_payload,body)=>{data=body;return gate.promise;};const pending=h.quick();await settle();
    h.evaluate(kind==='runner'?`m04View.executions=[{execution_id:'${EXEC}',status:'RUNNING'}]`:'m04View.preparation.busy=true');
    gate.resolve(h.reply(data,201));await pending;assert.equal(h.posts(EXECUTE).length,0);
    assert.equal(h.evaluate(`m04View.scripts.some(row=>row.script_id==='${SCRIPT}')`),true);
  }
});
test('execution rejection preserves preparation without retry or a fabricated zero score',async()=>{
  const h=harness();await settle();h.state.executeReply=()=>h.reply({error:'Synthetic execution rejected'},422);
  await h.quick();await settle();assert.equal(h.posts(PREPARE).length,1);assert.equal(h.posts(EXECUTE).length,1);
  assert.equal(h.evaluate('m04View.execution'),null);assert.equal(h.element('#m04-result').hidden,true);
  assert.equal(h.evaluate(`m04View.scripts.some(row=>row.script_id==='${SCRIPT}')`),true);
  assert.match(h.element('#m04-status').textContent,/Synthetic execution rejected/);
});
test('foreign execution cases and invalid execution IDs cannot become the accepted result',async()=>{
  for(const variant of ['empty','two','script','scenario','run','execution-id','session']){
    const h=harness();await settle();h.state.executeReply=(_payload,data)=>{
      if(variant==='empty')data.cases=[];if(variant==='two')data.cases.push({...data.cases[0],case_id:'CASE-002'});
      if(variant==='script')data.cases[0].script_id=OLD;if(variant==='scenario')data.cases[0].scenario_id=ID2;
      if(variant==='run')data.cases[0].source_m03_run_id=RUN2;if(variant==='execution-id')data.execution_id='bad';
      return h.reply({execution:data},202,variant==='session'?'SERVER-foreign':SERVER);
    };await h.quick();assert.equal(h.posts(EXECUTE).length,1);assert.equal(h.evaluate('m04View.execution'),null,variant);
    assert.equal(h.element('#m04-result').hidden,true);
  }
});
test('run selection is GET-only and stale run replies cannot overwrite a later source choice',async()=>{
  const h=harness();await settle();const gate=deferred();
  h.state.contexts.set(RUN2,listing(RUN2,[descriptor(ID2,RUN2)]));
  h.state.contextReply=(url,data)=>url.endsWith(encodeURIComponent(RUN))?gate.promise:h.reply(data);
  const first=h.context.bootstrapM04M03(h.evaluate('m04RequestNumber'),RUN);
  await h.context.bootstrapM04M03(h.evaluate('m04RequestNumber'),RUN2);gate.resolve(h.reply(listing()));await first;
  assert.equal(h.evaluate('m04View.m03.runId'),RUN2);assert.equal(h.evaluate('m04View.m03.selectedId'),ID2);
  assert.equal(h.posts().length,0);
});
test('an explicit M03 deep link filters to its saved scenario and never selects an unrelated source',async()=>{
  const h=harness({query:'&m03_run_id='+RUN+'&scenario_id='+ID});await settle();
  assert.deepEqual(clone(h.evaluate('m04View.m03.rows.map(row=>row.scenario_id)')),[ID]);
  assert.equal(h.element('#m04-m03-run').disabled,true);await h.quick();
  assert.equal(h.posts(PREPARE)[0].payload.scenario_id,ID);assert.equal(h.posts(EXECUTE).length,1);
  assert.equal(h.calls.some(row=>row.method==='POST'&&/cu02|m07/.test(row.url)),false);
});
test('reviewed Korean inputs keep registration and lookup values linked and preserve user edits',async()=>{
  const fields={BU01:[],BU03:['date','title','description'],BU05:['record_title'],BU07:['field_1','field_2'],
    BU09:['field_1','field_2','report_date'],BU12:[],BU13:['record_company'],
    BU14:Array.from({length:7},(_,i)=>'field_'+(i+1)),BU17:Array.from({length:6},(_,i)=>'field_'+(i+1)),
    BU20:Array.from({length:4},(_,i)=>'field_'+(i+1))};
  const rows=Object.entries(fields).map(([business_unit_id,names])=>({...descriptor(business_unit_id),business_unit_id,
    binding_version:business_unit_id==='BU03'?'m03-bu03-reviewed-execution-v1':'m03-observed-dom-binding-v2-20261116',
    parameters:names.map(name=>({name,label:name,type:name==='report_date'?'date':'text',required:true,default:''}))}));
  const h=harness({data:listing(RUN,rows)});await settle();const selected={};
  for(const row of rows){h.select(row.scenario_id);selected[row.business_unit_id]=clone(h.evaluate('m04View.m03.parameters'));}
  for(const values of Object.values(selected))for(const value of Object.values(values))assert.ok(value.trim());
  assert.equal(selected.BU05.record_title,selected.BU07.field_1);
  assert.equal(selected.BU13.record_company,selected.BU14.field_1);
  assert.match(selected.BU07.field_1,/^KTL 시험 일일보고 /);assert.match(selected.BU07.field_2,/[가-힣]/);
  assert.equal(selected.BU14.field_2,'시험담당자');assert.equal(selected.BU20.field_1,'문서');
  assert.match(selected.BU03.date,/^\d{4}-\d{2}-\d{2}$/);assert.equal(selected.BU03.date,selected.BU09.report_date);
  h.select('BU07');h.field('field_1','KTL 시험 수정한 일일보고');h.select('BU05');
  assert.equal(h.evaluate('m04View.m03.parameters.record_title'),'KTL 시험 수정한 일일보고');
  h.select('BU14');h.field('field_1','KTL 시험 수정한 회사');h.select('BU13');
  assert.equal(h.evaluate('m04View.m03.parameters.record_company'),'KTL 시험 수정한 회사');
  h.select('BU07');assert.equal(h.evaluate('m04View.m03.parameters.field_1'),'KTL 시험 수정한 일일보고');
  await h.quick();assert.equal(h.posts(PREPARE)[0].payload.parameters.field_1,'KTL 시험 수정한 일일보고');
  assert.equal(h.posts(EXECUTE)[0].payload.action_delay_ms,1500);
});

(async()=>{for(const item of tests){await item.run();console.log('PASS '+item.name);}console.log(tests.length+' M04 M03 UI groups passed');})().catch(error=>{console.error(error);process.exitCode=1;});
