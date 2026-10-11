# Plan commitment, future windows, and actual execution

At commitment all three policies know the literal templates, complete bounds and
total, exact template profiles, and initial attested world (24,8). They do not
receive future snapshots or the future schedule as selection inputs. Robust
commits one minimax tree. Known-fixed commits an ordinary scalar-DP optimum at
that same initial world. Adaptive uses scalar DP after each later revelation;
it shares the profile cache and pays only for the work it actually performs.
No assumed deployment penalty or artificial reoptimization delay is added.

Membership returns the actual world. Robust/fixed do not conceal or discard this
fact: their policy forbids switching trees within the session. Under unrestricted
changes there is no abstract-cost advantage over an exact known-world optimum.
`src/reuse.py` checks the plan once, owns its contract and tree, and accepts only
increasing window identifiers. Per-window checking owns input copies and returns
immutable row bags. Failure revokes the current gate, and changes to any contract
field require a new session. This is a local API; a caller must obey the gate.
It neither authenticates capture nor controls an external DBMS.

## Physical contract and schedules

`reuse_experiment.contract()` extends the mathematical hedge with one universal
center row and eight duplicate rows at each leaf. The four-alias star has two
templates, seven center rows and eight rows per leaf per copy. There are 32
isolated copies, with each count in 0..32. Six legal trees give three profiles:
(608,736), (672,672), (736,608). All 33 integer worlds are exhausted for the
minimax value, 2048. Each world produces 16,384 final row-identity tuples.

All three schedules have 24 windows and query counts repeating 4,8,16,8 (216
queries per policy/run). The first multiplicity starts at 24:

- Stationary: 24 throughout.
- Migration: 24,22,...,8; four further windows at 8; 10,12,...,24;
  three final windows at 24. The second coordinate is always 32 minus the first.
- Bursts: four windows at 24, eight at 8, four at 24, eight at 8.

Mix changes model replacement of isolated tenant components, and changing query
counts model batch demand. This is an endogenous synthetic stress workload, not
observed production drift, a distributional sample, or real JOB execution.
No schedule is selected by a regret oracle or replaced based on its outcome.
Source schedules are specified before the execution loop. The fixed-policy
selection functions take only initial information; future snapshots are
materialized after commitment. Keys and row shuffles are regenerated per window.

## Execution and timing

`src/physical.HashPlan` compiles and executes the exact binary tree. Each node
materializes tuples and hashes the right child on its unique crossing key. It
retains row identities and duplicates, uses exact integer equality, and admits
at most 200,000 emitted intermediate rows and 1,000,000 hash inputs per query.
It models neither payload columns, disk I/O, indexes, concurrency, nor spills.
SQLite is used only for independent untimed bag verification, not plan selection
or latency attribution. Output/intermediate counts are checked against profiles.

Three serial repeats rotate the three policies' order at each window. For each
policy, total measured time includes profile construction, initial attestation,
policy-specific selection and tree installation, robust certificate production
and checking, later snapshot copying/freezing and membership checking, adaptive
DP/installation, and all 216 requested hash-join executions. Initial and later
snapshot generation are reported as shared acquisition observations separately;
adding them gives `total_with_acquisition_wall_s`. Transactional capture,
template discovery, output serialization, and untimed oracle/bag checks are not
deployment measurements. Wall and process-CPU observations are retained.
The local Windows run is not CPU-pinned; no inferential significance is claimed.

One untimed validation execution precedes every policy/window batch for all three
policies. The timed loop reruns the actual joins for every query, not the cost
formula or a SQL COUNT query. Across nine runs this yields 648 bag-checked
policy-windows and 5832 timed queries. The Python code and JSON data are small,
local, and require no downloads or service account.

## Evidence and interpretation

`results/reuse/contract.json` and `certificate.json` define the consumed model and
fixed robust tree. `rounds.json.gz` records every scenario/repeat/window/policy,
world, query count, actual tree, cost, regret, operation counts, and stage times.
`runs.json` records setup, refresh, selection and execution totals. `summary.json`
contains medians and min/max wall totals, host/runtime identity, and exclusions.
Timings are observations, not deterministic fields.

The burst schedule saves 73,728 intermediate rows relative to known-fixed and
halves its maximum observed per-query regret from 2048 to 1024. Migration ties
total work but also halves maximum loss. Stationary data adds 221,184 unnecessary
rows for robust reuse. Adaptive has zero regret, lower work and lower median time
than robust in all three schedules. Small fixed-policy timing differences do not
establish a general speedup. These findings support a restricted fixed-tree work
bound, not a reason to forbid cheap adaptation or a venue-level novelty claim.

The ten tests in `regressions/test_reuse.py` are separate from the original 68
methods. They include all 102 retained contracts at two future worlds, exact
known-world DP for all 33 physical-contract worlds, one plan-check-only lifetime,
refresh failures, replay, changed-contract rejection, ownership/immutability,
SQL bag equivalence, wide integer keys, and illegal physical trees. Run them with
`python -B -m unittest discover -s regressions -p test_reuse.py -v`.

To regenerate physical observations, use a fresh output directory with
`python -B reuse_experiment.py --output OUTPUT --repeats 3`. This route supplements
the original full-reproduction entry point; it does not silently redefine that
entry point's historical CPU/RSS observations or 102/306 denominators.
