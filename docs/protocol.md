# Frozen protocol and measured scope

The artifact has two linked finite campaigns: a 102-instance plan-certificate
campaign and a 306-snapshot membership/composition campaign.  Inputs, inclusion
rules, baselines, tie breaking, mutations, and exact-oracle checks were fixed
before interpreting the new snapshot results.  The campaigns validate the
implementation and exercise the theorem boundaries; they are not random samples
of production workloads and support no workload-population confidence interval.

## 1. Plan-contract instances

### Generated factorial

The primary factorial is the full Cartesian product of:

- tree shape: `star`, `path`, `branch`;
- relation count: `n in {4,5,6,7}`;
- template count: `K in {4,6}`;
- correlation regime: `balanced`, `skewed`;
- seed: `101`, `202`.

All 96 combinations are included.  Leaves contain two zero-key rows; internal
relations contain four binary-key rows.  In the balanced regime every column has
two zeros, holding all unary and binary counts fixed across template types while
higher-order row correlations vary.  In the skewed regime the zero count is one,
two, or three.  Columns are independently permuted inside each literal template.

Copy-count bounds are `lower=0`, `upper=3`.  The shared total is five for `K=4`
and nine for `K=6`, yielding 40 and 580 feasible integer worlds respectively.
Exact generated JSON inputs are retained.

### Original schema-derived cases

Six seven-alias cases use the acyclic commerce graph

```text
customer--orders--lineitem--part
                     |
                  supplier--nation--region
```

with seeds 303, 404, and 505 in paired unfiltered and relation-locally filtered
forms.  Rows and queries are original and tiny.  No TPC-H `dbgen` data, JOB data,
or benchmark query result is represented as executed.  Foreign keys hold in the
unfiltered templates; local filtering can remove matching dimension rows.

Together these form the frozen 102 input contracts.

## 2. Exact plan oracle

For each template and every nonempty connected alias subset, SQLite independently
computes bag `COUNT(*)`.  The oracle enumerates every legal connected binary plan
and every feasible integer world, computes exact additive intermediate-cardinality
costs, and groups identical profiles only while evaluating exact regret.  It does
not remove distinct algebraic plans from equivalence checks.  Common root terms
cancel in pairwise differences.

Every primary case requires agreement among:

- the untrusted producer;
- the independently written plan checker;
- the exhaustive plan/world oracle;
- a separately generated componentwise-dominance frontier.

Bag results retain row identities and duplicates.  All plans are bag-compared
when `n<=4`; otherwise all distinct plans selected by the certified method and
four baselines are compared.  The checked worlds are the first, last, and the
selected plan's adversarial world in oracle order, deduplicated.

The retained primary plan evidence contains 12,816 SQLite template/subquery
checks and 607 plan/world bag comparisons.  Controls add all 120 plans in all 40
worlds of the local-pruning case and all six plans in both hedge worlds.

## 3. Plan-selection baselines

All policies use the same legal plan universe, contract, abstract cost, and
deterministic string-order tie breaking.

- **Point estimate.**  Allocate residual mass as equally as possible among
  noncapped coordinates using exact rational arithmetic, then minimize estimated
  cost.
- **Worst cost.**  Minimize a plan's maximum cost over the declared worlds.
- **Independent-cardinality box.**  Use exact connected marginal intervals but
  independently maximize each noncancelled intermediate-state difference, then
  solve the resulting conservative minimax problem exactly over all plans.
- **Local minimax.**  Retain only one locally lowest-regret expansion per state.
  This deliberately lacks the uniform-coverage argument and is retained as a
  negative baseline.

PARQO, EXPAND, Roq, the 2026 coreset method, and deployed DBMS optimizers were not
reimplemented or reported as executed.  No model training or parameter fitting
occurs.

## 4. Plan-certificate tests and controls

Thirty original malformed/semantic mutation methods attack missing or incorrect
containment, illegal or duplicated plans, incomplete or false coverage, invalid
root thresholds, invalid lower witnesses, wrong regret, parser ambiguity, and
admission budgets.  A support sweep exhausts:

- `K in {1,2,3}`;
- every coordinate bound `0 <= lower <= upper <= 2`;
- every feasible shared total;
- every direction in `{-2,-1,0,1,2}^K`.

This yields 83,150 exact comparisons with direct integer-world maximization.
Eighteen edge-contract cases vary `K` through 1, 2, 3, 4, 6, and 8, including
zero-total, fixed, and shared-mass contracts; the largest has 1,107 worlds.

The realizable hedge has plan costs `(6,14)`, `(10,10)`, `(14,6)` and regrets
`(8,4,8)`.  Removing the middle plan preserves the pointwise lower envelope but
raises best deterministic regret from four to eight.  The six-alias local-pruning
control has 120 plans and 40 worlds; global minimum regret is 36 while the local
policy yields 44.

## 5. Snapshot-membership campaign

For every one of the 102 input contracts, the campaign deterministically chooses
three distinct feasible worlds:

1. residual mass filled in ascending template order;
2. a normalized near-balanced allocation;
3. residual mass filled in descending template order.

For each world, `src/attestation.py` materializes isolated copies with fresh
per-edge key namespaces, independently shuffles every relation's rows, and writes
an untrusted row-partition packet.  The independent checker then derives all
renamings itself.  The production order is not visible in the snapshot.

The resulting 306 accepted snapshots contain:

- 2,106 template copies;
- 33,204 snapshot row occurrences;
- snapshot JSON sizes up to 5,642 bytes;
- attestation JSON sizes up to 932 bytes.

For every snapshot, SQLite recomputes all connected-subquery counts and compares
them with `H_S dot w`: 7,812 checks in total.  `verify_chain.py` then checks the
membership and retained plan certificate on the same input.  All 306 chains
accept.

To test the composed regret statement rather than only packet acceptance, the
campaign enumerates every legal plan's cost from the realized SQLite profile.  In
all 306 snapshots, the selected plan's realized regret is no larger than its
certificate value; the bound is exact on 126 snapshots.

## 6. Membership negative controls

Nine deterministic mutation operators are attempted on every accepted snapshot:

1. duplicate one row assignment;
2. leave one snapshot row uncovered;
3. remove a required edge attribute;
4. add an extra edge attribute;
5. violate the shared copy count;
6. bind the snapshot to a different instance name;
7. share one edge namespace across two copies;
8. make a per-edge renaming noninjective;
9. make one local key rename inconsistently across occurrences/endpoints.

All 2,754 attempted mutations are rejected and none is skipped.  Additional unit
tests reject unknown template types, boolean row indices, changed templates, and
duplicate JSON keys.

The full regression suite has 64 methods: 40 plan-certificate methods
(38 rejection-oriented), 20 membership methods (18 rejection-oriented), three
composition methods (two rejection-oriented), and one independent crosscheck
method covering 36 small contracts.  These are finite attacks, not exhaustive
malicious-input coverage.

## 7. Measured plan outcomes

Across the 102 frozen contracts, exact minimax regret is:

- lower than point estimation in 6 cases and tied in 96;
- lower than worst-cost selection in 16 cases and tied in 86;
- lower than the independent-cardinality-box policy in 10 cases and tied in 92;
- lower than local minimax in 5 cases and tied in 97.

There are 37 zero-regret optima.  Root frontier widths range from 1 to 21.
Canonical plan certificates range from 1,758 to 29,923 bytes.  In the original
single observation per case, checking is slower than producing in 80 of 102
cases.  These observations are not repeated-performance or DBMS-speed claims.

## 8. Resource protocol

Scientific runs are serial.  When available, the process is pinned to one CPU and
uses a 3 GiB address-space limit.  No GPU, external compute, model API, private
dataset, or child scientific worker is used.  The project ceilings are four CPU
cores, 4 GiB RAM, no swap, 8 CPU-hours, 1 GiB downloads, 2 GiB expanded inputs,
and 128 MiB per final ZIP.

The original completed plan campaign's per-case CPU sum is 18.024827583 seconds.
The retained membership campaign uses 4.338805182 process CPU seconds and peaks
at 98,224 KiB RSS.  `results/resource-accounting.json` records a conservative
lower bound for all measured scientific commands and explicitly lists gaps.
Compilation, web-managed literature transfer, and some interrupted exploratory
invocations are not claimed as byte- or CPU-exact campaign totals.

## 9. Reproduction and comparison policy

`reproduce.py` writes a fresh plan campaign.  `compare_results.py` compares all
non-observational CSV fields plus every certificate and detail object with the
retained campaign; CPU, wall-time, and RSS are deliberately excluded from exact
semantic equality.  `attestation_campaign.py` writes a fresh membership campaign.
`compare_attestation.py` compares it with the retained campaign.  The semantic
comparison excludes only `checker_cpu_s`, total CPU, wall time, and RSS; worlds,
counts, acceptance, SQL matches, regret checks, packet sizes, example packets,
and mutation outcomes must match.

A successful command demonstrates reproduction of the finite retained evidence.
It is not, by itself, a proof of the mathematical theorems or of checker
correctness.
