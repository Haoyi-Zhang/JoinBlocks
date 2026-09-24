# Attested block contracts and proof-carrying minimax plans

This repository is the standalone artifact for a bounded research prototype.  It
implements two independently checked packets over the same acyclic bag-equijoin
contract:

1. a **snapshot-membership attestation** that partitions every join-key row
   occurrence into isolated renamed copies of supplied literal templates; and
2. a **plan certificate** that proves tight connected-subquery containment,
   complete uniform-dominance coverage of binary join plans, and globally
   minimum worst-case additive regret under the declared abstract cost.

When both checkers accept the same contract and snapshot, the accepted snapshot
corresponds to one feasible integer world of the contract, the selected plan is
minimax over the whole declared family, and its regret on that snapshot is at
most the certified value.  The proof is in `docs/proofs.md`; packet fields and
trusted boundaries are in `docs/certificate-format.md`.

## What acceptance does and does not mean

The snapshot checker validates an exact join-key projection under bag semantics:
every row occurrence is covered exactly once, every template-row occurrence is
mapped in order, each edge-local key renaming is consistent and injective, key
namespaces are disjoint across copies, and the resulting template counts satisfy
the interval and shared-total contract.  It thereby checks membership of the
**current supplied snapshot**; it does not discover the templates, authenticate
where the snapshot came from, predict later updates, or provide an incremental
transactional capture mechanism.

The plan checker recomputes template profiles, legal connected splits, cost
profiles, support bounds, coverage obligations, and root witnesses.  Its cost is
the sum of intermediate result cardinalities.  Acceptance is not a claim about
wall-clock latency, physical operators, indexes, memory, or a production DBMS.
Neither Python checker is mechanically verified.

## Requirements

- Python 3.10 or newer;
- only the Python standard library and its SQLite module;
- no network access, package installation, GPU, external solver, or private data.

Run commands from this repository root and do not use `python -O`, because the
scientific producer and tests deliberately retain assertions.

## One complete checked chain

```sh
python verify_chain.py \
  inputs/star-4-4-balanced-101.json \
  results/attestation/examples/star-4-4-balanced-101-w0.snapshot.json \
  results/attestation/examples/star-4-4-balanced-101-w0.attestation.json \
  results/campaign/certificates/star-4-4-balanced-101.json
```

The command first invokes the independent membership checker and then the
independent plan checker.  A malformed packet exits with status 2 and a reason.
All contract, snapshot, attestation, and plan-certificate objects use closed
schemas.  Missing required fields, unknown fields, top-level arrays, duplicate
JSON object keys, and booleans or floating-point values in exact-integer fields
are rejected before semantic acceptance.

The two checkers can also be invoked separately:

```sh
python attest.py INSTANCE.json SNAPSHOT.json ATTESTATION.json
python checker.py INSTANCE.json CERTIFICATE.json
```

`produce.py` is an untrusted plan-certificate producer.  `src/attestation.py`
contains the untrusted snapshot/attestation materializer used by tests and the
finite campaign; `attest.py` does not import it.

## Full deterministic reproduction

Use fresh output directories:

```sh
python -m unittest discover -s tests -v
python reproduce.py --output /tmp/robust-plan-campaign
python attestation_campaign.py --output /tmp/robust-plan-attestation
python controls.py --output /tmp/robust-plan-controls
python summarize.py \
  --results /tmp/robust-plan-campaign \
  --output /tmp/robust-plan-summary
python compare_results.py results/campaign /tmp/robust-plan-campaign
python compare_attestation.py \
  results/attestation /tmp/robust-plan-attestation
python generate_inputs.py /tmp/robust-plan-inputs
python produce.py \
  inputs/star-4-4-balanced-101.json \
  /tmp/robust-plan-example-certificate.json
python validate_reproduction.py \
  --campaign /tmp/robust-plan-campaign \
  --attestation /tmp/robust-plan-attestation \
  --controls /tmp/robust-plan-controls \
  --summary /tmp/robust-plan-summary \
  --inputs /tmp/robust-plan-inputs \
  --example-certificate /tmp/robust-plan-example-certificate.json
```

`reproduce.py` runs all 102 frozen primary instances and writes each completed
case durably.  It accepts `--case EXACT-STEM` and `--resume` for bounded chunks.
`attestation_campaign.py` accepts the same repeatable `--case` selector but
requires a fresh directory.  `generate_inputs.py` deterministically rebuilds the
102 JSON inputs.  `validate_reproduction.py` performs the combined retained-data
check: plan and membership semantics, exact regenerated inputs and control
packets, non-observational control and summary fields, frontier plot data, and
the fresh worked-example certificate.  It deliberately excludes only the
listed timing and high-water-memory observations.

## Retained evidence

The plan campaign contains 102 exact instances.  Every instance agrees with the
exhaustive bounded oracle and the separate plan checker.  SQLite recomputes
12,816 connected template/subquery counts, and retained bag checks cover 607
primary plan/world pairs.  The exact-support test covers 83,150 bounded cases.
Targeted controls include a three-plan hedge whose middle plan is required for
minimum regret and a six-alias counterexample to one-local-minimax-plan pruning.

The membership campaign materializes three deterministic feasible worlds for
each primary input: 306 accepted snapshots, 2,106 isolated copies, and 33,204
row occurrences.  SQLite independently recomputes 7,812 connected-subquery
counts.  On every snapshot, direct enumeration of realized plan costs confirms
that selected-plan regret is no larger than the plan certificate; the bound is
tight on 126 snapshots.  Nine semantic mutation classes produce 2,754 attempted
corruptions, all rejected with none skipped.

The regression suite has 64 test methods: 40 plan-certificate methods (38
rejection-oriented), 20 membership methods (18 rejection-oriented), three
composition methods (two rejection-oriented), and one independently written
crosscheck method that exercises 36 additional small contracts.  Thus 58 methods
are rejection-oriented and six are valid, support-sweep, composition, or
crosscheck methods.  Finite tests complement the written proofs but do not prove
the implementations correct for all admitted inputs.

## Repository map

- `attest.py`: independent snapshot-membership checker;
- `checker.py`: independent plan-certificate checker;
- `verify_chain.py`: composition CLI over one contract and snapshot;
- `produce.py`: untrusted plan-certificate producer;
- `attestation_campaign.py`: finite end-to-end snapshot campaign and mutations;
- `compare_attestation.py`: semantic comparison excluding observation-only timing/RSS fields;
- `validate_reproduction.py`: combined fresh-output validation against all retained non-observational evidence;
- `reproduce.py`: frozen 102-case plan campaign;
- `controls.py`: hedge, local-pruning, pairwise-correlation, and drift controls;
- `src/`: producer, optimizer, exact oracle, SQL and model helpers;
- `tests/`: 64 deterministic regression methods, including a 36-instance independent crosscheck;
- `inputs/`: exact frozen JSON contracts;
- `results/`: retained raw campaign, control, test, and reproduction evidence;
- `claim_evidence_ledger.csv`: material claim-to-evidence map;
- `external_resources.csv`: scholarly, rules, runtime, and license provenance;
- `docs/`: proof, packet, protocol, and literature records.

## Scope boundary

The strongest supported statement is conditional and exact for a restricted
model: connected binary inner bag-equijoins on a tree; supplied finite literal
block templates; isolated per-edge namespaces; integer copy-count intervals with
one shared total; and additive intermediate-cardinality cost.  Automatic template
discovery, arbitrary overlapping correlations, cyclic queries, physical-property
states, production runtime, transactional snapshot acquisition, and future-drift
prediction are not claimed.

The software source written for this artifact is covered by `LICENSE`.  Cited
papers and publisher template files are not redistributed here and retain their
own terms.
