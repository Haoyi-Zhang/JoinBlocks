# Finite representation-invariance protocol

The protocol is fixed before evaluating the first case. It supplements, and does
not replace or enlarge, the 102 primary contracts, 20 topology cases, 306 snapshots,
2,754 membership mutations, and 68 scientific test methods.

Generate all 32 seeds 7001 through 7032 using the separate generator in
`invariance_campaign.py`. Each seed chooses 3–5 aliases, 2–4 templates, a labelled
Pruefer tree, nonuniform integer multiplicity intervals, and a feasible shared
mass. Each relation contains one common zero-key row and 0–2 independent extra
rows with keys in {0,1,2}. Rows are bags, including repetitions. This generator
imports neither the original generator nor its cases and does not retry inputs.

Evaluate identity plus six predetermined transformations: cyclic alias
renaming, cyclic template reordering with bounds, reversed edge indexing with
column renaming, bijective edge-key renaming, reversed bag-row order, and fixing
one multiplicity to the first feasible oracle world's value. The first five
transformations preserve the optimum; the last restricts the world family and
must not increase its minimax regret. Selected plans need not be identical.

For all 224 resulting cases, save the input, producer certificate, and lossless
SQLite/exhaustive oracle object. Round-trip both serializations, run the separate
plan checker, and compare certificate regret to `oracle['optimum']`. Save one case
record per execution with parent seed, transformation, expectation, and observed
values. Any disagreement or exception fails the campaign; there is no exclusion,
replacement, pruning of difficult cases, or tuning after observing results.

Only finite correctness and invariance are tested. No learned model is trained,
no statistical generalization claim is made, no production workload is sampled,
and no timing result is used as scientific evidence. These new records form a
new, explicitly identified retained suite; they are not reconstructed historical
outputs. Subsequent clean runs use different output directories and compare
inputs, certificates, decoded oracle results, and non-observational summaries.
