from __future__ import annotations
import json
import unittest
from pathlib import Path
from public_ai_capacity.capacity_signal.capacity_pressure import capacity_pressure, peer_distribution

class Record:
    def __init__(self,payload): self.payload=payload

class DomainSignalTests(unittest.TestCase):
    def setUp(self):
        fixture=json.loads((Path(__file__).resolve().parents[2]/'fixtures'/'acceptance.json').read_text(encoding='utf-8'))
        self.payload=fixture['records'][0]['payload']
    def test_signal_is_bounded_and_explainable(self):
        signal=capacity_pressure(self.payload)
        self.assertGreaterEqual(signal.score,0.0); self.assertLessEqual(signal.score,1.0)
        self.assertIn(signal.severity,{'info','warning','critical'}); self.assertTrue(signal.evidence)
    def test_peer_distribution_tracks_records(self):
        other=dict(self.payload); other['region_code']='group-b'
        result=peer_distribution([Record(self.payload),Record(other)])
        self.assertEqual(result['count'],2)
    def test_input_change_is_observable(self):
        base=capacity_pressure(self.payload); changed=dict(self.payload)
        changed['error_rate']=1
        changed_signal=capacity_pressure(changed)
        self.assertTrue(base.score != changed_signal.score or base.severity != changed_signal.severity)

    def test_zero_units_is_unavailable_not_saturated(self):
        empty=dict(self.payload); empty['capacity_units']=0; empty['request_queue']=0
        signal=capacity_pressure(empty)
        self.assertFalse(signal.evidence['allocatable'])
        self.assertIsNone(signal.evidence['saturation'])
        self.assertEqual(signal.evidence['capacity_state'],'unavailable')
        self.assertEqual(signal.severity,'critical')
        saturated=dict(self.payload); saturated['capacity_units']=1; saturated['request_queue']=10**6
        self.assertEqual(capacity_pressure(saturated).evidence['capacity_state'],'overloaded')
        self.assertTrue(capacity_pressure(saturated).evidence['allocatable'])

if __name__=='__main__': unittest.main()
