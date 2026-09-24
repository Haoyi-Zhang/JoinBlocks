"""Untrusted producer for snapshot-membership attestations.

A snapshot is the join-key projection of the participating relations.  The
attestation maps every supplied template-row occurrence to exactly one snapshot
row.  The independent checker in ``attest.py`` validates the mapping, derives
all key renamings itself, and checks copy-count feasibility and namespace
isolation.
"""
from __future__ import annotations

import copy
import random
from typing import Any


def feasible_world(inst: dict[str, Any], order: list[int] | None = None) -> list[int]:
    """Return one integral world by filling residual mass in the given order."""
    lo = list(inst["lower"])
    hi = list(inst["upper"])
    remaining = inst["total"] - sum(lo)
    if remaining < 0:
        raise ValueError("infeasible lower bounds")
    if order is None:
        order = list(range(len(lo)))
    if sorted(order) != list(range(len(lo))):
        raise ValueError("order must be a permutation")
    world = lo
    for j in order:
        take = min(hi[j] - world[j], remaining)
        world[j] += take
        remaining -= take
    if remaining:
        raise ValueError("infeasible upper bounds")
    return world


def balanced_world(inst: dict[str, Any]) -> list[int]:
    """Return a deterministic near-balanced feasible integral world."""
    lo = list(inst["lower"])
    hi = list(inst["upper"])
    world = lo.copy()
    remaining = inst["total"] - sum(world)
    while remaining:
        choices = [j for j in range(len(world)) if world[j] < hi[j]]
        if not choices:
            raise ValueError("infeasible contract")
        # Fill the currently smallest normalized coordinate, then by index.
        j = min(choices, key=lambda x: ((world[x] - lo[x]) / max(1, hi[x] - lo[x]), x))
        world[j] += 1
        remaining -= 1
    return world


def campaign_worlds(inst: dict[str, Any]) -> list[list[int]]:
    """Three deterministic, deduplicated witnesses spanning the bounded mass."""
    k = len(inst["lower"])
    candidates = [
        feasible_world(inst, list(range(k))),
        balanced_world(inst),
        feasible_world(inst, list(reversed(range(k)))),
    ]
    out: list[list[int]] = []
    for world in candidates:
        if world not in out:
            out.append(world)
    return out


def materialize_attestation(
    inst: dict[str, Any], world: list[int], *, seed: int = 0
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Materialize a shuffled snapshot and its untrusted row-partition packet.

    Key values are deterministic injective renamings, distinct per copy and
    edge.  Relation rows are shuffled independently so the checker cannot rely
    on construction order.
    """
    if len(world) != len(inst["blocks"]):
        raise ValueError("world dimension")
    if any(type(x) is not int for x in world):
        raise ValueError("world must be integral")
    if any(x < l or x > u for x, l, u in zip(world, inst["lower"], inst["upper"])):
        raise ValueError("world outside intervals")
    if sum(world) != inst["total"]:
        raise ValueError("world violates shared total")

    n = inst["n"]
    tables: list[list[dict[str, int]]] = [[] for _ in range(n)]
    copies: list[dict[str, Any]] = []
    copy_index = 0
    for template_type, count in enumerate(world):
        for _ in range(count):
            assignment: list[list[int]] = []
            for relation, template_rows in enumerate(inst["blocks"][template_type]):
                row_indices: list[int] = []
                for template_row in template_rows:
                    actual_row = {
                        edge: (copy_index + 1) * 10_000_000 + (int(edge) + 1) * 10_000 + local
                        for edge, local in template_row.items()
                    }
                    row_indices.append(len(tables[relation]))
                    tables[relation].append(actual_row)
                assignment.append(row_indices)
            copies.append({"type": template_type, "rows": assignment})
            copy_index += 1

    # Shuffle every relation and translate certificate row indices.  A distinct
    # derived seed makes the packet stable while avoiding construction-order rows.
    for relation, rows in enumerate(tables):
        order = list(range(len(rows)))
        random.Random((seed + 1) * 1_000_003 + relation * 9_973).shuffle(order)
        inverse = {old: new for new, old in enumerate(order)}
        tables[relation] = [rows[old] for old in order]
        for copy_packet in copies:
            copy_packet["rows"][relation] = [inverse[x] for x in copy_packet["rows"][relation]]

    snapshot = {"instance": inst["name"], "tables": tables}
    packet = {"instance": inst["name"], "copies": copies}
    return snapshot, packet


def clone_packet(snapshot: dict[str, Any], packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Convenience helper used only by deterministic negative controls."""
    return copy.deepcopy(snapshot), copy.deepcopy(packet)
