from itertools import combinations, product
from functools import lru_cache
import random, time, resource, json, os
# One scientific worker; bounded address space; no child processes.
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
t=time.process_time()

def conn(s,edges):
 if not s:return False
 seen=s&-s
 while True:
  z=seen
  for a,b in edges:
   if (seen>>a)&1 and (s>>b)&1:seen|=1<<b
   if (seen>>b)&1 and (s>>a)&1:seen|=1<<a
  if z==seen:return seen==s

def templates(n,edges,k,seed):
 r=random.Random(seed); result=[]
 for j in range(k):
  tables=[]
  for i in range(n):
   incident=[e for e,(a,b) in enumerate(edges) if i in (a,b)]
   if len(incident)==1: tables.append([{incident[0]:0} for _ in range(2)]);continue
   cols={e:set(r.sample(range(4),2)) for e in incident}
   tables.append([{e:int(row not in cols[e]) for e in incident} for row in range(4)])
  result.append(tables)
 return result

def cards(n,edges,ts):
 result={}
 for s in range(1,1<<n):
  if not conn(s,edges):continue
  aliases=[i for i in range(n) if s>>i&1];vals=[]
  for tables in ts:
   num=0
   for rows in product(*(tables[i] for i in aliases)):
    d=dict(zip(aliases,rows))
    if all(d[a][e]==d[b][e] for e,(a,b) in enumerate(edges) if a in d and b in d):num+=1
   vals.append(num)
  result[s]=tuple(vals)
 return result

def enum(n,edges,h):
 @lru_cache(None)
 def run(s):
  if s&(s-1)==0:return [((s.bit_length()-1), (0,)*len(next(iter(h.values()))))]
  out=[]
  for a in range(1,s):
   b=s^a
   if a&s!=a or not a&s&-s or not conn(a,edges) or not conn(b,edges):continue
   for p,x in run(a):
    for q,y in run(b):out.append(((p,q),tuple(xi+yi+zi for xi,yi,zi in zip(x,y,h[s]))))
  return out
 return run((1<<n)-1)

def sup(d,l,u,N):
 w=list(l);B=N-sum(l); lam=0
 for i in sorted(range(len(d)),key=lambda i:(-d[i],i)):
  z=min(u[i]-l[i],B);w[i]+=z;B-=z;lam=d[i]
  if B==0:break
 assert B==0
 # For B=0 from outset, threshold must be at least max coefficient.
 if N==sum(l):lam=max(d)
 v=sum(a*b for a,b in zip(d,w))
 ub=sum(a*b for a,b in zip(d,l))+lam*(N-sum(l))+sum((ui-li)*max(di-lam,0) for di,li,ui in zip(d,l,u))
 assert v==ub
 return v,w,lam

def regret(cost,l,u,N):
 vals=[]
 for p in cost:vals.append(max(sup(tuple(a-b for a,b in zip(p,q)),l,u,N)[0] for q in cost))
 return vals

rows=[]
for n,shape in [(4,'star'),(5,'path'),(6,'star')]:
 e=[(0,i) for i in range(1,n)] if shape=='star' else [(i,i+1) for i in range(n-1)]
 h=cards(n,e,templates(n,e,4,17));plans=enum(n,e,h); cc=list(dict.fromkeys(c for p,c in plans))
 l=[0]*4;u=[3]*4;N=5
 rr=regret(cc,l,u,N)
 worlds=[w for w in product(range(4),repeat=4) if sum(w)==N]
 oracle=[max(sum(a*b for a,b in zip(c,w))-min(sum(a*b for a,b in zip(q,w)) for q in cc) for w in worlds) for c in cc]
 assert rr==oracle
 rows.append({'n':n,'shape':shape,'plans':len(plans),'profiles':len(cc),'integer_worlds':len(worlds),'rstar':min(rr),'oracle_match':True})
print(json.dumps({'pilot':rows,'cpu_s':time.process_time()-t,'maxrss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss},indent=2))
