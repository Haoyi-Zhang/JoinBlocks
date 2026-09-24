#!/usr/bin/env python3
"""Create a certificate for a declared, bounded input. Refuse output replacement."""
import argparse, json, os, resource
from pathlib import Path
from checker import load, verify
from src.optimizer import optimize

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('instance',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args()
    if hasattr(os,'sched_setaffinity'):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    i=load(a.instance)
    if not (type(i['n']) is int and 2<=i['n']<=8 and 1<=len(i['blocks'])<=8):
        raise SystemExit('Unsupported declared dimensions')
    c,stats,_=optimize(i)
    verdict=verify(i,c)
    with a.output.open('x') as f:json.dump(c,f,sort_keys=True,separators=(',',':'));f.write('\n')
    print(json.dumps({'checker':verdict,'producer':stats},sort_keys=True))
if __name__=='__main__':main()
