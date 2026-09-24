"""Deterministic semantic and rejection tests; no claim of exhaustive program verification."""
from __future__ import annotations
import copy,itertools,json,tempfile,unittest
from pathlib import Path
from checker import verify,load,Rejected
from src.generate import make
from src.model import support
from src.optimizer import optimize

class SupportTests(unittest.TestCase):
    def test_exhaustive_bounded_mass(self):
        # All dimensions 1..3, coordinate intervals 0<=l<=u<=2, all feasible totals,
        # and all integer directions in {-2,-1,0,1,2}^K. Includes B=0, fixed boxes,
        # negative directions, ties, nonzero lower bounds and empty-cap coordinates.
        count=0
        for k in range(1,4):
            for bounds in itertools.product([(l,u) for l in range(3) for u in range(l,3)],repeat=k):
                lo=[p[0] for p in bounds];hi=[p[1] for p in bounds]
                for N in range(sum(lo),sum(hi)+1):
                    worlds=[w for w in itertools.product(*(range(l,u+1) for l,u in bounds)) if sum(w)==N]
                    for d in itertools.product(range(-2,3),repeat=k):
                        val,w,t=support(d,lo,hi,N)
                        exact=max(sum(a*b for a,b in zip(d,x)) for x in worlds)
                        dual=sum(a*b for a,b in zip(d,lo))+t*(N-sum(lo))+sum((u-l)*max(a-t,0) for a,l,u in zip(d,lo,hi))
                        self.assertEqual(val,exact);self.assertEqual(val,dual)
                        self.assertEqual(sum(w),N);self.assertTrue(all(l<=x<=u for x,l,u in zip(w,lo,hi)))
                        count+=1
        self.assertEqual(count,83150)

class PacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.instance=make(6,'star',4,'balanced',1)
        cls.packet=optimize(cls.instance)[0]
        cls.root=str((1<<cls.instance['n'])-1)
    def reject(self,change,instance_change=None):
        p=copy.deepcopy(self.packet);i=copy.deepcopy(self.instance)
        change(p)
        if instance_change:instance_change(i)
        with self.assertRaises((Rejected,KeyError,TypeError,ValueError,IndexError,RecursionError)):
            verify(i,p)
    def test_valid(self):self.assertEqual(verify(self.instance,self.packet)['regret'],36)
    def test_missing_containment(self):self.reject(lambda p:p['containment'].pop('1'))
    def test_wrong_containment_lower(self):self.reject(lambda p:p['containment']['1'].__setitem__('lower',0))
    def test_wrong_containment_upper(self):self.reject(lambda p:p['containment']['1'].__setitem__('upper',999))
    def test_missing_state(self):self.reject(lambda p:p['states'].pop('3'))
    def test_missing_coverage(self):self.reject(lambda p:p['states'][self.root]['coverage'].pop())
    def test_duplicate_coverage(self):self.reject(lambda p:p['states'][self.root]['coverage'].append(p['states'][self.root]['coverage'][0]))
    def test_invalid_dominator(self):self.reject(lambda p:p['states'][self.root]['coverage'][0].__setitem__(4,999))
    def test_invalid_threshold(self):self.reject(lambda p:p['states'][self.root]['coverage'][0].__setitem__(5,10**9))
    def test_repeated_leaf(self):self.reject(lambda p:p['states']['3']['plans'].__setitem__(0,[0,0]))
    def test_cartesian_plan(self):self.reject(lambda p:p['states'][self.root]['plans'].__setitem__(0,[[1,2],[0,[3,[4,5]]]]))
    def test_wrong_state_plan(self):self.reject(lambda p:p['states']['3']['plans'].__setitem__(0,0))
    def test_duplicate_frontier_plan(self):self.reject(lambda p:p['states'][self.root]['plans'].append(p['states'][self.root]['plans'][0]))
    def test_missing_upper(self):self.reject(lambda p:p['upper_thresholds'].pop())
    def test_bad_upper(self):self.reject(lambda p:p['upper_thresholds'].__setitem__(0,10**9))
    def test_missing_lower(self):self.reject(lambda p:p['lower_witnesses'].pop())
    def test_bad_lower_rival(self):self.reject(lambda p:p['lower_witnesses'][0].__setitem__('rival',999))
    def test_bad_lower_world(self):self.reject(lambda p:p['lower_witnesses'][0]['world'].__setitem__(0,999))
    def test_false_lower_witness(self):self.reject(lambda p:p['lower_witnesses'][0].__setitem__('rival',0))
    def test_smaller_regret(self):self.reject(lambda p:p.__setitem__('regret',35))
    def test_larger_regret(self):self.reject(lambda p:p.__setitem__('regret',37))
    def test_bool_regret(self):self.reject(lambda p:p.__setitem__('regret',True))
    def test_float_regret(self):self.reject(lambda p:p.__setitem__('regret',36.0))
    def test_huge_regret(self):self.reject(lambda p:p.__setitem__('regret',1<<200))
    def test_bad_selected(self):self.reject(lambda p:p.__setitem__('selected',-1))
    def test_wrong_instance_name(self):self.reject(lambda p:p.__setitem__('instance','other'))
    def test_empty_contract(self):self.reject(lambda p:None,lambda i:i.__setitem__('total',31))
    def test_cycle_graph(self):self.reject(lambda p:None,lambda i:i['edges'].__setitem__(0,[1,2]))
    def test_wrong_key_schema(self):self.reject(lambda p:None,lambda i:i['blocks'][0][0][0].__setitem__('extra',0))
    def test_changed_template(self):self.reject(lambda p:None,lambda i:i['blocks'][0][0].pop())
    def test_top_level_array_json(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'x.json';f.write_text('[]')
            with self.assertRaises(Rejected):load(f)
    def test_extra_contract_field(self):
        self.reject(lambda p:None,lambda i:i.__setitem__('unexpected',0))
    def test_null_seed(self):
        self.reject(lambda p:None,lambda i:i.__setitem__('seed',None))
    def test_missing_contract_field(self):
        self.reject(lambda p:None,lambda i:i.pop('name'))
    def test_extra_certificate_field(self):
        self.reject(lambda p:p.__setitem__('unexpected',0))
    def test_extra_containment_field(self):
        self.reject(lambda p:p['containment']['1'].__setitem__('unexpected',0))
    def test_extra_state_field(self):
        self.reject(lambda p:p['states']['1'].__setitem__('unexpected',0))
    def test_extra_lower_witness_field(self):
        self.reject(lambda p:p['lower_witnesses'][0].__setitem__('unexpected',0))
    def test_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'x.json';f.write_text('{"a":1,"a":2}')
            with self.assertRaises(Rejected):load(f)

if __name__=='__main__':unittest.main()
