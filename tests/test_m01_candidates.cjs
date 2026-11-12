'use strict';
// Pure Node VM fixtures: no server, files uploaded, registered truth, browser, or model calls.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {createHash}=require('node:crypto');
const source=fs.readFileSync(path.join(__dirname,'../frontend/app.js'),'utf8');
const DATASET='a'.repeat(32),SECOND='1'.repeat(32);
const SERVER_SESSION='SERVER-'+'7'.repeat(32),REPLAY_KEY='ktl.m01.replay-source.v1';
const TRUTHS={BU14:'b'.repeat(32),CU02:'c'.repeat(32)};
const DIGESTS={BU14:'d'.repeat(64),CU02:'e'.repeat(64)};
const FORMULA='0.5*C1 + 0.3*(100-C2) + 0.2*C3';
const clone=value=>JSON.parse(JSON.stringify(value));
const canonical=value=>JSON.stringify((function sort(item){
  return Array.isArray(item)?item.map(sort):item&&typeof item==='object'
    ?Object.fromEntries(Object.keys(item).sort().map(key=>[key,sort(item[key])])):item;
})(value));
const digest=value=>createHash('sha256').update(canonical(value)).digest('hex');
const deferred=()=>{let resolve;const promise=new Promise(done=>{resolve=done;});return {promise,resolve};};
const response=(value,status=200)=>({ok:status>=200&&status<300,status,json:async()=>value});
const failure=message=>response({status:'ERROR',error:message},422);
const settle=async()=>{for(let i=0;i<14;i++)await new Promise(resolve=>setImmediate(resolve));};
function freeze(value){if(value&&typeof value==='object'){Object.values(value).forEach(freeze);Object.freeze(value);}return value;}

function harness(search='?mode=DEVELOPMENT'){
  const elements=new Map(),calls=[],urls=[],datasets=new Map(),comparisons=new Map(),storage=new Map();
  let comparisonSequence=0,uploadSequence=0,presets=[];
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
  const summary={source_event_count:22,event_count:22,session_count:2,
    sessions:[{session_id:'s1',event_count:11},{session_id:'s2',event_count:11}],
    required_fields:['session_id','event_time','event_type','page_url','page_title','target_key'],
    missing_header_fields:[],raw_missing_fields:{},missing_fields:{},missing_field_count:0,required_field_slots:132,
    target_selector_mapping:false,mapping_version:'synthetic',raw_c2:0,c2:0,c3:75,
    type_counts:{navigation:2,click:5,input:3,select_change:0,submit_save:1,popup:2,network:6,key_input:0},
    missing_types:['select_change','key_input'],unclassified_event_count:3,duplicate_event_id_rows:0,
    missing_event_id_rows:0,event_time_min_utc:null,event_time_max_utc:null,invalid_or_timezone_missing_event_times:0};
  const makeDataset=id=>({dataset_id:id,filename:id===DATASET?'synthetic-events.csv':'new-events.csv',summary,
    sha256:(id===DATASET?'f':'2').repeat(64),uploaded_at:'synthetic'});
  const state={matches:{BU14:2,CU02:6},registrationHook:null,comparisonHook:null,verificationHook:null,
    datasetReplyHook:null,uploadReplyHook:null};
  const presetByName=name=>presets.find(p=>p.scenario_name===name);
  const truthFor=preset=>({truth:{truth_id:TRUTHS[preset.business_unit_id],scenario_name:preset.scenario_name,
    scenario_version:preset.scenario_version,event_count:preset.expected_events.length,sha256:DIGESTS[preset.business_unit_id],
    filename:'expected.csv',source:'stored_scenario',legacy_csv:false,run_mode:'DEVELOPMENT'},expected:preset.expected_events,run_mode:'DEVELOPMENT'});
  const normalComparison=payload=>{
    const preset=presets.find(p=>TRUTHS[p.business_unit_id]===payload.truth_id);
    assert.ok(preset,'Only the two fixed synthetic truth replies may be compared');
    const defined=preset.expected_events.length,matched=state.matches[preset.business_unit_id],c1=matched/defined*100;
    const count=payload.session_id===undefined?22:11;
    const measurement={c1,c2:0,c3:75,collection_accuracy:0.5*c1+30+15,formula:FORMULA,target:65,
      threshold_met:0.5*c1+45>=65,field_policy:'RAW_REQUIRED_FIELDS',mapping_version:'synthetic',
      counts:{defined_required_event_count:defined,collected_required_event_count:matched,total_collected_events:count,
        required_field_count:6,missing_required_field_count:0,defined_event_type_count:8,collected_event_type_count:6},
      scope:{session_id:payload.session_id??null,description:'Synthetic fixed scope',all_original_rows_included:true}};
    const result={comparison_id:(++comparisonSequence).toString(16).padStart(32,'0'),dataset_id:payload.dataset_id,
      truth_id:payload.truth_id,session_id:payload.session_id??null,scenario_name:preset.scenario_name,
      scenario_version:preset.scenario_version,run_mode:'DEVELOPMENT',status:'DEVELOPMENT_EVENT_COMPARISON',
      input_sha256:{collector_csv:datasets.get(payload.dataset_id).sha256,expected_csv:DIGESTS[preset.business_unit_id]},
      capture_scope:{notice:'Synthetic original observation scope is fixed.'},
      summary:{expected_count:defined,matched_count:matched,missing_count:defined-matched,extra_event_count:count-matched,
        duplicate_event_rows:0,source_event_count:22,scoped_unique_event_count:count,match_rate:c1,score:null,official_pass:null},
      measurement,score:null,official_pass:null,
      rows:[{sequence:1,expected_event_id:preset.business_unit_id+'-SYNTHETIC',matched_event_id:'<img onerror=bad>',
        expected_event_type:'click',expected_page_url:'https://example.invalid/fixture',expected_target_selector:'#synthetic',
        status:'MATCHED',reason:'<script>synthetic comparison'}]};
    comparisons.set(result.comparison_id,result);return result;
  };
  const context=vm.createContext({console,URLSearchParams,URL,Uint8Array,
    btoa:value=>Buffer.from(value,'binary').toString('base64'),
    location:{pathname:'/metrics/m01',search},history:{replaceState(_a,_b,url){urls.push(url);}},
    sessionStorage:{getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
    document:{querySelector:element},
    fetch:async(url,options)=>{
      calls.push({url,options});
      if(url==='/api/evaluations?mode=DEVELOPMENT')return response({server_session_id:SERVER_SESSION,metrics:[{metric_id:'M01',metric_name:'Synthetic M01',target:65,operator:'>=',details:{}}]});
      if(url==='/api/development/m01/prod/status')return response({configured:false,connection_status:'not_checked'});
      if(url==='/api/development/m01/csv'&&options?.method==='POST'){
        const payload=JSON.parse(options.body),id=uploadSequence++?SECOND:DATASET,dataset=makeDataset(id);
        datasets.set(id,dataset);return state.uploadReplyHook?state.uploadReplyHook(payload,dataset):response({dataset});
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
      if(url==='/api/development/m01/ground-truths'&&options?.method==='POST'){
        const payload=JSON.parse(options.body),preset=presetByName(payload.scenario_name);
        assert.ok(preset,'Only original fixed BU14/CU02 criteria may be registered');
        assert.deepEqual(payload.expected_events,clone(preset.expected_events));
        return state.registrationHook?state.registrationHook(preset,payload):response(truthFor(preset));
      }
      const truth=url.match(/^\/api\/development\/m01\/ground-truths\/([a-f0-9]{32})$/);
      if(truth){const preset=presets.find(p=>TRUTHS[p.business_unit_id]===truth[1]);assert.ok(preset);return response(truthFor(preset));}
      if(url==='/api/development/m01/compare'){
        const payload=JSON.parse(options.body),normal=()=>response(normalComparison(payload));
        return state.comparisonHook?state.comparisonHook(payload,normal):normal();
      }
      const verification=url.match(/^\/api\/development\/m01\/comparisons\/([a-f0-9]{32})\/verification$/);
      if(verification){const result=comparisons.get(verification[1]);return state.verificationHook
        ?state.verificationHook(verification[1],result)
        :response({verified:true,status:'VERIFIED',recalculated:result.measurement,differences:[]});}
      const saved=url.match(/^\/api\/development\/m01\/comparisons\/([a-f0-9]{32})$/);
      if(saved)return response(comparisons.get(saved[1]));
      throw new Error('Unexpected synthetic route '+url);
    }});
  vm.runInContext(source,context);
  presets=vm.runInContext('M01_SCENARIO_PRESETS',context);
  const posts=url=>calls.filter(call=>call.url===url&&call.options?.method==='POST');
  const choose=async name=>{
    const bytes=Buffer.from('\uFEFFevent_type\r\nPAGE_VIEW\r\n');
    element('#csv-file').files=[{name:name||'synthetic.csv',size:bytes.length,
      arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)}];
    return element('#csv-file').listeners.change({target:element('#csv-file')});
  };
  return {context,state,presets,calls,elements,element,posts,choose,urls,comparisons,datasets,storage,truthFor,normalComparison,
    html:()=>[...elements.values()].map(e=>e.innerHTML+' '+e.textContent).join('\n'),
    selector:vm.runInContext('selectM01Representative',context)};
}

const tests=[];
const test=(name,run)=>tests.push({name,run});
test('original BU14 and independent eight-event CU02 criteria stay byte-semantically fixed',async()=>{
  const h=harness();await settle();
  assert.deepEqual(h.presets.map(p=>p.business_unit_id).join(','),'BU14,CU02');
  assert.equal(digest(h.presets[0]),'02457ebc7560ec85649032c5f3fe09113d71a817a3d4769bebb6680173df547e');
  const cu=h.presets[1];assert.equal(cu.scenario_name,'CU02 별도 DEVELOPMENT M01 사전 고정 사용자 조작');
  assert.equal(cu.scenario_version,'CU02-M01-PREFROZEN-USER-COMMANDS-1');assert.equal(cu.expected_events.length,8);
  assert.equal(digest(cu.expected_events),'4b38a2b1ed3629033d5ea4b2c274a6e045b60e16301cc7f6f6747743b5dc250a');
  assert.equal(h.posts('/api/development/m01/ground-truths').length,0);
  assert.equal(h.posts('/api/development/m01/compare').length,0);
});
test('representative selects actual maximum without sorting or mutating inputs',async()=>{
  const h=harness();await settle();
  const rows=freeze([{status:'COMPLETED',result:{measurement:{collection_accuracy:60}}},
    {status:'COMPLETED',result:{measurement:{collection_accuracy:82.5}}}]);
  assert.equal(h.selector(rows),rows[1]);assert.equal(rows[0].result.measurement.collection_accuracy,60);
  assert.equal(h.selector([...rows].reverse()),rows[1]);
});
test('representative preserves first candidate on ties and accepts a genuine zero',async()=>{
  const h=harness();await settle();
  const rows=[{status:'COMPLETED',result:{measurement:{collection_accuracy:0}}},
    {status:'COMPLETED',result:{measurement:{collection_accuracy:0}}}];
  assert.equal(h.selector(rows),rows[0]);assert.equal(h.selector(rows.slice().reverse()),rows[1]);
});
test('invalid values, incomplete statuses and errors never become numeric zero or a winner',async()=>{
  const h=harness();await settle();const good={status:'COMPLETED',result:{measurement:{collection_accuracy:10}}};
  for(const value of [NaN,Infinity,-Infinity,null,undefined,'99',false,-1,101]){
    const invalid={status:'COMPLETED',result:{measurement:{collection_accuracy:value}}};
    assert.equal(h.selector([invalid,good]),good,String(value));assert.equal(h.selector([invalid]),null,String(value));
  }
  for(const invalid of [{status:'ERROR',result:{measurement:{collection_accuracy:100}}},{status:'RUNNING',result:{measurement:{collection_accuracy:100}}},
    {status:'COMPLETED',result:null},{status:'COMPLETED',result:{}},{status:'COMPLETED',result:{measurement:{}}}]){
    assert.equal(h.selector([invalid,good]),good);assert.equal(h.selector([invalid]),null);
  }
  assert.equal(h.selector([]),null);
});
test('one upload compares both fixed candidates over the identical dataset and raw scope',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  const registrations=h.posts('/api/development/m01/ground-truths').map(c=>JSON.parse(c.options.body));
  const comparisons=h.posts('/api/development/m01/compare').map(c=>JSON.parse(c.options.body));
  assert.equal(registrations.length,2);assert.equal(comparisons.length,2);
  assert.deepEqual(registrations.map(r=>r.scenario_name),clone(h.presets.map(p=>p.scenario_name)));
  assert.deepEqual(comparisons,[{dataset_id:DATASET,truth_id:TRUTHS.BU14},{dataset_id:DATASET,truth_id:TRUTHS.CU02}]);
  assert.ok(registrations.every(r=>Object.keys(r).sort().join(',')==='expected_events,scenario_name,scenario_version'));
  assert.deepEqual([...h.comparisons.values()].map(result=>result.measurement.collection_accuracy),[55,82.5],
    'Both independent comparison records remain intact without adding a ranking table');
  assert.ok(h.element('#comparison-result').innerHTML.includes('82.50%'));
  assert.equal(vm.runInContext('m01TruthReport.truth.truth_id',h.context),TRUTHS.CU02);
  const winner=[...h.comparisons.values()].find(r=>r.truth_id===TRUTHS.CU02);
  assert.ok(h.urls.at(-1).includes('comparison_id='+winner.comparison_id));
  assert.ok(h.html().includes('DEVELOPMENT'));
  assert.ok(!h.calls.some(c=>/m03|m04|m07|model|generate/.test(c.url)));
});
test('BU14 remains the representative when its completed score is higher',async()=>{
  const h=harness();await settle();h.state.matches={BU14:9,CU02:1};await h.choose();await settle();
  assert.ok(h.element('#comparison-result').innerHTML.includes('90.00%'));
  assert.equal(vm.runInContext('m01TruthReport.truth.truth_id',h.context),TRUTHS.BU14);
  assert.equal([...h.comparisons.values()].find(result=>result.truth_id===TRUTHS.CU02).measurement.collection_accuracy,51.25,
    'The unselected CU02 result remains recorded without a new candidate panel');
});
test('two completed candidates choose BU14 first on an exact tie',async()=>{
  const h=harness();await settle();h.state.matches={BU14:5,CU02:4};await h.choose();await settle();
  assert.ok(h.element('#comparison-result').innerHTML.includes('70.00%'));
  assert.equal(vm.runInContext('m01TruthReport.truth.truth_id',h.context),TRUTHS.BU14);
});
test('registration failure is reported in the existing status while the other comparison remains usable',async()=>{
  const h=harness();await settle();h.state.registrationHook=async preset=>preset.business_unit_id==='BU14'
    ?failure('BU14 <img onerror=bad> registration failed'):response(h.truthFor(preset));
  await h.choose();await settle();
  assert.equal(h.posts('/api/development/m01/ground-truths').length,2);
  assert.equal(h.posts('/api/development/m01/compare').length,1);
  assert.ok(h.element('#comparison-result').innerHTML.includes('82.50%'));
  assert.ok(/일부|오류/.test(h.element('#comparison-status').textContent));
  assert.ok(h.element('#comparison-status').textContent.includes('BU14 <img onerror=bad> registration failed'));
  assert.ok(!h.element('#comparison-status').innerHTML.includes('<img onerror=bad>'),
    'The existing status must render errors as text rather than injected markup');
});
test('comparison failure remains an error rather than replacing a missing result with zero',async()=>{
  const h=harness();await settle();h.state.comparisonHook=async(payload,normal)=>payload.truth_id===TRUTHS.CU02
    ?failure('CU02 comparison deliberately failed'):normal();
  await h.choose();await settle();
  assert.equal(h.posts('/api/development/m01/compare').length,2);
  assert.ok(h.element('#comparison-result').innerHTML.includes('55.00%'));
  assert.ok(/일부|오류/.test(h.element('#comparison-status').textContent));
  assert.ok(h.element('#comparison-status').textContent.includes('CU02 comparison deliberately failed'));
});
test('all candidate failures clear the representative and keep both errors visible',async()=>{
  const h=harness();await settle();h.state.registrationHook=async preset=>failure(preset.business_unit_id+' expected failure');
  await h.choose();await settle();
  assert.equal(h.posts('/api/development/m01/compare').length,0);
  assert.ok(h.element('#comparison-status').textContent.includes('BU14 expected failure'));
  assert.ok(h.element('#comparison-status').textContent.includes('CU02 expected failure'));
  assert.ok(!h.element('#comparison-result').innerHTML.includes('large-score">0.00%'));
  assert.ok(!h.urls.at(-1)?.includes('comparison_id='));
  assert.equal(h.element('#m01-open-upload').disabled,false);
});
test('malformed candidate measurements remain visible and cannot win',async()=>{
  for(const value of [NaN,null,'99']){
    const h=harness();await settle();h.state.comparisonHook=async(payload,normal)=>{
      const reply=await normal();if(payload.truth_id!==TRUTHS.CU02)return reply;
      const body=await reply.json();body.measurement.collection_accuracy=value;return response(body);
    };
    await h.choose();await settle();
    assert.ok(h.element('#comparison-result').innerHTML.includes('55.00%'));
    assert.ok(!h.html().includes('NaN%')&&!h.html().includes('Infinity%'));
    assert.ok(/일부|오류/.test(h.element('#comparison-status').textContent));
  }
});
test('selected sessions including a blank session are copied identically to both comparisons',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  for(const session of ['s1','']){
    h.element('#csv-session').value=session;await h.element('#csv-session').listeners.change();await settle();
    const pair=h.posts('/api/development/m01/compare').slice(-2).map(c=>JSON.parse(c.options.body));
    assert.equal(pair.length,2);assert.ok(pair.every(p=>p.dataset_id===DATASET&&p.session_id===session));
    assert.deepEqual(pair.map(p=>p.truth_id),[TRUTHS.BU14,TRUTHS.CU02]);
  }
});
test('a superseded registration does not launch any comparison for the old dataset',async()=>{
  const h=harness();await settle();const gate=deferred();let registrations=0;
  h.state.registrationHook=async preset=>++registrations===1?gate.promise:response(h.truthFor(preset));
  const old=h.choose();await settle();await h.choose('new.csv');await settle();
  gate.resolve(response(h.truthFor(h.presets[0])));await old;await settle();
  const payloads=h.posts('/api/development/m01/compare').map(c=>JSON.parse(c.options.body));
  assert.equal(payloads.length,2);assert.ok(payloads.every(p=>p.dataset_id===SECOND));
});
test('a late second candidate cannot overwrite a newer upload or change its winning truth',async()=>{
  const h=harness();await settle();const gate=deferred();let oldResponse;
  h.state.comparisonHook=async(payload,normal)=>{
    const reply=await normal();if(payload.dataset_id===DATASET&&payload.truth_id===TRUTHS.CU02){oldResponse=reply;return gate.promise;}return reply;
  };
  const old=h.choose();await settle();assert.ok(oldResponse);
  h.state.matches={BU14:10,CU02:0};await h.choose('new.csv');await settle();
  assert.ok(h.element('#comparison-result').innerHTML.includes('95.00%'));
  const latest=h.element('#comparison-result').innerHTML,winner=vm.runInContext('m01TruthReport.truth.truth_id',h.context);
  gate.resolve(oldResponse);await old;await settle();
  assert.equal(h.element('#comparison-result').innerHTML,latest);
  assert.equal(vm.runInContext('m01TruthReport.truth.truth_id',h.context),winner);
  assert.equal(winner,TRUTHS.BU14);
});
test('changing sessions during registration invalidates the old scope before comparisons',async()=>{
  const h=harness();await settle();const gate=deferred();let registrations=0;
  h.state.registrationHook=async preset=>++registrations===1?gate.promise:response(h.truthFor(preset));
  const old=h.choose();await settle();h.element('#csv-session').value='s1';
  await h.element('#csv-session').listeners.change();await settle();
  gate.resolve(response(h.truthFor(h.presets[0])));await old;await settle();
  const payloads=h.posts('/api/development/m01/compare').map(c=>JSON.parse(c.options.body));
  assert.equal(payloads.length,2);assert.ok(payloads.every(p=>p.session_id==='s1'));
});
test('a late verification cannot relabel the newer winning comparison',async()=>{
  const h=harness();await settle();const gate=deferred();let checks=0;
  h.state.verificationHook=async(_id,result)=>++checks===1?gate.promise:response({verified:true,status:'VERIFIED',recalculated:result.measurement});
  await h.choose();await settle();h.state.matches={BU14:10,CU02:0};await h.choose();await settle();
  const text=h.element('#comparison-verification').textContent;
  gate.resolve(response({verified:true,status:'VERIFIED',recalculated:{collection_accuracy:1}}));await settle();
  assert.equal(h.element('#comparison-verification').textContent,text);
  assert.ok(!h.element('#comparison-verification').textContent.includes('1.00%'));
});
test('file picker cancellation and diagnostics mapping do not register extra candidates',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  const count=h.calls.length,html=h.element('#comparison-result').innerHTML;
  h.element('#csv-file').files=[];await h.element('#csv-file').listeners.change();await settle();
  assert.equal(h.calls.length,count);assert.equal(h.element('#comparison-result').innerHTML,html);
  h.element('#csv-target-mapping').checked=true;await h.element('#csv-target-mapping').listeners.change();await settle();
  assert.equal(h.posts('/api/development/m01/ground-truths').length,2);
  assert.equal(h.posts('/api/development/m01/compare').length,2);
  assert.equal(h.element('#comparison-result').innerHTML,html);
});
test('the first candidate is not published while the second candidate is still pending',async()=>{
  const h=harness();await settle();const gate=deferred();let delayed;
  h.state.comparisonHook=async(payload,normal)=>{
    const reply=await normal();if(payload.truth_id===TRUTHS.CU02){delayed=reply;return gate.promise;}return reply;
  };
  const pending=h.choose();await settle();assert.ok(delayed);
  assert.ok(!h.element('#comparison-result').innerHTML.includes('55.00%'));
  assert.equal(vm.runInContext('m01TruthReport',h.context),null);
  gate.resolve(delayed);await pending;await settle();
  assert.ok(h.element('#comparison-result').innerHTML.includes('82.50%'));
});
test('a candidate response for a different dataset, truth or session is exposed as an error',async()=>{
  for(const [field,value]of [['dataset_id',SECOND],['truth_id',TRUTHS.BU14],['session_id','different-session']]){
    const h=harness();await settle();h.state.comparisonHook=async(payload,normal)=>{
      const reply=await normal();if(payload.truth_id!==TRUTHS.CU02)return reply;
      const body=await reply.json();body[field]=value;return response(body);
    };
    await h.choose();await settle();
    assert.equal(vm.runInContext('m01TruthReport.truth.truth_id',h.context),TRUTHS.BU14,field);
    assert.ok(h.element('#comparison-result').innerHTML.includes('55.00%'),field);
    assert.ok(/일부|오류/.test(h.element('#comparison-status').textContent),field);
  }
});
test('restoring a stored comparison preserves its single-criterion meaning without new posts',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  const saved=[...h.comparisons.values()].find(r=>r.truth_id===TRUTHS.BU14);
  const postsBefore=h.calls.filter(c=>c.options?.method==='POST').length;
  await vm.runInContext(`restoreM01Comparison(${JSON.stringify(saved.comparison_id)})`,h.context);await settle();
  assert.equal(h.calls.filter(c=>c.options?.method==='POST').length,postsBefore);
  assert.ok(h.element('#comparison-status').textContent.includes('단일 기준'));
  assert.ok(h.element('#comparison-result').innerHTML.includes('55.00%'));
  assert.equal(vm.runInContext('m01TruthReport.truth.truth_id',h.context),TRUTHS.BU14);
});
test('restoring a result invalidates an unfinished candidate run and its delayed response',async()=>{
  const h=harness();await settle();const gate=deferred();let delayed;
  h.state.comparisonHook=async(payload,normal)=>{
    const reply=await normal();if(payload.truth_id===TRUTHS.CU02){delayed=reply;return gate.promise;}return reply;
  };
  const pending=h.choose();await settle();assert.ok(delayed);
  const saved=[...h.comparisons.values()].find(r=>r.truth_id===TRUTHS.BU14);
  await vm.runInContext(`restoreM01Comparison(${JSON.stringify(saved.comparison_id)})`,h.context);await settle();
  const html=h.element('#comparison-result').innerHTML;
  gate.resolve(delayed);await pending;await settle();
  assert.equal(h.element('#comparison-result').innerHTML,html);
  assert.ok(h.element('#comparison-status').textContent.includes('단일 기준'));
  assert.equal(vm.runInContext('m01TruthReport.truth.truth_id',h.context),TRUTHS.BU14);
});
test('replay source stores only confirmed comparison and server IDs after both candidates complete',async()=>{
  const h=harness();await settle();
  assert.equal(h.storage.has(REPLAY_KEY),false);await h.choose();await settle();
  const saved=JSON.parse(h.storage.get(REPLAY_KEY));
  assert.deepEqual(Object.keys(saved).sort(),['comparison_id','server_session_id']);
  assert.equal(saved.server_session_id,SERVER_SESSION);
  assert.equal(h.comparisons.get(saved.comparison_id).truth_id,TRUTHS.CU02);
});
test('pending second comparison never publishes a replay source and late old results cannot overwrite a newer source',async()=>{
  const h=harness();await settle();const gate=deferred(),entered=deferred();let lateReply;
  h.state.comparisonHook=(payload,normal)=>{
    if(payload.truth_id!==TRUTHS.CU02)return normal();
    lateReply=normal();entered.resolve();return gate.promise;
  };
  const old=h.choose();await entered.promise;
  assert.equal(h.storage.has(REPLAY_KEY),false);
  h.state.comparisonHook=null;await h.choose('new.csv');await settle();
  const confirmed=h.storage.get(REPLAY_KEY);assert.ok(confirmed);
  assert.equal(h.comparisons.get(JSON.parse(confirmed).comparison_id).dataset_id,SECOND);
  gate.resolve(lateReply);await old;await settle();assert.equal(h.storage.get(REPLAY_KEY),confirmed);
});
test('selection change clears replay source immediately and failed new upload leaves no stale source',async()=>{
  const h=harness();await settle();await h.choose();await settle();assert.ok(h.storage.has(REPLAY_KEY));
  h.element('#csv-session').value='s1';
  const changed=h.element('#csv-session').listeners.change();assert.equal(h.storage.has(REPLAY_KEY),false);
  await changed;await settle();assert.ok(h.storage.has(REPLAY_KEY));
  h.state.uploadReplyHook=()=>failure('synthetic upload failure');
  const upload=h.choose('failure.csv');assert.equal(h.storage.has(REPLAY_KEY),false);
  await upload;await settle();assert.equal(h.storage.has(REPLAY_KEY),false);
});
test('partial candidate failure keeps its normal result display but clears replay source',async()=>{
  const h=harness();await settle();await h.choose();await settle();assert.ok(h.storage.has(REPLAY_KEY));
  h.state.comparisonHook=(payload,normal)=>payload.truth_id===TRUTHS.CU02?failure('synthetic candidate failure'):normal();
  await vm.runInContext('evaluateM01Csv()',h.context);await settle();
  assert.equal(h.storage.has(REPLAY_KEY),false);
  assert.ok(h.element('#comparison-status').textContent.includes('일부 평가'));
});
test('successful stored comparison restoration replaces replay source; failed restoration clears it',async()=>{
  const h=harness();await settle();await h.choose();await settle();
  const saved=[...h.comparisons.values()].find(row=>row.truth_id===TRUTHS.BU14);
  await vm.runInContext('restoreM01Comparison('+JSON.stringify(saved.comparison_id)+')',h.context);await settle();
  assert.equal(JSON.parse(h.storage.get(REPLAY_KEY)).comparison_id,saved.comparison_id);
  await vm.runInContext('restoreM01Comparison('+JSON.stringify('f'.repeat(32))+')',h.context);await settle();
  assert.equal(h.storage.has(REPLAY_KEY),false);
});
test('malformed IDs extra fields and a different catalog session are rejected from replay storage',async()=>{
  const h=harness();await settle();
  for(const saved of [{comparison_id:['a'.repeat(32)],server_session_id:SERVER_SESSION},
    {comparison_id:'invalid',server_session_id:SERVER_SESSION},
    {comparison_id:'a'.repeat(32),server_session_id:'SERVER-'+'8'.repeat(32)},
    {comparison_id:'a'.repeat(32),server_session_id:SERVER_SESSION,events:[]}]) {
    h.storage.set(REPLAY_KEY,JSON.stringify(saved));vm.runInContext('m01ValidateReplaySource()',h.context);
    assert.equal(h.storage.has(REPLAY_KEY),false);
  }
  await h.choose();await settle();assert.ok(h.storage.has(REPLAY_KEY));
  vm.runInContext('load=async()=>{}',h.context);
  assert.throws(()=>vm.runInContext("ktlCheckServerSession({headers:{get:()=> 'SERVER-'+'8'.repeat(32)}},{},catalog.server_session_id)",h.context),/서버 세션/);
  assert.equal(h.storage.has(REPLAY_KEY),false);await settle();
});
test('blocked replay storage does not fail a valid M01 comparison',async()=>{
  const h=harness();await settle();
  vm.runInContext("sessionStorage.setItem=()=>{throw new Error('blocked storage')};sessionStorage.removeItem=()=>{throw new Error('blocked storage')}",h.context);
  await h.choose();await settle();assert.equal(h.element('#comparison-status').textContent,'비교 완료 · 정답별 실제 이벤트 ID와 판정 사유를 확인하세요.');
});
test('the original M01 screen structure is preserved without ranking or candidate additions',async()=>{
  const h=harness();await settle();
  const html=h.element('#app').innerHTML;
  const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
  // The optional scenario-name subtitle is removed; the original controls remain.
  const originalIds=['m01-input-panel','m01-dataset-name','m01-event-count','m01-ready-status','m01-open-upload',
    'csv-file','csv-status','m01-input-cards','comparison-selection','m01-diagnostics-card','m01-csv-options',
    'csv-dataset','csv-session','csv-target-mapping','csv-diagnostics','m01-prod-card','prod-status','prod-search',
    'prod-from','prod-to','prod-session','prod-event','prod-query','prod-logs','comparison-status','m01-result-panel','comparison-result'];
  assert.deepEqual(ids,originalIds);
  assert.equal(html.includes('m01-scenario-label'),false);
  assert.deepEqual([...html.matchAll(/<h2>(.*?)<\/h2>/g)].map(match=>match[1]),
    ['입력 및 현재 준비 상태','CSV 진단 및 수집 이벤트 로그','PROD 수집 로그 조회','Development Result']);
  assert.equal(vm.runInContext('typeof renderM01CandidateResults',h.context),'undefined');
  assert.ok(!source.includes('m01-candidate-results'),'No candidate DOM remains in the source');
  const start=source.indexOf('function renderM01ComparisonResult('),end=source.indexOf('async function loadM01Verification',start);
  assert.ok(start>=0&&end>start);
  assert.equal(createHash('sha256').update(source.slice(start,end).replace(/\r\n/g,'\n').trim()).digest('hex'),
    '4d192de9418d062562d68eda3900d387ef50dae6b99164fe135125b5a2f21188',
    'The original result renderer and its markup stay unchanged');
  await h.choose();await settle();
  assert.ok(!/최고점|대표|후보|사후 비교|CU02 기준의 적용 범위|개별 결과 보기/.test(h.html()),
    'Internal comparison does not add ranking terminology, panels, links or scope blocks');
  assert.equal(h.element('#comparison-status').textContent,'비교 완료 · 정답별 실제 이벤트 ID와 판정 사유를 확인하세요.');
  assert.equal(source.includes('#m01-scenario-label'),false);
  for(const id of ['collection-accuracy','comparison-match-rate','comparison-field-missing','comparison-type-coverage']){
    assert.ok(h.element('#comparison-result').innerHTML.includes(`id="${id}"`),id);
  }
});

(async()=>{
  let count=0;
  for(const {name,run} of tests){await run();count++;console.log('PASS '+name);}
  console.log(`${count}/${tests.length} M01 candidate regression groups passed (synthetic VM only; HTTP/browser/model calls 0)`);
})().catch(error=>{console.error(error);process.exitCode=1;});
