#!/usr/bin/env python3
from __future__ import annotations
import csv, json, statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def rows(path):
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))

def as_int(s):
    try:return int(s)
    except Exception:return None

def numeric_columns(rs):
    out=[]
    for c in rs[0]:
        vals=[as_int(r[c]) for r in rs if r[c] != '']
        if vals and len(vals)==sum(r[c] != '' for r in rs):out.append(c)
    return out

def choose(fields, include, exclude=()):
    c=[f for f in fields if all(t in f.lower() for t in include) and not any(t in f.lower() for t in exclude)]
    if not c:return None
    return sorted(c,key=lambda x:(len(x),x))[0]

campaign=rows(ROOT/'results/campaign/cases.csv')
att=rows(ROOT/'results/attestation/cases.csv')
topo=rows(ROOT/'results/topology/cases.csv')
fields=campaign[0].keys(); nums=numeric_columns(campaign)
regret='regret' if 'regret' in fields else choose(fields,('regret',),('baseline','point','worst','box','local'))
if regret is None: raise RuntimeError('cannot locate selected regret column')
baseline_tokens={
    'point estimate':('point','regret'),
    'worst cost':('worst','regret'),
    'independent box':('box','regret'),
    'local minimax':('local','regret'),
}
baselines={}
for label,tokens in baseline_tokens.items():
    col=choose(fields,tokens,('cpu','delta','better','tie'))
    if col and col != regret:
        lower=sum(int(r[regret]) < int(r[col]) for r in campaign)
        equal=sum(int(r[regret]) == int(r[col]) for r in campaign)
        worse=sum(int(r[regret]) > int(r[col]) for r in campaign)
        baselines[label]={'column':col,'lower':lower,'equal':equal,'worse':worse}

sqlite_cols=[c for c in ('sql_profile_checks',) if c in fields]
bag_cols=[c for c in ('sql_plan_world_checks',) if c in fields]
cert_col=choose(fields,('certificate','bytes')) or choose(fields,('cert','bytes'))
root_col=choose(fields,('root','frontier'))
checker_cpu=choose(fields,('checker','cpu'))
producer_cpu=choose(fields,('producer','cpu'))
metrics={
 'schema_version':1,
 'campaign_fields':list(fields),
 'field_mapping':{
   'regret':regret,'baselines':baselines,'sqlite_columns':sqlite_cols,'bag_columns':bag_cols,
   'certificate_bytes':cert_col,'root_frontier':root_col,'checker_cpu':checker_cpu,'producer_cpu':producer_cpu,
 },
 'core':{
   'cases':len(campaign),
   'n_min':min(int(r['n']) for r in campaign if r.get('n')),
   'n_max':max(int(r['n']) for r in campaign if r.get('n')),
   'zero_regret':sum(int(r[regret])==0 for r in campaign),
   'sqlite_checks':sum(sum(int(r[c]) for c in sqlite_cols) for r in campaign),
   'bag_checks':sum(sum(int(r[c]) for c in bag_cols) for r in campaign),
   'certificate_bytes_min':min(int(r[cert_col]) for r in campaign) if cert_col else None,
   'certificate_bytes_max':max(int(r[cert_col]) for r in campaign) if cert_col else None,
   'root_frontier_min':min(int(r[root_col]) for r in campaign) if root_col else None,
   'root_frontier_max':max(int(r[root_col]) for r in campaign) if root_col else None,
   'checker_slower':sum(float(r[checker_cpu])>float(r[producer_cpu]) for r in campaign) if checker_cpu and producer_cpu else None,
   'baselines':baselines,
 },
 'attestation':{
   'snapshots':len(att),
   'copies':sum(int(r['copies']) for r in att),
   'rows':sum(int(r['snapshot_rows']) for r in att),
   'sqlite_checks':sum(int(r['connected_subqueries']) for r in att),
   'bound_tight':sum(int(r['actual_snapshot_regret'])==int(r['certified_regret']) for r in att),
 },
 'topology':{
   'cases':len(topo),'query_ids':sorted({r['query_id'] for r in topo}),
   'n_min':min(int(r['n']) for r in topo),'n_max':max(int(r['n']) for r in topo),
   'plan_count_max':max(int(r['plan_count']) for r in topo),
   'certificate_bytes_max':max(int(r['certificate_bytes']) for r in topo),
   'root_frontier_max':max(int(r['root_frontier']) for r in topo),
 },
 'tests':json.loads((ROOT/'results/tests/summary.json').read_text()),
 'overhead':json.loads((ROOT/'results/attestation/overhead.json').read_text()),
}
att_summary=json.loads((ROOT/'results/attestation/summary.json').read_text())
metrics['attestation']['mutation_attempts']=att_summary['negative_controls_attempted']
metrics['attestation']['mutation_rejections']=att_summary['negative_controls_rejected']
metrics['attestation']['chain_acceptances']=att_summary['end_to_end_chain_acceptances']
metrics['attestation']['regret_bound_violations']=att_summary['snapshot_regret_bound_checks']-sum(r['regret_within_bound'].lower()=='true' for r in att)
(ROOT/'results/reviewer-metrics.json').write_text(json.dumps(metrics,sort_keys=True,indent=2)+'\n',encoding='utf-8')
print(json.dumps(metrics,sort_keys=True,indent=2))
