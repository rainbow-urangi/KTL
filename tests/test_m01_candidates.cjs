'use strict';
// Synthetic Node VM fixtures only: no real HTTP, browser, collector dataset, model, or truth registration.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {createHash}=require('node:crypto');
const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8');
const DATASET='a'.repeat(32),SECOND='1'.repeat(32),SERVER_SESSION='SERVER-'+'7'.repeat(32);
const REPLAY_KEY='ktl.m01.replay-source.v1',FORMULA='0.5*C1 + 0.3*(100-C2) + 0.2*C3';
const CATALOG_VERSION='SYNTHETIC-PRESENCE-1',CATALOG_SHA='e'.repeat(64);
const clone=value=>JSON.parse(JSON.stringify(value));
const response=(value,status=200)=>({ok:status>=200&&status<300,status,json:async()=>value});
const failure=message=>response({status:'ERROR',error:message},422);
const settle=async()=>{for(let i=0;i<14;i++)await new Promise(resolve=>setImmediate(resolve));};
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
function harness(){
  const elements=new Map(),calls=[],urls=[],datasets=new Map(),comparisons=new Map(),truths=new Map(),storage=new Map();
  let comparisonSequence=0,uploadSequence=0;
  function element(selector){
    if(!elements.has(selector)){
      const e={textContent:'',value:'',checked:false,disabled:false,hidden:false,open:false,files:[],listeners:{},dataset:{},
        classList:{toggle(){}},addEventListener(name,callback){this.listeners[name]=callback;},
        click(){return this.listeners.click?.({target:this});},focus(){},scrollIntoView(){},
        insertAdjacentHTML(position,value){this.innerHTML=position==='afterbegin'?value+this.innerHTML:this.innerHTML+value;}};
      let html='';Object.defineProperty(e,'innerHTML',{get:()=>html,set(value){
        html=String(value);const options=[...html.matchAll(/<option value="([^"]*)"/g)].map(match=>match[1]);
        if(options.length&&!options.includes(this.value))this.value=options[0];
      }});
      elements.set(selector,e);
    }
    return elements.get(selector);
  }
  const fixed={version:CATALOG_VERSION,sha256:CATALOG_SHA,scenarios:Array.from({length:20},(_,index)=>({
    scenario_id:'S'+String(index+1).padStart(2,'0'),scenario_name:'Synthetic scenario '+(index+1),scenario_version:'1',
    aliases:[],requirements:Array.from({length:3},(_,i)=>({requirement_id:'R'+(i+1),name:'Synthetic required '+(i+1)}))
  }))};
  const summary={source_event_count:22,event_count:22,session_count:2,
    sessions:[{session_id:'s1',event_count:11},{session_id:'s2',event_count:11}],
    required_fields:['session_id','event_time','event_type','page_url','page_title','target_key'],
    missing_header_fields:[],raw_missing_fields:{},missing_fields:{},missing_field_count:0,required_field_slots:132,
    target_selector_mapping:false,mapping_version:'synthetic',raw_c2:0,c2:0,c3:75,
    type_counts:{navigation:2,click:5,input:3,select_change:0,submit_save:1,popup:2,network:6,key_input:0},
    missing_types:['select_change','key_input'],unclassified_event_count:3,duplicate_event_id_rows:0,
    missing_event_id_rows:0,event_time_min_utc:null,event_time_max_utc:null,invalid_or_timezone_missing_event_times:0};
  const state={matches:{'S14/s2':3},catalogHook:null,reportHook:null,verificationHook:null,datasetReplyHook:null};
  function normalReport(payload){
    const sessions=payload.session_id===undefined?['s1','s2']:[payload.session_id],candidates=[];
    for(const [index,scenario] of fixed.scenarios.entries()){
      const truth={truth:{truth_id:(index+100).toString(16).padStart(32,'0'),scenario_name:scenario.scenario_name,
        scenario_version:scenario.scenario_version,event_count:3,matching_policy:'PRESENCE',run_mode:'DEVELOPMENT'},
        expected:scenario.requirements.map((requirement,i)=>({expected_event_id:requirement.requirement_id,sequence:i+1}))};
      truths.set(truth.truth.truth_id,truth);
      for(const session of sessions){
        const matched=state.matches[scenario.scenario_id+'/'+session]??1,c1=matched/3*100;
        const measurement={c1,c2:0,c3:75,collection_accuracy:0.5*c1+45,formula:FORMULA,target:65,
          threshold_met:0.5*c1+45>=65,field_policy:'RAW_REQUIRED_FIELDS',
          counts:{defined_required_event_count:3,collected_required_event_count:matched,total_collected_events:11,
            required_field_count:6,missing_required_field_count:0,defined_event_type_count:8,collected_event_type_count:6},
          scope:{session_id:session,description:'Synthetic single-session scope',all_original_rows_included:true}};
        const result={comparison_id:(++comparisonSequence).toString(16).padStart(32,'0'),dataset_id:payload.dataset_id,
          truth_id:truth.truth.truth_id,session_id:session,scenario_name:scenario.scenario_name,
          scenario_version:scenario.scenario_version,run_mode:'DEVELOPMENT',status:'DEVELOPMENT_EVENT_COMPARISON',
          input_sha256:{collector_csv:datasets.get(payload.dataset_id).sha256,expected_csv:CATALOG_SHA},
          capture_scope:{notice:'Synthetic original observation scope is fixed.'},measurement,score:null,official_pass:null,
          summary:{expected_count:3,matched_count:matched,missing_count:3-matched,extra_event_count:11-matched,
            duplicate_event_rows:0,source_event_count:22,scoped_unique_event_count:11,match_rate:c1,score:null,official_pass:null},
          rows:scenario.requirements.map((requirement,i)=>({sequence:i+1,expected_event_id:requirement.requirement_id,
            matched_event_id:i<matched?'event-'+i:'',status:i<matched?'MATCHED':'MISSING',
            reason:scenario.scenario_name+' / '+requirement.name+(i<matched?' 포함':' 누락')})),presence_truth:truth};
        comparisons.set(result.comparison_id,result);
        candidates.push({scenario_id:scenario.scenario_id,scenario_name:scenario.scenario_name,scenario_version:scenario.scenario_version,
          preset:{business_unit_id:scenario.scenario_id,scenario_name:scenario.scenario_name,scenario_version:scenario.scenario_version},
          session_id:session,status:'COMPLETED',result,truth});
      }
    }
    const winner=candidates.reduce((best,row)=>!best||row.result.measurement.collection_accuracy>best.result.measurement.collection_accuracy?row:best,null);
    return {status:'COMPLETED',run_mode:'DEVELOPMENT',official_pass:null,dataset_id:payload.dataset_id,
      catalog:{version:CATALOG_VERSION,sha256:CATALOG_SHA,scenario_count:20},scenario_count:20,evaluated_scenario_count:20,
      evaluated_session_count:sessions.length,candidate_count:candidates.length,completed_count:candidates.length,
      candidates,representative:winner,result:winner.result,truth:winner.truth,session_id:winner.session_id};
  }
  const context=vm.createContext({console,URLSearchParams,URL,Uint8Array,
    btoa:value=>Buffer.from(value,'binary').toString('base64'),
    location:{pathname:'/metrics/m01',search:'?mode=DEVELOPMENT'},history:{replaceState(_a,_b,url){urls.push(url);}},
    sessionStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
    document:{querySelector:element},fetch:async(url,options)=>{
      calls.push({url,options});
      if(url==='/api/evaluations?mode=DEVELOPMENT')return response({server_session_id:SERVER_SESSION,metrics:[{metric_id:'M01',metric_name:'Synthetic M01',target:65,operator:'>=',details:{}}]});
      if(url==='/api/development/m01/prod/status')return response({configured:false,connection_status:'not_checked'});
      if(url==='/api/development/m01/csv'&&options?.method==='POST'){
        const id=uploadSequence++?SECOND:DATASET,dataset={dataset_id:id,filename:'synthetic.csv',summary,sha256:'f'.repeat(64),uploaded_at:'synthetic'};
        datasets.set(id,dataset);return response({dataset});
      }
      if(url==='/api/development/m01/csv')return response({datasets:[...datasets.values()]});
      const csv=url.match(/^\/api\/development\/m01\/csv\/([a-f0-9]{32})\?/);
      if(csv){
        const query=new URL(url,'http://localhost').searchParams,session=query.get('session_id');
        const result={dataset:datasets.get(csv[1]),summary:{...summary,...(session!==null?{event_count:11,required_field_slots:66}:{})},
          rows:[{csv_row:2,event_type:'DOM_EVENT',interaction_type:'collector_boot',ktl_type:'unclassified',missing_fields:''}],
          offset:Number(query.get('offset')||0),limit:100,has_more:false};
        return state.datasetReplyHook?state.datasetReplyHook(csv[1],query,result):response(result);
      }
      if(url==='/api/development/m01/scenarios')return state.catalogHook?state.catalogHook(clone(fixed)):response(clone(fixed));
      if(url==='/api/development/m01/compare-scenarios'){
        const payload=JSON.parse(options.body),report=normalReport(payload);
        return state.reportHook?state.reportHook(payload,report):response(report);
      }
      const verification=url.match(/^\/api\/development\/m01\/comparisons\/([a-f0-9]{32})\/verification$/);
      if(verification){const result=comparisons.get(verification[1]);return state.verificationHook
        ?state.verificationHook(verification[1],result):response({verified:true,status:'VERIFIED',recalculated:result.measurement,differences:[]});}
      const saved=url.match(/^\/api\/development\/m01\/comparisons\/([a-f0-9]{32})$/);
      if(saved)return response(comparisons.get(saved[1]));
      const truth=url.match(/^\/api\/development\/m01\/ground-truths\/([a-f0-9]{32})$/);
      if(truth)return response(truths.get(truth[1]));
      throw new Error('Unexpected synthetic route '+url);
    }});
  vm.runInContext(source,context);
  const posts=url=>calls.filter(call=>call.url===url&&call.options?.method==='POST');
  const choose=async()=>{
    const bytes=Buffer.from('\uFEFFevent_type\r\nPAGE_VIEW\r\n');
    element('#csv-file').files=[{name:'synthetic.csv',size:bytes.length,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)}];
    return element('#csv-file').listeners.change({target:element('#csv-file')});
  };
  return {context,state,calls,urls,datasets,comparisons,truths,storage,element,posts,choose,fixed,
    html:()=>[...elements.values()].map(e=>e.innerHTML+' '+e.textContent).join('\n'),
    selector:vm.runInContext('selectM01Representative',context)};
}
const tests=[],test=(name,run)=>tests.push({name,run});
const hasScore=h=>h.element('#comparison-result').innerHTML.includes('id="collection-accuracy"');
test('no upload means no comparison, and original BU14/CU02 presets remain fixed',async()=>{
  const h=harness();await settle();assert.equal(h.posts('/api/development/m01/compare-scenarios').length,0);
  const start=source.indexOf('const M01_BU14_PRESET ='),end=source.indexOf('function selectM01Representative(',start);
  assert.equal(createHash('sha256').update(source.slice(start,end).replace(/\r\n/g,'\n').trim()).digest('hex'),
    'e6c9c449619b055c4ed993699800294da6c0b1f1373557f0a9503fe3b065008a');
});
test('one upload pins the server catalog and requests every scenario/session with a single POST',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  assert.equal(h.posts('/api/development/m01/compare-scenarios').length,1);
  assert.deepEqual(JSON.parse(h.posts('/api/development/m01/compare-scenarios')[0].options.body),
    {dataset_id:DATASET,catalog_version:CATALOG_VERSION,catalog_sha256:CATALOG_SHA});
  assert.equal(h.comparisons.size,40);assert.equal(h.posts('/api/development/m01/ground-truths').length,0);
  assert.equal(h.posts('/api/development/m01/compare').length,0);
  assert.ok(h.element('#comparison-result').innerHTML.includes('95.00%'));
  assert.ok(h.element('#comparison-result').innerHTML.includes('Synthetic scenario 14'));
  assert.ok(h.element('#comparison-result').innerHTML.includes('세션: s2'));
  assert.equal(vm.runInContext('m01TruthReport.truth.scenario_name',h.context),'Synthetic scenario 14');
  assert.ok(!h.calls.some(c=>/m03|m04|m07|model|generate/.test(c.url)));
});
test('the actual maximum is selected independently of a wrong aggregate representative',async()=>{
  const h=harness();await settle();h.state.reportHook=(_payload,report)=>{report.representative=report.candidates[0];return response(report);};
  await h.choose();await settle();assert.equal(vm.runInContext('m01TruthReport.truth.scenario_name',h.context),'Synthetic scenario 14');
});
test('the representative follows weighted collection accuracy when the highest C1 has worse field completeness',async()=>{
  const h=harness();await settle();h.state.matches={};
  h.state.reportHook=(_payload,report)=>{
    for(const [index,matched,c2,c3] of [[0,3,50,25],[1,2,0,100]]){
      const result=report.candidates[index].result,measurement=result.measurement;
      Object.assign(result.summary,{matched_count:matched,missing_count:3-matched,extra_event_count:11-matched,match_rate:matched/3*100});
      Object.assign(measurement,{c1:matched/3*100,c2,c3,collection_accuracy:0.5*(matched/3*100)+0.3*(100-c2)+0.2*c3});
      measurement.threshold_met=measurement.collection_accuracy>=65;
      Object.assign(measurement.counts,{collected_required_event_count:matched,missing_required_field_count:c2/100*66,
        collected_event_type_count:c3/100*8});
      result.rows.forEach((row,i)=>Object.assign(row,{status:i<matched?'MATCHED':'MISSING',
        matched_event_id:i<matched?'event-'+i:'',reason:'Synthetic weighted fixture '+(i<matched?'포함':'누락')}));
    }
    return response(report);
  };
  await h.choose();await settle();const html=h.element('#comparison-result').innerHTML;
  assert.ok(html.includes('83.33%'));assert.ok(html.includes('66.67%'));assert.ok(html.includes('세션: s2'));
});
test('ties retain catalog/session order and the selector accepts real zero without mutating inputs',async()=>{
  const h=harness();await settle();h.state.matches={};await h.choose();await settle();
  assert.equal(vm.runInContext('m01TruthReport.truth.scenario_name',h.context),'Synthetic scenario 1');
  assert.ok(h.element('#comparison-result').innerHTML.includes('세션: s1'));
  const rows=Object.freeze([Object.freeze({status:'COMPLETED',result:{measurement:{collection_accuracy:0}}}),
    Object.freeze({status:'COMPLETED',result:{measurement:{collection_accuracy:0}}})]);
  assert.equal(h.selector(rows),rows[0]);assert.equal(h.selector([...rows].reverse()),rows[1]);
  for(const value of [NaN,Infinity,-Infinity,null,undefined,'99',false,-1,101]){
    assert.equal(h.selector([{status:'COMPLETED',result:{measurement:{collection_accuracy:value}}}]),null);
  }
});
test('a selected session is sent once and all 20 comparisons remain within that session',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  h.element('#csv-session').value='s1';await h.element('#csv-session').listeners.change();await settle();
  const payload=JSON.parse(h.posts('/api/development/m01/compare-scenarios').at(-1).options.body);
  assert.equal(payload.session_id,'s1');assert.equal(h.comparisons.size,60);
  assert.ok(h.element('#comparison-result').innerHTML.includes('세션: s1'));
});
test('required-event counts, missing reasons and criterion names use the existing result details',async()=>{
  const h=harness();await settle();h.state.matches={};await h.choose();await settle();
  const html=h.element('#comparison-result').innerHTML;
  assert.ok(html.includes('일치 1 / 3'));assert.ok(html.includes('필수 이벤트 1 / 3'));
  assert.ok(html.includes('Synthetic scenario 1 / Synthetic required 2 누락'));
  assert.ok(html.includes(FORMULA));assert.ok(html.includes('기준 미달 (개발)'));
  assert.ok(html.includes('공식 시험 판정은 아닙니다.'));
});
test('all session/scenario results must finish before any final score or replay source is published',async()=>{
  const h=harness(),pending=deferred();await settle();
  h.state.reportHook=(_payload,report)=>pending.promise.then(()=>response(report));
  const work=h.choose();await settle();
  assert.equal(hasScore(h),false);assert.equal(vm.runInContext('m01TruthReport',h.context),null);
  assert.equal(h.storage.has(REPLAY_KEY),false);
  pending.resolve();await work;await settle();assert.equal(hasScore(h),true);
});
test('partial errors clear a prior score and expose every failed scenario without fallback scoring',async()=>{
  const h=harness();await settle();await h.choose();await settle();assert.equal(h.storage.has(REPLAY_KEY),true);
  h.state.reportHook=(_payload,report)=>{
    for(const index of [1,38]){report.candidates[index].status='ERROR';report.candidates[index].error='synthetic failure '+index;}
    report.completed_count-=2;report.status='ERROR';return response(report);
  };
  await vm.runInContext('evaluateM01Csv()',h.context);await settle();
  assert.equal(hasScore(h),false);assert.equal(h.storage.has(REPLAY_KEY),false);
  assert.ok(h.element('#comparison-status').textContent.includes('S01 / s2: synthetic failure 1'));
  assert.ok(h.element('#comparison-status').textContent.includes('S20 / s1: synthetic failure 38'));
});
test('invalid fixed catalogs are rejected before a comparison request',async()=>{
  for(const mutate of [fixed=>{fixed.scenarios.pop();},fixed=>{fixed.sha256='bad';},
    fixed=>{fixed.version='';},fixed=>{fixed.scenarios[1].scenario_id=fixed.scenarios[0].scenario_id;},
    fixed=>{fixed.scenarios[0].requirements=[];}]){
    const h=harness();await settle();h.state.catalogHook=fixed=>{mutate(fixed);return response(fixed);};
    await h.choose();await settle();assert.equal(h.posts('/api/development/m01/compare-scenarios').length,0);assert.equal(hasScore(h),false);
  }
});
test('catalog, denominator, scope and official-result contract mismatches cannot publish a score',async()=>{
  const cases=[
    report=>{report.catalog.sha256='f'.repeat(64);},report=>{report.catalog.version='changed';},
    report=>{report.scenario_count=19;},report=>{report.evaluated_scenario_count=19;},
    report=>{report.candidate_count=39;},report=>{report.completed_count=39;},
    report=>{report.evaluated_session_count=11;},report=>{report.candidates.pop();},
    report=>{report.candidates=report.candidates.filter(candidate=>candidate.session_id==='s1');report.evaluated_session_count=1;report.candidate_count=20;report.completed_count=20;},
    report=>{report.dataset_id=SECOND;},report=>{report.official_pass=true;},report=>{report.run_mode='OFFICIAL';},
    report=>{report.candidates[1]=report.candidates[0];},
    report=>{report.candidates[0].scenario_id='UNKNOWN';},
    report=>{report.candidates[0].session_id='';},
    report=>{for(const candidate of report.candidates)if(candidate.session_id==='s2'){candidate.session_id='unknown-session';candidate.result.session_id='unknown-session';}},
    report=>{report.candidates[0].result.dataset_id=SECOND;},
    report=>{report.candidates[0].result.input_sha256.collector_csv='0'.repeat(64);},
    report=>{report.candidates[1].result.comparison_id=report.candidates[0].result.comparison_id;},
    report=>{report.candidates[0].result.session_id='s2';},
    report=>{report.candidates[0].result.truth_id='bad';},
    report=>{report.candidates[0].truth.truth.scenario_version='changed';},
    report=>{report.candidates[0].truth.expected.pop();},
    report=>{report.candidates[0].result.rows.pop();},
    report=>{report.candidates[0].result.summary.expected_count=2;},
    report=>{report.candidates[0].result.official_pass=true;},
    report=>{report.candidates[0].result.summary.official_pass=true;},
    report=>{report.candidates[0].result.run_mode='OFFICIAL';},
    report=>{report.candidates[0].result.measurement.collection_accuracy=null;},
    report=>{report.candidates[0].result.measurement.collection_accuracy=NaN;},
    report=>{report.candidates[0].result.measurement.collection_accuracy=101;}
  ];
  for(const [index,mutate] of cases.entries()){
    const h=harness();await settle();h.state.reportHook=(_payload,report)=>{mutate(report);return response(report);};
    await h.choose();await settle();assert.equal(hasScore(h),false,'case '+index);
    assert.equal(h.storage.has(REPLAY_KEY),false,'case '+index);assert.ok(h.element('#comparison-status').textContent,'case '+index);
  }
});
test('a different returned session cannot satisfy a specifically selected session',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  h.state.reportHook=(_payload,report)=>{report.candidates[0].session_id='s2';return response(report);};
  h.element('#csv-session').value='s1';await h.element('#csv-session').listeners.change();await settle();assert.equal(hasScore(h),false);
});
test('catalog or comparison server errors preserve an explicit error without a numeric result',async()=>{
  for(const stage of ['catalogHook','reportHook']){
    const h=harness();await settle();h.state[stage]=()=>failure('synthetic '+stage);
    await h.choose();await settle();assert.equal(hasScore(h),false);
    assert.ok(h.element('#comparison-status').textContent.includes('synthetic '+stage));
  }
});
test('late comparison responses cannot overwrite a newer upload, selection or replay source',async()=>{
  const h=harness(),pending=deferred();await settle();
  h.state.reportHook=(payload,report)=>payload.dataset_id===DATASET?pending.promise.then(()=>response(report)):response(report);
  const first=h.choose();await settle();await h.choose();await settle();
  const latest=h.element('#comparison-result').innerHTML,replay=h.storage.get(REPLAY_KEY);
  assert.ok(latest.includes(SECOND));pending.resolve();await first;await settle();
  assert.equal(h.element('#comparison-result').innerHTML,latest);assert.equal(h.storage.get(REPLAY_KEY),replay);
});
test('a stale catalog response cannot submit an old dataset after a new upload starts',async()=>{
  const h=harness(),pending=deferred();await settle();let count=0;
  h.state.catalogHook=fixed=>++count===1?pending.promise.then(()=>response(fixed)):response(fixed);
  const first=h.choose();await settle();await h.choose();await settle();pending.resolve();await first;await settle();
  const payloads=h.posts('/api/development/m01/compare-scenarios').map(call=>JSON.parse(call.options.body));
  assert.equal(payloads.length,1);assert.equal(payloads[0].dataset_id,SECOND);
});
test('mapping diagnostics and picker cancellation do not register or compare extra criteria',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  h.element('#csv-target-mapping').checked=true;await h.element('#csv-target-mapping').listeners.change();await settle();
  h.element('#csv-file').files=[];await h.element('#csv-file').listeners.change();await settle();
  assert.equal(h.posts('/api/development/m01/compare-scenarios').length,1);
  assert.equal(h.posts('/api/development/m01/ground-truths').length,0);
});
test('server-provided matching reasons remain escaped in the unchanged result table',async()=>{
  const h=harness();await settle();h.state.matches={};
  h.state.reportHook=(_payload,report)=>{report.candidates[0].result.rows[0].reason='<script>synthetic</script>';return response(report);};
  await h.choose();await settle();const html=h.element('#comparison-result').innerHTML;
  assert.ok(html.includes('&lt;script&gt;synthetic&lt;/script&gt;'));assert.ok(!html.includes('<script>'));
});
test('replay storage contains only the confirmed winning comparison and server session',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  const replay=JSON.parse(h.storage.get(REPLAY_KEY));
  assert.deepEqual(Object.keys(replay).sort(),['comparison_id','server_session_id']);
  assert.equal(replay.server_session_id,SERVER_SESSION);
  const winner=h.comparisons.get(replay.comparison_id);assert.equal(winner.session_id,'s2');
  assert.equal(winner.scenario_name,'Synthetic scenario 14');assert.ok(h.urls.at(-1).includes(replay.comparison_id));
});
test('presence comparisons restore their embedded truth without a legacy truth request or new evaluation',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  const replay=JSON.parse(h.storage.get(REPLAY_KEY)),before=h.calls.length;
  await vm.runInContext('restoreM01Comparison('+JSON.stringify(replay.comparison_id)+')',h.context);await settle();
  assert.equal(hasScore(h),true);assert.equal(h.element('#csv-session').value,'s2');
  assert.equal(h.calls.slice(before).some(call=>call.url.includes('/ground-truths/')),false);
  assert.equal(h.posts('/api/development/m01/compare-scenarios').length,1);
});
test('legacy comparison restore keeps the original truth GET fallback',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  const replay=JSON.parse(h.storage.get(REPLAY_KEY));delete h.comparisons.get(replay.comparison_id).presence_truth;
  await vm.runInContext('restoreM01Comparison('+JSON.stringify(replay.comparison_id)+')',h.context);await settle();
  assert.equal(hasScore(h),true);assert.ok(h.calls.some(call=>call.url.includes('/ground-truths/')));
});
test('restoring a saved result invalidates an unfinished scenario comparison',async()=>{
  const h=harness(),pending=deferred();await settle();await h.choose();await settle();
  const replay=JSON.parse(h.storage.get(REPLAY_KEY));
  h.state.reportHook=(_payload,report)=>pending.promise.then(()=>response(report));
  const work=vm.runInContext('evaluateM01Csv()',h.context);await settle();
  await vm.runInContext('restoreM01Comparison('+JSON.stringify(replay.comparison_id)+')',h.context);await settle();
  const restored=h.element('#comparison-result').innerHTML;pending.resolve();await work;await settle();
  assert.equal(h.element('#comparison-result').innerHTML,restored);
});
test('verification failures remain visible and storage denial does not invalidate the measurement',async()=>{
  const h=harness();await settle();
  h.state.verificationHook=()=>response({verified:false,status:'ERROR',notice:'synthetic verification mismatch'});
  vm.runInContext("sessionStorage.setItem=()=>{throw new Error('blocked')};sessionStorage.removeItem=()=>{throw new Error('blocked')}",h.context);
  await h.choose();await settle();assert.equal(hasScore(h),true);
  assert.ok(h.element('#comparison-verification').textContent.includes('synthetic verification mismatch'));
});
test('M01 input and result renderers retain their exact existing design and controls',async()=>{
  const h=harness();await settle();
  for(const [startMarker,endMarker,expected] of [
    ['function renderM01Csv(','async function loadM01ProdStatus(','3006407f8ac8bfe0d9446c6f6bd17ad86c6a5a6eafd197bb1b64e06de9a87d49'],
    ['function renderM01ComparisonResult(','async function loadM01Verification(','31aa05f055a85a2bb9f73d80058161fb5d5dcad229f70751add67bec3f1b3666']]){
    const start=source.indexOf(startMarker),end=source.indexOf(endMarker,start);
    const unchangedDesign=source.slice(start,end).replace("/${measurement?'ktl-evidence.csv':'evidence.csv'}",'/evidence.csv');
    assert.equal(createHash('sha256').update(unchangedDesign.replace(/\r\n/g,'\n').trim()).digest('hex'),expected);
  }
  const html=h.element('#app').innerHTML,ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
  const expectedIds=['m01-input-panel','m01-dataset-name','m01-event-count','m01-ready-status','m01-open-upload','csv-file','csv-status',
    'm01-input-cards','comparison-selection','m01-diagnostics-card','m01-csv-options','csv-dataset','csv-session','csv-target-mapping',
    'csv-diagnostics','m01-prod-card','prod-status','prod-search','prod-from','prod-to','prod-session','prod-event','prod-query',
    'prod-logs','comparison-status','m01-result-panel','comparison-result'];
  assert.equal(ids.length,expectedIds.length);assert.deepEqual([...new Set(ids)].sort(),[...expectedIds].sort());
  assert.ok(html.includes('class="simple-evaluation"'));assert.ok(!html.includes('mode-switch'));
  assert.ok(html.indexOf('id="csv-dataset"')<html.indexOf('id="m01-input-cards"'));
  await h.choose();await settle();const result=h.element('#comparison-result').innerHTML,details=result.indexOf('<details>');
  assert.ok(result.includes('/ktl-evidence.csv'));
  for(const id of ['collection-accuracy','comparison-match-rate','comparison-field-missing','comparison-type-coverage'])
    assert.ok(result.includes('id="'+id+'"'));
  assert.ok(result.indexOf('id="collection-accuracy"')<details);
  assert.ok(result.indexOf('시험 시나리오:')>details);assert.ok(result.indexOf('m01-result-note')>details);
  assert.ok(result.indexOf(FORMULA)>details);assert.ok(result.indexOf('comparison-verification')>details);
  assert.ok(!result.includes('<details open'));assert.ok(result.includes('Evidence CSV 다운로드'));
  assert.ok(!/최고점|대표|후보|개별 결과 보기/.test(h.html()));assert.ok(!source.includes('m01-candidate-results'));
});
(async()=>{
  let count=0;for(const {name,run} of tests){await run();count++;console.log('PASS '+name);}
  console.log(count+'/'+tests.length+' M01 presence UI regression groups passed (synthetic VM only; real HTTP/browser/model calls 0)');
})().catch(error=>{console.error(error);process.exitCode=1;});
