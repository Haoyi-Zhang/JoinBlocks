#!/usr/bin/env python3
"""Reproduce the snapshot-membership campaign with exact SQLite cross-checks."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import resource
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from attest import Rejected, load, verify
import checker
from verify_chain import verify as verify_chain
from src.attestation import campaign_worlds, materialize_attestation
from src.model import block_profile, subsets


def compact_bytes(value: Any) -> int:
    return len((json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())


def sql_profile(inst: dict[str, Any], snapshot: dict[str, Any]) -> dict[int, int]:
    """Compute every connected-subquery cardinality from the shuffled snapshot."""
    connection = sqlite3.connect(":memory:")
    try:
        incident = [
            [edge for edge, (a, b) in enumerate(inst["edges"]) if relation in (a, b)]
            for relation in range(inst["n"])
        ]
        for relation, edges in enumerate(incident):
            columns = ", ".join(f"e{edge} INTEGER NOT NULL" for edge in edges)
            connection.execute(f"CREATE TABLE t{relation} ({columns})")
            placeholders = ",".join("?" for _ in edges)
            rows = [tuple(row[str(edge)] for edge in edges) for row in snapshot["tables"][relation]]
            if rows:
                connection.executemany(f"INSERT INTO t{relation} VALUES ({placeholders})", rows)
        results: dict[int, int] = {}
        for mask in subsets(inst["n"], inst["edges"]):
            relations = [i for i in range(inst["n"]) if mask & (1 << i)]
            from_clause = ", ".join(f"t{i} AS r{i}" for i in relations)
            predicates = [
                f"r{a}.e{edge} = r{b}.e{edge}"
                for edge, (a, b) in enumerate(inst["edges"])
                if mask & (1 << a) and mask & (1 << b)
            ]
            where = " WHERE " + " AND ".join(predicates) if predicates else ""
            results[mask] = connection.execute(f"SELECT COUNT(*) FROM {from_clause}{where}").fetchone()[0]
        return results
    finally:
        connection.close()


def assigned_pairs(inst: dict[str, Any], packet: dict[str, Any], copy_id: int, edge: int):
    """Yield (relation, template-row-index, snapshot-row-index, local-key)."""
    copy_packet = packet["copies"][copy_id]
    block = inst["blocks"][copy_packet["type"]]
    name = str(edge)
    for relation, template_rows in enumerate(block):
        for row_id, template_row in enumerate(template_rows):
            if name in template_row:
                yield relation, row_id, copy_packet["rows"][relation][row_id], template_row[name]


def mutate_duplicate_assignment(inst, snapshot, packet) -> bool:
    del inst, snapshot
    for relation in range(len(packet["copies"][0]["rows"])):
        locations = []
        for copy_packet in packet["copies"]:
            locations.extend((copy_packet["rows"][relation], pos)
                             for pos in range(len(copy_packet["rows"][relation])))
        if len(locations) < 2:
            continue
        first_rows, first_pos = locations[0]
        first = first_rows[first_pos]
        for rows, pos in locations[1:]:
            if rows[pos] != first:
                rows[pos] = first
                return True
    return False


def mutate_uncovered_row(inst, snapshot, packet) -> bool:
    del inst, packet
    for rows in snapshot["tables"]:
        if rows:
            rows.append(copy.deepcopy(rows[0]))
            return True
    return False


def mutate_missing_attribute(inst, snapshot, packet) -> bool:
    del inst, packet
    for rows in snapshot["tables"]:
        if rows:
            rows[0].pop(next(iter(rows[0])))
            return True
    return False


def mutate_extra_attribute(inst, snapshot, packet) -> bool:
    del inst, packet
    for rows in snapshot["tables"]:
        if rows:
            rows[0]["999"] = 0
            return True
    return False


def mutate_copy_count(inst, snapshot, packet) -> bool:
    del inst, snapshot
    if packet["copies"]:
        packet["copies"].pop()
        return True
    return False


def mutate_wrong_instance(inst, snapshot, packet) -> bool:
    del inst
    snapshot["instance"] = "other"
    packet["instance"] = "other"
    return True


def mutate_cross_copy_namespace(inst, snapshot, packet) -> bool:
    if len(packet["copies"]) < 2:
        return False
    for edge in range(len(inst["edges"])):
        left = list(assigned_pairs(inst, packet, 0, edge))
        right = list(assigned_pairs(inst, packet, 1, edge))
        if not left or not right:
            continue
        left_actual = snapshot["tables"][left[0][0]][left[0][2]][str(edge)]
        target_local = right[0][3]
        changed = False
        for relation, _, snapshot_row, local in right:
            if local == target_local:
                snapshot["tables"][relation][snapshot_row][str(edge)] = left_actual
                changed = True
        if changed:
            return True
    return False


def mutate_noninjective(inst, snapshot, packet) -> bool:
    for copy_id in range(len(packet["copies"])):
        for edge in range(len(inst["edges"])):
            pairs = list(assigned_pairs(inst, packet, copy_id, edge))
            locals_seen = []
            for *_, local in pairs:
                if local not in locals_seen:
                    locals_seen.append(local)
            if len(locals_seen) < 2:
                continue
            first, second = locals_seen[:2]
            actual_first = next(
                snapshot["tables"][relation][snapshot_row][str(edge)]
                for relation, _, snapshot_row, local in pairs
                if local == first
            )
            for relation, _, snapshot_row, local in pairs:
                if local == second:
                    snapshot["tables"][relation][snapshot_row][str(edge)] = actual_first
            return True
    return False


def mutate_inconsistent_renaming(inst, snapshot, packet) -> bool:
    for copy_id in range(len(packet["copies"])):
        for edge in range(len(inst["edges"])):
            pairs = list(assigned_pairs(inst, packet, copy_id, edge))
            by_local: dict[int, list[tuple[int, int]]] = defaultdict(list)
            for relation, _, snapshot_row, local in pairs:
                by_local[local].append((relation, snapshot_row))
            repeated = next((rows for rows in by_local.values() if len(rows) >= 2), None)
            if repeated:
                relation, snapshot_row = repeated[0]
                snapshot["tables"][relation][snapshot_row][str(edge)] += 1_000_000_000_000
                return True
    return False


def connected_masks(inst: dict[str, Any]) -> list[int]:
    n = inst["n"]
    edges = inst["edges"]
    out: list[int] = []
    for mask in range(1, 1 << n):
        vertices = {i for i in range(n) if mask & (1 << i)}
        reached = {min(vertices)}
        changed = True
        while changed:
            changed = False
            for a, b in edges:
                if a in reached and b in vertices and b not in reached:
                    reached.add(b); changed = True
                if b in reached and a in vertices and a not in reached:
                    reached.add(a); changed = True
        if reached == vertices:
            out.append(mask)
    return out


def enumerate_actual_costs(inst: dict[str, Any], profile: dict[int, int]) -> list[int]:
    """Enumerate all legal connected binary plans using snapshot cardinalities."""
    masks = set(connected_masks(inst))
    memo: dict[int, list[int]] = {}

    def costs(mask: int) -> list[int]:
        if mask in memo:
            return memo[mask]
        if mask & (mask - 1) == 0:
            memo[mask] = [0]
            return memo[mask]
        values: list[int] = []
        anchor = mask & -mask
        for left in range(1, mask):
            if left & mask != left or not (left & anchor):
                continue
            right = mask ^ left
            if left not in masks or right not in masks:
                continue
            for a in costs(left):
                for b in costs(right):
                    values.append(a + b + profile[mask])
        memo[mask] = values
        return values

    return costs((1 << inst["n"]) - 1)


def actual_plan_cost(plan: Any, profile: dict[int, int]) -> tuple[int, int]:
    if type(plan) is int:
        return 1 << plan, 0
    left_mask, left_cost = actual_plan_cost(plan[0], profile)
    right_mask, right_cost = actual_plan_cost(plan[1], profile)
    mask = left_mask | right_mask
    return mask, left_cost + right_cost + profile[mask]


Mutation = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], bool]
MUTATIONS: dict[str, Mutation] = {
    "duplicate-assignment": mutate_duplicate_assignment,
    "uncovered-row": mutate_uncovered_row,
    "missing-attribute": mutate_missing_attribute,
    "extra-attribute": mutate_extra_attribute,
    "copy-count": mutate_copy_count,
    "wrong-instance": mutate_wrong_instance,
    "cross-copy-namespace": mutate_cross_copy_namespace,
    "noninjective-renaming": mutate_noninjective,
    "inconsistent-renaming": mutate_inconsistent_renaming,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", action="append", default=[], help="exact input stem; may repeat")
    args = parser.parse_args()
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    root = Path(__file__).resolve().parent
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit("Output is nonempty; choose a fresh directory.")
    (out / "examples").mkdir(parents=True, exist_ok=True)

    inputs = sorted((root / "inputs").glob("*.json"))
    if args.case:
        requested = set(args.case)
        missing = requested - {path.stem for path in inputs}
        if missing:
            raise SystemExit("Unknown exact input stems: " + ", ".join(sorted(missing)))
        inputs = [path for path in inputs if path.stem in requested]
    if not inputs:
        raise SystemExit("No matching exact inputs")

    rows: list[dict[str, Any]] = []
    negative = {name: {"attempted": 0, "rejected": 0, "skipped": 0, "example_reason": ""}
                for name in MUTATIONS}
    example_families: set[str] = set()
    start_cpu = time.process_time()
    start_wall = time.perf_counter()
    total_sql_checks = 0
    total_snapshot_rows = 0
    chain_acceptances = 0
    regret_bound_checks = 0
    regret_bound_tight = 0

    for input_path in inputs:
        inst = load(input_path)
        profile = block_profile(inst)
        certificate = checker.load(root / "results" / "campaign" / "certificates" / input_path.name)
        for world_id, world in enumerate(campaign_worlds(inst)):
            snapshot, packet = materialize_attestation(
                inst, world, seed=inst.get("seed", 0) * 10 + world_id
            )
            check_start = time.process_time()
            verdict = verify(inst, snapshot, packet)
            chain_verdict = verify_chain(inst, snapshot, packet, certificate)
            checker_cpu = time.process_time() - check_start
            chain_acceptances += 1
            actual = sql_profile(inst, snapshot)
            expected = {mask: sum(a * b for a, b in zip(values, world)) for mask, values in profile.items()}
            if actual != expected:
                raise AssertionError(f"snapshot profile mismatch for {inst['name']} world {world}")
            selected_plan = certificate["states"][str((1 << inst["n"]) - 1)]["plans"][certificate["selected"]]
            _, selected_cost = actual_plan_cost(selected_plan, actual)
            all_costs = enumerate_actual_costs(inst, actual)
            actual_regret = selected_cost - min(all_costs)
            if actual_regret > chain_verdict["regret"]:
                raise AssertionError(f"certified regret violated on {inst['name']} world {world}")
            regret_bound_checks += 1
            regret_bound_tight += int(actual_regret == chain_verdict["regret"])
            total_sql_checks += len(actual)
            total_snapshot_rows += verdict["rows"]

            for name, mutation in MUTATIONS.items():
                mutated_snapshot = copy.deepcopy(snapshot)
                mutated_packet = copy.deepcopy(packet)
                if not mutation(inst, mutated_snapshot, mutated_packet):
                    negative[name]["skipped"] += 1
                    continue
                negative[name]["attempted"] += 1
                try:
                    verify(inst, mutated_snapshot, mutated_packet)
                except (Rejected, KeyError, TypeError, ValueError, IndexError, RecursionError) as exc:
                    negative[name]["rejected"] += 1
                    if not negative[name]["example_reason"]:
                        negative[name]["example_reason"] = str(exc)
                else:
                    raise AssertionError(f"negative control accepted: {name} on {inst['name']}")

            snapshot_bytes = compact_bytes(snapshot)
            packet_bytes = compact_bytes(packet)
            row = {
                "case": inst["name"],
                "family": inst["family"],
                "regime": inst["regime"],
                "n": inst["n"],
                "k": len(inst["lower"]),
                "world_id": world_id,
                "world": json.dumps(world, separators=(",", ":")),
                "copies": verdict["copies"],
                "snapshot_rows": verdict["rows"],
                "mapped_key_occurrences": verdict["mapped_key_occurrences"],
                "distinct_edge_values": verdict["distinct_edge_values"],
                "connected_subqueries": len(actual),
                "snapshot_bytes": snapshot_bytes,
                "attestation_bytes": packet_bytes,
                "checker_cpu_s": round(checker_cpu, 9),
                "checker_accepted": True,
                "chain_accepted": True,
                "certified_regret": chain_verdict["regret"],
                "actual_snapshot_regret": actual_regret,
                "regret_within_bound": True,
                "sqlite_profile_match": True,
            }
            rows.append(row)
            print(json.dumps({"case": inst["name"], "world": world, "rows": verdict["rows"],
                              "checks": "accepted"}, sort_keys=True), flush=True)

            if inst["family"] not in example_families:
                stem = f"{inst['name']}-w{world_id}"
                (out / "examples" / f"{stem}.snapshot.json").write_text(
                    json.dumps(snapshot, sort_keys=True, indent=2) + "\n", encoding="utf-8"
                )
                (out / "examples" / f"{stem}.attestation.json").write_text(
                    json.dumps(packet, sort_keys=True, indent=2) + "\n", encoding="utf-8"
                )
                example_families.add(inst["family"])

    with (out / "cases.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "negative-controls.json").write_text(
        json.dumps(negative, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "input_cases": len(inputs),
        "accepted_snapshots": len(rows),
        "attested_copies": sum(int(row["copies"]) for row in rows),
        "snapshot_rows": total_snapshot_rows,
        "sqlite_connected_subquery_checks": total_sql_checks,
        "end_to_end_chain_acceptances": chain_acceptances,
        "snapshot_regret_bound_checks": regret_bound_checks,
        "snapshot_regret_bound_tight": regret_bound_tight,
        "negative_controls_attempted": sum(item["attempted"] for item in negative.values()),
        "negative_controls_rejected": sum(item["rejected"] for item in negative.values()),
        "negative_controls_skipped": sum(item["skipped"] for item in negative.values()),
        "max_snapshot_bytes": max(int(row["snapshot_bytes"]) for row in rows),
        "max_attestation_bytes": max(int(row["attestation_bytes"]) for row in rows),
        "checker_cpu_s_sum": round(sum(float(row["checker_cpu_s"]) for row in rows), 9),
        "campaign_cpu_s": round(time.process_time() - start_cpu, 9),
        "campaign_wall_s": round(time.perf_counter() - start_wall, 9),
        "maxrss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "all_membership_checks_accepted": True,
        "all_sqlite_profiles_matched": True,
        "all_snapshot_regrets_within_certificate": True,
        "all_attempted_negative_controls_rejected": True,
    }
    (out / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
