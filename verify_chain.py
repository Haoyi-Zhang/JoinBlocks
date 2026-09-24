#!/usr/bin/env python3
"""Compose snapshot-membership and minimax-plan certificate checks.

The two checkers remain separately implemented.  This small composition layer
accepts only when the same declared instance passes both obligations: the
join-key snapshot is a feasible isolated-template realization, and the selected
plan has the certified globally minimum worst-case additive regret for that
contract.  Acceptance is snapshot-specific and cost-model-specific; it is not a
wall-clock performance claim or a prediction about later database contents.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import attest
import checker


class Rejected(ValueError):
    pass


def verify(
    inst: dict[str, Any],
    snapshot: dict[str, Any],
    membership_packet: dict[str, Any],
    plan_certificate: dict[str, Any],
) -> dict[str, Any]:
    try:
        membership = attest.verify(inst, snapshot, membership_packet)
    except (attest.Rejected, KeyError, TypeError, ValueError, IndexError, RecursionError) as exc:
        raise Rejected(f"membership: {exc}") from exc
    try:
        plan = checker.verify(inst, plan_certificate)
    except (checker.Rejected, KeyError, TypeError, ValueError, IndexError, RecursionError) as exc:
        raise Rejected(f"plan: {exc}") from exc
    return {
        "accepted": True,
        "instance": inst["name"],
        "world": membership["world"],
        "snapshot_rows": membership["rows"],
        "copies": membership["copies"],
        "regret": plan["regret"],
        "root_frontier": plan["root_frontier"],
        "containment_masks": plan["containment_masks"],
        "coverage_records": plan["coverage_records"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("instance", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("membership_attestation", type=Path)
    parser.add_argument("plan_certificate", type=Path)
    args = parser.parse_args()
    try:
        verdict = verify(
            attest.load(args.instance),
            attest.load(args.snapshot),
            attest.load(args.membership_attestation),
            checker.load(args.plan_certificate),
        )
        print(json.dumps(verdict, sort_keys=True))
    except (Rejected, OSError) as exc:
        print(json.dumps({"accepted": False, "reason": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
