#!/usr/bin/env python3
"""Reconcile the complete fixed campaign and emit table/plot inputs; no experiments."""
import argparse,csv,json,statistics
from pathlib import Path

TIMING={'producer_cpu_s','checker_cpu_s','oracle_cpu_s','baseline_cpu_s','sql_cpu_s','case_cpu_s','case_wall_s','maxrss_kib'}
def summary(root):
    with (root/'cases.csv').open(newline='') as f:raw=list(csv.DictReader(f))
    if len(raw)!=102 or len({r['case'] for r in raw})!=102:raise ValueError('Expected all 102 unique frozen cases')
    rows=[]
    text={'case','family','regime','oracle_match','checker_accepted'}
    for row in raw:
        r={k:(v if k in text else (float(v) if k.endswith('_s') else int(v))) for k,v in row.items()}
        if r['oracle_match']!='True' or r['checker_accepted']!='True':raise ValueError('Failed case in results')
        for k in ['point_regret','worst_cost_regret','box_regret','local_regret']:
            if r[k]<r['regret']:raise ValueError('Exact-minimax inconsistency')
        c=json.loads((root/'certificates'/(r['case']+'.json')).read_text())
        if c['regret']!=r['regret']:raise ValueError('Certificate/CSV disagreement')
        detail=json.loads((root/'details'/(r['case']+'.json')).read_text())
        if detail['regrets']['certified']!=r['regret']:raise ValueError('Detail/CSV disagreement')
        rows.append(r)
    result={'cases':102,'zero_regret_cases':sum(r['regret']==0 for r in rows),
            'sql_profile_checks':sum(r['sql_profile_checks'] for r in rows),
            'sql_plan_world_checks':sum(r['sql_plan_world_checks'] for r in rows),
            'contract_prunes_more':sum(r['root_frontier']<r['component_frontier'] for r in rows),
            'checker_slower_cases':sum(r['checker_cpu_s']>r['producer_cpu_s'] for r in rows),
            'baselines':{},'metrics':{},'families':{},'regimes':{},'alias_counts':{}}
    for k in ['regret','root_frontier','certificate_bytes','producer_cpu_s','checker_cpu_s','case_cpu_s','maxrss_kib','plans','unique_profiles','expansions','support_calls']:
        v=[r[k] for r in rows];result['metrics'][k]={'min':min(v),'median':statistics.median(v),'max':max(v),'sum':sum(v)}
    for k in ['point_regret','worst_cost_regret','box_regret','local_regret']:
        gaps=[r[k]-r['regret'] for r in rows]
        result['baselines'][k]={'strictly_better':sum(x>0 for x in gaps),'tied':sum(x==0 for x in gaps),'worse':sum(x<0 for x in gaps),'sum_gap':sum(gaps),'max_gap':max(gaps)}
    for f in sorted({r['family'] for r in rows}):
        rr=[r for r in rows if r['family']==f]
        result['families'][f]={'cases':len(rr),'zero_regret':sum(r['regret']==0 for r in rr),'max_plans':max(r['plans'] for r in rr),'max_frontier':max(r['root_frontier'] for r in rr),'max_cert_bytes':max(r['certificate_bytes'] for r in rr),'median_regret':statistics.median(r['regret'] for r in rr),'sum_regret':sum(r['regret'] for r in rr)}
    for field,dest in [('regime','regimes'),('n','alias_counts')]:
        for value in sorted({r[field] for r in rows}):
            rr=[r for r in rows if r[field]==value]
            result[dest][str(value)]={'cases':len(rr),'zero_regret':sum(r['regret']==0 for r in rr),
                'point_improvements':sum(r['point_regret']>r['regret'] for r in rr),
                'box_improvements':sum(r['box_regret']>r['regret'] for r in rr),
                'median_root_frontier':statistics.median(r['root_frontier'] for r in rr),
                'max_root_frontier':max(r['root_frontier'] for r in rr)}
    result['box_bound_checks']=sum(r['box_claim']>=r['box_regret'] for r in rows)
    if result['box_bound_checks']!=len(rows):raise ValueError('Box relaxation upper bound violated')
    # High-water memory observations cannot meaningfully be added across cases.
    result['metrics']['maxrss_kib'].pop('sum')
    return rows,result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists() and any(a.output.iterdir()):raise SystemExit('Choose a fresh summary directory.')
    rows,s=summary(a.results);a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'summary.json').write_text(json.dumps(s,sort_keys=True,indent=2)+'\n')
    with (a.output/'timings.dat').open('w') as f:
        f.write('producer checker n k\n')
        for r in rows:f.write(f"{1000*r['producer_cpu_s']:.9f} {1000*r['checker_cpu_s']:.9f} {r['n']} {r['k']}\n")
    with (a.output/'frontiers.dat').open('w') as f:
        f.write('contract component n k\n')
        for r in rows:f.write(f"{r['root_frontier']} {r['component_frontier']} {r['n']} {r['k']}\n")
    print(json.dumps(s,sort_keys=True,indent=2))
if __name__=='__main__':main()
