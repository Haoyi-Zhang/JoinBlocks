#!/usr/bin/env python3
"""Validate a fresh reproduction against all retained non-observational evidence."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from compare_attestation import compare as compare_attestation
from compare_results import rows as plan_rows
from summarize import TIMING

CONTROL_OBSERVATIONS = {"cpu_s", "maxrss_kib"}
SUMMARY_OBSERVATION_KEYS = {"checker_slower_cases"}
SUMMARY_OBSERVATION_METRICS = {
    "producer_cpu_s",
    "checker_cpu_s",
    "case_cpu_s",
    "maxrss_kib",
}
CONTROL_PACKET_FILES = (
    "pointwise-cover-input.json",
    "pointwise-cover-certificate.json",
    "local-pruning-input.json",
    "local-pruning-certificate.json",
)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def compare_plan(reference: Path, candidate: Path) -> dict[str, Any]:
    expected = plan_rows(reference)
    actual = plan_rows(candidate)
    if expected != actual:
        raise AssertionError("non-observational plan cases.csv fields differ")
    for case in sorted(expected):
        for folder in ("certificates", "details"):
            relative = Path(folder) / f"{case}.json"
            if load_json(reference / relative) != load_json(candidate / relative):
                raise AssertionError(f"plan JSON differs: {relative}")
    return {
        "matching_cases": len(expected),
        "exact_certificates": len(expected),
        "exact_details": len(expected),
        "excluded_observations": sorted(TIMING),
    }


def normalized_controls(path: Path) -> dict[str, Any]:
    return {
        key: value
        for key, value in load_json(path / "controls.json").items()
        if key not in CONTROL_OBSERVATIONS
    }


def normalized_summary(path: Path) -> dict[str, Any]:
    value = load_json(path / "summary.json")
    normalized = {
        key: entry
        for key, entry in value.items()
        if key not in SUMMARY_OBSERVATION_KEYS
    }
    metrics = dict(normalized["metrics"])
    for key in SUMMARY_OBSERVATION_METRICS:
        metrics.pop(key, None)
    normalized["metrics"] = metrics
    return normalized


def exact_input_count(reference: Path, candidate: Path) -> int:
    expected = sorted(path.name for path in reference.glob("*.json"))
    actual = sorted(path.name for path in candidate.glob("*.json"))
    if expected != actual:
        raise AssertionError("regenerated input file set differs")
    for name in expected:
        if (reference / name).read_bytes() != (candidate / name).read_bytes():
            raise AssertionError(f"regenerated input bytes differ: {name}")
    return len(expected)


def validate(args: argparse.Namespace) -> dict[str, Any]:
    retained = args.retained.resolve()
    plan = compare_plan(retained / "campaign", args.campaign.resolve())
    attestation = compare_attestation(
        retained / "attestation", args.attestation.resolve()
    )

    retained_controls = retained / "controls"
    candidate_controls = args.controls.resolve()
    exact_packets = 0
    for name in CONTROL_PACKET_FILES:
        if load_json(retained_controls / name) != load_json(candidate_controls / name):
            raise AssertionError(f"control packet differs: {name}")
        exact_packets += 1
    if normalized_controls(retained_controls) != normalized_controls(candidate_controls):
        raise AssertionError("non-observational control fields differ")

    retained_summary = retained / "summary"
    candidate_summary = args.summary.resolve()
    if normalized_summary(retained_summary) != normalized_summary(candidate_summary):
        raise AssertionError("non-observational summary fields differ")
    if (retained_summary / "frontiers.dat").read_bytes() != (
        candidate_summary / "frontiers.dat"
    ).read_bytes():
        raise AssertionError("frontier plot data differ")

    input_count = exact_input_count(args.inputs_reference.resolve(), args.inputs.resolve())

    example_exact = None
    if args.example_certificate is not None:
        reference_example = (
            retained
            / "campaign"
            / "certificates"
            / "star-4-4-balanced-101.json"
        )
        example_exact = load_json(reference_example) == load_json(
            args.example_certificate.resolve()
        )
        if not example_exact:
            raise AssertionError("fresh example certificate differs")

    result = {
        "plan": plan,
        "attestation": attestation,
        "regenerated_inputs_exact": input_count,
        "exact_control_packets": exact_packets,
        "control_semantics_match_excluding_observations": True,
        "summary_scientific_fields_match_excluding_timing_observations": True,
        "frontier_plot_data_exact": True,
        "example_certificate_exact": example_exact,
        "excluded_control_observations": sorted(CONTROL_OBSERVATIONS),
        "excluded_summary_keys": sorted(SUMMARY_OBSERVATION_KEYS),
        "excluded_summary_metrics": sorted(SUMMARY_OBSERVATION_METRICS),
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retained",
        type=Path,
        default=Path("results"),
        help="retained results root (default: results)",
    )
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--controls", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--inputs-reference", type=Path, default=Path("inputs"))
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--example-certificate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = validate(args)
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()
