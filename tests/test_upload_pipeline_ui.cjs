'use strict';
// API-consumer regressions. This replaces the retired upload-analysis UI suite.
// Synthetic in-memory responses only: HTTP/browser/model/GPT calls 0.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {createHash}=require('node:crypto');
const source=fs.readFileSync(path.resolve(__dirname,'../frontend/app.js'),'utf8');
const SESSION='SERVER-'+'1'.repeat(32);
const RUN='DEV-M03-20261112T000000-'+'1'.repeat(12);
const OTHER_RUN='DEV-M03-20261112T000001-'+'2'.repeat(12);
const UNIT='UNIT:external/확정-7',WORKFLOW='FLOW:opaque/7',SCENARIO='SCN:외부/0007';
const DATASET='m03-real-development-'+'2'.repeat(12);
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const plain=value=>JSON.parse(JSON.stringify(value));
const hash=text=>createHash('sha256').update(text).digest('hex');
function scenarioFixture(){return {scenario_id:SCENARIO,business_unit_id:UNIT,workflow_id:WORKFLOW,
  status:'SUCCESS',run_mode:'DEVELOPMENT',generator_mode:'REAL',synthetic:false,
  scenario_name:'Synthetic external scenario',steps:[{order:1,action:'click',target:'#synthetic-control'}]};}
function contextFixture(){return {run_mode:'DEVELOPMENT',generator_mode:'REAL',synthetic:false,dataset_id:DATASET,
  dataset_manifest_sha256:'3'.repeat(64),business_units:[{business_unit_id:UNIT,workflow_id:WORKFLOW}],
  real_generator_configured:true,verified_input:{dataset_id:'external-analysis',manifest_sha256:'4'.repeat(64)},
  source_module:'external-scenario-api',source_version:'test-v1'};}
function resultFixture(){return {metric_id:'M03',run_id:RUN,run_mode:'DEVELOPMENT',dataset_id:DATASET,
  status:'COMPLETED',score:null,official_pass:null,threshold_met:null,
  details:{evaluation_status:'NOT_READY',successful_scenario_count:null,total_scenario_count:1,
    success_policy:'STRUCTURE_AND_REFERENCE_ORDER',rows:[{business_unit_id:UNIT,success:null,reference_available:false}],
    external_details:{synthetic:false}}};}
function harness({search='?mode=DEVELOPMENT',pathname='/metrics/m03'}={}) {
  const elements=new Map(),calls=[],state={session:SESSION,storageReads:0};
  function element(key) {
    if(!elements.has(key))elements.set(key,{innerHTML:'',textContent:'',value:'',checked:false,disabled:false,hidden:false,
      listeners:{},classList:{toggle(){}},addEventListener(name,callback){this.listeners[name]=callback;},
      setAttribute(name,value){this[name]=value;},getAttribute(name){return this[name]??null;},removeAttribute(name){delete this[name];},
      scrollIntoView(){},focus(){}});
    return elements.get(key);
  }
  const location={pathname,search};
  const response=(body,status=200)=>({ok:status>=200&&status<300,status,
    headers:{get:name=>name==='X-KTL-Server-Session'?state.session:null},json:async()=>body});
  state.reply=async(url,options)=>{
    if(url==='/api/development/m03/context')return response(contextFixture());
    if(url==='/api/development/m03/connection')return response({m03:{generator_mode:'REAL',transport:'HTTP'},
      configured:true,current_mode:'REAL',transport:'HTTP',message:''});
    if(url==='/api/development/m03/runs')return response({run_mode:'DEVELOPMENT',runs:[{run_id:RUN,active_scenario_count:1}]});
    if(url==='/api/evaluations/m03/runs/'+RUN+'/result.json')return response(resultFixture());
    if(url==='/api/evaluations/m03/runs/'+RUN+'/received_payload.json')return response({scenarios:[scenarioFixture()]});
    if(url==='/api/development/m03/runs/'+RUN+'/scenarios')return response({run_id:RUN,scenarios:[scenarioFixture()],deleted_scenario_ids:[]});
    if(url==='/api/development/m03/runs/'+RUN+'/executions')return response({executions:[]});
    if(url==='/api/m03/generate'&&options?.method==='POST')return response(scenarioFixture());
    if(url==='/api/integrations/m03/result'&&options?.method==='POST')return response(resultFixture());
    if(url==='/api/evaluations?mode=DEVELOPMENT')return response({server_session_id:SESSION,metrics:[{metric_id:'M03',latest:resultFixture()}]});
    throw new Error('Unexpected request: '+url);
  };
  const context=vm.createContext({URL,URLSearchParams,AbortController,setTimeout,clearTimeout,Uint8Array,
    crypto:{randomUUID:()=> 'synthetic-ui-run'},location,
    history:{replaceState(_state,_title,value){const url=new URL(value,'http://127.0.0.1');location.pathname=url.pathname;location.search=url.search;}},
    sessionStorage:{getItem(key){if(key==='ktl.m01.replay-source.v1')return null;state.storageReads++;throw new Error('Retired pipeline storage must not be read');}},
    document:{querySelector:element,querySelectorAll:()=>[]},
    fetch:async(url,options)=>{calls.push({url,options});return state.reply(url,options);}});
  vm.runInContext(source.replace(/\bload\(\);\s*$/,''),context);
  const evaluate=code=>vm.runInContext(code,context);
  evaluate('catalog={server_session_id:'+JSON.stringify(SESSION)+',metrics:[]};m03RequestNumber=1;');
  context.fixture=contextFixture();
  evaluate('m03View={scenarios:[],attempts:[],result:null,sample:false,busy:false,context:fixture,savedRuns:[],executions:[],deletedCount:0,managementReady:false};');
  return {context,evaluate,element,calls,state,response,location};
}
const tests=[];
function test(name,run){tests.push({name,run});}
function assertReadOnly(h){assert.ok(h.calls.every(call=>!call.options?.method),'restoration must use GET only');}

test('retired CSV/analysis query and session storage never propagate into links or catalog requests',async()=>{
  const h=harness({search:'?mode=DEVELOPMENT&csv_dataset_id='+'a'.repeat(32)+'&analysis_id=UPLOAD-ANALYSIS-'+'b'.repeat(32)});
  h.evaluate('render=()=>{}');await h.evaluate('load()');
  assert.equal(h.calls.length,1);assert.equal(h.calls[0].url,'/api/evaluations?mode=DEVELOPMENT');
  for(const id of ['m01','m02','m03','m04','m05','m06','m07'])assert.equal(h.evaluate("link('/metrics/"+id+"')"),'/metrics/'+id+'?mode=DEVELOPMENT');
  assert.equal(h.state.storageReads,0);
  assert.equal(/uploadPipeline|ktlPipeline|analyze-upload|M02에서 업로드 CSV|시나리오 생성 시 업로드 CSV/.test(source),false);
});
test('REFERENCE and OFFICIAL navigation remain independent of development input',()=>{
  for(const mode of ['REFERENCE','OFFICIAL']) {
    const h=harness({search:'?mode='+mode+'&csv_dataset_id=obsolete'});
    assert.equal(h.evaluate("link('/metrics/m03')"),'/metrics/m03?mode='+mode);assert.equal(h.calls.length,0);
  }
});
test('generic execution remains the original bodyless run and never starts uploaded analysis',async()=>{
  for(const id of ['M02','M06']) {
    const h=harness({pathname:'/metrics/'+id.toLowerCase()});h.evaluate('load=async()=>{}');
    h.state.reply=async()=>h.response({run_id:'synthetic-existing-run'});
    await h.evaluate("run('"+id+"')");
    assert.equal(h.calls.length,1);assert.equal(h.calls[0].url,'/api/evaluations/'+id.toLowerCase()+'/run?mode=DEVELOPMENT');
    assert.deepEqual(plain(h.calls[0].options),{method:'POST'});
  }
  const a=source.indexOf('async function run(id) {'),b=source.indexOf('async function load()',a);
  assert.equal(hash(source.slice(a,b).trim().replace(/\r\n/g,'\n')),'6581292b0e53fb493a2cf8269901c123a45c8c5b4db9a4371cfd09b80117c745');
});
test('both immutable M01 criteria and the original score renderer are preserved',()=>{
  for(const [name,expected] of [['M01_BU14_PRESET','703ecc02c62a8db6d6694677f80bae785d5095fb55dade63b9fa398f9a9ee9bf'],
    ['M01_CU02_PRESET','ac8c2f246d42a6d0eabcf903e3fb0b4caff83369341cf600773f5c6eef5a9aa7']]) {
    const value=JSON.parse(source.split('const '+name+' = ')[1].split(/;\r?\n/)[0]);
    assert.equal(hash(JSON.stringify({scenario_name:value.scenario_name,scenario_version:value.scenario_version,expected_events:value.expected_events})),expected);
  }
  const a=source.indexOf('function renderM01ComparisonResult('),b=source.indexOf('async function loadM01Verification(',a);
  assert.equal(hash(source.slice(a,b).trim()),'d799ed5a8872207ff1b3e0585284ca3c8465e743b93faaa7cc714263bdafe251');
});
test('M03 entry reads context connection and history without generation or model work',async()=>{
  const h=harness();await h.evaluate('prepareM03(null,1,null)');
  assert.deepEqual(h.calls.map(call=>call.url).sort(),['/api/development/m03/context','/api/development/m03/connection','/api/development/m03/runs'].sort());
  assertReadOnly(h);assert.equal(h.evaluate('m03View.result'),null);assert.equal(h.evaluate('m03View.context.business_units[0].business_unit_id'),UNIT);
});
test('explicit M03 click consumes context then generation API then result API while preserving opaque IDs',async()=>{
  const h=harness();await h.evaluate('generateM03Sample()');
  const posts=h.calls.filter(call=>call.options?.method==='POST');
  assert.deepEqual(posts.map(call=>call.url),['/api/m03/generate','/api/integrations/m03/result']);
  assert.deepEqual(JSON.parse(posts[0].options.body),{business_unit_id:UNIT,workflow_id:WORKFLOW,run_mode:'DEVELOPMENT',generator_mode:'REAL',dataset_id:DATASET});
  const payload=JSON.parse(posts[1].options.body);
  assert.equal(payload.dataset_id,DATASET);assert.equal(payload.scenarios[0].scenario_id,SCENARIO);
  assert.equal(payload.scenarios[0].business_unit_id,UNIT);assert.equal(payload.scenarios[0].workflow_id,WORKFLOW);
  assert.deepEqual(payload.scenarios[0].steps,scenarioFixture().steps);
  assert.equal(payload.details.generation_attempts.length,1);
  assert.equal('csv_dataset_id' in payload,false);assert.equal('analysis_id' in payload,false);
  assert.equal(h.calls.some(call=>/pipeline|analyze-upload|\/m0[26]\/run/.test(call.url)),false);
  assert.equal(h.evaluate('m03View.result.score'),null);assert.equal(h.evaluate('m03View.managementReady'),true);
});
test('double generation clicks do not duplicate API calls',async()=>{
  const h=harness(),reply=h.state.reply,pending=deferred();
  h.state.reply=async(url,options)=>url==='/api/development/m03/context'?pending.promise:reply(url,options);
  const first=h.evaluate('generateM03Sample()');await h.evaluate('generateM03Sample()');
  pending.resolve(h.response(contextFixture()));await first;
  assert.equal(h.calls.filter(call=>call.url==='/api/m03/generate').length,1);
  assert.equal(h.calls.filter(call=>call.url==='/api/integrations/m03/result').length,1);
});
test('a mismatched generation identity is retained as a failed attempt in the submitted denominator',async()=>{
  const h=harness(),reply=h.state.reply;
  h.state.reply=async(url,options)=>url==='/api/m03/generate'?h.response({...scenarioFixture(),workflow_id:'different-workflow'}):reply(url,options);
  await h.evaluate('generateM03Sample()');
  const payload=JSON.parse(h.calls.find(call=>call.url==='/api/integrations/m03/result').options.body);
  assert.equal(payload.scenarios.length,1);assert.equal(payload.scenarios[0].status,'FAILED');
  assert.equal(payload.scenarios[0].workflow_id,WORKFLOW);assert.equal(payload.details.generation_attempts.length,1);
});
test('failed ingestion never displays a completed evaluation',async()=>{
  const h=harness(),reply=h.state.reply;
  h.state.reply=async(url,options)=>url==='/api/integrations/m03/result'?h.response({error:'synthetic ingest failure'},422):reply(url,options);
  await h.evaluate('generateM03Sample()');
  assert.equal(h.evaluate('m03View.result'),null);assert.match(h.element('#m03-status').textContent,/synthetic ingest failure/);
});
test('superseded generation response cannot submit an old result',async()=>{
  const h=harness(),reply=h.state.reply,pending=deferred(),entered=deferred();
  h.state.reply=async(url,options)=>{if(url==='/api/m03/generate'){entered.resolve();return pending.promise;}return reply(url,options);};
  const request=h.evaluate('generateM03Sample()');await entered.promise;h.evaluate('++m03RequestNumber');
  pending.resolve(h.response(scenarioFixture()));await request;
  assert.equal(h.calls.some(call=>call.url==='/api/integrations/m03/result'),false);assert.equal(h.evaluate('m03View.result'),null);
});
test('externally received results restore through GET even when the current generator context is unavailable',async()=>{
  const h=harness(),reply=h.state.reply;h.context.external=resultFixture();
  h.state.reply=async(url,options)=>url==='/api/development/m03/context'?h.response({error:'synthetic context unavailable'},422):reply(url,options);
  await h.evaluate('prepareM03(external,1,'+JSON.stringify(RUN)+')');
  assertReadOnly(h);assert.equal(h.evaluate('m03View.result.run_id'),RUN);
  assert.equal(h.evaluate('m03View.result.score'),null);assert.equal(h.evaluate('m03View.result.official_pass'),null);
  assert.equal(h.evaluate('m03View.scenarios[0].scenario_id'),SCENARIO);assert.equal(h.evaluate('m03View.managementReady'),true);
  assert.match(h.element('#m03-result').innerHTML,/정답 업무 순서 기준이 없어 평가 대기/);
});
test('opening a saved external result preserves original scenario and hands off only run/scenario IDs',async()=>{
  const h=harness();h.context.saved=[{run_id:RUN}];h.evaluate('m03View.savedRuns=saved');
  await h.evaluate('openM03Saved('+JSON.stringify(RUN)+')');assertReadOnly(h);
  for(const metric of ['m04','m07']) {
    const anchor=h.element('#m03-'+metric+'-handoff');assert.equal(anchor.hidden,false);
    const url=new URL(anchor.href,'http://local');assert.equal(url.pathname,'/metrics/'+metric);
    assert.deepEqual([...url.searchParams.keys()].sort(),['mode','m03_run_id','scenario_id'].sort());
    assert.equal(url.searchParams.get('m03_run_id'),RUN);assert.equal(url.searchParams.get('scenario_id'),SCENARIO);
  }
  assert.equal(new URLSearchParams(h.location.search).get('run_id'),RUN);
  assert.deepEqual(plain(h.evaluate('m03View.scenarios[0].steps')),scenarioFixture().steps);
});
test('M03 refresh reads the catalog without generating or re-ingesting an external result',async()=>{
  const h=harness();h.evaluate('renderM03=metric=>{globalThis.refreshedMetric=metric;}');
  await h.evaluate('refreshM03()');assert.equal(h.calls.length,1);assertReadOnly(h);
  assert.equal(h.calls[0].url,'/api/evaluations?mode=DEVELOPMENT');assert.equal(h.evaluate('refreshedMetric.latest.run_id'),RUN);
});
test('a run outside the current session catalog is not restored or regenerated',async()=>{
  const h=harness();h.context.saved=[{run_id:RUN}];h.evaluate('m03View.savedRuns=saved');
  await h.evaluate('readM03Result(null,1,'+JSON.stringify(OTHER_RUN)+')');
  assert.equal(h.calls.length,0);assert.equal(h.evaluate('m03View.result'),null);
  assert.equal(h.evaluate('m03View.managementReady'),false);
});
test('execution-history read failure does not regenerate or discard a stored scenario',async()=>{
  const h=harness(),reply=h.state.reply;h.context.saved=[{run_id:RUN}];h.evaluate('m03View.savedRuns=saved');
  h.state.reply=async(url,options)=>url.endsWith('/executions')?h.response({error:'synthetic execution list failure'},503):reply(url,options);
  await h.evaluate('readM03Result(null,1,'+JSON.stringify(RUN)+')');assertReadOnly(h);
  assert.equal(h.evaluate('m03View.result.run_id'),RUN);assert.equal(h.evaluate('m03View.managementReady'),true);
  assert.match(h.evaluate('m03View.executionError'),/execution list failure/);
});
test('malformed saved raw scenarios are rejected before management or handoff activation',async()=>{
  const h=harness(),reply=h.state.reply;h.context.saved=[{run_id:RUN}];h.evaluate('m03View.savedRuns=saved');
  h.state.reply=async(url,options)=>url.endsWith('/received_payload.json')?h.response({scenarios:[null]}):reply(url,options);
  await assert.rejects(h.evaluate('readM03Result(null,1,'+JSON.stringify(RUN)+')'),/원본 시나리오/);
  assert.equal(h.evaluate('m03View.result'),null);assert.equal(h.evaluate('m03View.managementReady'),false);assertReadOnly(h);
});
test('late stored-result response is ignored after selection changes',async()=>{
  const h=harness(),reply=h.state.reply,pending=deferred();h.context.saved=[{run_id:RUN}];h.evaluate('m03View.savedRuns=saved');
  h.state.reply=async(url,options)=>url.endsWith('/result.json')?pending.promise:reply(url,options);
  const request=h.evaluate('readM03Result(null,1,'+JSON.stringify(RUN)+')');h.evaluate('++m03RequestNumber');
  pending.resolve(h.response(resultFixture()));await request;
  assert.equal(h.calls.length,1);assert.equal(h.evaluate('m03View.result'),null);assertReadOnly(h);
});
test('session mismatch rejects an API response and starts only a catalog reload',async()=>{
  const h=harness();h.evaluate('load=async()=>{globalThis.reloadCount=(globalThis.reloadCount||0)+1;}');
  h.state.session='SERVER-new';await assert.rejects(h.evaluate("m03Json('/api/development/m03/context')"),/서버 세션/);
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.evaluate('reloadCount'),1);assert.equal(h.evaluate('m03View'),null);assertReadOnly(h);
});
(async()=>{for(const item of tests){await item.run();console.log('PASS '+item.name);}console.log(tests.length+' API consumer UI groups passed');})()
  .catch(error=>{console.error(error);process.exitCode=1;});
