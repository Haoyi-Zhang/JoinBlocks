#!/usr/bin/env python3
"""Run the complete regression suite and emit a source/input-linked inventory."""
from __future__ import annotations

import argparse
import inspect
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT_ASSOCIATIONS = {
    "test_attestation": [
        "generated: src.generate.make(6, star, 4, balanced, 1)",
        "generated: src.attestation.materialize_attestation",
    ],
    "test_certificate": [
        "generated: src.generate.make(6, star, 4, balanced, 1)",
        "generated: exhaustive bounded-mass directions in SupportTests",
    ],
    "test_chain": [
        "inputs/star-4-4-balanced-101.json",
        "results/campaign/certificates/star-4-4-balanced-101.json",
    ],
    "test_crosscheck": [
        "generated: 36 contracts over n=3..5, three shapes, two regimes, two seeds",
    ],
    "test_job_topologies": [
        "benchmarks/job-tree-topologies.json",
        "generated: src.generate.make_tree/make_job_topology",
    ],
}


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def category(test_id: str) -> tuple[str, str]:
    module, cls, method = test_id.split(".", 2)
    if module == "test_certificate":
        if cls == "SupportTests":
            return "plan", "support"
        return "plan", "valid" if method == "test_valid" else "rejection"
    if module == "test_attestation":
        return "membership", "valid" if method in {"test_valid", "test_three_campaign_worlds"} else "rejection"
    if module == "test_chain":
        return "composition", "valid" if method == "test_valid_chain" else "rejection"
    if module == "test_crosscheck":
        return "independent-crosscheck", "crosscheck"
    if module == "test_job_topologies":
        return "topology-interface", "rejection" if method == "test_tree_validation_rejects_non_trees" else "validation"
    raise RuntimeError(f"unclassified test: {test_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"))
    tests = list(flatten(suite))
    records = []
    counts: dict[str, int] = {}
    orientations: dict[str, int] = {}
    for test in tests:
        test_id = test.id()
        module = test_id.split(".", 1)[0]
        method = getattr(test, test._testMethodName)
        source = Path(inspect.getsourcefile(method) or "").resolve()
        line = inspect.getsourcelines(method)[1]
        area, orientation = category(test_id)
        counts[area] = counts.get(area, 0) + 1
        orientations[orientation] = orientations.get(orientation, 0) + 1
        records.append({
            "test_id": test_id,
            "source_file": source.relative_to(ROOT).as_posix(),
            "source_line": line,
            "area": area,
            "orientation": orientation,
            "input_associations": INPUT_ASSOCIATIONS[module],
        })

    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    log = stream.getvalue()
    (args.output / "unittest.txt").write_text(log, encoding="utf-8")
    inventory = {
        "schema_version": 1,
        "discovered_methods": len(records),
        "records": records,
    }
    (args.output / "inventory.json").write_text(json.dumps(inventory, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    summary = {
        "schema_version": 1,
        "command": "python test_protocol.py --output OUTPUT",
        "discovered_methods": len(records),
        "tests_run": result.testsRun,
        "passed": result.wasSuccessful(),
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "area_counts": counts,
        "orientation_counts": orientations,
        "rejection_oriented_methods": orientations.get("rejection", 0),
        "non_rejection_methods": len(records) - orientations.get("rejection", 0),
    }
    (args.output / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0 if result.wasSuccessful() and result.testsRun == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
