# Inputs, packets, and checker semantics

The artifact has one shared contract plus two packet types.  All JSON documents
must have a top-level object, be at most 32 MiB, and contain no duplicate object
keys.  Fields described as integers accept exact JSON integers only: booleans and
floating-point values are rejected.  Certificate integers are bounded to 120
bits unless a tighter field limit is stated.  Object schemas are closed: every
required field must occur and every field not explicitly listed as optional is
rejected.  This rule applies recursively to the contract, snapshot, attestation,
plan certificate, containment records, frontier states, and lower witnesses.

## 1. Shared contract input

An input object contains:

- `name`: instance identifier bound into all packets;
- `n`: number of relation aliases, with `2 <= n <= 8`;
- `edges`: exactly `n-1` distinct endpoint pairs forming a connected tree;
- `lower`, `upper`: template-copy bounds, with `1 <= K <= 8` and
  `0 <= lower[j] <= upper[j] <= 32`;
- `total`: shared copy total, `0 <= total <= 32`, with a nonempty feasible set;
- `blocks`: `K` literal templates, each an `n`-element list of bag tables.

These seven fields are required.  The only admitted optional contract fields are
`family`, `regime`, `seed`, `provenance`, `aliases`, and `edge_attributes`; any
other contract field is rejected.  `name`, `family`, `regime`, `provenance`, and
labels are length-bounded strings, while `seed` is an exact bounded integer.

A template table is a list of at most eight rows.  Each row is an object whose
keys are exactly the decimal edge indices incident to that relation and whose
values are local nonnegative integer keys at most 1024.  Repeated equal rows are
separate bag occurrences.  The admitted descriptive fields do not change the mathematical semantics, but
their types, lengths, and list shapes are still checked.

Every conceptual copy receives an injective fresh renaming on each edge.  Key
values on different edge attributes are semantically separate and may coincide.

## 2. Snapshot JSON

A complete join-key snapshot has the form

```json
{
  "instance": "same-name-as-contract",
  "tables": [
    [ {"0": 10001}, {"0": 10002} ],
    [ {"0": 10001, "1": 20001} ],
    [ {"1": 20001} ]
  ]
}
```

The snapshot object contains exactly `instance` and `tables`.  `tables` has one bag table per alias.  Every row has exactly the incident edge
attributes for that alias.  Each table may have at most 8,192 row occurrences.
Rows are addressed by zero-based position, so duplicates remain distinguishable.
The checker accepts only a complete supplied projection; it does not query a DBMS
or authenticate how the projection was captured.

Snapshot keys are exact signed integers with at most 120 magnitude bits. The
SQLite snapshot-count adapter binds their canonical decimal strings to binary
text columns: this injective encoding preserves equality without narrowing keys
to SQLite's signed 64-bit `INTEGER` domain. It does not change bag multiplicity,
the admitted key domain, or the cost model.

## 3. Snapshot-membership packet

A membership packet has the form

```json
{
  "instance": "same-name-as-contract",
  "copies": [
    {
      "type": 0,
      "rows": [
        [3, 0],
        [1],
        [4]
      ]
    }
  ]
}
```

The attestation object contains exactly `instance` and `copies`.  There must be exactly `total` copy records.  A record contains exactly `type` and
`rows`.  `type` is a template index.  `rows` has one list per relation; the list
length equals that template table's row count.  Entry position identifies the
ordered template-row occurrence, and its integer value is the zero-based snapshot
row index assigned to it.

`attest.py` derives each local-to-actual key map from the mapped rows and verifies:

- graph, schema, contract feasibility, and all admission budgets;
- every snapshot row index is used exactly once;
- each ordered template-row occurrence is mapped exactly once;
- equal local edge keys map consistently at both endpoint relations;
- each per-copy edge map is injective;
- no actual key on one edge is shared between two copies;
- counted template types satisfy all bounds and the shared total.

Acceptance returns the feasible `world` vector, copy count, row count, mapped key
occurrences, and distinct per-edge actual values.  The packet never supplies a
renaming map for the checker to trust.

CLI:

```sh
python attest.py INSTANCE.json SNAPSHOT.json ATTESTATION.json
```

Success prints a JSON object with `"accepted": true` and exits 0.  Rejection
prints `"accepted": false` plus a reason and exits 2.

## 4. Plan-certificate top-level schema

A plan certificate contains exactly `instance`, `containment`, `states`,
`selected`, `regret`, `upper_thresholds`, and `lower_witnesses`.  No optional
top-level certificate fields exist.  `containment` and `states` must have exactly
the decimal keys of all nonempty connected alias subsets admitted by the
contract; missing or unexpected state keys are rejected.

## 5. Plan representation

Connected alias subsets are bit masks written as decimal strings when used as
JSON object keys.  A plan is either an integer alias leaf or a two-element list
`[left_plan, right_plan]`.  The checker requires distinct leaves, exactly the
state's aliases, connected internal states, and a legal connected split at every
node.  It recomputes all cost profiles from the templates; producer-supplied cost
coefficients are never trusted.

## 6. Containment records

`containment[S]` is required for every nonempty connected state, including
singletons and the root.  Each record contains exactly:

- `lower`, `upper`;
- `min_world`, `max_world`;
- `min_threshold`, `max_threshold`.

The worlds must satisfy the integral copy-count contract.  For the positive and
negative template-count directions, the checker recomputes the dot products and
scalar-threshold expressions and requires exact equality.  The two endpoints may
be attained by different worlds.

Template profile computation is capped at two million row-tuple probes over all
templates and connected states.

## 7. Dynamic-programming state records

Each `states[S]` object contains exactly `plans` and `coverage`.
`states[S].plans` is a nonempty list of legal retained plans for `S`, with at
most 2,000 entries.  Full syntactic trees are serialized; the packet is not a DAG
or a globally minimal encoding.

`states[S].coverage` contains one row

```text
[A, B, i, j, z, threshold]
```

for every connected unordered split `A|B` of `S` and every pair of retained
child indices `i,j`.  `A` contains the least-significant set bit of `S`, fixing a
canonical split orientation.  Index `z` names a retained parent plan.  The
threshold must prove that parent `z` uniformly dominates the expansion made from
children `i,j` for every feasible world.

The checker independently enumerates the expected split/child Cartesian product.
Missing, duplicate, unexpected, or false records are rejected.  Both expected
and supplied coverage are capped at 50,000 rows per state.  A singleton has its
one leaf and no coverage rows.

## 8. Root optimality records

At the root:

- `selected` is a retained-plan index;
- `regret` is a nonnegative exact integer;
- `upper_thresholds` has exactly one threshold per retained rival;
- `lower_witnesses` has exactly one `{rival, world}` object per retained
  candidate; those are the only two fields admitted in a witness object.

Every upper threshold must bound the selected-minus-rival support by `regret`.
Every lower witness must be a feasible world where the candidate-minus-rival
difference is at least `regret`.  Complete dynamic-programming coverage is what
extends these finite root checks from retained plans to all legal plans.

CLI:

```sh
python checker.py INSTANCE.json CERTIFICATE.json
```

Success exits 0.  A failed semantic obligation exits 2.  No packet field can
waive a failed check.

## 9. Composed chain

```sh
python verify_chain.py \
  INSTANCE.json SNAPSHOT.json ATTESTATION.json CERTIFICATE.json
```

The composition CLI loads one contract, invokes `attest.py`'s verification logic
and `checker.py`'s verification logic, and returns the accepted world, plan, and
certified regret only when both succeed.  A valid plan packet cannot mask a bad
snapshot decomposition, and a valid membership packet cannot mask a bad plan
proof.

Acceptance proves exact statements only about the supplied contract and snapshot.
It does not sign either packet, authenticate external files, discover a contract,
predict updates, approve a live database, or force a DBMS to execute the plan.
