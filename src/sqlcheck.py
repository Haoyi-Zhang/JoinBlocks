"""Bag-result equivalence against SQLite; does not use SQLite physical timings."""
from __future__ import annotations
import sqlite3
from collections import Counter
from .model import instantiate,execute_plan

def check_world(inst,w,plans):
    tables=instantiate(inst,w);db=sqlite3.connect(':memory:')
    for i,rows in enumerate(tables):
        es=[str(e) for e,(a,b) in enumerate(inst['edges']) if i in (a,b)]
        db.execute(f'CREATE TABLE r{i} (tid INTEGER,'+','.join(f'e{e} TEXT' for e in es)+')')
        db.executemany(f'INSERT INTO r{i} VALUES ('+','.join('?' for _ in range(len(es)+1))+')',
            [(t,*(f'{r[e][0]}:{r[e][1]}' for e in es)) for t,r in enumerate(rows)])
    sql='SELECT '+','.join(f'r{i}.tid' for i in range(inst['n']))+' FROM '+','.join(f'r{i}' for i in range(inst['n']))
    sql+=' WHERE '+' AND '.join(f'r{a}.e{e}=r{b}.e{e}' for e,(a,b) in enumerate(inst['edges']))
    expected=Counter(db.execute(sql));db.close()
    for p in plans:
        if execute_plan(inst,w,p)!=expected:raise AssertionError('SQLite bag result mismatch')
    return {'plans_checked':len(plans),'output_rows':sum(expected.values()),'world':list(w)}
