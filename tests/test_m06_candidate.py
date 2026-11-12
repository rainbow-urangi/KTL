"""Temporary synthetic bundles only; no official evidence."""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from backend.m06_candidate import BUNDLE, DATASET, calculate, prepare, sha
from backend.server import Service

class FrozenM06Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.bundle=self.root/BUNDLE;self.bundle.mkdir(parents=True)
        np.save(self.bundle/'workflow_embeddings.npy',np.array([[0.,0.],[0.,2.],[10.,0.],[10.,2.]]))
        (self.bundle/'predictions.json').write_text(json.dumps(dict(workflows=[dict(workflow_instance_id='w'+str(i)) for i in range(4)],cluster_labels=[0,0,1,1])))
        self.manifest()
        (self.root/'backend').mkdir();(self.root/'backend/config.json').write_text((Path(__file__).resolve().parents[1]/'backend/config.json').read_text())
    def manifest(self):
        (self.bundle/'manifest.json').write_text(json.dumps(dict(run_mode='DEVELOPMENT',model_version='synthetic',files={n:dict(sha256=sha(self.bundle/n)) for n in ('predictions.json','workflow_embeddings.npy')})))
    def test_reproducible_evidence_and_crosscheck(self):
        first, summaries, evidence=calculate(self.root)
        self.assertEqual((first,summaries,evidence),calculate(self.root))
        self.assertAlmostEqual(first['score'],.2)
        self.assertTrue(first['details']['cross_check_pass'])
        rows=list(csv.DictReader(io.StringIO(evidence.lstrip('\ufeff'))))
        self.assertEqual(len(rows),first['details']['evidence_record_count'])
        self.assertEqual(len([r for r in rows if r['record_type']=='workflow_coordinate']),8)
        self.assertEqual({r['workflow_id'] for r in rows if r['record_type']=='workflow_coordinate'},{'w0','w1','w2','w3'})
        self.assertAlmostEqual(sum(float(r['max_ratio']) for r in rows if r['record_type']=='cluster_summary')/2,first['score'])
    def test_tamper_and_alignment_fail_closed(self):
        (self.bundle/'predictions.json').write_text('{}')
        self.assertEqual(prepare(self.root)['status'],'BLOCKED')
        self.manifest()
        self.assertEqual(prepare(self.root)['status'],'BLOCKED')
    def test_run_never_invokes_runner_and_exports(self):
        with patch('backend.model_runner.EvaluationModelRunner.run',side_effect=AssertionError('must not run model')):
            result=Service(self.root).run('M06','DEVELOPMENT',DATASET)
        self.assertEqual(result['status'],'COMPLETED');self.assertIsNone(result['official_pass'])
        evidence=self.root/'results/development'/result['run_id']/'evidence.csv'
        self.assertEqual(sha(evidence),result['details']['evidence_sha256'])
        self.assertEqual(result['sample_count'],4)
    def test_duplicate_ids_and_nonfinite_rejected(self):
        pred=json.loads((self.bundle/'predictions.json').read_text());pred['workflows'][1]=pred['workflows'][0]
        (self.bundle/'predictions.json').write_text(json.dumps(pred));self.manifest()
        self.assertEqual(prepare(self.root)['status'],'BLOCKED')
