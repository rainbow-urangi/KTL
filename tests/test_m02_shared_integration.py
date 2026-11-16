"""Synthetic shared routing guards; no actual metric evaluation."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backend import m02_candidate,m02_integrated_candidate as candidate
from backend.evaluators import EvaluationError
class SharedIntegrationTests(unittest.TestCase):
 def test_new_candidate_dispatch(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/candidate.SNAPSHOT;p.mkdir(parents=True);(p/'manifest.json').write_text('{}')
   with patch.object(candidate,'assess',return_value=('sentinel',[])):
    self.assertEqual(m02_candidate.assess(root),('sentinel',[]))
 def test_pending_never_persists(self):
  with patch.object(candidate,'assess',return_value=({'status':'NOT_CONFIGURED'},[])),patch('backend.run_storage.save_run') as save:
   with self.assertRaises(EvaluationError):candidate.run(Path('/tmp'),{})
   save.assert_not_called()
 def test_inventory_detects_new_runtime_file(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'backend').mkdir();(root/'frontend').mkdir()
   a=candidate.runtime_inventory(root);(root/'backend/new.py').write_text('')
   self.assertNotEqual(a,candidate.runtime_inventory(root))
