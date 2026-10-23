"""Exercise the real small-packet path and explicit unsupported sweep rows."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scaling_campaign


class ScalingCampaignTests(unittest.TestCase):
    def test_current_producer_packet_and_current_checker_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary)/'sweep'
            summary=scaling_campaign.run(out,relations=(4,),templates=(4,),shapes=('path',))
            self.assertEqual((1,1,0),(summary['cases'],summary['accepted'],summary['unsupported']))
            certificate=json.loads(next((out/'certificates').glob('*.json')).read_text())
            self.assertIsInstance(certificate,dict)
            self.assertIn('states',certificate)
            self.assertIn('No exhaustive oracle',summary['oracle_boundary'])
            with self.assertRaises(FileExistsError):
                scaling_campaign.run(out,relations=(4,),shapes=('path',))

    def test_unsupported_size_never_launches_producer(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch('scaling_campaign.optimizer.optimize',side_effect=AssertionError('must not run')):
            out=Path(temporary)/'unsupported'
            summary=scaling_campaign.run(out,relations=(10,),shapes=('path',))
            self.assertEqual((1,0,1),(summary['cases'],summary['accepted'],summary['unsupported']))
            self.assertIsNone(summary['max_accepted_relations'])
            self.assertEqual([],list((out/'certificates').iterdir()))

    def test_false_verdict_is_not_the_truthiness_of_a_dictionary(self):
        with tempfile.TemporaryDirectory() as temporary, \
             patch('scaling_campaign.checker.verify',return_value={'accepted':False}):
            with self.assertRaisesRegex(RuntimeError,'checker rejected'):
                scaling_campaign.run(Path(temporary)/'bad',relations=(4,),shapes=('path',))

    def test_invalid_dimensions_reject_without_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary)/'absent'
            for kwargs in (dict(relations=(True,)),dict(relations=(4,4)),dict(templates=(1,)),dict(shapes=('typo',))):
                with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                    scaling_campaign.run(out,**kwargs)
            self.assertFalse(out.exists())


if __name__=='__main__':
    unittest.main()
