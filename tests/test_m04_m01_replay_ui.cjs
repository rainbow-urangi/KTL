'use strict';
// Actual UI functions with in-memory synthetic APIs. No HTTP, browser, app, model or GPT calls.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.resolve(__dirname,'../frontend/m04.js'),'utf8');
const A='a'.repeat(32),B='b'.repeat(32),SCRIPT='c'.repeat(32),COMPARE='d'.repeat(32),SHA='e'.repeat(64),SERVER='SERVER-'+'f'.repeat(32);
const KEY='ktl.m01.replay-source.v1',EID='M04-RUN-'+'1'.repeat(32);
const clone=value=>JSON.parse(JSON.stringify(value));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const settle=async()=>{for(let i=0;i<16;i++)await new Promise(done=>setImmediate(done));};
function contextFor(dataset=A,missing=true){return {dataset_id:dataset,filename:'synthetic.csv',source_sha256:SHA,
  session_id:null,event_count:6,steps:[{kind:'execute',action:'navigate'},{kind:'execute',action:'input'},{kind:'reference'}],
  missing_inputs:missing?[{name:'value_row_2',row:2,target:'#synthetic-title',input_control_type:'text',reason:'New test value required'}]:[],
  blockers:[],status:missing?'NEEDS_INPUT':'READY',notice:'Synthetic observed source only'};}
function harness({stored=null}={}) {
  const calls=[],elements=new Map(),storage=new Map(stored===null?[]:[[KEY,JSON.stringify(stored)]]),timers=new Map();let sequence=0;
  const location={pathname:'/metrics/m04',search:'?mode=DEVELOPMENT'};
  const element=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',disabled:false,hidden:false,checked:false,value:'',files:[],dataset:{},listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},removeAttribute(name){delete this[name];}});return elements.get(id);};
  const response=(data,status=200,session=SERVER)=>({ok:status>=200&&status<300,status,headers:{get:()=>session},json:async()=>data});
  const state={contexts:new Map([[A,contextFor(A)],[B,contextFor(B,false)]]),sourceReply:null,importReply:null};
  const scriptFor=context=>({script_id:SCRIPT,filename:'m01-replay.py',sha256:'2'.repeat(64),scenario_id:'M01-OBSERVED-SYNTHETIC',
    scenario_name:'Synthetic replay',source_kind:'M01_OBSERVED_REPLAY',generated_by_llm:false,business_step_required:true,
    execution_ready:true,source_m01_dataset_id:context.dataset_id,source_m01_csv_sha256:context.source_sha256,source_m01_session_id:context.session_id});
  const context=vm.createContext({URL,URLSearchParams,AbortController,Uint8Array,Date,console,location,
    setTimeout(fn,delay){const id=++sequence;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),
    sessionStorage:{getItem:key=>storage.get(key)??null,removeItem:key=>storage.delete(key)},
    document:{querySelector:element},app:element('#app'),banner:()=>'',link:value=>value,labels:{M04:'M04'},
    esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    score:value=>value==null?'—':value+'%',catalog:{server_session_id:SERVER,metrics:[]},
    ktlDropQuery(keys){const query=new URLSearchParams(location.search);keys.forEach(key=>query.delete(key));location.search='?'+query;},
    ktlCheckServerSession(reply){if(reply.headers.get()!==SERVER)throw new Error('synthetic server session changed');},
    fetch:async(url,options)=>{
      const payload=options?.body?JSON.parse(options.body):undefined;calls.push({url,options,payload});
      if(url==='/api/development/m04/scripts')return response({run_mode:'DEVELOPMENT',scripts:[],readiness:{selenium:true,chrome:true}});
      if(url==='/api/development/m04/executions')return response(payload?{execution:{execution_id:EID,status:'RUNNING',cases:[],logs:[]}}:{executions:[]});
      if(url==='/api/development/m03/runs')return response({runs:[]});
      if(url==='/api/development/m07/context')return response({run_mode:'DEVELOPMENT',scenarios:[],readiness:{configured:false}});
      if(url==='/api/development/m07/generations')return response({generations:[]});
      if(url==='/api/development/m01/csv')return response({datasets:[A,B].map(id=>({dataset_id:id,filename:'synthetic.csv',summary:{event_count:6}}))});
      if(url.startsWith('/api/development/m04/m01-source?')) {
        const query=new URL(url,'http://local').searchParams,id=query.get('dataset_id')||A;
        const data={...clone(state.contexts.get(id)),...(query.has('comparison_id')?{comparison_id:query.get('comparison_id')}:{})};
        return state.sourceReply?state.sourceReply(query,data):response(data);
      }
      if(url==='/api/development/m04/import-m01') {
        const data={...clone(state.contexts.get(payload.dataset_id||A)),...(payload.comparison_id?{comparison_id:payload.comparison_id}:{})};
        const result={script:scriptFor(data),source:data};return state.importReply?state.importReply(payload,result):response(result);
      }
      if(url==='/api/development/m04/scripts/'+SCRIPT)return response({script:{script_id:SCRIPT},code:'# synthetic <script>safe</script>\r\nassert True\r\n'});
      throw new Error('Unexpected route '+url);
    }});
  vm.runInContext(source,context);context.renderM04({metric_id:'M04',target:90});
  const evaluate=code=>vm.runInContext(code,context);
  const field=(name,value)=>element('#m04-m01-fields').listeners.input({target:{dataset:{m01Parameter:name},value}});
  return {context,state,evaluate,calls,element,response,storage,location,field,timers,
    select:id=>context.selectM04M01Source(id),import:()=>context.importM04M01Source(),
    posts:route=>calls.filter(item=>item.url===route&&item.options?.method==='POST')};
}
const tests=[];const test=(name,run)=>tests.push({name,run});
test('entry restores only a current-session comparison with read-only APIs and never starts execution',async()=>{
  const h=harness({stored:{comparison_id:COMPARE,server_session_id:SERVER}});await settle();
  assert.ok(h.calls.some(call=>call.url==='/api/development/m04/m01-source?comparison_id='+COMPARE));
  assert.equal(h.evaluate('m04View.m01.context.dataset_id'),A);assert.equal(h.evaluate('m04View.m01.scope.comparison_id'),COMPARE);
  assert.ok(h.calls.every(call=>!call.options?.method));assert.equal(h.evaluate('m04View.selected.size'),0);
  assert.match(h.element('#m04-m01-status').textContent,/6개 이벤트 · 실행·확인 2단계/);
});
test('no saved scope or a stale server session keeps explicit empty selection instead of choosing latest upload',async()=>{
  for(const stored of [null,{comparison_id:COMPARE,server_session_id:'SERVER-'+'0'.repeat(32)}]) {
    const h=harness({stored});await settle();assert.equal(h.evaluate('m04View.m01.selectedId'),'');
    assert.equal(h.calls.some(call=>call.url.includes('/m01-source?')),false);assert.equal(h.element('#m04-m01-import').disabled,true);
  }
});
test('missing input blocks import until a new value is typed without repainting or losing input focus',async()=>{
  const h=harness();await settle();await h.select(A);assert.equal(h.element('#m04-m01-import').disabled,true);
  const fields=h.element('#m04-m01-fields'),html=fields.innerHTML;h.field('value_row_2','synthetic new value');
  assert.equal(fields.innerHTML,html);assert.equal(h.element('#m04-m01-import').disabled,false);
  await h.import();assert.equal(h.posts('/api/development/m04/import-m01').length,1);
  assert.deepEqual(h.posts('/api/development/m04/import-m01')[0].payload,{dataset_id:A,parameters:{value_row_2:'synthetic new value'}});
  assert.equal(h.posts('/api/development/m04/executions').length,0);assert.equal(h.evaluate('m04View.selected.has('+JSON.stringify(SCRIPT)+')'),true);
  assert.ok(h.element('#m04-scripts').innerHTML.includes('M01 수집 동작'));assert.ok(h.element('#m04-scripts').innerHTML.includes('&lt;script&gt;safe&lt;/script&gt;'));
  await h.import();assert.equal(h.posts('/api/development/m04/import-m01').length,1);
});
test('successful import drops explicit M03 lock and query without requiring a M03 scenario',async()=>{
  const h=harness();await settle();await h.select(B);h.location.search+='&m03_run_id=old&scenario_id=old';h.evaluate('m04View.locked=true');
  await h.import();assert.equal(h.evaluate('m04View.locked'),false);
  for(const key of ['m03_run_id','scenario_id'])assert.equal(new URLSearchParams(h.location.search).has(key),false);
  assert.equal(h.element('#m04-start').disabled,false);assert.equal(h.posts('/api/development/m04/executions').length,0);
});
test('switching source discards parameters and late source replies cannot overwrite the new scope',async()=>{
  const h=harness();await settle();await h.select(A);h.field('value_row_2','first');
  const gate=deferred();h.state.sourceReply=(query,data)=>query.get('dataset_id')===A?gate.promise:h.response(data);
  const first=h.select(A);await h.select(B);gate.resolve(h.response(contextFor(A)));await first;
  assert.equal(h.evaluate('m04View.m01.context.dataset_id'),B);assert.deepEqual(clone(h.evaluate('m04View.m01.parameters')),{});
});
test('NOT_READY and blockers retain row-specific reasons and cannot post an import',async()=>{
  for(const status of ['READY','NOT_READY']) {
    const h=harness();await settle();h.state.contexts.set(B,{...contextFor(B,false),status,blockers:[{row:3,reason:'synthetic unsupported target'}]});
    await h.select(B);assert.equal(h.element('#m04-m01-import').disabled,true);await h.import();
    assert.match(h.element('#m04-m01-fields').innerHTML,/행 3: synthetic unsupported target/);assert.equal(h.posts('/api/development/m04/import-m01').length,0);
  }
});
test('foreign source identity malformed SHA and server-session response are rejected before import',async()=>{
  for(const variant of ['dataset','hash','session']) {
    const h=harness();await settle();h.state.sourceReply=(_query,data)=>h.response({...data,...(variant==='dataset'?{dataset_id:B}:variant==='hash'?{source_sha256:'bad'}:{})},200,variant==='session'?'SERVER-new':SERVER);
    await h.select(A);assert.equal(h.evaluate('m04View.m01.context'),null);await h.import();assert.equal(h.posts('/api/development/m04/import-m01').length,0);
  }
});
test('import validates CSV and session provenance including the distinction between null and blank session',async()=>{
  const h=harness();await settle();await h.select(B);
  h.state.importReply=(_payload,result)=>h.response({...result,script:{...result.script,source_m01_session_id:''}});
  await h.import();assert.equal(h.evaluate('m04View.scripts.length'),0);assert.match(h.element('#m04-m01-status').textContent,/SHA 연결/);
  h.state.importReply=null;h.state.contexts.set(B,{...contextFor(B,false),session_id:''});await h.select(B);await h.import();
  assert.equal(h.evaluate('m04View.scripts[0].source_m01_session_id'),'');
});
test('double import and simultaneous execute are blocked while a source is being fixed',async()=>{
  const h=harness();await settle();await h.select(B);const gate=deferred();let answer;
  h.state.importReply=(_payload,result)=>{answer=result;return gate.promise;};
  const first=h.import();await h.import();await h.context.startM04();
  assert.equal(h.posts('/api/development/m04/import-m01').length,1);assert.equal(h.posts('/api/development/m04/executions').length,0);
  gate.resolve(h.response(answer));await first;assert.equal(h.evaluate('m04View.scripts.length'),1);
});
test('active Runner and active code preparation block import without creating new GPT or browser work',async()=>{
  for(const active of ['runner','prep']) {
    const h=harness();await settle();await h.select(B);
    h.evaluate(active==='runner'?'m04View.executions=[{execution_id:'+JSON.stringify(EID)+',status:"RUNNING"}]':'m04View.preparation.busy=true');
    h.context.paintM04();await h.import();assert.equal(h.element('#m04-m01-import').disabled,true);
    assert.equal(h.posts('/api/development/m04/import-m01').length,0);assert.ok(h.calls.every(call=>!call.options?.method));
  }
});
test('a retired page cannot accept a delayed import response',async()=>{
  const h=harness();await settle();await h.select(B);const gate=deferred();let answer;
  h.state.importReply=(_payload,result)=>{answer=result;return gate.promise;};const pending=h.import();h.evaluate('++m04RequestNumber');
  gate.resolve(h.response(answer));await pending;assert.equal(h.evaluate('m04View.scripts.length'),0);
});
test('visible execution is default while unchecking sends exactly the original execution payload',async()=>{
  for(const visible of [true,false]) {
    const h=harness();await settle();await h.select(B);await h.import();
    assert.equal(h.element('#m04-visible-browser').checked,true);
    if(!visible)h.element('#m04-visible-browser').listeners.change({target:{checked:false}});
    await h.context.startM04();const posted=h.posts('/api/development/m04/executions');assert.equal(posted.length,1);
    assert.deepEqual(posted[0].payload,{script_ids:[SCRIPT],...(visible?{visible_browser:true,action_delay_ms:700,keep_open_seconds:15}:{})});
  }
});
(async()=>{for(const item of tests){await item.run();console.log('PASS '+item.name);}console.log(tests.length+' M04 M01 replay UI groups passed');})().catch(error=>{console.error(error);process.exitCode=1;});
