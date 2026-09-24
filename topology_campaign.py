#!/usr/bin/env python3
"""Exact campaign on equality-reduced tree topologies derived from public JOB SQL.

This campaign uses only alias/edge provenance.  It does not redistribute SQL or
IMDB data and is not a JOB runtime benchmark.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path

from checker import verify
from src.generate import load_job_tree_topologies, make_job_topology
from src.optimizer import optimize
from src.oracle import oracle


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value))


def first(mapping: dict, names: tuple[str, ...], default=None):
    for name in names:
        if name in mapping:
            return mapping[name]
    return default


def exact_regret(result: dict) -> int:
    value = first(result, ("optimal_regret", "minimax_regret", "regret"))
    if value is None:
        raise RuntimeError(f"oracle result lacks a regret field: {sorted(result)}")
    return value


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    manifest = load_job_tree_topologies()
    dump_json(output / "source-manifest.json", manifest)
    rows: list[dict] = []
    for entry in manifest["queries"]:
        for regime in ("balanced", "skewed"):
            for seed in (313, 919):
                instance = make_job_topology(entry, 4, regime, seed)
                case = instance["name"]
                dump_json(output / "inputs" / f"{case}.json", instance)

                start = time.process_time()
                certificate, stats, _profiles = optimize(instance)
                producer_cpu = time.process_time() - start
                dump_json(output / "certificates" / f"{case}.json", certificate)

                start = time.process_time()
                checked = verify(instance, certificate)
                checker_cpu = time.process_time() - start

                start = time.process_time()
                exact = oracle(instance)
                oracle_cpu = time.process_time() - start
                dump_json(output / "oracles" / f"{case}.json", exact)

                r_exact = exact_regret(exact)
                if certificate["regret"] != r_exact:
                    raise RuntimeError(f"exact regret mismatch for {case}: {certificate['regret']} != {r_exact}")

                cert_bytes = len(canonical_bytes(certificate))
                input_bytes = len(canonical_bytes(instance))
                rows.append({
                    "case": case,
                    "query_id": entry["query_id"],
                    "source_path": entry["path"],
                    "source_blob_sha": entry["blob_sha"],
                    "n": len(entry["aliases"]),
                    "k": 4,
                    "regime": regime,
                    "seed": seed,
                    "equality_predicates": entry["equality_predicates"],
                    "transitive_equalities_removed": entry["transitive_equalities_removed"],
                    "regret": certificate["regret"],
                    "checker_accepted": True,
                    "oracle_match": True,
                    "input_bytes": input_bytes,
                    "certificate_bytes": cert_bytes,
                    "root_frontier": first(stats, ("root_frontier", "root_frontier_size"), ""),
                    "states": first(stats, ("states", "state_count"), ""),
                    "expansions": first(stats, ("expansions", "candidate_expansions"), ""),
                    "plan_count": first(exact, ("plan_count", "plans"), ""),
                    "unique_profiles": first(exact, ("unique_profiles", "profile_count"), ""),
                    "producer_cpu_seconds": f"{producer_cpu:.9f}",
                    "checker_cpu_seconds": f"{checker_cpu:.9f}",
                    "oracle_cpu_seconds": f"{oracle_cpu:.9f}",
                    "checker_result": json.dumps(checked, sort_keys=True, separators=(",", ":")) if checked is not None else "null",
                })

    fields = list(rows[0])
    with (output / "cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)

    by_n = {}
    for n in sorted({int(row["n"]) for row in rows}):
        group = [row for row in rows if int(row["n"]) == n]
        by_n[str(n)] = {
            "cases": len(group),
            "certificate_bytes_min": min(int(row["certificate_bytes"]) for row in group),
            "certificate_bytes_median": statistics.median(int(row["certificate_bytes"]) for row in group),
            "certificate_bytes_max": max(int(row["certificate_bytes"]) for row in group),
            "input_bytes_median": statistics.median(int(row["input_bytes"]) for row in group),
            "root_frontier_max": max(int(row["root_frontier"]) for row in group),
            "plan_count_max": max(int(row["plan_count"]) for row in group),
            "producer_cpu_seconds_median": statistics.median(float(row["producer_cpu_seconds"]) for row in group),
            "checker_cpu_seconds_median": statistics.median(float(row["checker_cpu_seconds"]) for row in group),
            "oracle_cpu_seconds_median": statistics.median(float(row["oracle_cpu_seconds"]) for row in group),
        }
    summary = {
        "schema_version": 1,
        "scope": "Exact proof/check/oracle runs on JOB-derived equality-reduced tree topologies with synthetic literal templates; not a JOB data or runtime benchmark.",
        "source_repository": manifest["source"]["repository"],
        "source_commit": manifest["source"]["commit"],
        "query_ids": [q["query_id"] for q in manifest["queries"]],
        "cases": len(rows),
        "all_checker_accepted": all(row["checker_accepted"] for row in rows),
        "all_oracle_match": all(row["oracle_match"] for row in rows),
        "n_min": min(int(row["n"]) for row in rows),
        "n_max": max(int(row["n"]) for row in rows),
        "certificate_bytes_max": max(int(row["certificate_bytes"]) for row in rows),
        "by_n": by_n,
    }
    dump_json(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
