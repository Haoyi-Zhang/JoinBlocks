#!/usr/bin/env python3
"""Compare scientific results exactly, excluding observational time and memory fields."""
import argparse,csv,json
from pathlib import Path
from summarize import TIMING

def rows(root):
    with (root/'cases.csv').open(newline='') as f:rs=list(csv.DictReader(f))
    if len(rs)!=len({r['case'] for r in rs}):raise ValueError('Duplicate case row')
    return {r['case']:{k:v for k,v in r.items() if k not in TIMING} for r in rs}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('reference',type=Path);p.add_argument('rerun',type=Path);a=p.parse_args()
    x,y=rows(a.reference),rows(a.rerun)
    if x!=y:raise SystemExit('Non-timing CSV mismatch')
    for case in x:
        for folder in ['certificates','details']:
            f=folder+'/'+case+'.json'
            if json.loads((a.reference/f).read_text())!=json.loads((a.rerun/f).read_text()):raise SystemExit('JSON mismatch: '+f)
    print(json.dumps({'matching_cases':len(x),'exact_certificates':len(x),'exact_details':len(x),'excluded_observations':sorted(TIMING)},sort_keys=True))
if __name__=='__main__':main()
