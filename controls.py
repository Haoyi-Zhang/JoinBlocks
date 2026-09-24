#!/usr/bin/env python3
"""Reproduce negative controls and contract edge cases, independently against SQLite."""
from __future__ import annotations
import argparse,itertools,json,os,resource,sqlite3,time
from pathlib import Path
from src.generate import make
from src.model import all_plans,plan_cost,block_profile,support,as_plan,execute_plan,instantiate
from src.optimizer import optimize
from src.oracle import oracle
from src.baselines import select_baselines
from src.sqlcheck import check_world
from checker import verify

def hedge_instance():
    # Six distinct central rows. Each leaf is a bag of two equal zero-valued rows.
    a={0,1,2};b={3,4,5};c={0,1,3};blocks=[]
    for zeros in [(a,b,c),(a,c,b)]:
        center=[{str(e):0 if r in zeros[e] else 1 for e in range(3)} for r in range(6)]
        blocks.append([center]+[[{str(e):0},{str(e):0}] for e in range(3)])
    return {'name':'pointwise-cover-counterexample','n':4,'edges':[[0,1],[0,2],[0,3]],
            'lower':[0,0],'upper':[1,1],'total':1,'blocks':blocks,
            'family':'star','regime':'hedging'}

def run(out):
    start=time.process_time();data={}
    con=sqlite3.connect(':memory:');con.executescript('CREATE TABLE R(a);CREATE TABLE S(a,b);CREATE TABLE T(b);INSERT INTO R VALUES(0);INSERT INTO T VALUES(0);')
    counts=[]
    for rows in [[(0,0),(1,1)],[(0,1),(1,0)]]:
        con.execute('DELETE FROM S');con.executemany('INSERT INTO S VALUES(?,?)',rows)
        counts.append([con.execute(q).fetchone()[0] for q in ['SELECT COUNT(*) FROM R','SELECT COUNT(*) FROM S','SELECT COUNT(*) FROM T','SELECT COUNT(*) FROM R JOIN S USING(a)','SELECT COUNT(*) FROM S JOIN T USING(b)','SELECT COUNT(*) FROM R JOIN S USING(a) JOIN T USING(b)']])
    con.close();assert counts==[[1,2,1,1,1,1],[1,2,1,1,1,0]]
    data['pairwise_indistinguishability']=counts
    i=make(6,'star',4,'balanced',1);c,st,h=optimize(i);o=oracle(i)
    base,extra=select_baselines(i,h,[p for p,v in o['plans']])
    r={name:o['regret_by_profile'][plan_cost(p,h)] for name,p in base.items()}
    assert verify(i,c)['regret']==o['optimum']==36 and r['local_regret']==44
    data['local_pruning']={'regret':36,'baselines':r,'plan':base['local_regret'],
                           'cost_profile':plan_cost(base['local_regret'],h),'oracle_worlds':len(o['worlds'])}
    for name,inst in [('local-pruning',i),('pointwise-cover',hedge_instance())]:
        cert,_,h=optimize(inst);o=oracle(inst);assert verify(inst,cert)['regret']==o['optimum']
        (out/(name+'-input.json')).write_text(json.dumps(inst,indent=2)+'\n')
        (out/(name+'-certificate.json')).write_text(json.dumps(cert,sort_keys=True,indent=2)+'\n')
        for w in o['worlds']:check_world(inst,w,[p for p,v in o['plans']])
        if name=='pointwise-cover':
            profiles=sorted(o['regret_by_profile']);assert profiles==[(6,14),(10,10),(14,6)]
            assert [o['regret_by_profile'][p] for p in profiles]==[8,4,8]
            # min(6t+14(1-t),14t+6(1-t))<=10 on the entire continuous interval;
            # checked as an algebraic inequality in the proof, sampled here only as regression.
            assert all(min(14-8*t/100,6+8*t/100)<=10 for t in range(101))
            data['pointwise_cover']={'cost_profiles':profiles,'regrets':[8,4,8],
                'optimum':4,'optimum_after_dropping_middle':8,'integer_worlds':o['worlds']}
    # N=0, nonzero lower bounds, singleton contract, varied N and K; exact oracle and checker.
    edges=[]
    for k in [1,2,3,4,6,8]:
        for mode in ['zero','fixed','mass']:
            z=make(4,'star',k,'balanced',701)
            z['lower']=([1]*k if mode=='fixed' else [0]*k)
            z['upper']=([1]*k if mode=='fixed' else [2]*k)
            z['total']=(0 if mode=='zero' else k)
            z['name']=f'edge-{k}-{mode}'
            cc,ss,hh=optimize(z);oo=oracle(z)
            assert verify(z,cc)['regret']==oo['optimum'] and hh==oo['h']
            edges.append({'k':k,'mode':mode,'regret':cc['regret'],'worlds':len(oo['worlds'])})
    data['contract_edges']=edges
    # In-contract movement is already covered by all worlds above. Out-of-contract mass
    # can violate the single-relation interval; packet checking alone cannot detect a live DB.
    h=hedge_instance();cc,_,_=optimize(h)
    w=[1,1];size=len(instantiate(h,w)[0]);bound=cc['containment']['1']['upper']
    assert size==12 and bound==6 and verify(h,cc)['accepted']
    data['out_of_contract_drift']={'declared_total':1,'actual_total':2,
        'declared_base_upper':bound,'actual_base_count':size,
        'unchanged_declared_packet_accepts':True,
        'meaning':'No live-database membership attestation is claimed.'}
    data['cpu_s']=time.process_time()-start
    data['maxrss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    (out/'controls.json').write_text(json.dumps(data,sort_keys=True,indent=2)+'\n')
    return data

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):raise SystemExit('Choose a fresh output directory.')
    a.output.mkdir(parents=True,exist_ok=True)
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    print(json.dumps(run(a.output),sort_keys=True))
if __name__=='__main__':main()
