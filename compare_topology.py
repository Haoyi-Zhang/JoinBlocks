#!/usr/bin/env python3
"""Compare retained and reproduced topology campaigns, excluding observations."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def normalized_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        {k: v for k, v in row.items() if not k.endswith("_cpu_seconds")}
        for row in rows
    ]


def strip_observations(value):
    if isinstance(value, dict):
        return {
            k: strip_observations(v)
            for k, v in value.items()
            if "cpu_seconds" not in k
        }
    if isinstance(value, list):
        return [strip_observations(v) for v in value]
    return value


def compare(retained: Path, reproduced: Path) -> dict:
    retained = retained.resolve()
    reproduced = reproduced.resolve()
    if retained == reproduced:
        raise RuntimeError("retained and reproduced topology directories must be distinct")
    required = {"source-manifest.json", "cases.csv", "summary.json"}
    for directory in (retained, reproduced):
        missing = sorted(name for name in required if not (directory / name).is_file())
        for subdir in ("inputs", "certificates", "oracles"):
            if not (directory / subdir).is_dir():
                missing.append(subdir + "/")
        if missing:
            raise RuntimeError(f"incomplete topology evidence in {directory}: {missing}")
    for name in ("source-manifest.json",):
        if (retained / name).read_bytes() != (reproduced / name).read_bytes():
            raise RuntimeError(f"byte mismatch: {name}")
    for subdir in ("inputs", "certificates", "oracles"):
        left = sorted(p.name for p in (retained / subdir).glob("*.json"))
        right = sorted(p.name for p in (reproduced / subdir).glob("*.json"))
        if left != right:
            raise RuntimeError(f"file set mismatch in {subdir}")
        for name in left:
            if (retained / subdir / name).read_bytes() != (reproduced / subdir / name).read_bytes():
                raise RuntimeError(f"byte mismatch: {subdir}/{name}")
    left_rows = normalized_rows(retained / "cases.csv")
    right_rows = normalized_rows(reproduced / "cases.csv")
    if left_rows != right_rows:
        raise RuntimeError("non-observational topology case rows differ")
    left_summary = strip_observations(json.loads((retained / "summary.json").read_text()))
    right_summary = strip_observations(json.loads((reproduced / "summary.json").read_text()))
    if left_summary != right_summary:
        raise RuntimeError("non-observational topology summaries differ")
    return {
        "cases": len(left_rows),
        "inputs": len(list((retained / "inputs").glob("*.json"))),
        "certificates": len(list((retained / "certificates").glob("*.json"))),
        "oracles": len(list((retained / "oracles").glob("*.json"))),
        "semantic_match": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("retained", type=Path)
    parser.add_argument("reproduced", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.retained, args.reproduced), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
