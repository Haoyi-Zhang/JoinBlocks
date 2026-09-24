#!/usr/bin/env python3
"""Offline, one-worker reproduction from exact supplied JSON inputs.
No external packages, network, database service, GPU, or model is used.
"""
from __future__ import annotations
import argparse,csv,json,resource,time,os
from pathlib import Path
from src.model import as_plan,plan_cost,support,key
from src.optimizer import optimize
from src.oracle import oracle
from src.baselines import select_baselines
from src.sqlcheck import check_world
from checker import verify,load

def run_case(inst,out):
    clock=time.process_time();wall=time.perf_counter()
    cert,stats,h=optimize(inst);produce_cpu=time.process_time()-clock
    check_start=time.process_time();verdict=verify(inst,cert);check_cpu=time.process_time()-check_start
    check_start=time.process_time();ref=oracle(inst);oracle_cpu=time.process_time()-check_start
    assert ref['h']==h,'independent SQLite block cardinality mismatch'
    assert ref['optimum']==cert['regret'],'independent exhaustive minimax mismatch'
    plans=[p for p,c in ref['plans']]
    start=time.process_time();base,extra=select_baselines(inst,h,plans);baseline_cpu=time.process_time()-start
    root=str((1<<inst['n'])-1)
    chosen=as_plan(cert['states'][root]['plans'][cert['selected']]);base['certified']=chosen
    regrets={name:ref['regret_by_profile'][plan_cost(p,h)] for name,p in base.items()}
    sql=[];ws=[]
    for w in [ref['worlds'][0],tuple(cert['lower_witnesses'][cert['selected']]['world']),ref['worlds'][-1]]:
        if w not in ws:ws.append(w)
    checks=list({key(p):p for p in (plans if inst['n']<=4 else base.values())}.values())
    start=time.process_time()
    for w in ws:sql.append(check_world(inst,w,checks))
    sql_cpu=time.process_time()-start
    component,compstats,_=optimize(inst,pruning='component')
    assert verify(inst,component)['regret']==cert['regret'],'componentwise ablation mismatch'
    raw=json.dumps(cert,sort_keys=True,separators=(',',':'))+'\n'
    (out/'certificates'/(inst['name']+'.json')).write_text(raw)
    common=(0,)*len(inst['lower'])
    row={'case':inst['name'],'family':inst['family'],'regime':inst['regime'],'n':inst['n'],
         'k':len(inst['lower']),'integer_worlds':len(ref['worlds']),'vertices':ref['vertices'],
         'plans':ref['plan_count'],'unique_profiles':ref['unique_profiles'],
         'regret':cert['regret'],'point_regret':regrets['point'],
         'worst_cost_regret':regrets['worst_cost'],'box_regret':regrets['cardinality_box'],
         'local_regret':regrets['local_regret'],'box_claim':extra['box_own_regret'],
         **stats,'component_frontier':compstats['root_frontier'],
         'component_expansions':compstats['expansions'],
         'certificate_bytes':len(raw.encode()),'checker_records':verdict['coverage_records'],
         'sql_profile_checks':ref['sql_profile_checks'],
         'sql_plan_world_checks':sum(x['plans_checked'] for x in sql),
         'producer_cpu_s':round(produce_cpu,9),'checker_cpu_s':round(check_cpu,9),
         'oracle_cpu_s':round(oracle_cpu,9),'baseline_cpu_s':round(baseline_cpu,9),
         'sql_cpu_s':round(sql_cpu,9),'case_cpu_s':round(time.process_time()-clock,9),
         'case_wall_s':round(time.perf_counter()-wall,9),
         'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
         'oracle_match':True,'checker_accepted':True}
    (out/'details'/(inst['name']+'.json')).write_text(json.dumps({'sql_checks':sql,
           'plans':base,'regrets':regrets,'baseline_details':extra},sort_keys=True,indent=2)+'\n')
    return row

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--case',action='append',default=[],help='exact input stem; may repeat')
    parser.add_argument('--resume',action='store_true',help='skip completed rows in this output only')
    args=parser.parse_args()
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    os.environ['OMP_NUM_THREADS']='1';os.environ['OPENBLAS_NUM_THREADS']='1'
    root=Path(__file__).resolve().parent;out=args.output.resolve()
    if out.exists() and any(out.iterdir()) and not args.resume:
        raise SystemExit('Output is nonempty; choose a fresh directory or explicitly use --resume.')
    (out/'certificates').mkdir(parents=True,exist_ok=True);(out/'details').mkdir(exist_ok=True)
    rows=[];dest=out/'cases.csv'
    if args.resume and dest.exists():
        with dest.open(newline='') as f:rows=list(csv.DictReader(f))
    done={r['case'] for r in rows};inputs=sorted((root/'inputs').glob('*.json'))
    if args.case:
        missing=set(args.case)-{p.stem for p in inputs}
        if missing:raise SystemExit('Unknown exact input stems: '+', '.join(sorted(missing)))
        inputs=[p for p in inputs if p.stem in set(args.case)]
    for name in done:
        if not (out/'certificates'/(name+'.json')).is_file() or not (out/'details'/(name+'.json')).is_file():
            raise SystemExit('Resume evidence missing for '+name+'; choose a fresh output directory.')
    if not inputs:raise SystemExit('No matching exact inputs')
    for path in inputs:
        if path.stem in done:continue
        row=run_case(load(path),out);rows.append(row)
        # Atomic whole-table replacement makes bounded resumption unambiguous.
        temp=dest.with_suffix('.tmp')
        with temp.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader();writer.writerows(rows)
        temp.replace(dest)
        print(json.dumps({'case':row['case'],'regret':row['regret'],'cpu_s':row['case_cpu_s'],
                          'frontier':row['root_frontier'],'checks':'accepted'},sort_keys=True),flush=True)
if __name__=='__main__':main()
