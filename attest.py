#!/usr/bin/env python3
"""Independent checker for membership in a supplied block-correlation contract.

The checker does not import the producer or optimizer.  Its trusted inputs are a
query/template contract, a complete join-key snapshot projection, a row-partition
attestation, and this checker.  Acceptance proves that the projected snapshot is
isomorphic (as a bag instance for the declared joins) to a feasible multiset of
isolated template copies.  It does not predict future snapshots or validate the
abstract cost model against wall-clock execution time.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class Rejected(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Rejected(message)


def integer(value: Any, limit: int = 120) -> int:
    require(type(value) is int and value.bit_length() <= limit, "expected bounded exact integer")
    return value


def object_shape(value: Any, required: set[str], optional: set[str], name: str) -> dict[str, Any]:
    require(type(value) is dict, f"{name} must be an object")
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional
    require(not missing, f"{name} missing fields: {sorted(missing)}")
    require(not unknown, f"{name} unknown fields: {sorted(unknown)}")
    return value


def text(value: Any, name: str, limit: int) -> str:
    require(type(value) is str and 0 < len(value) <= limit, f"invalid {name}")
    return value


CONTRACT_REQUIRED = {"name", "n", "edges", "lower", "upper", "total", "blocks"}
CONTRACT_OPTIONAL = {"family", "regime", "seed", "provenance", "aliases", "edge_attributes"}
SNAPSHOT_FIELDS = {"instance", "tables"}
ATTESTATION_FIELDS = {"instance", "copies"}


def validate_contract_shape(inst: Any) -> dict[str, Any]:
    inst = object_shape(inst, CONTRACT_REQUIRED, CONTRACT_OPTIONAL, "contract")
    text(inst["name"], "contract name", 256)
    for field in ("family", "regime"):
        if field in inst:
            text(inst[field], field, 128)
    if "provenance" in inst:
        text(inst["provenance"], "provenance", 4096)
    if "seed" in inst:
        integer(inst["seed"])
    return inst


def validate_optional_labels(inst: dict[str, Any], n: int, edge_count: int) -> None:
    if "aliases" in inst:
        aliases = inst["aliases"]
        require(type(aliases) is list and len(aliases) == n, "alias labels")
        for alias in aliases:
            text(alias, "alias label", 128)
        require(len(set(aliases)) == len(aliases), "duplicate alias label")
    if "edge_attributes" in inst:
        labels = inst["edge_attributes"]
        require(type(labels) is list and len(labels) == edge_count, "edge attribute labels")
        for pair in labels:
            require(type(pair) is list and len(pair) == 2, "edge attribute label pair")
            text(pair[0], "edge attribute label", 128)
            text(pair[1], "edge attribute label", 128)


def load(path: Path) -> dict[str, Any]:
    require(path.stat().st_size <= 32 * 1024**2, "JSON byte budget exceeded")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            require(key not in out, "duplicate JSON object key")
            out[key] = value
        return out

    with path.open(encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=object_pairs)
    require(type(value) is dict, "top-level JSON object required")
    return value


def verify(inst: dict[str, Any], snapshot: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    inst = validate_contract_shape(inst)
    object_shape(snapshot, SNAPSHOT_FIELDS, set(), "snapshot")
    object_shape(packet, ATTESTATION_FIELDS, set(), "attestation")
    n = integer(inst["n"])
    require(2 <= n <= 8, "unsupported relation count")
    edges = inst["edges"]
    require(type(edges) is list and len(edges) == n - 1, "not a tree")
    edge_pairs: list[tuple[int, int]] = []
    seen_edges: set[tuple[int, int]] = set()
    for raw in edges:
        require(type(raw) is list and len(raw) == 2, "edge encoding")
        a, b = map(integer, raw)
        require(0 <= a < n and 0 <= b < n and a != b, "edge endpoint")
        normalized = tuple(sorted((a, b)))
        require(normalized not in seen_edges, "duplicate edge")
        seen_edges.add(normalized)
        edge_pairs.append((a, b))

    # Check connectedness without trusting any producer-side helper.
    reached = {0}
    changed = True
    while changed:
        changed = False
        for a, b in edge_pairs:
            if a in reached and b not in reached:
                reached.add(b)
                changed = True
            if b in reached and a not in reached:
                reached.add(a)
                changed = True
    require(len(reached) == n, "disconnected tree")
    validate_optional_labels(inst, n, len(edge_pairs))

    lower = inst["lower"]
    upper = inst["upper"]
    require(type(lower) is list and type(upper) is list, "contract arrays")
    k = len(lower)
    total = integer(inst["total"])
    require(1 <= k <= 8 and len(upper) == k and 0 <= total <= 32, "contract dimensions or total")
    for lo, hi in zip(lower, upper):
        require(0 <= integer(lo) <= integer(hi) <= 32, "invalid multiplicity interval")
    require(sum(lower) <= total <= sum(upper), "empty uncertainty set")

    blocks = inst["blocks"]
    require(type(blocks) is list and len(blocks) == k, "template count")
    incident = [
        {str(edge) for edge, (a, b) in enumerate(edge_pairs) if relation in (a, b)}
        for relation in range(n)
    ]
    for block in blocks:
        require(type(block) is list and len(block) == n, "template relation count")
        for relation, rows in enumerate(block):
            require(type(rows) is list and len(rows) <= 8, "template row budget")
            for row in rows:
                require(type(row) is dict and set(row) == incident[relation], "template edge attributes")
                for value in row.values():
                    require(0 <= integer(value) <= 1024, "template key domain")

    require(type(snapshot["instance"]) is str and snapshot["instance"] == inst["name"], "snapshot instance mismatch")
    require(type(packet["instance"]) is str and packet["instance"] == inst["name"], "attestation instance mismatch")
    tables = snapshot["tables"]
    require(type(tables) is list and len(tables) == n, "snapshot relation count")
    for relation, rows in enumerate(tables):
        require(type(rows) is list and len(rows) <= 8192, "snapshot row budget")
        for row in rows:
            require(type(row) is dict and set(row) == incident[relation], "snapshot edge attributes")
            for value in row.values():
                integer(value)

    copies = packet["copies"]
    require(type(copies) is list and len(copies) == total, "attested copy count differs from shared total")
    counts = [0] * k
    used_rows: list[set[int]] = [set() for _ in range(n)]
    namespace_owner: list[dict[int, int]] = [dict() for _ in edge_pairs]
    mapped_values = 0

    for copy_id, copy_packet in enumerate(copies):
        require(type(copy_packet) is dict and set(copy_packet) == {"type", "rows"}, "copy packet shape")
        template_type = integer(copy_packet["type"])
        require(0 <= template_type < k, "unknown template type")
        counts[template_type] += 1
        rows_by_relation = copy_packet["rows"]
        require(type(rows_by_relation) is list and len(rows_by_relation) == n, "copy relation mapping")

        local_to_actual: list[dict[int, int]] = [dict() for _ in edge_pairs]
        actual_to_local: list[dict[int, int]] = [dict() for _ in edge_pairs]
        for relation in range(n):
            template_rows = blocks[template_type][relation]
            mapped_rows = rows_by_relation[relation]
            require(type(mapped_rows) is list and len(mapped_rows) == len(template_rows), "template-row mapping length")
            for template_row, raw_index in zip(template_rows, mapped_rows):
                row_index = integer(raw_index)
                require(0 <= row_index < len(tables[relation]), "snapshot row index")
                require(row_index not in used_rows[relation], "snapshot row assigned more than once")
                used_rows[relation].add(row_index)
                snapshot_row = tables[relation][row_index]
                for edge_name, local_value in template_row.items():
                    edge = int(edge_name)
                    actual_value = snapshot_row[edge_name]
                    previous_actual = local_to_actual[edge].get(local_value)
                    if previous_actual is None:
                        local_to_actual[edge][local_value] = actual_value
                    else:
                        require(previous_actual == actual_value, "inconsistent key renaming")
                    previous_local = actual_to_local[edge].get(actual_value)
                    if previous_local is None:
                        actual_to_local[edge][actual_value] = local_value
                    else:
                        require(previous_local == local_value, "non-injective key renaming")
                    mapped_values += 1

        # Fresh namespaces are required only per join edge; values from different
        # edge attributes are semantically distinct and may coincide.
        for edge, mapping in enumerate(local_to_actual):
            for actual_value in mapping.values():
                require(actual_value not in namespace_owner[edge], "join-key namespace shared by two copies")
                namespace_owner[edge][actual_value] = copy_id

    for template_type, (count, lo, hi) in enumerate(zip(counts, lower, upper)):
        require(lo <= count <= hi, f"template multiplicity {template_type} outside interval")
    require(sum(counts) == total, "shared total mismatch")
    for relation, used in enumerate(used_rows):
        require(len(used) == len(tables[relation]), "snapshot row is not covered by attestation")

    return {
        "accepted": True,
        "copies": len(copies),
        "world": counts,
        "rows": sum(len(rows) for rows in tables),
        "mapped_key_occurrences": mapped_values,
        "distinct_edge_values": sum(len(values) for values in namespace_owner),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("attestation", type=Path)
    args = parser.parse_args()
    try:
        verdict = verify(load(args.instance), load(args.snapshot), load(args.attestation))
        print(json.dumps(verdict, sort_keys=True))
    except (Rejected, KeyError, TypeError, ValueError, IndexError, RecursionError, OSError) as exc:
        print(json.dumps({"accepted": False, "reason": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
