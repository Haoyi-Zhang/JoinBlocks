"""Bounded independent exhaustive oracle: SQLite cardinalities, subset enumeration,
and integer-world enumeration. It imports neither producer nor checker logic.
"""
from __future__ import annotations
import sqlite3
from itertools import product
from functools import lru_cache


def oracle(inst):
    n=inst['n'];edges=inst['edges'];K=len(inst['blocks']);masks=[]
    for s in range(1,1<<n):
        vs={i for i in range(n) if s>>i&1};reach={min(vs)}
        for _ in range(n):
            for a,b in edges:
                if a in reach and b in vs:reach.add(b)
                if b in reach and a in vs:reach.add(a)
        if reach==vs:masks.append(s)
    H={s:[] for s in masks};sql_checks=0
    for block in inst['blocks']:
        db=sqlite3.connect(':memory:')
        for i,rows in enumerate(block):
            attrs=[str(e) for e,(a,b) in enumerate(edges) if i in (a,b)]
            db.execute(f'CREATE TABLE r{i} ('+','.join(f'e{e} INTEGER' for e in attrs)+')')
            if rows:db.executemany(f'INSERT INTO r{i} VALUES ('+','.join('?' for _ in attrs)+')',
                                   [tuple(row[e] for e in attrs) for row in rows])
        for s in masks:
            aliases=[i for i in range(n) if s>>i&1]
            sql='SELECT COUNT(*) FROM '+','.join(f'r{i}' for i in aliases)
            predicates=[f'r{a}.e{e}=r{b}.e{e}' for e,(a,b) in enumerate(edges)
                        if a in aliases and b in aliases]
            if predicates:sql+=' WHERE '+' AND '.join(predicates)
            H[s].append(db.execute(sql).fetchone()[0]);sql_checks+=1
        db.close()
    @lru_cache(None)
    def enumerate_plans(s):
        if s&(s-1)==0:return [(s.bit_length()-1,(0,)*K)]
        result=[]
        for a in masks:
            if a==s or a&s!=a or not a&(s&-s):continue
            b=s^a
            if b not in H:continue
            for p,x in enumerate_plans(a):
                for q,y in enumerate_plans(b):
                    result.append(((p,q),tuple(xi+yi+zi for xi,yi,zi in zip(x,y,H[s]))))
        return result
    plans=enumerate_plans((1<<n)-1);unique={}
    for p,c in plans:unique.setdefault(c,p)
    cc=list(unique);regrets=[0]*len(cc);worlds=[];vertices=set()
    volume=1
    for l,u in zip(inst['lower'],inst['upper']):volume*=u-l+1
    if volume>1_000_000:raise ValueError('bounded oracle world budget exceeded')
    for w in product(*(range(l,u+1) for l,u in zip(inst['lower'],inst['upper']))):
        if sum(w)!=inst['total']:continue
        worlds.append(w)
        # Integer points with at most one non-bound coordinate are vertices of this polytope.
        if sum(l<x<u for x,l,u in zip(w,inst['lower'],inst['upper']))<=1:vertices.add(w)
        values=[sum(a*b for a,b in zip(c,w)) for c in cc];best=min(values)
        for i,v in enumerate(values):regrets[i]=max(regrets[i],v-best)
    return {'optimum':min(regrets),'plan_count':len(plans),'unique_profiles':len(cc),
            'worlds':worlds,'vertices':len(vertices),'regret_by_profile':dict(zip(cc,regrets)),
            'h':{s:tuple(v) for s,v in H.items()},'sql_profile_checks':sql_checks,
            'plans':plans}
