"""Deterministic original synthetic tables. No external benchmark rows are copied."""
from __future__ import annotations
import random
from pathlib import Path
import json

def make(n,shape,k,regime,seed,name=None):
    if shape=='star':edges=[[0,i] for i in range(1,n)]
    elif shape=='path':edges=[[i,i+1] for i in range(n-1)]
    elif shape=='branch':edges=[[(i-1)//2,i] for i in range(1,n)]
    else:raise ValueError('unknown shape')
    rng=random.Random(seed);blocks=[]
    for j in range(k):
        tables=[]
        for i in range(n):
            incident=[e for e,(a,b) in enumerate(edges) if i==a or i==b]
            if len(incident)==1:
                tables.append([{str(incident[0]):0} for _ in range(2)]);continue
            cols={e:set(rng.sample(range(4),2 if regime=='balanced' else rng.choice([1,2,3])))
                  for e in incident}
            tables.append([{str(e):int(r not in cols[e]) for e in incident} for r in range(4)])
        blocks.append(tables)
    return {'name':name or f'{shape}-{n}-{k}-{regime}-{seed}', 'n':n,'edges':edges,
            'lower':[0]*k,'upper':[3]*k,'total':5 if k==4 else 9,
            'blocks':blocks,'family':shape,'regime':regime,'seed':seed,
            'provenance':'Original disjoint-key template generator; not a JOB or TPC-H benchmark run.'}

def tpch(seed,filtered):
    """Original rows on Customer--Orders--Lineitem--{Part,Supplier--Nation--Region}.
    Key uniqueness and foreign keys hold before optional relation-local filtering.
    Attribute names are mapped to conventional TPC-H schema edges; rows and queries
    are not taken from dbgen and do not represent a TPC-H benchmark result.
    """
    rng=random.Random(seed);edges=[[0,1],[1,2],[2,3],[2,4],[4,5],[5,6]];blocks=[]
    for j in range(4):
        nc,no,np,ns,nn,nr=2,3,3,2,2,1
        order_c=[rng.randrange(nc) for _ in range(no)]
        supplier_n=[rng.randrange(nn) for _ in range(ns)]
        tables=[[],[],[],[],[],[],[]]
        tables[0]=[{'0':c} for c in range(nc)]
        tables[1]=[{'0':order_c[o],'1':o} for o in range(no)]
        tables[2]=[{'1':rng.randrange(no),'2':rng.randrange(np),'3':rng.randrange(ns)} for _ in range(6)]
        tables[3]=[{'2':p} for p in range(np) if not filtered or (p+j)%3!=0]
        tables[4]=[{'3':s,'4':supplier_n[s]} for s in range(ns)]
        tables[5]=[{'4':nnn,'5':0} for nnn in range(nn) if not filtered or (nnn+j)%2==0]
        tables[6]=[{'5':0}]
        blocks.append(tables)
    return {'name':f'commerce-{seed}-{int(filtered)}','n':7,'edges':edges,'lower':[0]*4,
            'upper':[3]*4,'total':5,'blocks':blocks,'family':'commerce',
            'regime':'filtered' if filtered else 'unfiltered','seed':seed,
            'aliases':['customer','orders','lineitem','part','supplier','nation','region'],
            'edge_attributes':[['c_custkey','o_custkey'],['o_orderkey','l_orderkey'],
                ['l_partkey','p_partkey'],['l_suppkey','s_suppkey'],
                ['s_nationkey','n_nationkey'],['n_regionkey','r_regionkey']],
            'provenance':'Original tiny data on an acyclic TPC-H schema-derived join; not a TPC-H benchmark query or result.'}

def suite():
    cases=[]
    for shape in ['star','path','branch']:
        for n in [4,5,6,7]:
            for k in [4,6]:
                for regime in ['balanced','skewed']:
                    for seed in [101,202]:cases.append(make(n,shape,k,regime,seed))
    for seed in [303,404,505]:
        for filtered in [False,True]:cases.append(tpch(seed,filtered))
    return cases

def write_inputs(out:Path):
    out.mkdir(parents=True,exist_ok=True)
    for inst in suite():
        (out/(inst['name']+'.json')).write_text(json.dumps(inst,sort_keys=True,indent=2)+'\n')

# BEGIN JOB-TOPOLOGY SUPPORT
def _normalize_tree_edges(n, edges):
    if isinstance(n, bool) or not isinstance(n, int) or n < 2:
        raise ValueError("n must be an integer at least two")
    if not isinstance(edges, (list, tuple)):
        raise ValueError("edges must be a sequence")
    out = []
    seen = set()
    for edge in edges:
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            raise ValueError("each edge must contain two endpoints")
        a, b = edge
        if any(isinstance(x, bool) or not isinstance(x, int) for x in (a, b)):
            raise ValueError("edge endpoints must be integers")
        if not (0 <= a < n and 0 <= b < n) or a == b:
            raise ValueError("edge endpoint out of range or self-loop")
        key = tuple(sorted((a, b)))
        if key in seen:
            raise ValueError("duplicate undirected edge")
        seen.add(key)
        out.append((a, b))
    if len(out) != n - 1:
        raise ValueError("a tree on n vertices must have n-1 edges")
    adj = [[] for _ in range(n)]
    for a, b in out:
        adj[a].append(b); adj[b].append(a)
    stack = [0]; reached = {0}
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in reached:
                reached.add(v); stack.append(v)
    if len(reached) != n:
        raise ValueError("edges must form a connected tree")
    return out

def make_tree(n, edges, shape, k, regime, seed, name=None):
    edges = _normalize_tree_edges(n, edges)
    rng = random.Random(seed)
    blocks = []
    for j in range(k):
        tables = []
        for i in range(n):
            incident = [e for e, (a, b) in enumerate(edges) if i == a or i == b]
            if len(incident) == 1:
                tables.append([{str(incident[0]): 0} for _ in range(2)])
                continue
            cols = {e: set(rng.sample(range(4), 2 if regime == 'balanced' else rng.choice([1, 2, 3]))) for e in incident}
            tables.append([{str(e): int(r not in cols[e]) for e in incident} for r in range(4)])
        blocks.append(tables)
    return {'name': name or f'{shape}-{n}-{k}-{regime}-{seed}', 'n': n, 'edges': edges, 'lower': [0] * k, 'upper': [3] * k, 'total': 5 if k == 4 else 9, 'blocks': blocks, 'family': shape, 'regime': regime, 'seed': seed, 'provenance': 'Original disjoint-key template generator; not a JOB or TPC-H benchmark run.'}

def load_job_tree_topologies(path=None):
    import json
    from pathlib import Path
    if path is None:
        path = Path(__file__).resolve().parents[1] / "benchmarks" / "job-tree-topologies.json"
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("queries"), list):
        raise ValueError("unsupported JOB topology manifest")
    seen = set()
    for q in data["queries"]:
        required = {"query_id", "path", "blob_sha", "aliases", "edges", "equality_predicates", "transitive_equalities_removed"}
        if set(q) != required:
            raise ValueError("closed JOB topology schema violation")
        if q["query_id"] in seen:
            raise ValueError("duplicate JOB query id")
        seen.add(q["query_id"])
        aliases = q["aliases"]
        if not isinstance(aliases, list) or len(aliases) < 2 or len(set(aliases)) != len(aliases):
            raise ValueError("aliases must be a unique list")
        _normalize_tree_edges(len(aliases), q["edges"])
        sha = q["blob_sha"]
        if not isinstance(sha, str) or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("invalid source blob sha")
        if q["path"] != q["query_id"] + ".sql":
            raise ValueError("query id/path mismatch")
        if q["equality_predicates"] - q["transitive_equalities_removed"] != len(aliases) - 1:
            raise ValueError("equality accounting does not match reduced tree")
    return data

def make_job_topology(entry, k, regime, seed):
    query_id = entry["query_id"]
    return make_tree(len(entry["aliases"]), entry["edges"], "job-" + query_id, k, regime, seed)
# END JOB-TOPOLOGY SUPPORT

