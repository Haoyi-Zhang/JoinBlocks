"""Fail-closed retained/fresh comparison tests, separate from science methods."""
import json,shutil,tempfile,unittest
from pathlib import Path
from invariance_campaign import run,compare

class InvarianceComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.retained=cls.root/'retained';run(cls.retained)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.fresh=self.root/'fresh'
        if self.fresh.exists():shutil.rmtree(self.fresh)
        shutil.copytree(self.retained,self.fresh)
    def test_same_directory_rejected(self):
        with self.assertRaisesRegex(ValueError,'distinct directories'):
            compare(self.retained,self.retained)
    def test_missing_input_rejected(self):
        next((self.fresh/'inputs').glob('*.json')).unlink()
        with self.assertRaisesRegex(RuntimeError,'asset inventory'):
            compare(self.retained,self.fresh)
    def test_altered_input_rejected(self):
        path=next((self.fresh/'inputs').glob('*.json'));obj=json.loads(path.read_text())
        obj['total']+=1;path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(RuntimeError,'evidence mismatch'):
            compare(self.retained,self.fresh)
    def test_altered_oracle_rejected(self):
        path=next((self.fresh/'oracles').glob('*.json'));obj=json.loads(path.read_text())
        obj['optimum']+=1;path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(RuntimeError,'evidence mismatch'):
            compare(self.retained,self.fresh)
