#!/usr/bin/env python3
"""Independent finite generator and exact representation-invariance checks."""
from __future__ import annotations
import argparse,copy,json,random
from pathlib import Path
from checker import verify
from src.optimizer import optimize
from src.oracle import oracle
from src.oracle_json import to_jsonable,from_jsonable

SEEDS=tuple(range(7001,7033))
TRANSFORMS=('identity','alias-permutation','template-permutation','edge-permutation',
            'key-bijection','bag-order','contract-refinement')

def write(path:Path,value:object)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')

def make(seed:int)->dict:
    """Own labelled-tree/row/bounds generator; no imports from src.generate."""
    rng=random.Random(seed);n=rng.randrange(3,6);k=rng.randrange(2,5)
    code=[rng.randrange(n) for _ in range(n-2)];degree=[1]*n
    for value in code:degree[value]+=1
    edges=[]
    for value in code:
        leaf=next(i for i in range(n) if degree[i]==1)
        edges.append([leaf,value]);degree[leaf]-=1;degree[value]-=1
    edges.append([i for i in range(n) if degree[i]==1])
    blocks=[]
    for _ in range(k):
        block=[]
        for alias in range(n):
            cols=[str(e) for e,edge in enumerate(edges) if alias in edge]
            rows=[{col:0 for col in cols}]
            rows.extend({col:rng.randrange(3) for col in cols} for _ in range(rng.randrange(3)))
            block.append(rows)
        blocks.append(block)
    lower=[rng.randrange(2) for _ in range(k)]
    upper=[lo+rng.randrange(1,3) for lo in lower]
    return {'name':f'invariance-{seed}', 'n':n, 'edges':edges, 'blocks':blocks,
            'lower':lower,'upper':upper,'total':rng.randrange(sum(lower),sum(upper)+1)}

def transform(base:dict,kind:str,world:tuple)->dict:
    inst=copy.deepcopy(base);n=base['n'];k=len(base['blocks'])
    inst['name']+='-'+kind
    if kind=='alias-permutation':
        perm=[(i+1)%n for i in range(n)]
        inst['edges']=[[perm[a],perm[b]] for a,b in base['edges']]
        inst['blocks']=[]
        for block in base['blocks']:
            new=[None]*n
            for old in range(n):new[perm[old]]=copy.deepcopy(block[old])
            inst['blocks'].append(new)
    elif kind=='template-permutation':
        perm=list(range(1,k))+[0]
        for field in ('blocks','lower','upper'):inst[field]=[copy.deepcopy(base[field][i]) for i in perm]
    elif kind=='edge-permutation':
        order=list(reversed(range(n-1)));inverse={old:new for new,old in enumerate(order)}
        inst['edges']=[copy.deepcopy(base['edges'][i]) for i in order]
        inst['blocks']=[[[{str(inverse[int(c)]):v for c,v in row.items()} for row in rows]
                         for rows in block] for block in base['blocks']]
    elif kind=='key-bijection':
        inst['blocks']=[[[{c:10*int(c)+7-2*v for c,v in row.items()} for row in rows]
                         for rows in block] for block in base['blocks']]
    elif kind=='bag-order':
        inst['blocks']=[[list(reversed(rows)) for rows in block] for block in inst['blocks']]
    elif kind=='contract-refinement':
        inst['lower'][0]=inst['upper'][0]=world[0]
    elif kind!='identity':raise ValueError(kind)
    return inst

def run(output:Path)->dict:
    if output.exists() and any(output.iterdir()):raise ValueError('output must be empty')
    output.mkdir(parents=True,exist_ok=True);rows=[]
    for seed in SEEDS:
        base=make(seed);base_oracle=oracle(base);base_value=base_oracle['optimum']
        for kind in TRANSFORMS:
            inst=transform(base,kind,base_oracle['worlds'][0]);case=inst['name']
            write(output/'inputs'/f'{case}.json',inst)
            # Use the actual serialized boundary accepted by the independent checker.
            inst=json.loads((output/'inputs'/f'{case}.json').read_text())
            cert,stats,_=optimize(inst);write(output/'certificates'/f'{case}.json',cert)
            cert=json.loads((output/'certificates'/f'{case}.json').read_text())
            checked=verify(inst,cert);exact=oracle(inst)
            write(output/'oracles'/f'{case}.json',to_jsonable(exact))
            decoded=from_jsonable(json.loads((output/'oracles'/f'{case}.json').read_text()))
            if decoded!=exact:raise RuntimeError(f'{case}: oracle round trip')
            if cert['regret']!=exact['optimum']:raise RuntimeError(f'{case}: oracle mismatch')
            invariant=(exact['optimum']<=base_value if kind=='contract-refinement'
                       else exact['optimum']==base_value)
            if not invariant:raise RuntimeError(f'{case}: violated {kind}')
            rows.append({'case':case,'seed':seed,'transform':kind,'n':inst['n'],'k':len(inst['blocks']),
                         'base_optimum':base_value,'optimum':exact['optimum'],
                         'plan_count':exact['plan_count'],'worlds':len(exact['worlds']),
                         'sql_profile_checks':exact['sql_profile_checks'],
                         'checker_result':checked,'oracle_match':True,'relation_holds':invariant})
    summary={'schema_version':1,'base_cases':len(SEEDS),'executed_cases':len(rows),
             'seeds':list(SEEDS),'transforms':list(TRANSFORMS),
             'all_oracle_matches':all(row['oracle_match'] for row in rows),
             'all_relations_hold':all(row['relation_holds'] for row in rows),
             'nonzero_base_optima':sum(row['optimum']>0 for row in rows if row['transform']=='identity'),
             'strict_refinement_reductions':sum(row['optimum']<row['base_optimum'] for row in rows if row['transform']=='contract-refinement'),
             'sql_profile_checks':sum(row['sql_profile_checks'] for row in rows),
             'scope':'Finite representation invariance and contract refinement; not a workload or runtime benchmark.'}
    write(output/'cases.json',rows);write(output/'summary.json',summary)
    return summary

def compare(retained:Path,fresh:Path)->dict:
    if retained.resolve()==fresh.resolve():raise ValueError('distinct directories required')
    for root in (retained,fresh):
        rows=json.loads((root/'cases.json').read_text())
        names={row['case']+'.json' for row in rows}
        if len(rows)!=len(SEEDS)*len(TRANSFORMS) or len(names)!=len(rows):raise RuntimeError('case inventory')
        for sub in ('inputs','certificates','oracles'):
            if {p.name for p in (root/sub).glob('*.json')}!=names:raise RuntimeError('asset inventory')
    left={str(p.relative_to(retained)) for p in retained.rglob('*.json')}
    right={str(p.relative_to(fresh)) for p in fresh.rglob('*.json')}
    if left!=right:raise RuntimeError('different file inventories')
    for rel in sorted(left):
        a=json.loads((retained/rel).read_text());b=json.loads((fresh/rel).read_text())
        if rel.startswith('oracles/'):
            a,b=from_jsonable(a),from_jsonable(b)
        if a!=b:raise RuntimeError(f'evidence mismatch: {rel}')
    return {'compared_cases':len(SEEDS)*len(TRANSFORMS),'compared_json_assets':len(left),
            'distinct_directories':True,'semantic_match':True}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--compare',type=Path,nargs=2,metavar=('RETAINED','FRESH'))
    args=parser.parse_args()
    if bool(args.output)==bool(args.compare):parser.error('choose --output or --compare')
    result=run(args.output) if args.output else compare(*args.compare)
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
