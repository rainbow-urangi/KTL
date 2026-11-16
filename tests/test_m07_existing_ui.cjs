'use strict';
// Existing-code view with real click handlers and synthetic in-memory network responses only.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {webcrypto,createHash}=require('node:crypto');
const source=fs.readFileSync('frontend/m07.js','utf8');
const ENDPOINT='/api/development/m07/existing-codes',SERVER='SERVER-'+'a'.repeat(32);
const sha=text=>createHash('sha256').update(text,'utf8').digest('hex');
const clone=value=>JSON.parse(JSON.stringify(value));
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const settle=async()=>{for(let i=0;i<24;i++)await new Promise(done=>setImmediate(done));};
function fixture(){return {code_source:'EXISTING_LLM',source_generation_id:'SYNTHETIC-ARCHIVED-GPT-R1',source_manifest_sha256:'b'.repeat(64),required_count:10,target:80,result:null,
  cases:Array.from({length:10},(_,index)=>{
    const case_id='CASE-'+String(index+1).padStart(3,'0'),scenario_id='SYNTHETIC-ORIGINAL-'+index;
    const code='\ufeff# 기존 코드 <script>SYNTHETIC</script>\r\nSCENARIO_ID = '+JSON.stringify(scenario_id)+'\r\nassert True\r\n';
    return {case_id,scenario_id,workflow_id:'CAPTURE-WF-SYNTHETIC-'+index,business_unit_id:'CU'+String(index+1).padStart(2,'0'),scenario_name:'Synthetic case '+index,
      code,code_sha256:sha(code),expected_syntax_status:'PASS',problem:{scenario_id,steps:[{order:1,action:'click',target:'#synthetic-'+index,expected_result:'Synthetic expected'}]},
      expected_results:[{order:1,action:'click',target:{by:'css selector',value:'#synthetic-'+index},checks:[{kind:'visible',expected:true}]}]};
  })};}
function checked(data,passed=10){return {...clone(data),result:{status:'COMPLETED',score:passed*10,sample_count:10,syntax_pass_count:passed,syntax_fail_count:10-passed,official_pass:null,
  source_generation_id:data.source_generation_id,source_manifest_sha256:data.source_manifest_sha256,checked_at:'2026-11-13T12:00:00+09:00',
  cases:data.cases.map((row,index)=>({case_id:row.case_id,scenario_id:row.scenario_id,workflow_id:row.workflow_id,code_sha256:row.code_sha256,
    syntax_status:index<passed?'PASS':'FAIL',expected_syntax_status:'PASS',matches_expected:index<passed,error:index<passed?null:'Synthetic <img src=x onerror=x> syntax failure'}))}};}
function harness({data=fixture(),query='?mode=DEVELOPMENT&skip_gpt=1',port='8000',render=true}={}){
  const nodes=new Map(),calls=[],timers=new Map();let timer=0;
  const node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',disabled:false,hidden:false,value:'',listeners:{},
    addEventListener(name,fn){this.listeners[name]=fn;}});return nodes.get(id);};
  const response=(value,status=200,session=SERVER)=>({ok:status>=200&&status<300,status,headers:{get:()=>session},json:async()=>clone(value)});
  const state={data:clone(data),getReply:null,validateReply:null};
  const location={pathname:'/metrics/m07',search:query,port};
  const context=vm.createContext({URLSearchParams,TextEncoder,TextDecoder,Uint8Array,AbortController,crypto:webcrypto,console,location,
    catalog:{server_session_id:SERVER},document:{querySelector:node},app:node('#app'),labels:{M07:'M07'},link:value=>value,
    esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    score:value=>value==null?'—':Number(value).toFixed(2)+'%',
    setTimeout(fn,ms){const id=++timer;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
    ktlCheckServerSession(reply){if(reply.headers.get()!==SERVER)throw new Error('Synthetic server session changed');},
    fetch:async(url,options)=>{
      const payload=options?.body?JSON.parse(options.body):undefined;calls.push({url,method:options?.method||'GET',payload});
      if(url===ENDPOINT)return state.getReply?state.getReply():response(state.data);
      if(url===ENDPOINT+'/validate')return state.validateReply?state.validateReply(payload):response(checked(state.data));
      throw new Error('Unexpected API '+url);
    }});
  vm.runInContext(source,context);if(render)context.renderM07({metric_id:'M07',target:80});
  return {context,state,calls,node,response,location,timers,evaluate:code=>vm.runInContext(code,context),
    click:id=>node(id).listeners.click({target:node(id)}),posts:()=>calls.filter(row=>row.method==='POST')};
}
const tests=[];const test=(name,run)=>tests.push([name,run]);
test('port 8002 defaults to existing codes without a query while port 8000 and explicit skip zero keep the original flow',async()=>{
  for(const options of [{port:'8002',query:''},{port:'8002',query:'?mode=DEVELOPMENT'},{port:'8000',query:'?skip_gpt=1'}]){
    const h=harness(options);await settle();assert.equal(h.evaluate('m07ExistingPage()'),true);
    assert.equal(h.evaluate('m07ExistingView.context.cases.length'),10);assert.match(h.node('#app').innerHTML,/검증 실행/);
    assert.deepEqual(h.calls.map(row=>[row.method,row.url]),[['GET',ENDPOINT]]);
    await h.click('#m07-existing-validate');assert.equal(h.posts().length,1);assert.match(h.node('#m07-existing-result').innerHTML,/100.00%/);
  }
  for(const options of [{port:'8000',query:''},{port:'8000',query:'?mode=DEVELOPMENT'},{port:'8002',query:'?mode=DEVELOPMENT&skip_gpt=0'}]){
    const h=harness({...options,render:false});assert.equal(h.evaluate('m07ExistingPage()'),false);
    h.evaluate('paintM07=()=>{};bootstrapM07Meeting=()=>{};bootstrapM07Workflows=()=>{};bootstrapM07=async()=>{};');
    h.context.renderM07({metric_id:'M07',target:80});await settle();assert.notEqual(h.evaluate('m07View'),null);assert.equal(h.evaluate('m07ExistingView'),null);
    assert.match(h.node('#app').innerHTML,/시험 입력 20건/);assert.doesNotMatch(h.node('#app').innerHTML,/기존 GPT 생성 코드 · 10건/);assert.equal(h.calls.length,0);
  }
});
test('skip flag loads the ten original problems expected conditions and exact UTF8 codes with one GET',async()=>{
  const h=harness();await settle();assert.deepEqual(h.calls.map(row=>[row.method,row.url]),[['GET',ENDPOINT]]);
  assert.equal(h.node('#m07-existing-validate').disabled,false);assert.equal(h.evaluate('m07View'),null);
  assert.equal((h.node('#m07-existing-cases').innerHTML.match(/data-m07-existing-row=/g)||[]).length,10);
  assert.match(h.node('#app').innerHTML,/검증 실행/);assert.doesNotMatch(h.node('#app').innerHTML,/429|로그인|설치|시연|예시|새 GPT 호출/);
  assert.match(h.node('#m07-existing-cases').innerHTML,/CU01/);assert.match(h.node('#m07-existing-cases').innerHTML,/<summary>상세<\/summary>/);
  assert.match(h.node('#m07-existing-cases').innerHTML,/기존 문법 판정/);assert.match(h.node('#m07-existing-cases').innerHTML,/이번 문법 검사/);assert.match(h.node('#m07-existing-cases').innerHTML,/판정 비교/);assert.doesNotMatch(h.node('#m07-existing-cases').innerHTML,/<caption>|문제·기대조건은 참조자료입니다/);
  assert.match(h.node('#m07-existing-cases').innerHTML,/&lt;script&gt;SYNTHETIC&lt;\/script&gt;/);assert.doesNotMatch(h.node('#m07-existing-cases').innerHTML,/<script>/);
  assert.equal(h.evaluate('m07ExistingView.context.cases[0].code'),fixture().cases[0].code);
  assert.equal(h.posts().length,0);assert.match(h.node('#m07-existing-result').innerHTML,/검사 대기/);
});
test('the real verification click sends one empty POST and renders the stored comparison without generating code',async()=>{
  const h=harness();await settle();await h.click('#m07-existing-validate');
  assert.deepEqual(h.posts(),[{url:ENDPOINT+'/validate',method:'POST',payload:{}}]);
  assert.match(h.node('#m07-existing-result').innerHTML,/data-m07-existing="score">100.00%/);
  assert.match(h.node('#m07-existing-result').innerHTML,/10 \/ 10건/);assert.match(h.node('#m07-existing-result').innerHTML,/기준 충족/);
  assert.match(h.node('#m07-existing-cases').innerHTML,/일치/);assert.equal(h.node('#m07-existing-status').textContent,'');assert.equal(h.node('#m07-existing-status').hidden,true);
  assert.ok(h.calls.every(row=>row.url.startsWith(ENDPOINT)));assert.equal(h.evaluate('m07ExistingView.context.result.official_pass'),null);
});
test('eight and seven syntax passes keep denominator ten and show the real failures and escaped errors',async()=>{
  for(const passed of [8,7]){
    const h=harness();await settle();h.state.validateReply=()=>h.response(checked(h.state.data,passed));await h.click('#m07-existing-validate');
    assert.match(h.node('#m07-existing-result').innerHTML,new RegExp('score">'+passed+'0.00%'));
    assert.match(h.node('#m07-existing-result').innerHTML,passed===8?/기준 충족/:/기준 미달/);
    assert.match(h.node('#m07-existing-cases').innerHTML,/불일치/);assert.match(h.node('#m07-existing-cases').innerHTML,/&lt;img/);
    assert.doesNotMatch(h.node('#m07-existing-cases').innerHTML,/<img/);
  }
});
test('refresh is GET only and restores an actual saved result instead of checking again',async()=>{
  const h=harness({data:checked(fixture(),8)});await settle();assert.match(h.node('#m07-existing-result').innerHTML,/80.00%/);
  await h.click('#m07-existing-refresh');assert.equal(h.posts().length,0);assert.equal(h.calls.length,2);
  assert.equal(h.node('#m07-existing-refresh').disabled,false);assert.equal(h.node('#m07-existing-status').textContent,'');assert.equal(h.node('#m07-existing-status').hidden,true);
});
test('expected FAIL is displayed from the source and a missing SCENARIO_ID declaration is not a syntax failure',async()=>{
  const data=fixture();data.cases[0].expected_syntax_status='FAIL';
  data.cases[5].code='print("SYNTHETIC valid Python without identity declaration")\r\n';data.cases[5].code_sha256=sha(data.cases[5].code);
  const h=harness({data});await settle();assert.equal(h.node('#m07-existing-validate').disabled,false);
  assert.match(h.node('#m07-existing-cases').innerHTML,/<td><span class="m07-fail">FAIL<\/span><\/td>/);
  h.state.validateReply=()=>{const reply=checked(h.state.data);Object.assign(reply.result,{score:90,syntax_pass_count:9,syntax_fail_count:1});
    Object.assign(reply.result.cases[0],{syntax_status:'FAIL',expected_syntax_status:'FAIL',matches_expected:true,error:'Synthetic expected syntax failure'});return h.response(reply);};
  await h.click('#m07-existing-validate');assert.match(h.node('#m07-existing-result').innerHTML,/90.00%/);
  assert.equal(h.evaluate('m07ExistingView.context.result.cases[0].matches_expected'),true);
  assert.equal(h.evaluate('m07ExistingView.context.result.cases[5].syntax_status'),'PASS');
});
test('double verification and refresh clicks are blocked throughout the request with no automatic retry',async()=>{
  const h=harness();await settle();const gate=deferred();h.state.validateReply=()=>gate.promise;
  const first=h.click('#m07-existing-validate');await h.click('#m07-existing-validate');await h.click('#m07-existing-refresh');
  assert.equal(h.posts().length,1);assert.equal(h.node('#m07-existing-validate').disabled,true);assert.equal(h.calls.length,2);
  gate.resolve(h.response(checked(h.state.data)));await first;await settle();assert.equal(h.posts().length,1);
});
test('unreadable unavailable or altered input data never becomes a fake ready dataset',async()=>{
  for(const mutate of [data=>data.code_source='PREPARED',data=>data.required_count=20,data=>data.cases.pop(),
    data=>data.cases[1].case_id=data.cases[0].case_id,data=>data.cases[0].code+='\n# changed',
    data=>data.cases[0].problem.scenario_id='OTHER',data=>data.cases[0].expected_results=[]]){
    const data=fixture();mutate(data);const h=harness({data});await settle();
    assert.equal(h.evaluate('m07ExistingView.context'),null);assert.equal(h.node('#m07-existing-validate').disabled,true);
    await h.click('#m07-existing-validate');assert.equal(h.posts().length,0);assert.ok(h.node('#m07-existing-status').textContent);
  }
});
test('a changed generation code problem or expected condition cannot replace the pinned comparison after POST',async()=>{
  for(const mutate of [data=>data.source_generation_id='OTHER',data=>data.source_manifest_sha256='c'.repeat(64),
    data=>{data.cases[0].code+='\n# changed';data.cases[0].code_sha256=sha(data.cases[0].code);},
    data=>data.cases[0].problem.steps[0].target='#other',data=>data.cases[0].expected_results[0].checks[0].expected=false]){
    const h=harness();await settle();h.state.validateReply=()=>{const data=clone(h.state.data);mutate(data);return h.response(checked(data));};
    await h.click('#m07-existing-validate');assert.equal(h.evaluate('m07ExistingView.context.result'),null);
    assert.match(h.node('#m07-existing-status').textContent,/변경|연결|SHA/);assert.doesNotMatch(h.node('#m07-existing-result').innerHTML,/100.00%/);
  }
});
test('foreign incomplete and internally contradictory results are rejected instead of displaying success',async()=>{
  for(const mutate of [data=>data.result.sample_count=9,data=>data.result.status='RUNNING',data=>data.result.official_pass=true,
    data=>data.result.cases[0].case_id='CASE-020',data=>data.result.cases[0].matches_expected=false,
    data=>data.result.cases[0].code_sha256='d'.repeat(64),data=>data.result.source_generation_id='OTHER',
    data=>data.result.syntax_pass_count=9,data=>data.result.score=80]){
    const h=harness();await settle();h.state.validateReply=()=>{const data=checked(h.state.data);mutate(data);return h.response(data);};
    await h.click('#m07-existing-validate');assert.equal(h.evaluate('m07ExistingView.context.result'),null);assert.doesNotMatch(h.node('#m07-existing-result').innerHTML,/100.00%/);
  }
});
test('request errors preserve the verified originals and do not create zero scores or retry calls',async()=>{
  const h=harness();await settle();h.state.validateReply=()=>h.response({error:'Synthetic comparison unavailable'},503);
  await h.click('#m07-existing-validate');await settle();assert.equal(h.posts().length,1);assert.equal(h.evaluate('m07ExistingView.context.result'),null);
  assert.match(h.node('#m07-existing-status').textContent,/Synthetic comparison unavailable/);assert.equal(h.node('#m07-existing-validate').disabled,false);
  assert.doesNotMatch(h.node('#m07-existing-result').innerHTML,/0.00%/);
});
test('late verification navigation and a foreign server session cannot paint a result',async()=>{
  for(const variant of ['page','navigation','flag','session']){
    const h=harness();await settle();const gate=deferred();h.state.validateReply=()=>gate.promise;
    const pending=h.click('#m07-existing-validate');if(variant==='page')h.evaluate('++m07RequestNumber');
    if(variant==='navigation')h.location.pathname='/metrics/m01';if(variant==='flag')h.location.search='?mode=DEVELOPMENT';
    gate.resolve(h.response(checked(h.state.data),200,variant==='session'?'SERVER-OTHER':SERVER));await pending;
    assert.equal(h.evaluate('m07ExistingView.context.result'),null,variant);assert.doesNotMatch(h.node('#m07-existing-result').innerHTML,/100.00%/);
  }
});
(async()=>{for(const [name,run]of tests){await run();console.log('PASS '+name);}console.log(tests.length+' M07 existing-code UI groups passed');})().catch(error=>{console.error(error);process.exitCode=1;});
