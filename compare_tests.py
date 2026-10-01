#!/usr/bin/env python3
"""Compare retained and fresh test inventories and pass summaries."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compare(retained: Path, fresh: Path) -> dict:
    retained = retained.resolve(); fresh = fresh.resolve()
    if retained == fresh:
        raise RuntimeError("retained and fresh test directories must be distinct")
    for name in ("inventory.json", "summary.json", "unittest.txt"):
        if not (retained / name).is_file() or not (fresh / name).is_file():
            raise RuntimeError(f"missing test evidence: {name}")
    if load(retained / "inventory.json") != load(fresh / "inventory.json"):
        raise RuntimeError("test inventories differ")
    left = load(retained / "summary.json"); right = load(fresh / "summary.json")
    if left != right:
        raise RuntimeError("test summaries differ")
    for directory in (retained, fresh):
        text = (directory / "unittest.txt").read_text(encoding="utf-8")
        if f"Ran {left['tests_run']} tests" not in text or not text.rstrip().endswith("OK"):
            raise RuntimeError(f"test log does not record a clean pass: {directory}")
    return {
        "test_methods": left["tests_run"],
        "rejection_oriented_methods": left["rejection_oriented_methods"],
        "inventory_exact": True,
        "summary_exact": True,
        "both_logs_pass": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("retained", type=Path)
    parser.add_argument("fresh", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.retained, args.fresh), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
