"""Exact same-model baselines, not reimplementations of PARQO/Roq/SafeBound."""
from __future__ import annotations
from functools import lru_cache
from .model import (key,mask,plan_cost,midworld,support,dot,sub,cuts,add,internals)

def select_baselines(inst,h,plans):
    lo,hi,N=inst['lower'],inst['upper'],inst['total']
    cc=[plan_cost(p,h) for p in plans];point=midworld(lo,hi,N)
    pi=min(range(len(plans)),key=lambda i:(dot(cc[i],point),key(plans[i])))
    wi=min(range(len(plans)),key=lambda i:(support(cc[i],lo,hi,N)[0],key(plans[i])))
    intervals={s:(-support(tuple(-x for x in v),lo,hi,N)[0],support(v,lo,hi,N)[0]) for s,v in h.items()}
    signatures=[internals(p) for p in plans]
    # Prune duplicate internal-node signatures, not candidates according to the true contract.
    unique={}
    for i,s in enumerate(signatures):
        if s not in unique or key(plans[i])<key(plans[unique[s]]):unique[s]=i
    sis=list(unique)
    br=[]
    for x in sis:
        br.append(max(sum(intervals[s][1] for s in x-y)-sum(intervals[s][0] for s in y-x)
                      for y in sis))
    bx=min(range(len(sis)),key=lambda i:(br[i],key(plans[unique[sis[i]]])))
    @lru_cache(None)
    def local(s):
        if s&(s-1)==0:return s.bit_length()-1,(0,)*len(lo)
        ex=[]
        for a,b in cuts(s,inst['edges']):
            p,x=local(a);q,y=local(b);ex.append(((p,q),add(x,y,h[s])))
        rr=[max(support(sub(x,y),lo,hi,N)[0] for q,y in ex) for p,x in ex]
        return ex[min(range(len(ex)),key=lambda i:(rr[i],key(ex[i][0])))]
    lp,lc=local((1<<inst['n'])-1)
    return {'point':plans[pi],'worst_cost':plans[wi],'cardinality_box':plans[unique[sis[bx]]],
            'local_regret':lp}, {'box_own_regret':br[bx], 'point_world':[str(x) for x in point]}
