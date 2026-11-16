import csv,io,json,tempfile,unittest
from pathlib import Path
from backend.m05_heldout import *
class M05HeldOutTests(unittest.TestCase):
    def events(self):
        return [dict(event_id=str(i),expected_label='REMOVE' if i<10 else 'KEEP',remove_category='noise' if i<10 else '',held_out=True,features={'text':str(i)}) for i in range(20)]
    def predictions(self):return [dict(event_id=e['event_id'],predicted_label=e['expected_label']) for e in self.events()]
    def test_contract(self):self.assertEqual(len(check_events(self.events())),20)
    def test_invalid(self):
        for key,value in [('held_out',False),('event_id','1'),('expected_label','KEEP'),('remove_category','unknown')]:
            e=self.events();e[0][key]=value
            with self.assertRaises(EvaluationError):check_events(e)
        with self.assertRaises(EvaluationError):check_events(self.events()[:-1])
    def test_leakage(self):
        e=self.events();e[0]['features']['nested']={'expected_label':'REMOVE'}
        with self.assertRaises(EvaluationError):check_events(e)
    def test_confusion_csv_determinism(self):
        p=self.predictions();p[0]['predicted_label']='KEEP';p[10]['predicted_label']='REMOVE'
        a,rows=calculate(self.events(),p,{'model_version':'SYNTHETIC_TEST_ONLY','dataset_sha256':'fixture'})
        self.assertEqual([a[k] for k in ('TP','FP','FN','TN')],[9,1,1,9]);self.assertEqual(a['f1'],.9)
        self.assertEqual(a['precision'],.9);self.assertEqual(a['recall'],.9)
        out=list(csv.DictReader(io.StringIO(evidence_csv(rows))));c=Counter(r['classification'] for r in out)
        self.assertEqual(2*c['TP']/(2*c['TP']+c['FP']+c['FN']),a['f1'])
        self.assertEqual((a,rows),calculate(self.events(),p,{'model_version':'SYNTHETIC_TEST_ONLY','dataset_sha256':'fixture'}))
    def test_threshold(self):
        self.assertTrue(meets_target(.79));self.assertTrue(meets_target(.79001));self.assertFalse(meets_target(.78999))
    def test_predictions_rejected(self):
        with self.assertRaises(EvaluationError):calculate(self.events(),self.predictions()[:-1],{})
    def test_no_proof_no_score(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'data/held_out/events.json';p.parent.mkdir(parents=True);p.write_text(json.dumps({'events':self.events()}))
            manifest={'used_for_training':False,'used_for_development':False,'dataset':{'path':str(p.relative_to(root)),'sha256':sha(p)}}
            with self.assertRaises(EvaluationError):evaluate(root,manifest,{})
    def test_ui_contract(self):
        from backend.m05_readiness_web import PAGE
        for value in ('0.79','20건','BLOCKED','evidence CSV','stale'):self.assertIn(value,PAGE)
    def test_empty_history_and_empty_audit_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def write(name,obj):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj));return {'path':name,'sha256':sha(p)}
            dataset=write('data/held_out/events.json',{'events':self.events()})
            for history in ({'events':[]}, {'scope':'training','events':[{'event_id':'old','feature_sha256':'0'*64}]}):
                entry=write('history.json',history);audit=write('audit.json',{})
                m={'used_for_training':False,'used_for_development':False,'dataset':dataset,'provenance':{'reviewer':'test','reviewed_at':'2026-11-09','complete_history_attested':True,'training_inventories':[entry],'development_inventories':[entry],'audit_evidence':[audit]}}
                with self.assertRaises(EvaluationError):evaluate(root,m,{})
    def test_engine_argv_binding(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();cfg={'cleaning_model_version':'TEST','adapters':{}}
            for key in ('model_artifact','adapter_artifact','interpreter_artifact'):
                p=root/key;p.write_text(key);cfg[key]={'path':key,'sha256':sha(p)}
            args=[str(root/'interpreter_artifact'),str(root/'adapter_artifact'),'--model',str(root/'model_artifact')]
            cfg['adapters']['cleaning']=args;self.assertEqual(validate_engine(root,cfg),args)
            for bad in (['python','-c','print(1)'],args+['--extra'],[args[0],args[1],'--model','other']):
                cfg['adapters']['cleaning']=bad
                with self.assertRaises(EvaluationError):validate_engine(root,cfg)
    def test_source_reconciliation_and_independent_approval(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            def write(name,obj):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj));return {'path':name,'sha256':sha(p)}
            dataset=write('data/held_out/events.json',{'events':self.events()})
            raw=write('raw.json',{'events':[{'event_id':'old','features':{'old':True}}]})
            histories=[write(scope+'.json',{'scope':scope,'source_files':[raw],'events':[{'event_id':'old','feature_sha256':digest({'old':True})}]}) for scope in ('training','development')]
            hashes=[h['sha256'] for h in histories]
            audit_obj={'dataset_sha256':dataset['sha256'],'inventory_sha256':hashes,'method':'SOURCE_HISTORY_RECONCILIATION','findings':'Synthetic audit fixture only','coverage_complete':True}
            audit=write('audit.json',audit_obj)
            proof={'reviewer':'preparer','reviewed_at':'2026-11-09','complete_history_attested':True,'training_inventories':histories[:1],'development_inventories':histories[1:],'audit_evidence':[audit]}
            m={'used_for_training':False,'used_for_development':False,'dataset':dataset,'provenance':proof}
            with self.assertRaises(EvaluationError):validate_dataset(root,m)
            approval={'dataset_sha256':dataset['sha256'],'status':'PASS','reviewer':'independent','reviewed_at':'2026-11-09','inventory_sha256':hashes,'audit_sha256':[audit['sha256']]}
            write('evaluation_contracts/m05_approved_provenance.json',{'approvals':[approval]})
            self.assertEqual(len(validate_dataset(root,m)),20)
            proof['audit_evidence']=[write('empty.json',{})]
            with self.assertRaises(EvaluationError):validate_dataset(root,m)
            proof['audit_evidence']=[audit]
            raw_path=root/'raw.json';raw_path.write_text(json.dumps({'events':[{'event_id':'0','features':{'text':'0'}}]}))
            with self.assertRaises(EvaluationError):validate_dataset(root,m)
