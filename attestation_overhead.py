#!/usr/bin/env python3
"""Deterministically summarize attestation packet size relative to snapshots."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path


def q(values, numerator, denominator):
    values = sorted(values)
    if not values:
        raise ValueError("empty sequence")
    # Nearest-rank quantile, documented and deterministic.
    rank = (numerator * len(values) + denominator - 1) // denominator
    return values[max(0, min(len(values) - 1, rank - 1))]


def run(results: Path, output: Path, expected_snapshots: int | None = None, expected_rows: int | None = None) -> dict:
    with (results / "cases.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("attestation cases.csv is empty")
    required = {"snapshot_rows", "snapshot_bytes", "attestation_bytes", "chain_accepted", "regret_within_bound"}
    if not required.issubset(rows[0]):
        raise ValueError(f"missing fields: {sorted(required - set(rows[0]))}")
    parsed = []
    for row in rows:
        nrows = int(row["snapshot_rows"])
        snapshot = int(row["snapshot_bytes"])
        packet = int(row["attestation_bytes"])
        if nrows <= 0 or snapshot <= 0 or packet <= 0:
            raise ValueError("size metrics must be positive")
        parsed.append((nrows, snapshot, packet))
    ratios_ppm = [packet * 1_000_000 // snapshot for _, snapshot, packet in parsed]
    packet_per_row_milli = [packet * 1000 // nrows for nrows, _, packet in parsed]
    snapshot_per_row_milli = [snapshot * 1000 // nrows for nrows, snapshot, _ in parsed]
    summary = {
        "schema_version": 1,
        "quantile_definition": "nearest-rank",
        "snapshots": len(parsed),
        "rows_total": sum(nrows for nrows, _, _ in parsed),
        "rows_min": min(nrows for nrows, _, _ in parsed),
        "rows_median": statistics.median(nrows for nrows, _, _ in parsed),
        "rows_p90": q([nrows for nrows, _, _ in parsed], 9, 10),
        "rows_max": max(nrows for nrows, _, _ in parsed),
        "snapshot_bytes_total": sum(snapshot for _, snapshot, _ in parsed),
        "attestation_bytes_total": sum(packet for _, _, packet in parsed),
        "attestation_to_snapshot_ratio_min_ppm": min(ratios_ppm),
        "attestation_to_snapshot_ratio_median_ppm": int(statistics.median(ratios_ppm)),
        "attestation_to_snapshot_ratio_p90_ppm": q(ratios_ppm, 9, 10),
        "attestation_to_snapshot_ratio_max_ppm": max(ratios_ppm),
        "attestation_bytes_per_row_median_milli": int(statistics.median(packet_per_row_milli)),
        "attestation_bytes_per_row_p90_milli": q(packet_per_row_milli, 9, 10),
        "attestation_bytes_per_row_max_milli": max(packet_per_row_milli),
        "snapshot_bytes_per_row_median_milli": int(statistics.median(snapshot_per_row_milli)),
        "all_chain_accepted": all(row["chain_accepted"].lower() == "true" for row in rows),
        "all_bounds_hold": all(row["regret_within_bound"].lower() == "true" for row in rows),
        "interpretation": "The packet is an explicit row-occurrence mapping, not a succinct proof. Ratios include canonical JSON field-name overhead and are not asymptotic constants.",
    }
    if expected_snapshots is not None and summary["snapshots"] != expected_snapshots:
        raise ValueError(f"snapshot count mismatch: {summary['snapshots']} != {expected_snapshots}")
    if expected_rows is not None and summary["rows_total"] != expected_rows:
        raise ValueError(f"row count mismatch: {summary['rows_total']} != {expected_rows}")
    if not summary["all_chain_accepted"] or not summary["all_bounds_hold"]:
        raise ValueError("not all retained chain/bound checks hold")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-snapshots", type=int)
    parser.add_argument("--expect-rows", type=int)
    args = parser.parse_args()
    print(json.dumps(run(args.results, args.output, args.expect_snapshots, args.expect_rows), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
