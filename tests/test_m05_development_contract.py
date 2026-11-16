"""Synthetic labels/predictions only. Never runs the engine on real data."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.m05_development_contract import calculate_binary, policy_for, MODE
from backend.m05_full_context import csv_text
from backend.m05_full_context_csv import recalculate_csv
from backend.evaluators import EvaluationError

class DevelopmentContractTests(unittest.TestCase):
    def test_binary_unknown_heldout_no_category_quota(self):
        targets=[dict(event_id=str(i),expected_label='REMOVE' if i<10 else 'KEEP',remove_category='',held_out='') for i in range(20)]
        pred=[dict(event_id=str(i),predicted_label='REMOVE' if i<8 else 'KEEP') for i in range(20)]
        meta=dict(is_target=True,held_out='',run_mode='DEVELOPMENT',evaluation_eligibility=MODE,held_out_evidence_status='INSUFFICIENT_NOT_BLOCKING_FOR_THIS_DEVELOPMENT')
        result,rows=calculate_binary(targets,pred,meta)
        self.assertEqual((result['TP'],result['FP'],result['FN'],result['TN']),(8,0,2,10))
        check=recalculate_csv(csv_text(rows))
        for k,v in check.items():self.assertAlmostEqual(result[k],v)
        self.assertTrue(result['passed']); self.assertIsNone(result['official_pass'])
        self.assertTrue(all(t['held_out']=='' for t in targets))
        pred[0]['event_id']='1'
        with self.assertRaises(EvaluationError):calculate_binary(targets,pred,meta)

    def test_unauthorized_empty_heldout_rejected(self):
        targets=[dict(event_id=str(i),expected_label='REMOVE' if i<10 else 'KEEP',remove_category='noise' if i<10 else '') for i in range(20)]
        pred=[dict(event_id=str(i),predicted_label='KEEP') for i in range(20)]
        _,rows=calculate_binary(targets,pred,dict(is_target=True,held_out='',run_mode='DEVELOPMENT'))
        with self.assertRaises(ValueError):recalculate_csv(csv_text(rows))

    def test_policy_hash_bound_not_blanket_bypass(self):
        root=Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'data/held_out/m05/raw01_raw02_raw03_target20_20261111/manifest.json').read_text())
        self.assertEqual(policy_for(root,manifest)['eligibility'],MODE)
        changed=copy.deepcopy(manifest);changed['target_labels']['sha256']='0'*64
        with self.assertRaises(EvaluationError):policy_for(root,changed)
        changed['dataset_id']='other';self.assertIsNone(policy_for(root,changed))
