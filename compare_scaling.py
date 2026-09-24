#!/usr/bin/env python3
"""Compare a fresh scaling sweep with the retained non-timing evidence."""
from __future__ import annotations
import csv, json, sys
from pathlib import Path

TIMING_FIELDS={"producer_cpu_ns","checker_cpu_ns"}
TIMING_SUMMARY={"producer_cpu_ns","checker_cpu_ns"}

def parse_paths(argv:list[str])->tuple[Path,Path]:
    vals=[]; i=0
    while i<len(argv):
        a=argv[i]
        if a in {"--retained","--reference","--expected","--candidate","--fresh","--actual"}:
            if i+1>=len(argv): raise SystemExit(f"missing value after {a}")
            vals.append(argv[i+1]); i+=2; continue
        if a.startswith('-'):
            i+=1; continue
        vals.append(a); i+=1
    if len(vals)!=2: raise SystemExit(f"expected two directories, got {vals}")
    return Path(vals[0]),Path(vals[1])

def load_rows(p:Path):
    with (p/'cases.csv').open(newline='') as fh:
        rows=list(csv.DictReader(fh))
    return [{k:v for k,v in r.items() if k not in TIMING_FIELDS} for r in rows]

def scrub_summary(o):
    if isinstance(o,dict): return {k:scrub_summary(v) for k,v in o.items() if k not in TIMING_SUMMARY}
    if isinstance(o,list): return [scrub_summary(v) for v in o]
    return o

def files_under(p:Path,sub:str):
    base=p/sub
    return {x.relative_to(base).as_posix():x.read_bytes() for x in sorted(base.rglob('*.json'))}

def main()->int:
    ref,cand=parse_paths(sys.argv[1:])
    assert load_rows(ref)==load_rows(cand),"non-timing case rows differ"
    assert files_under(ref,'inputs')==files_under(cand,'inputs'),"inputs differ"
    assert files_under(ref,'certificates')==files_under(cand,'certificates'),"certificates differ"
    rs=scrub_summary(json.loads((ref/'summary.json').read_text()))
    cs=scrub_summary(json.loads((cand/'summary.json').read_text()))
    assert rs==cs,"non-timing summaries differ"
    print(json.dumps({'status':'match','cases':len(load_rows(ref))},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
