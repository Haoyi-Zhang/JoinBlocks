"""Untrusted producer of containment, dominance-closure, and minimax certificates."""
from __future__ import annotations
from .model import (subsets,cuts,support,sub,add,mask,key,block_profile,plan_cost)

def optimize(inst, pruning='contract'):
    n,lo,hi,N=inst['n'],inst['lower'],inst['upper'],inst['total']
    h=block_profile(inst); k=len(lo); front={}; profile={}; coverage={}
    calls=0
    def sp(d):
        nonlocal calls
        calls+=1
        return support(d,lo,hi,N)
    def dominates(a,b):
        if pruning=='component': return all(x<=y for x,y in zip(a,b))
        return sp(sub(a,b))[0]<=0
    expansions=0
    for s in subsets(n,inst['edges']):
        if s&(s-1)==0:
            front[s]=[s.bit_length()-1]; profile[s]=[(0,)*k]; coverage[s]=[];continue
        ex=[]
        for a,b in cuts(s,inst['edges']):
            for i,p in enumerate(front[a]):
                for j,q in enumerate(front[b]):
                    ex.append((a,b,i,j,(p,q),add(profile[a][i],profile[b][j],h[s])))
        expansions+=len(ex)
        if len(ex)>50000: raise ValueError('state expansion limit exceeded')
        unique={}
        for *_,p,c in sorted(ex,key=lambda row:key(row[4])): unique.setdefault(c,p)
        kept=[]
        for c,p in unique.items():
            if pruning!='none' and any(dominates(d,c) for q,d in kept): continue
            if pruning!='none': kept=[(q,d) for q,d in kept if not dominates(c,d)]
            kept.append((p,c))
        kept.sort(key=lambda pc:key(pc[0]))
        if len(kept)>2000: raise ValueError('frontier width limit exceeded')
        front[s]=[p for p,c in kept];profile[s]=[c for p,c in kept]
        cv=[]
        for a,b,i,j,p,c in ex:
            for idx,d in enumerate(profile[s]):
                v,_,lam=sp(sub(d,c))
                if v<=0:
                    cv.append([a,b,i,j,idx,lam]);break
            else: raise AssertionError('frontier does not cover expansion')
        coverage[s]=cv
    root=(1<<n)-1; costs=profile[root]; regrets=[]; lower=[]
    for p in costs:
        best=(-1,None,None)
        for qi,q in enumerate(costs):
            val,w,lam=sp(sub(p,q))
            if val>best[0]: best=(val,qi,w)
        regrets.append(best[0]);lower.append({'rival':best[1],'world':best[2]})
    winner=min(range(len(costs)),key=lambda i:(regrets[i],key(front[root][i])))
    upper=[sp(sub(costs[winner],q))[2] for q in costs]
    containment={}
    for s,v in h.items():
        ub,w1,t1=sp(v); neg,w2,t2=sp(tuple(-x for x in v))
        containment[str(s)]={'lower':-neg,'upper':ub,
              'max_world':w1,'max_threshold':t1,'min_world':w2,'min_threshold':t2}
    cert={'instance':inst['name'],'containment':containment,
          'states':{str(s):{'plans':front[s],'coverage':coverage[s]} for s in front},
          'selected':winner,'regret':regrets[winner],'upper_thresholds':upper,
          'lower_witnesses':lower}
    stats={'support_calls':calls,'expansions':expansions,
           'root_frontier':len(costs),'max_frontier':max(map(len,front.values())),
           'states':len(front)}
    return cert,stats,h
