"""Original producer-side model. The independent checker does not import this module."""
from __future__ import annotations
from collections import Counter
from functools import lru_cache
from itertools import product
from fractions import Fraction
from typing import Any

Plan = int | tuple['Plan', 'Plan']

def as_plan(p: Any) -> Plan:
    return p if type(p) is int else (as_plan(p[0]), as_plan(p[1]))

def key(p: Plan) -> str:
    return str(p)

def mask(p: Plan) -> int:
    return 1 << p if type(p) is int else mask(p[0]) | mask(p[1])

def connected(s: int, edges: list[list[int]]) -> bool:
    seen = s & -s
    while seen:
        old = seen
        for a, b in edges:
            if seen & (1 << a) and s & (1 << b): seen |= 1 << b
            if seen & (1 << b) and s & (1 << a): seen |= 1 << a
        if old == seen: return seen == s
    return False

def subsets(n: int, edges: list[list[int]]) -> list[int]:
    return sorted((s for s in range(1, 1 << n) if connected(s, edges)),
                  key=lambda s: (s.bit_count(), s))

def cuts(s: int, edges: list[list[int]]) -> list[tuple[int,int]]:
    # A connected induced subtree can be split into two connected parts only at an edge.
    out = []
    for ei, (a, b) in enumerate(edges):
        if not s & (1 << a) or not s & (1 << b): continue
        seen = 1 << a
        while True:
            old = seen
            for ej, (u, v) in enumerate(edges):
                if ej == ei: continue
                if seen & (1 << u) and s & (1 << v): seen |= 1 << v
                if seen & (1 << v) and s & (1 << u): seen |= 1 << u
            if old == seen: break
        left, right = seen, s ^ seen
        if not left & (s & -s): left, right = right, left
        out.append((left, right))
    return sorted(out)

def support(d: tuple[int,...] | list[int], lo: list[int], hi: list[int], total: int):
    """Exact bounded-mass support: returns value, integral maximizer, dual threshold."""
    remaining = total - sum(lo)
    if remaining < 0 or total > sum(hi): raise ValueError('infeasible contract')
    w = lo.copy()
    lam = max(d)
    if remaining:
        for j in sorted(range(len(d)), key=lambda j: (-d[j], j)):
            take = min(hi[j] - lo[j], remaining)
            w[j] += take
            remaining -= take
            lam = d[j]
            if not remaining: break
    if remaining: raise ValueError('infeasible contract')
    return sum(a*b for a,b in zip(d,w)), w, lam

def sub(a,b): return tuple(x-y for x,y in zip(a,b))

def dot(a,b): return sum(x*y for x,y in zip(a,b))

def add(a,b,c): return tuple(x+y+z for x,y,z in zip(a,b,c))

def midworld(lo,hi,total):
    # Euclidean capped equal-fill of the residual mass, not an infeasible box midpoint.
    w = [Fraction(x) for x in lo]
    pending = set(range(len(lo)))
    rem = Fraction(total-sum(lo))
    while pending:
        share = rem / len(pending)
        capped = [j for j in sorted(pending) if hi[j]-w[j] < share]
        if not capped:
            for j in pending: w[j] += share
            break
        for j in capped:
            rem -= hi[j]-w[j]; w[j] = Fraction(hi[j]); pending.remove(j)
    return w

def block_profile(inst):
    """Join partial row-index bindings recursively; no Cartesian-product checker reuse."""
    n, edges, blocks = inst['n'], inst['edges'], inst['blocks']
    ss = subsets(n,edges)
    h = {s: [] for s in ss}
    for block in blocks:
        @lru_cache(None)
        def bindings(s):
            if s & (s-1) == 0:
                i = s.bit_length()-1
                return [tuple((r if j==i else -1) for j in range(n)) for r in range(len(block[i]))]
            a,b = cuts(s,edges)[0]
            bridge = [(ei,u,v) for ei,(u,v) in enumerate(edges)
                      if (a>>u&1 and b>>v&1) or (a>>v&1 and b>>u&1)]
            out = []
            for x in bindings(a):
                for y in bindings(b):
                    row = tuple(max(xi,yi) for xi,yi in zip(x,y))
                    if all(block[u][row[u]][str(ei)] == block[v][row[v]][str(ei)]
                           for ei,u,v in bridge): out.append(row)
            return out
        for s in ss: h[s].append(len(bindings(s)))
    return {s:tuple(v) for s,v in h.items()}

def plan_cost(p: Plan, h):
    if type(p) is int: return (0,)*len(next(iter(h.values())))
    return add(plan_cost(p[0],h),plan_cost(p[1],h),h[mask(p)])

def internals(p: Plan):
    if type(p) is int: return frozenset()
    return internals(p[0]) | internals(p[1]) | {mask(p)}

def all_plans(inst, limit=10000):
    @lru_cache(None)
    def gen(s):
        if s&(s-1)==0: return (s.bit_length()-1,)
        out=[]
        for a,b in cuts(s,inst['edges']):
            for x in gen(a):
                for y in gen(b):
                    out.append((x,y))
                    if len(out)>limit: raise ValueError('plan enumeration limit exceeded')
        return tuple(out)
    return list(gen((1<<inst['n'])-1))

def instantiate(inst, world):
    """Fresh edge-key namespaces per copy. Rows retain distinct tuple identifiers."""
    tables=[[] for _ in range(inst['n'])]
    copy=0
    for j, count in enumerate(world):
        for _ in range(count):
            for i,rows in enumerate(inst['blocks'][j]):
                for r in rows:
                    tables[i].append({e:(copy,v) for e,v in r.items()})
            copy+=1
    return tables

def execute_plan(inst, world, p):
    """A materializing bag join interpreter; rows are full-length tuple-id bindings."""
    tables=instantiate(inst,world); n=inst['n']; edges=inst['edges']
    def run(t):
        if type(t) is int:
            return [tuple(r if i==t else -1 for i in range(n)) for r in range(len(tables[t]))]
        a,b=mask(t[0]),mask(t[1]); out=[]
        bridge=[(str(e),u,v) for e,(u,v) in enumerate(edges)
                if (a>>u&1 and b>>v&1) or (a>>v&1 and b>>u&1)]
        bridge=[(e,u,v) if a>>u&1 else (e,v,u) for e,u,v in bridge]
        index={}
        for y in run(t[1]):
            join_key=tuple(tables[v][y[v]][e] for e,u,v in bridge)
            index.setdefault(join_key,[]).append(y)
        for x in run(t[0]):
            join_key=tuple(tables[u][x[u]][e] for e,u,v in bridge)
            for y in index.get(join_key,[]):
                out.append(tuple(max(xi,yi) for xi,yi in zip(x,y)))
        return out
    return Counter(run(p))
