# Attested block contracts and proof-carrying minimax plans

This repository is the standalone artifact for a bounded research prototype.  It
implements two independently checked packets over the same tree-shaped connected binary inner bag-equijoin
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

- Python 3.10 or newer on Linux/POSIX (the campaigns use the standard-library
  `resource` module; native Windows execution has not been validated);
- only the Python standard library and its SQLite module;
- no network access, package installation, GPU, external solver, or private data.

Run commands from this repository root and do not use `python -O`, because the
scientific producer and tests deliberately retain assertions.

The snapshot-count adapter uses canonical decimal text with binary equality for
snapshot keys, preserving the checker's exact signed 120-bit key domain rather
than narrowing it to SQLite's 64-bit integers. Three additional adapter boundary
regressions are separate from the frozen 68-method suite:

```sh
python -B -m unittest discover -s regressions -v
```

The current producer additionally uses a call-local 4,096-entry exact-direction
LRU for support requests in all three pruning modes. Contract bounds are owned
inside the query; stored worlds are immutable and each request returns a fresh
list. Certificates, profiles and historical `support_calls` (logical requests)
are unchanged. Four separate support/cache/whole-plan regression methods are
included by the existing `regressions` CI discovery; that directory now has
seven methods, without altering the source-linked frozen 68-method inventory.
They also run alone, with current included code and the standard library:

```sh
python -B -m unittest discover -s regressions -p test_support_cache.py -v
```

The bounded tests include independent integer-world/SQL plan enumeration,
eviction, witness isolation and changed-contract calls. They are finite checks,
not snapshot-membership validation or a general implementation proof. Frozen
runtime/RSS results precede this support reuse; no new timing benefit is claimed.

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

Use a fresh output directory (the entry point also works when invoked by absolute
path from another working directory):

```sh
python full_reproduction.py --output /tmp/robust-plan-full
```

The orchestrator runs the traceable 68-method test protocol, the 102-case plan
campaign, the 306-snapshot membership campaign, controls, summaries, deterministic
input regeneration, the 20-case topology-interface route, the attestation-overhead
gate, a fresh worked certificate, retained-versus-fresh comparisons, and one
complete two-packet chain. It also runs 29 separately inventoried adapter tests
and a 32-base-contract/224-execution representation-invariance campaign, then
compares all 674 new JSON assets against a distinct regenerated directory. There
are 17 required stages with the paper directory and 16 in the standalone artifact;
only the paper-side bibliography audit is omitted in the latter. Every subprocess
return code is recorded, and a partial run is not labelled complete.  The test
protocol writes the discovered method name, source file and line, evidence area,
orientation, and associated retained inputs to `tests/inventory.json`; the
retained copy is under `results/tests/`.

The standalone artifact's `scientific-checks.yml` workflow runs these three
boundary regressions and the complete offline route on Ubuntu 24.04/Python 3.12,
with a 900-second whole-command limit, 900-second per-process CPU limit, and
3 GiB address-space limit. Failed gates remain failures; raw output and partial
results are uploaded even after failure. Preparing the workflow does not establish
that it has run on a remote runner. Local reruns do not replace the retained
historical CPU/RSS observations.

`reproduce.py` and `attestation_campaign.py` remain independently invocable for
bounded reruns.  The former accepts `--case EXACT-STEM` and `--resume`; the latter
accepts the same repeatable selector but requires a fresh directory.
`validate_reproduction.py` compares the 102/306 core evidence and exact controls.
`compare_tests.py` compares the discovered test inventory and passing logs.
`compare_topology.py` compares a distinct retained and fresh topology directory
and rejects a same-directory comparison.  Timing and high-water-memory
observations are excluded from semantic equality; inputs, packets, oracle values,
counts, acceptance decisions, and bounded-regret results are not.

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

The regression suite has 68 test methods: 40 plan-certificate methods (38
rejection-oriented), 20 membership methods (18 rejection-oriented), three
composition methods (two rejection-oriented), one independently written
crosscheck method over 36 additional small contracts, and four topology-interface
methods (one rejection-oriented).  Thus 59 methods are rejection-oriented and
nine are valid, support, validation, or crosscheck methods.  The retained
inventory identifies every method's source line and evidence area; the retained
log reports 68/68 passed.  Finite tests complement the written proofs but do not
prove the implementations correct for all admitted inputs.

The topology-interface route is auxiliary and excluded from the 102 primary
contracts and 306 snapshot totals.  It uses five pinned public JOB SQL files only
to derive connected equality-reduced tree topologies, then supplies synthetic
literal templates.  Two regimes and two seeds give 20 exact producer/checker/
oracle cases.  `results/topology/source-manifest.json` records repository commit,
SQL blob identifiers, aliases, equality counts, and derived edges.  Oracle output
uses a lossless JSON schema for tuple-keyed regret profiles.  This route is not a
JOB data or runtime benchmark.

`attestation_overhead.py` reads the campaign's actual `snapshot_rows` and
`regret_within_bound` columns.  Its retained and fresh gates both confirm 306
snapshots, 33,204 rows, all chains accepted, and all realized-regret bounds held.
The separate two-copy drift control is also end-to-end: its plan packet accepts
the declared $N=1$ family, while membership and composition reject the supplied
two-copy snapshot.  It is not counted among the 2,754 campaign mutations.

## Additional finite invariance evidence

`invariance_campaign.py` uses a separate Pruefer-tree generator for seeds
7001--7032, with nonuniform multiplicity bounds and 3--5 aliases. Each of 32
base contracts is evaluated unchanged and after alias/template/edge permutations,
a bijective key renaming, bag-row reversal, and one feasible coordinate fixation.
All 224 cases agree with the SQLite/exhaustive-plan/world oracle and satisfy
optimum invariance or nonincreasing regret under refinement. Only four base
optima are nonzero; four refinements strictly improve regret. The route performs
7,539 SQLite profile checks, separate from the primary counts. No seed is replaced.

The protocol was written before executing this suite. Inputs, certificates and
lossless oracle records are retained under `results/invariance/`; these newly
formed results are not described as reconstructed older assets. `--compare A B`
rejects identical directories, missing files, and semantic differences. These
are 32 related groups, not 224 independent queries or a population generalization
study. No model is trained. `audit_tests/` contains 25 bibliography and four
comparison-adapter test methods, separate from `tests/` and its 68 methods.

## Repository map

- `attest.py`: independent snapshot-membership checker;
- `checker.py`: independent plan-certificate checker;
- `verify_chain.py`: composition CLI over one contract and snapshot;
- `produce.py`: untrusted plan-certificate producer;
- `attestation_campaign.py`: finite end-to-end snapshot campaign and mutations;
- `attestation_overhead.py`: row-explicit packet-size and bound-consistency gate;
- `compare_attestation.py`: semantic comparison excluding observation-only timing/RSS fields;
- `test_protocol.py` and `compare_tests.py`: discovered test inventory, log, and retained/fresh comparison;
- `topology_campaign.py` and `compare_topology.py`: auxiliary pinned-topology route and comparison;
- `full_reproduction.py`: default complete reproduction route;
- `validate_reproduction.py`: combined fresh-output validation against retained 102/306 core evidence;
- `reproduce.py`: frozen 102-case plan campaign;
- `controls.py`: hedge, local-pruning, pairwise-correlation, and drift controls;
- `src/`: producer, optimizer, exact oracle, lossless oracle JSON, SQL, and model helpers;
- `tests/`: 68 deterministic regression methods, including a 36-instance independent crosscheck;
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
