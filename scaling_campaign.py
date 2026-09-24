#!/usr/bin/env python3
"""Deterministic producer/checker scaling sweep beyond the exhaustive-oracle range.

The sweep is engineering evidence only.  Exact oracle agreement is established by
reproduce.py/topology_campaign.py through eight relations; cases above eight are
not labelled as ground-truth optimality experiments.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any

import checker
from src import generate, optimizer


def canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def quantile_nearest(values: list[int], q: float) -> int:
    if not values:
        raise ValueError("empty values")
    xs=sorted(values)
    return xs[max(0,min(len(xs)-1,round(q*(len(xs)-1))))]


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ns=ap.parse_args()
    out=ns.output
    for sub in ("inputs","certificates"):
        (out/sub).mkdir(parents=True,exist_ok=True)
    rows=[]
    for n in (8,10,12,14,16):
        for shape_index,shape in enumerate(("path","star","branch")):
            seed=16000+n*31+shape_index
            case_id=f"scale-{n}-{shape}"
            instance=generate.make(n,shape,4,"balanced",seed)
            ib=canonical_bytes(instance)
            ip=out/"inputs"/f"{case_id}.json"; ip.write_bytes(ib)
            t0=time.process_time_ns()
            cert=optimizer.optimize(instance)
            producer_ns=time.process_time_ns()-t0
            cb=canonical_bytes(cert)
            cp=out/"certificates"/f"{case_id}.json"; cp.write_bytes(cb)
            t0=time.process_time_ns()
            accepted=bool(checker.verify_files(ip,cp))
            checker_ns=time.process_time_ns()-t0
            if not accepted:
                raise RuntimeError(f"checker rejected {case_id}")
            rows.append({
                "case_id":case_id,"relations":n,"shape":shape,"regime":"balanced","templates":4,"seed":seed,
                "checker_accepted":accepted,"oracle_checked":n<=8,
                "producer_cpu_ns":producer_ns,"checker_cpu_ns":checker_ns,
                "input_bytes":len(ib),"certificate_bytes":len(cb),
                "input_sha256":hashlib.sha256(ib).hexdigest(),"certificate_sha256":hashlib.sha256(cb).hexdigest(),
            })
    fields=list(rows[0])
    with (out/"cases.csv").open("w",newline="") as fh:
        w=csv.DictWriter(fh,fieldnames=fields); w.writeheader(); w.writerows(rows)
    sizes=[int(r["certificate_bytes"]) for r in rows]
    producer=[int(r["producer_cpu_ns"]) for r in rows]
    checking=[int(r["checker_cpu_ns"]) for r in rows]
    summary={
        "schema":"scaling-campaign-v1",
        "cases":len(rows),"accepted":sum(bool(r["checker_accepted"]) for r in rows),
        "relation_counts":sorted({int(r["relations"]) for r in rows}),
        "shapes":sorted({str(r["shape"]) for r in rows}),
        "max_relations":max(int(r["relations"]) for r in rows),
        "certificate_bytes":{"min":min(sizes),"median":int(statistics.median(sizes)),"p90":quantile_nearest(sizes,.9),"max":max(sizes)},
        "producer_cpu_ns":{"median":int(statistics.median(producer)),"max":max(producer)},
        "checker_cpu_ns":{"median":int(statistics.median(checking)),"max":max(checking)},
        "oracle_boundary":"Only the 8-relation members overlap the exact-oracle range; n>8 is producer/checker engineering evidence, not independent optimality ground truth.",
        "timing_scope":"Single-process CPU observations on the reproduction host; not a latency or throughput claim.",
    }
    (out/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print(json.dumps(summary,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
