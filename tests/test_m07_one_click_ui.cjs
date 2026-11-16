'use strict';
// Synthetic VM/API fixtures only: no server, provider, Selenium or business browser.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {webcrypto,createHash}=require('node:crypto');
const source=fs.readFileSync('frontend/m07.js','utf8');
const SERVER='SERVER-'+'f'.repeat(32),ID='M07-GEN-'+'c'.repeat(32),BASE='/api/development/m07';
const clone=value=>JSON.parse(JSON.stringify(value)),sha=value=>createHash('sha256').update(value).digest('hex');
const settle=async()=>{for(let i=0;i<20;i++)await new Promise(resolve=>setImmediate(resolve));};
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
function inputs(){return Array.from({length:20},(_,index)=>{
  const scenario_id='SYNTHETIC-ONE-CLICK-'+index;
  return {input_id:'INPUT-'+index,scenario:{scenario_id,scenario_name:'합성 입력 '+index,business_unit_id:'BUSINESS-'+index,workflow_id:'WORKFLOW-'+index,
    steps:[{order:1,action:'input',target:'#synthetic-field',input_value:'합성 '+index,expected_result:'합성 '+index}],
    execution_contract:{version:1,scenario_id,steps:[{order:1,target:{by:'css selector',value:'#synthetic-field'},checks:[{kind:'value',expected:'합성 '+index}]}]}}};
});}
function job(status='QUEUED',{items=inputs(),auto=true,passed=16}={}){
  const generated=!['QUEUED','GENERATING'].includes(status),completed=status==='COMPLETED';
  const cases=items.map((item,index)=>{
    const code='SCENARIO_ID = '+JSON.stringify(item.scenario.scenario_id)+'\nassert True\n';
    return {case_id:'CASE-'+String(index+1).padStart(3,'0'),input_id:item.input_id,...clone(item.scenario),code_source:'LLM',generated_by_llm:true,
      generation_status:generated?'PASS':'PENDING',syntax_status:completed?(index<passed?'PASS':'FAIL'):'PENDING',
      execution_status:completed?(index<passed?'PASS':'SKIPPED'):'PENDING',final_status:completed?(index<passed?'PASS':'FAIL'):'PENDING',
      code_sha256:sha(code),execution_contract_sha256:'b'.repeat(64),_code:code};
  });
  return {generation_id:ID,status,meeting_protocol:true,auto_validate:auto,required_count:20,measurement_protocol:'M07_MEETING_20_V1',
    code_source:'LLM',source_kind:'MEETING_LLM_BATCH',generated_by_llm:true,cases,logs:[],
    counts:{generation_request_count:20,generated_code_count:generated?20:0,syntax_pass_count:completed?passed:0,execution_pass_count:completed?passed:0,both_pass_count:completed?passed:0},
    measurement:{version:1,evaluation_status:completed?'COMPLETED':'NOT_READY',registered_count:20,provider_http_attempt_count:generated?20:0,
      provider_http_unknown_count:0,not_attempted_count:generated?0:20,generated_code_count:generated?20:0,syntax_pass_count:completed?passed:0,
      execution_pass_count:completed?passed:0,both_pass_count:completed?passed:0,browser_started_count:completed?passed:0,
      generation_percent:completed?100:null,syntax_percent:completed?passed*5:null,integrated_percent:completed?passed*5:null,browser_percent:completed?100:null,
      syntax_target_percent:80,syntax_target_met:completed?passed>=16:null,integrated_reference_target_percent:80,integrated_reference_target_met:completed?passed>=16:null},
    result:completed?{score:passed*5,run_id:ID,official_pass:null}:null};
}
function harness({query='?mode=DEVELOPMENT',saved=null,provider=null,fetch:customFetch}={}){
  const nodes=new Map(),calls=[],timers=new Map();let timer=0;
  const node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',value:'',disabled:false,hidden:false,attrs:{},listeners:{},
    addEventListener(name,fn){this.listeners[name]=fn;},setAttribute(name,value){this.attrs[name]=value;},insertAdjacentHTML(position,value){this.innerHTML+=value;}});return nodes.get(id);};
  const state={current:saved?clone(saved):null,next:[],provider:provider?clone(provider):{blocked:false},customFetch};
  const location={pathname:'/metrics/m07',search:query,port:'8000'};
  const response=(value,status=200)=>({ok:status>=200&&status<300,status,headers:{get:()=>SERVER},json:async()=>clone(value)});
  const context=vm.createContext({URLSearchParams,URL,TextEncoder,TextDecoder,Uint8Array,AbortController,crypto:webcrypto,console,Date,Number,Set,Map,
    location,history:{replaceState(_,__,url){location.search=url.includes('?')?'?'+url.split('?')[1]:'';}},catalog:{server_session_id:SERVER},
    document:{title:'',querySelector:node},app:node('#app'),labels:{M07:'M07'},esc,score:value=>value==null?'—':Number(value).toFixed(2)+'%',
    banner:()=>'',link:value=>value,setTimeout(fn,delay){const id=++timer;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),
    ktlCheckServerSession(reply){assert.equal(reply.headers.get(),SERVER);},
    fetch:async(url,init={})=>{
      const call={url,method:init.method||'GET',body:init.body?JSON.parse(init.body):undefined};calls.push(call);
      if(state.customFetch){const value=await state.customFetch(call);if(value!==undefined)return value?.json?value:response(value);}
      if(url===BASE+'/meeting-context')return response({run_mode:'DEVELOPMENT',required_count:20,target_percent:80,provider_state:state.provider,
        readiness:{configured:true,selenium:true,chrome:true,model:'synthetic-model',model_display_name:'합성 모델'}});
      if(url===BASE+'/context')return response({run_mode:'DEVELOPMENT',scenarios:[],readiness:{configured:true,selenium:true,chrome:true},provider_state:state.provider});
      if(url===BASE+'/workflows')return response({run_mode:'DEVELOPMENT',browser:'chrome',login_configured:true,readiness:{selenium:true,chrome:true},workflows:[],defaults:{date:'2028-02-29',title:'합성 제목',description:'합성 설명',cases_per_workflow:2},parameter_fields:[]});
      if(url===BASE+'/meeting-input-draft')return response({draft:true,description:'SYNTHETIC 검토용 초안',items:inputs()});
      if(url===BASE+'/generations')return response({generations:state.current?[state.current]:[]});
      if(url===BASE+'/meeting-generations'){
        state.current=job('QUEUED',{items:call.body.items,auto:call.body.auto_validate===true});return response({generation:state.current});
      }
      if(url===BASE+'/generations/'+ID){if(state.next.length)state.current=clone(state.next.shift());return response({generation:state.current});}
      if(url===BASE+'/generations/'+ID+'/validate'){state.current={...state.current,status:'VALIDATING'};return response({generation:state.current});}
      throw new Error('Unexpected synthetic request '+url);
    }});
  vm.runInContext(source,context);
  return {context,state,node,calls,timers,location,response,evaluate:code=>vm.runInContext(code,context),
    async start(){context.renderM07({metric_id:'M07',target:80});await settle();},
    async click(id){await node(id).listeners.click({target:node(id)});await settle();},
    async edit(value){node('#m07-meeting-input').value=typeof value==='string'?value:JSON.stringify(value);await node('#m07-meeting-input').listeners.input();await settle();},
    posts:()=>calls.filter(row=>row.method==='POST'),polls:()=>[...timers.values()].filter(row=>row.delay===1500),
    async poll(){const entry=[...timers].find(([,row])=>row.delay===1500);assert.ok(entry,'running automatic job remains polled');timers.delete(entry[0]);await entry[1].fn();await settle();}};
}
const tests=[];const test=(name,run)=>tests.push([name,run]);
test('meeting entry exposes one verification action without an automatic mutation',async()=>{
  const h=harness();await h.start();assert.equal(h.evaluate('m07View.mode'),'meeting');
  assert.match(h.node('#app').innerHTML,/id="m07-meeting-generate"[^>]*>검증 실행</);
  assert.equal(h.node('#m07-validate').hidden,true);assert.equal(h.node('#m07-meeting-generate').disabled,true);assert.equal(h.posts().length,0);
});
test('textarea edits automatically check valid input and discard stale validation on invalid JSON',async()=>{
  const h=harness(),payload={items:inputs()},original=JSON.stringify(payload);await h.start();await h.edit(payload);
  assert.equal(h.evaluate('m07View.meeting.items.length'),20);assert.equal(h.node('#m07-meeting-generate').disabled,false);assert.equal(h.posts().length,0);
  await h.edit('{');assert.equal(h.evaluate('m07View.meeting.items.length'),0);assert.equal(h.node('#m07-meeting-generate').disabled,true);
  await h.click('#m07-meeting-generate');assert.equal(h.posts().length,0);await h.edit(payload);assert.equal(h.node('#m07-meeting-generate').disabled,false);
  assert.equal(JSON.stringify(payload),original,'UI confirmation must not mutate the input problem');
});
test('file and draft loading only confirm input and the single action sends auto_validate true',async()=>{
  for(const mode of ['file','draft']){
    const h=harness();await h.start();
    if(mode==='file')await h.node('#m07-meeting-file').listeners.change({target:{files:[{size:1024,text:async()=>JSON.stringify({items:inputs()})}]}});
    else await h.click('#m07-meeting-draft');
    assert.equal(h.node('#m07-meeting-generate').disabled,false);assert.equal(h.posts().length,0);
    await h.click('#m07-meeting-generate');assert.deepEqual(h.posts(),[{url:BASE+'/meeting-generations',method:'POST',body:{items:inputs(),auto_validate:true}}]);
    assert.equal(h.node('#m07-validate').hidden,true);assert.equal(h.evaluate('m07View.generation.auto_validate'),true);
  }
});
test('two explicit batches preserve twenty inputs and the original policy while enabling automatic validation',async()=>{
  const first=inputs().slice(0,10),items=[...first,...first.map((row,index)=>({...clone(row),input_id:'SECOND-'+index}))];
  const trial_policy={batches:[{batch_id:'FIRST',input_ids:items.slice(0,10).map(row=>row.input_id)},{batch_id:'SECOND',input_ids:items.slice(10).map(row=>row.input_id)}]};
  const payload={items,trial_policy},original=JSON.stringify(payload),h=harness();await h.start();await h.edit(payload);assert.equal(h.node('#m07-meeting-generate').disabled,false);
  await h.click('#m07-meeting-generate');assert.deepEqual(h.posts()[0].body,{...payload,auto_validate:true});assert.equal(JSON.stringify(payload),original);
});
test('two clicks while the request is pending create only one job',async()=>{
  const wait=deferred(),h=harness({fetch:async call=>{if(call.url===BASE+'/meeting-generations'){await wait.promise;return {generation:job()};}}});
  await h.start();await h.edit({items:inputs()});const pending=h.click('#m07-meeting-generate');await settle();await h.click('#m07-meeting-generate');
  assert.equal(h.posts().length,1);wait.resolve();await pending;assert.equal(h.posts().length,1);
});
test('automatic generated phase keeps polling through validation and completion without a validation POST',async()=>{
  const h=harness();await h.start();await h.edit({items:inputs()});await h.click('#m07-meeting-generate');
  h.state.next=[job('GENERATING'),job('GENERATED'),job('VALIDATING'),job('COMPLETED')];
  for(const status of ['GENERATING','GENERATED','VALIDATING','COMPLETED']){
    await h.poll();assert.equal(h.evaluate('m07View.generation.status'),status);assert.equal(h.node('#m07-validate').hidden,true);
  }
  assert.equal(h.posts().length,1);assert.equal(h.polls().length,0);assert.equal(h.calls.filter(row=>row.url===BASE+'/generations/'+ID).length,4);
  assert.match(h.node('#m07-result').innerHTML,/data-m07-overview="integrated">80\.00%/);
  assert.equal((h.node('#m07-cases').innerHTML.match(/data-m07-result-row=/g)||[]).length,20);
  assert.equal(h.evaluate('m07View.generation.result.official_pass'),null);
});
test('URL restoration and explicit refresh resume automatic jobs using GET only',async()=>{
  for(const status of ['GENERATED','VALIDATING','COMPLETED']){
    const h=harness({saved:job(status),query:'?mode=DEVELOPMENT&generation_id='+ID});await h.start();
    assert.equal(h.evaluate('m07View.generation.generation_id'),ID);assert.equal(h.posts().length,0);assert.equal(h.node('#m07-validate').hidden,true);
    if(status!=='COMPLETED'){assert.equal(h.polls().length,1);h.state.next=[job('COMPLETED')];await h.poll();}
    await h.click('#m07-refresh');assert.equal(h.posts().length,0);assert.equal(h.evaluate('m07View.generation.generation_id'),ID);assert.equal(h.polls().length,0);
  }
});
test('legacy generated meeting jobs still expose an explicit validation action',async()=>{
  for(const auto of [false,undefined]){
    const legacy=job('GENERATED',{auto:false});if(auto===undefined)delete legacy.auto_validate;
    const h=harness({saved:legacy});await h.start();assert.equal(h.node('#m07-validate').hidden,false);assert.equal(h.node('#m07-validate').disabled,false);
    assert.equal(h.posts().length,0);await h.click('#m07-validate');assert.deepEqual(h.posts().map(row=>[row.method,row.url]),[['POST',BASE+'/generations/'+ID+'/validate']]);
  }
});
test('an old server response without automatic validation is rejected rather than silently requiring a second action',async()=>{
  const old=job();delete old.auto_validate;const h=harness({fetch:async call=>call.url===BASE+'/meeting-generations'?{generation:old}:undefined});
  await h.start();await h.edit({items:inputs()});await h.click('#m07-meeting-generate');
  assert.equal(h.evaluate('m07View.generation'),null);assert.match(h.node('#m07-status').textContent,/자동|출처|검증/);assert.equal(h.posts().length,1);assert.equal(h.polls().length,0);
});
test('mismatched response inputs and responses arriving after navigation cannot start polling or execution',async()=>{
  const wrong=job();wrong.cases[19].input_id='FOREIGN';
  const bad=harness({fetch:async call=>call.url===BASE+'/meeting-generations'?{generation:wrong}:undefined});
  await bad.start();await bad.edit({items:inputs()});await bad.click('#m07-meeting-generate');assert.equal(bad.evaluate('m07View.generation'),null);assert.equal(bad.polls().length,0);
  const wait=deferred(),late=harness({fetch:async call=>{if(call.url===BASE+'/meeting-generations'){await wait.promise;return {generation:job()};}}});
  await late.start();await late.edit({items:inputs()});const pending=late.click('#m07-meeting-generate');await settle();late.location.pathname='/metrics/m01';wait.resolve();await pending;
  assert.equal(late.evaluate('m07View.generation'),null);assert.equal(late.polls().length,0);assert.equal(late.posts().length,1);
});
test('provider blocking prevents a new automatic job without disabling legacy code verification',async()=>{
  const provider={blocked:true,http_status:429,error_type:'tokens',error_code:'rate_limit_exceeded',next_eligible_at:'2028-02-29T00:00:00Z'};
  const h=harness({provider});await h.start();await h.edit({items:inputs()});assert.equal(h.node('#m07-meeting-generate').disabled,true);await h.click('#m07-meeting-generate');assert.equal(h.posts().length,0);
  assert.match(h.node('#m07-meeting-provider').innerHTML,/HTTP429/);
  const legacy=harness({provider,saved:job('GENERATED',{auto:false})});await legacy.start();assert.equal(legacy.node('#m07-validate').disabled,false);await legacy.click('#m07-validate');assert.equal(legacy.posts().length,1);
});
test('an automatic partial provider stop remains NOT_READY with twenty denominator and no follow-up POST',async()=>{
  const partial=job('COMPLETED');Object.assign(partial.measurement,{evaluation_status:'NOT_READY',provider_http_attempt_count:3,not_attempted_count:17,generated_code_count:2,syntax_pass_count:2,execution_pass_count:2,both_pass_count:2,generation_percent:null,syntax_percent:null,integrated_percent:null,browser_percent:null});
  partial.result=null;partial.cases.forEach((row,index)=>{if(index>=2)Object.assign(row,{generation_status:index===2?'ERROR':'SKIPPED',syntax_status:'SKIPPED',execution_status:'SKIPPED',final_status:'FAIL'});});
  const h=harness({saved:partial});await h.start();const html=h.node('#m07-result').innerHTML;
  assert.match(html,/NOT_READY/);assert.match(html,/data-m07-summary="registered_count">20</);assert.match(html,/data-m07-summary="not_attempted_count">17</);
  assert.match(html,/data-m07-overview="integrated">—/);assert.ok(!html.includes('100.00%'));assert.equal(h.posts().length,0);assert.equal(h.node('#m07-validate').hidden,true);
});
test('the primary evidence CSV control links to the selected job artifact without an extra request',async()=>{
  const h=harness();await h.start();assert.doesNotMatch(h.node('#m07-result').innerHTML,/<a[^>]*>Evidence CSV 다운로드/);
  await h.edit({items:inputs()});await h.click('#m07-meeting-generate');const html=h.node('#m07-result').innerHTML;
  assert.match(html,new RegExp('<a class="download" href="'+BASE+'/generations/'+ID+'/artifacts/steps\\.csv" download>Evidence CSV 다운로드</a>'));
  assert.equal(h.calls.filter(row=>row.url.includes('/artifacts/')).length,0,'rendering an evidence link must not issue another request');assert.equal(h.posts().length,1);
});
test('unattempted and transport-unknown rows remain unexecuted instead of a fabricated final failure',async()=>{
  const h=harness({saved:job('COMPLETED')});await h.start();
  for(const fields of [{generation_http_attempted:false},{generation_invoked:true,generation_http_attempted:null}]){
    const row={...clone(h.state.current.cases[0]),...fields,generation_status:'SKIPPED',syntax_status:'SKIPPED',execution_status:'SKIPPED',final_status:'FAIL'};
    h.context.syntheticRow=row;assert.equal(h.evaluate('m07FinalStatus(syntheticRow)'),'SKIPPED');
    const snapshot=clone(h.state.current);snapshot.cases[0]=row;Object.assign(snapshot.measurement,{evaluation_status:'NOT_READY',provider_http_attempt_count:19,not_attempted_count:1});snapshot.result=null;
    const original=JSON.stringify(snapshot);h.context.syntheticJob=snapshot;h.evaluate('acceptM07Generation(syntheticJob)');
    const first=h.node('#m07-cases').innerHTML.match(/<tr data-m07-result-row="1"[^>]*>[\s\S]*?<\/tr>/)?.[0];assert.ok(first);assert.match(first,/미실행/);assert.doesNotMatch(first,/>FAIL</);
    assert.equal(JSON.stringify(snapshot),original,'rendering must retain the original stored statuses');assert.equal(h.posts().length,0);
  }
});
test('missing execution preparation stays pending and preserves all twenty inputs without browser or retry requests',async()=>{
  const snapshot=job('COMPLETED');snapshot.automatic_phase='NOT_READY';snapshot.result=null;
  snapshot.cases.forEach(row=>Object.assign(row,{execution_preparation_status:'NOT_READY',syntax_status:'PASS',execution_status:'SKIPPED',final_status:'PENDING'}));
  Object.assign(snapshot.measurement,{evaluation_status:'NOT_READY',syntax_pass_count:20,execution_pass_count:0,both_pass_count:0,browser_started_count:0,syntax_percent:null,integrated_percent:null,browser_percent:null});
  const h=harness({saved:snapshot});await h.start();h.context.syntheticRow=snapshot.cases[0];assert.equal(h.evaluate('m07FinalStatus(syntheticRow)'),'NOT_READY');
  assert.match(h.node('#m07-cases').innerHTML,/평가 대기|준비 대기|판정 대기/);assert.match(h.node('#m07-result').innerHTML,/NOT_READY/);
  assert.match(h.node('#m07-result').innerHTML,/data-m07-overview="integrated">—/);assert.equal((h.node('#m07-cases').innerHTML.match(/data-m07-result-row=/g)||[]).length,20);
  assert.equal(h.posts().length,0);assert.equal(h.polls().length,0);assert.equal(h.node('#m07-validate').hidden,true);
});
(async()=>{let failed=0;for(const[name,run]of tests){try{await run();console.log('PASS '+name);}catch(error){failed++;console.error('FAIL '+name);console.error(error);}}console.log((tests.length-failed)+'/'+tests.length+' M07 one-click synthetic UI groups passed');if(failed)process.exitCode=1;})().catch(error=>{console.error(error);process.exitCode=1;});
