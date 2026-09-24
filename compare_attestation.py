#!/usr/bin/env python3
"""Compare two snapshot-attestation campaigns modulo observation-only fields."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

CASE_OBSERVATIONS = {"checker_cpu_s"}
SUMMARY_OBSERVATIONS = {"checker_cpu_s_sum", "campaign_cpu_s", "campaign_wall_s", "maxrss_kib"}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def normalized_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    normalized = [
        {key: value for key, value in row.items() if key not in CASE_OBSERVATIONS}
        for row in rows
    ]
    return sorted(normalized, key=lambda row: (row["case"], int(row["world_id"])))


def normalized_summary(path: Path) -> dict[str, Any]:
    return {
        key: value
        for key, value in load_json(path).items()
        if key not in SUMMARY_OBSERVATIONS
    }


def relative_json(directory: Path) -> dict[str, Any]:
    examples = directory / "examples"
    return {
        path.relative_to(directory).as_posix(): load_json(path)
        for path in sorted(examples.glob("*.json"))
    }


def compare(reference: Path, candidate: Path) -> dict[str, Any]:
    reference_rows = normalized_rows(reference / "cases.csv")
    candidate_rows = normalized_rows(candidate / "cases.csv")
    if reference_rows != candidate_rows:
        raise AssertionError("non-observational cases.csv fields differ")

    reference_summary = normalized_summary(reference / "summary.json")
    candidate_summary = normalized_summary(candidate / "summary.json")
    if reference_summary != candidate_summary:
        raise AssertionError("non-observational summary fields differ")

    reference_negative = load_json(reference / "negative-controls.json")
    candidate_negative = load_json(candidate / "negative-controls.json")
    if reference_negative != candidate_negative:
        raise AssertionError("negative-control outcomes differ")

    reference_examples = relative_json(reference)
    candidate_examples = relative_json(candidate)
    if reference_examples != candidate_examples:
        raise AssertionError("retained example snapshots or packets differ")

    return {
        "matching_snapshot_rows": len(reference_rows),
        "matching_summary_fields": len(reference_summary),
        "matching_negative_control_classes": len(reference_negative),
        "matching_example_json_files": len(reference_examples),
        "excluded_case_observations": sorted(CASE_OBSERVATIONS),
        "excluded_summary_observations": sorted(SUMMARY_OBSERVATIONS),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare(args.reference.resolve(), args.candidate.resolve())
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
