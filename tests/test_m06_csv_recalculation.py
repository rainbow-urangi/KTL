import csv
import tempfile
import unittest
from pathlib import Path
from scripts.recalculate_m06_csv import recalculate

class CSVRecalculationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'evidence.csv'
        self.rows = []
        for i, vector in enumerate(((0,0),(0,2),(10,0),(10,2))):
            for d, value in enumerate(vector):
                self.rows.append(dict(record_type='workflow_coordinate',row_index=i,workflow_id='w'+str(i),cluster=i//2,dimension=d,value=value))
        self.rows += [dict(record_type='cluster_summary',cluster=k,max_ratio=.2) for k in (0,1)]
    def write(self):
        with self.path.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['record_type','row_index','workflow_id','cluster','dimension','value','max_ratio']);writer.writeheader();writer.writerows(self.rows)
    def test_recalculate(self):
        self.write(); result=recalculate(self.path)
        self.assertAlmostEqual(result['sklearn_dbi'],.2);self.assertIsNone(result['official_pass'])
    def test_duplicate_rejected(self):
        self.rows.append(self.rows[0]);self.write()
        with self.assertRaisesRegex(ValueError,'Duplicate coordinate'): recalculate(self.path)
    def test_missing_dimension_rejected(self):
        self.rows.pop(2);self.write()
        with self.assertRaisesRegex(ValueError,'dimensions'): recalculate(self.path)
    def test_bad_summary_rejected(self):
        self.rows[-1]['max_ratio']=.8;self.write()
        with self.assertRaisesRegex(ValueError,'mismatch'): recalculate(self.path)
