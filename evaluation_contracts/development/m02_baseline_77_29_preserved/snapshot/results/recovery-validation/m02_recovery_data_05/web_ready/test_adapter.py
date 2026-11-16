import unittest,importlib.util,hashlib,json
from pathlib import Path
p=Path(__file__).with_name('server.py');s=importlib.util.spec_from_file_location('adapter',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class AdapterTest(unittest.TestCase):
 def test_frozen_and_provenance(self):self.assertTrue(m.verify())
 def test_exact_cohort_and_formula(self):
  r=m.measure();self.assertEqual(r['execution_count'],5);self.assertEqual(r['overall']['generated'],31);self.assertEqual(r['overall']['matched'],20);self.assertEqual(r['overall']['satisfied'],25);self.assertAlmostEqual(r['overall']['score'],77.28981596002805);self.assertIsNone(r['official_pass'])
 def test_evidence(self):self.assertEqual(m.measure()['evidence_sha256'],hashlib.sha256((m.OUT/'evidence.csv').read_bytes()).hexdigest())
 def test_repeated_runs_do_not_write_artifacts(self):
  before={p.name:m.sha(p) for p in m.OUT.iterdir() if p.is_file()};m.measure();self.assertEqual(before,{p.name:m.sha(p) for p in m.OUT.iterdir() if p.is_file()})
if __name__=='__main__':unittest.main()
