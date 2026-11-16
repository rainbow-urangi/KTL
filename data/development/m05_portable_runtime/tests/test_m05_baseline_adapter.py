import copy
import json
import random
import unittest
from pathlib import Path
from backend.m05_baseline_adapter import load_rules, predict

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'evaluation_contracts/development/m05_baseline_adapter_candidate/rules.json'

class M05BaselineAdapterTests(unittest.TestCase):
    def setUp(self): self.rules, _ = load_rules(CONFIG)
    def events(self, activities):
        return [{'id':str(i),'features':{'case_id':'case','activity':a,'ts':None}} for i,a in enumerate(activities)]
    def test_rules_and_link(self):
        p=predict(self.events(['A','API:POST_/Chk/sessionchk_2xx','A',None,'B','B','A']),self.rules)['predictions']
        self.assertEqual([x['label'] for x in p],['KEEP','REMOVE','REMOVE','REMOVE','KEEP','REMOVE','KEEP'])
        self.assertEqual(p[2]['duplicate_of_event_id'],'0')
        self.assertEqual(p[5]['duplicate_of_event_id'],'4')
        self.assertEqual(p[1]['remove_reason'],'drop_exact')
    def test_prefix_empty(self):
        p=predict(self.events(['','API:GET_/static/a_2xx','API:GET_/resources/a_2xx','API:GET_/favicon.ico_2xx','EVT:unknown']),self.rules)['predictions']
        self.assertEqual([x['label'] for x in p],['REMOVE']*4+['KEEP'])
    def test_case_isolation_and_order(self):
        e=self.events(['A','A','B']);e[1]['features']['case_id']='other'
        e[0]['features']['ts']='2026-01-01T00:00:02';e[2]['features']['ts']='2026-01-01T00:00:01'
        before=copy.deepcopy(e);p=predict(e,self.rules)
        self.assertEqual(e,before);self.assertEqual([x['id'] for x in p['predictions']],['0','1','2'])
        self.assertEqual([x['label'] for x in p['predictions']],['KEEP']*3)
    def test_invalid_and_gt_rejected(self):
        for mutate in (lambda e:e.append(e[0]),lambda e:e[0]['features'].update(expected_label='KEEP'),lambda e:e[0]['features'].pop('case_id')):
            e=self.events(['A']);mutate(e)
            with self.assertRaises(ValueError):predict(e,self.rules)
    def test_generated_sequences_exact_equivalence(self):
        rng=random.Random(17)
        for _ in range(200):
            e=self.events([rng.choice(['A','B',None,'','API:POST_/Chk/sessionchk_2xx','API:GET_/static/x_2xx']) for _ in range(rng.randrange(1,100))])
            rows=[dict(x['features'],source_event_pk=x['id']) for x in e]
            expected=[r['source_event_pk'] for r in self.rules['rle_dedupe_rows'](rows)]
            result=predict(e,self.rules)
            self.assertEqual(expected,[p['id'] for p in result['predictions'] if p['label']=='KEEP'])
            self.assertEqual(result,predict(e,self.rules))
    def test_no_min_length_or_truncation(self):
        self.assertEqual(len(predict(self.events(['A']),self.rules)['predictions']),1)
        self.assertEqual(len(predict(self.events(['A','B']*200),self.rules)['predictions']),400)
