#!/usr/bin/env python3
"""Independent certificate checker, implemented without importing the optimizer.

The trusted inputs are the query, block templates, multiplicity contract and this
checker. Passing checks establishes the finite packet's mathematical assertions;
it does not validate an unseen deployment against its declared contract.
"""
from __future__ import annotations
import argparse
import json
from itertools import product
from pathlib import Path
from typing import Any

class Rejected(ValueError):
    pass

def require(b: bool, message: str) -> None:
    if not b: raise Rejected(message)

def integer(x: Any, limit: int = 120) -> int:
    require(type(x) is int and x.bit_length() <= limit, 'expected bounded exact integer')
    return x


def object_shape(value: Any, required: set[str], optional: set[str], name: str) -> dict:
    require(type(value) is dict, f'{name} must be an object')
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    require(not missing, f'{name} missing fields: {sorted(missing)}')
    require(not unknown, f'{name} unknown fields: {sorted(unknown)}')
    return value


def text(value: Any, name: str, limit: int) -> str:
    require(type(value) is str and 0 < len(value) <= limit, f'invalid {name}')
    return value


CONTRACT_REQUIRED = {'name', 'n', 'edges', 'lower', 'upper', 'total', 'blocks'}
CONTRACT_OPTIONAL = {'family', 'regime', 'seed', 'provenance', 'aliases', 'edge_attributes'}
CERTIFICATE_FIELDS = {
    'instance', 'containment', 'states', 'selected', 'regret',
    'upper_thresholds', 'lower_witnesses'
}
CONTAINMENT_FIELDS = {
    'lower', 'upper', 'max_world', 'min_world',
    'max_threshold', 'min_threshold'
}
STATE_FIELDS = {'plans', 'coverage'}
LOWER_WITNESS_FIELDS = {'rival', 'world'}


def validate_contract_shape(inst: Any) -> dict:
    inst = object_shape(inst, CONTRACT_REQUIRED, CONTRACT_OPTIONAL, 'contract')
    text(inst['name'], 'contract name', 256)
    for field in ('family', 'regime'):
        if field in inst:
            text(inst[field], field, 128)
    if 'provenance' in inst:
        text(inst['provenance'], 'provenance', 4096)
    if 'seed' in inst:
        integer(inst['seed'])
    return inst


def validate_optional_labels(inst: dict, n: int, edge_count: int) -> None:
    if 'aliases' in inst:
        aliases = inst['aliases']
        require(type(aliases) is list and len(aliases) == n, 'alias labels')
        for alias in aliases:
            text(alias, 'alias label', 128)
        require(len(set(aliases)) == len(aliases), 'duplicate alias label')
    if 'edge_attributes' in inst:
        labels = inst['edge_attributes']
        require(type(labels) is list and len(labels) == edge_count, 'edge attribute labels')
        for pair in labels:
            require(type(pair) is list and len(pair) == 2, 'edge attribute label pair')
            text(pair[0], 'edge attribute label', 128)
            text(pair[1], 'edge attribute label', 128)


def load(path: Path) -> dict:
    require(path.stat().st_size <= 32*1024**2, 'JSON byte budget exceeded')
    def object_pairs(pairs):
        d={}
        for k,v in pairs:
            require(k not in d,'duplicate JSON object key');d[k]=v
        return d
    with path.open(encoding='utf-8') as f:
        value = json.load(f, object_pairs_hook=object_pairs)
    require(type(value) is dict, 'top-level JSON object required')
    return value


def verify(inst: dict, cert: dict) -> dict:
    inst = validate_contract_shape(inst)
    object_shape(cert, CERTIFICATE_FIELDS, set(), 'certificate')
    n=integer(inst['n']);require(2<=n<=8,'unsupported relation count')
    edges=inst['edges'];require(type(edges) is list and len(edges)==n-1,'not a tree')
    seen_edges=set()
    for e in edges:
        require(type(e) is list and len(e)==2,'edge encoding')
        a,b=map(integer,e);require(0<=a<n and 0<=b<n and a!=b,'edge endpoint')
        z=tuple(sorted((a,b)));require(z not in seen_edges,'duplicate edge');seen_edges.add(z)
    def connected(s):
        todo=[(s&-s).bit_length()-1];visited=set()
        while todo:
            v=todo.pop()
            if v in visited: continue
            visited.add(v)
            for a,b in edges:
                if a==v and s&(1<<b) and b not in visited: todo.append(b)
                if b==v and s&(1<<a) and a not in visited: todo.append(a)
        return s>0 and sum(1<<i for i in visited)==s
    require(connected((1<<n)-1),'disconnected tree')
    validate_optional_labels(inst, n, len(edges))
    masks=[s for s in range(1,1<<n) if connected(s)]
    lo,hi=inst['lower'],inst['upper'];require(type(lo) is list and type(hi) is list,'contract arrays')
    k=len(lo);N=integer(inst['total'])
    require(1<=k<=8 and len(hi)==k and 0<=N<=32,'contract dimensions or total')
    for l,u in zip(lo,hi):require(0<=integer(l)<=integer(u)<=32,'invalid multiplicity interval')
    require(sum(lo)<=N<=sum(hi),'empty uncertainty set')
    blocks=inst['blocks'];require(type(blocks) is list and len(blocks)==k,'template count')
    cardinalities={s:[0]*k for s in masks};work=0
    for j,block in enumerate(blocks):
        require(len(block)==n,'template relation count')
        for i,rows in enumerate(block):
            attrs={str(e) for e,(a,b) in enumerate(edges) if i==a or i==b}
            require(type(rows) is list and len(rows)<=8,'template row budget')
            for row in rows:
                require(set(row)==attrs,'template edge attributes')
                for x in row.values():require(0<=integer(x)<=1024,'key domain')
        for s in masks:
            aliases=[i for i in range(n) if s&(1<<i)]
            probes=1
            for i in aliases:probes*=len(block[i])
            work+=probes;require(work<=2_000_000,'template verification work budget')
            relevant=[(str(e),a,b) for e,(a,b) in enumerate(edges)
                      if s&(1<<a) and s&(1<<b)]
            for chosen in product(*(block[i] for i in aliases)):
                binding=dict(zip(aliases,chosen))
                if all(binding[a][e]==binding[b][e] for e,a,b in relevant):cardinalities[s][j]+=1
    require(type(cert['instance']) is str and cert['instance']==inst['name'],'instance name mismatch')
    def world(w):
        require(type(w) is list and len(w)==k,'world dimension')
        for x,l,u in zip(w,lo,hi):require(l<=integer(x)<=u,'world outside interval')
        require(sum(w)==N,'world violates shared mass')
    def upper(d,t):
        t=integer(t)
        # Weak duality only. No sorting, optimization, LP solver, or oracle is used.
        return sum(x*l for x,l in zip(d,lo))+t*(N-sum(lo))+sum(
            (u-l)*max(x-t,0) for x,l,u in zip(d,lo,hi))
    def diff(a,b):return [x-y for x,y in zip(a,b)]
    def scalar(a,b):return sum(x*y for x,y in zip(a,b))
    cn=cert['containment'];require(type(cn) is dict and set(cn)=={str(s) for s in masks},'missing/extra containment mask')
    for s in masks:
        item=object_shape(cn[str(s)],CONTAINMENT_FIELDS,set(),'containment record');h=cardinalities[s];neg=[-x for x in h]
        L,U=integer(item['lower']),integer(item['upper']);require(0<=L<=U,'cardinality interval')
        world(item['max_world']);world(item['min_world'])
        require(upper(h,item['max_threshold'])==U==scalar(h,item['max_world']),'upper containment proof')
        require(upper(neg,item['min_threshold'])==-L==scalar(neg,item['min_world']),'lower containment proof')
    def plan(p,depth=0):
        require(depth<=n,'plan recursion depth')
        if type(p) is int:
            require(0<=p<n,'plan leaf');return 1<<p,[0]*k
        require(type(p) in (list,tuple) and len(p)==2,'plan node')
        a,x=plan(p[0],depth+1);b,y=plan(p[1],depth+1)
        require(not a&b,'plan repeats relation');s=a|b
        require(s in cardinalities,'plan contains Cartesian product')
        return s,[u+v+w for u,v,w in zip(x,y,cardinalities[s])]
    states=cert['states'];require(type(states) is dict and set(states)=={str(s) for s in masks},'missing/extra frontier state')
    costs={};counts={};coverage_count=0
    for s in sorted(masks,key=lambda t:(t.bit_count(),t)):
        state=object_shape(states[str(s)],STATE_FIELDS,set(),'frontier state');plans=state['plans'];require(type(plans) is list and 0<len(plans)<=2000,'frontier size')
        cc=[];ids=set()
        for p in plans:
            ident=json.dumps(p,separators=(',',':'));require(ident not in ids,'duplicate plan');ids.add(ident)
            m,c=plan(p);require(m==s,'plan leaf coverage');cc.append(c)
        costs[s]=cc;counts[s]=len(cc)
        rows=state['coverage'];require(type(rows) is list and len(rows)<=50000,'coverage record budget')
        if s&(s-1)==0:
            require(len(plans)==1 and type(plans[0]) is int and not rows,'leaf frontier');continue
        # Deliberately enumerate subsets, rather than using the producer's edge-cut code.
        expected=set()
        for a in range(1,s):
            if a&s!=a or not a&(s&-s):continue
            b=s^a
            if a in counts and b in counts:
                require(len(expected)+counts[a]*counts[b]<=50000,'expected coverage work budget')
                for i in range(counts[a]):
                    for j in range(counts[b]):expected.add((a,b,i,j))
        got=set()
        for row in rows:
            require(type(row) is list and len(row)==6,'coverage record shape')
            a,b,i,j,z,t=map(integer,row);idx=(a,b,i,j)
            require(idx in expected and idx not in got,'duplicate/invalid coverage expansion')
            require(0<=z<len(cc),'dominator index');got.add(idx)
            candidate=[x+y+h for x,y,h in zip(costs[a][i],costs[b][j],cardinalities[s])]
            require(upper(diff(cc[z],candidate),t)<=0,'invalid dominance certificate')
        require(got==expected,'uncovered legal expansion');coverage_count+=len(got)
    root=(1<<n)-1;full=costs[root];selected=integer(cert['selected']);R=integer(cert['regret'])
    require(0<=selected<len(full) and R>=0,'selected plan or regret')
    ts=cert['upper_thresholds'];ls=cert['lower_witnesses']
    require(type(ts) is list and type(ls) is list and len(ts)==len(full)==len(ls),'regret certificate coverage')
    for j,t in enumerate(ts):require(upper(diff(full[selected],full[j]),t)<=R,'selected regret upper bound')
    for i,item in enumerate(ls):
        item=object_shape(item,LOWER_WITNESS_FIELDS,set(),'lower witness')
        q=integer(item['rival']);require(0<=q<len(full),'lower witness rival')
        w=item['world'];world(w)
        require(scalar(diff(full[i],full[q]),w)>=R,'candidate lacks minimax lower witness')
    return {'accepted':True,'regret':R,'root_frontier':len(full),
            'containment_masks':len(masks),'coverage_records':coverage_count,
            'template_assignments':work}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('instance',type=Path);parser.add_argument('certificate',type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(verify(load(args.instance),load(args.certificate)),sort_keys=True))
    except (Rejected,KeyError,TypeError,ValueError,IndexError,RecursionError,OSError) as exc:
        print(json.dumps({'accepted':False,'reason':str(exc)},sort_keys=True));raise SystemExit(2)
if __name__=='__main__':main()
