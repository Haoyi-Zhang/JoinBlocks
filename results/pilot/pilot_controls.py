from pathlib import Path
exec((Path(__file__).with_name('pilot.py')).read_text().split('rows=[]')[0])
import sqlite3

def sqlite_card(tables,edges,s):
 db=sqlite3.connect(':memory:')
 aliases=[i for i in range(len(tables)) if s>>i&1]
 for i in aliases:
  es=sorted(tables[i][0]);db.execute(f'create table r{i} ('+','.join(f'e{e} integer' for e in es)+')')
  db.executemany(f'insert into r{i} values ('+','.join('?' for e in es)+')',[tuple(row[e] for e in es) for row in tables[i]])
 sql='select count(*) from '+','.join(f'r{i}' for i in aliases)
 wh=[f'r{a}.e{e}=r{b}.e{e}' for e,(a,b) in enumerate(edges) if a in aliases and b in aliases]
 if wh:sql+=' where '+' and '.join(wh)
 v=db.execute(sql).fetchone()[0];db.close();return v

def local_frontier(n,e,h,l,u,N):
 @lru_cache(None)
 def rec(s):
  if s&(s-1)==0:return [(s.bit_length()-1,(0,)*len(l))]
  out=[]
  for a in range(1,s):
   b=s^a
   if a&s!=a or not a&s&-s or not conn(a,e) or not conn(b,e):continue
   for p,x in rec(a):
    for q,y in rec(b):out.append(((p,q),tuple(xi+yi+zi for xi,yi,zi in zip(x,y,h[s]))))
  rr=regret([x for p,x in out],l,u,N);return [out[min(range(len(out)),key=lambda i:(rr[i],str(out[i][0])))]]
 return rec((1<<n)-1)[0]
report={'sql_blocks_checked':0}
n=6;e=[(0,i) for i in range(1,n)];ts=templates(n,e,4,17);h=cards(n,e,ts)
for s,vs in h.items():
 for j,v in enumerate(vs):
  assert v==sqlite_card(ts[j],e,s);report['sql_blocks_checked']+=1
for seed in range(1,101):
 ts=templates(6,e,4,seed);h=cards(6,e,ts);cc=list(dict.fromkeys(c for p,c in enum(6,e,h)));rr=regret(cc,[0]*4,[3]*4,5)
 p,c=local_frontier(6,e,h,[0]*4,[3]*4,5)
 loc=max(sup(tuple(a-b for a,b in zip(c,q)),[0]*4,[3]*4,5)[0] for q in cc)
 if loc>min(rr):
  report['local_minimax_counterexample']={'seed':seed,'global_regret':min(rr),'local_regret':loc,'local_plan':p,'local_profile':c};break
else:report['local_minimax_counterexample']='not found in first 100 seeds'
# Explicit three-key alignment counterexample: identical unary and pair sizes.
R=[0];T=[0];Sd=[(0,0),(1,1)];Sa=[(0,1),(1,0)]
def stats(S):
 return [len(R),len(S),len(T),sum(a==r for a,b in S for r in R),sum(b==t for a,b in S for t in T),sum(a==r and b==t for a,b in S for r in R for t in T)]
report['pairwise_indistinguishability']=[stats(Sd),stats(Sa)]
report['cpu_s']=time.process_time()-t;report['maxrss_kib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps(report,indent=2))
