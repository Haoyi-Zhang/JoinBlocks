#!/usr/bin/env python3
"""Bounded producer/checker admission sweep, not a large-query optimality study.

Dimensions above the delivered checker's eight-alias limit are recorded as
unsupported before producer expansion. Accepted packets are actually checked;
no row claims exhaustive-oracle agreement because this driver runs no oracle.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path
from typing import Any

import checker
from src import generate, optimizer


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def quantile_nearest(values: list[int], q: float) -> int:
    if not values:
        raise ValueError("empty values")
    xs=sorted(values)
    return xs[max(0,min(len(xs)-1,round(q*(len(xs)-1))))]


def run(out: Path, relations=(8, 10, 12, 14, 16), templates=(4,), shapes=('path', 'star', 'branch')) -> dict:
    if (not relations or any(type(n) is not int or not 2 <= n <= 16 for n in relations)
            or not templates or any(type(k) is not int or k not in (4, 6, 8) for k in templates)
            or not shapes or any(shape not in ('path', 'star', 'branch') for shape in shapes)
            or len(set(relations)) != len(relations) or len(set(templates)) != len(templates)
            or len(set(shapes)) != len(shapes)):
        raise ValueError('invalid bounded sweep dimensions')
    out=Path(out)
    out.mkdir(parents=True, exist_ok=False)
    for sub in ("inputs","certificates"):
        (out/sub).mkdir()
    rows=[]
    for n in relations:
        for k in templates:
          for shape_index,shape in enumerate(shapes):
            seed=16000+n*31+shape_index
            case_id=f"scale-{n}-{k}-{shape}"
            instance=generate.make(n,shape,k,"balanced",seed)
            ib=canonical_bytes(instance)
            ip=out/"inputs"/f"{case_id}.json"; ip.write_bytes(ib)
            row={"case_id":case_id,"relations":n,"shape":shape,"regime":"balanced","templates":k,"seed":seed,
                 "checker_accepted":False,"oracle_checked":False,"status":"UNSUPPORTED_DIMENSION" if n>8 else "INCOMPLETE",
                 "producer_cpu_ns":None,"checker_cpu_ns":None,"input_bytes":len(ib),"certificate_bytes":None,
                 "root_frontier":None,"max_frontier":None,"expansions":None,"template_assignments":None}
            rows.append(row)
            if n>8:
                continue
            t0=time.process_time_ns()
            cert,stats,_profiles=optimizer.optimize(instance)
            producer_ns=time.process_time_ns()-t0
            cb=canonical_bytes(cert)
            cp=out/"certificates"/f"{case_id}.json"; cp.write_bytes(cb)
            t0=time.process_time_ns()
            checked=checker.verify(checker.load(ip),checker.load(cp))
            checker_ns=time.process_time_ns()-t0
            if checked.get('accepted') is not True:
                raise RuntimeError(f"checker rejected {case_id}")
            row.update({
                "checker_accepted":True,"status":"ACCEPTED",
                "producer_cpu_ns":producer_ns,"checker_cpu_ns":checker_ns,
                "certificate_bytes":len(cb),"root_frontier":stats['root_frontier'],
                "max_frontier":stats['max_frontier'],"expansions":stats['expansions'],
                "template_assignments":checked['template_assignments'],
            })
    fields=list(rows[0])
    with (out/"cases.csv").open("w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=fields); w.writeheader(); w.writerows(rows)
    accepted=[row for row in rows if row['checker_accepted']]
    sizes=[int(r["certificate_bytes"]) for r in accepted]
    producer=[int(r["producer_cpu_ns"]) for r in accepted]
    checking=[int(r["checker_cpu_ns"]) for r in accepted]
    summary={
        "schema":"bounded-admission-sweep",
        "cases":len(rows),"accepted":len(accepted),"unsupported":sum(r['status']=='UNSUPPORTED_DIMENSION' for r in rows),
        "relation_counts":sorted({int(r["relations"]) for r in rows}),
        "shapes":sorted({str(r["shape"]) for r in rows}),
        "max_accepted_relations":max((int(r['relations']) for r in accepted),default=None),
        "certificate_bytes":None if not sizes else {"min":min(sizes),"median":statistics.median(sizes),"p90":quantile_nearest(sizes,.9),"max":max(sizes)},
        "producer_cpu_ns":None if not producer else {"median":statistics.median(producer),"max":max(producer)},
        "checker_cpu_ns":None if not checking else {"median":statistics.median(checking),"max":max(checking)},
        "oracle_boundary":"No exhaustive oracle is run by this driver. n>8 is unsupported, not certified scaling evidence.",
        "timing_scope":"Single-process CPU observations on the reproduction host; not a latency or throughput claim.",
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    return summary


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--relations',type=int,nargs='+',choices=range(2,17),default=[8,10,12,14,16])
    ap.add_argument('--templates',type=int,nargs='+',choices=(4,6,8),default=[4])
    ap.add_argument('--shapes',nargs='+',choices=('path','star','branch'),default=['path','star','branch'])
    args=ap.parse_args()
    print(json.dumps(run(args.output,tuple(args.relations),tuple(args.templates),tuple(args.shapes)),indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
