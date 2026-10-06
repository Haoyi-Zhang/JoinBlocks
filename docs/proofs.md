# Proof obligations and trust boundary

This document is the repository-side proof account.  The manuscript presents the
same argument more compactly.  The implementation has two independent consumers:
`attest.py` checks that a complete join-key snapshot belongs to the declared
block family, and `checker.py` checks that a plan packet proves containment and
globally minimum worst-case additive regret for that family.  `verify_chain.py`
accepts only when both checks pass on the same contract and snapshot.

The proofs below are mathematical arguments about the declared model.  The
Python checkers are separately implemented and heavily tested, but they are not
mechanically verified.  Parsing, exact-integer arithmetic, the checker source,
the supplied templates, and the completeness of the supplied join-key snapshot
remain in the trusted base.

## 1. Model and realizable database family

The query graph is a tree whose vertices are relation aliases.  Every edge names
one equijoin-key attribute at each endpoint.  Relations are bags: duplicate row
occurrences are distinct.

A literal template `B_j` supplies, for every alias, a finite bag of rows projected
to the incident join-key attributes.  A copy of a template applies, independently
on each query edge, an injective renaming of the template's local key values.
Images used by two different copies on the same edge are disjoint.  Values on
different edges are separate attributes and may coincide numerically.

The copy-count world is

```
W_Z = { w in Z^K : lower_j <= w_j <= upper_j, sum_j w_j = total }.
```

`D(w)` is the bag union of `w_j` isolated renamed copies of template `j`.
`W` denotes the same constraints over the reals.  All bounds and the shared
total are integral.

For every nonempty connected alias set `S`, let `H_Sj` be the exact bag count of
joining the rows of `S` inside one copy of template `j`, and let `H_S` be the
vector of these counts.

### Lemma 1: connected-copy realization

For every connected `S` and `w in W_Z`,

```
x_S(D(w)) = H_S dot w.
```

**Reason.**  A joined tuple chooses one row occurrence per alias.  Equality on
one internal edge forces its two endpoint rows to use the same copy namespace.
Connectivity propagates that copy identity through all aliases in `S`.  Thus a
result tuple lies wholly inside one template copy.  The copies are bag-disjoint,
so their exact template counts add.  This argument fails for a disconnected
state because different components could choose different copies; only connected
states are admitted by the plan model and checker.

## 2. Snapshot-membership attestation

A snapshot is a complete join-key projection

```
J(D) = { one bag table per alias, with exactly its incident edge attributes }.
```

A membership packet contains one record per claimed template copy.  For every
relation of that copy, it lists, in template-row order, the index of the
corresponding snapshot row occurrence.  The checker derives all key renamings;
the packet never supplies a renaming map to trust.

The checker verifies:

1. the graph, template schema, bounds, total, and input budgets;
2. exact row cover: every snapshot row occurrence is assigned once and only once;
3. per-copy multiplicity: the mapped list has exactly the template's row count;
4. consistency: one local key value maps to one actual value at both endpoints;
5. injectivity: two local values on one edge cannot map to the same actual value;
6. isolation: actual values used by different copies on one edge are disjoint;
7. type counts: the number of copies of every template lies in its interval and
   all counts sum to the shared total.

### Theorem 2: membership soundness

If `attest.py` accepts `(contract, J(D), packet)`, then the accepted type-count
vector `w` belongs to `W_Z`, and `J(D)` is bag-isomorphic to the join-key
projection of `D(w)`, preserving aliases and equality on every declared edge.
Consequently, every connected count in the snapshot is `H_S dot w`.

**Proof.**  Exact cover partitions each relation's row occurrences into the
claimed copies and preserves duplicate multiplicity.  Within one copy, the
consistency checks define one local-to-actual map for every edge.  Injectivity
makes each such map an isomorphism of the template's equality pattern.  Isolation
makes the edge images of different copies disjoint, so no joined tuple can cross
copy boundaries.  The checked type counts form a feasible `w`.  Taking the bag
union of the per-copy isomorphisms yields an isomorphism from the snapshot to the
join-key projection of `D(w)`.  Lemma 1 then gives all connected counts.

### Theorem 3: membership completeness for the construction

Every join-key snapshot constructed as a feasible bag union of isolated,
injectively renamed template copies has an accepting membership packet.

**Proof.**  Enumerate the constructed copies.  For each ordered template-row
occurrence, record the corresponding snapshot row occurrence.  The construction's
renamings satisfy consistency and injectivity, its fresh namespaces satisfy
isolation, and its feasible copy counts satisfy the contract.  Every snapshot
row originates in exactly one copy, so the cover is exact.

Completeness is relative to this explicit representation.  Arbitrary databases
may have no useful isolated-template decomposition, and the checker does not
search for one.  It verifies a supplied decomposition in time linear in the
combined contract, snapshot, and packet sizes, up to dictionary operations.
Contract validation reads even unused template types; row-schema validation
reads the supplied snapshot before the cover is checked. Those input costs are
not bounded by the mapping packet alone.

## 3. Linear plan costs

A legal plan for connected state `S` is a binary tree whose leaves are exactly
the aliases of `S`, and every internal alias set is connected.  Leaves cost zero.
Joining child plans for `A` and `B` adds the exact output count of `S=A union B`:

```
cost_<pA,pB>(w) = cost_pA(w) + cost_pB(w) + H_S dot w.
```

Induction yields an exact nonnegative integer profile `c_p` with

```
cost_p(w) = c_p dot w.
```

This is an abstract sum of intermediate result cardinalities.  It does not model
operators, interesting orders, memory, indexes, parallelism, or elapsed time.

Worst-case additive regret is

```
R(p) = max_{w in W_Z} [ cost_p(w) - min_{q in P_V} cost_q(w) ].
```

Since the plan and world sets are finite,

```
R(p) = max_{q in P_V} support(c_p - c_q),
support(d) = max_{w in W_Z} d dot w.
```

No maximum/minimum interchange is used: the rival operation on the right is also
a maximum after subtracting the pointwise oracle.

## 4. Exact support with one scalar threshold

Write `a_j = upper_j - lower_j` and
`B = total - sum(lower)`.  For an integer direction `d` and scalar `lambda`,
define

```
U(d, lambda) = d dot lower
             + lambda * B
             + sum_j a_j * max(d_j - lambda, 0).
```

### Lemma 4: weak threshold bound

For every real `w in W` and every scalar `lambda`,

```
d dot w <= U(d, lambda).
```

**Proof.**  Put `v=w-lower`; then `0<=v_j<=a_j` and `sum v_j=B`.
For each coordinate,

```
(d_j-lambda) v_j <= a_j max(d_j-lambda,0).
```

Summing and restoring `d dot lower + lambda B` proves the claim.

### Lemma 5: exact integral support

There is an integral feasible world `w*` and an integer threshold `lambda*`
with

```
d dot w* = U(d, lambda*) = max_{w in W} d dot w
                         = max_{w in W_Z} d dot w.
```

**Proof.**  Start at `lower` and allocate the residual mass `B` to coordinates in
nonincreasing order of `d_j`, filling each capacity `a_j` before moving on.  The
allocation is integral.  When `B>0`, choose `lambda*` equal to the coefficient of
the last coordinate that receives mass.  Coordinates above the threshold are
full, those below are empty, and ties contribute zero coefficient difference,
so every inequality in Lemma 4 is tight.  When `B=0`, use `w*=lower` and
`lambda*=max d_j`.  Weak duality and the integral attained point prove equality.

This argument covers negative directions, tied coefficients, fixed coordinates,
zero residual mass, and a saturated contract.  It also gives the primal world
and scalar threshold that the checker can verify without a solver.

For each connected state, the tight marginal interval is

```
L_S = -support(-H_S),     U_S = support(H_S).
```

The packet supplies an attaining world and threshold for each sign.  The checker
requires primal feasibility and equality between the attained dot product and
the threshold expression.  Lemmas 1, 4, and 5 then give sound containment and
attainable endpoints inside the database family.

## 5. Independent-cardinality box

Let `X` be the Cartesian product of all connected intermediate intervals.  For
plans `p,q`, cancel shared states and maximize the remaining linear difference
coordinatewise over `X`.  The resulting value `b(p,q)` is at least the true
pairwise maximum because every actual world maps into `X`.  Therefore

```
R(p) <= max_q b(p,q).
```

Minimizing this outer bound is a sound conservative policy, but its minimizer
need not be minimax for the narrower joint contract.  The artifact treats it as
a baseline, not as a false-containment method.

## 6. Uniform coverage of dynamic-programming states

For every connected state `S`, the producer supplies a nonempty retained family
`F_S` of legal plans.  Singletons retain their leaf.  For every connected
unordered split `A|B` of `S` and every retained child pair `(p_A,p_B)`, the packet
identifies a retained plan `q in F_S` and threshold `lambda` such that

```
U(c_q - c_pA - c_pB - H_S, lambda) <= 0.
```

By Lemma 4, `q` is no more expensive than the expansion `<p_A,p_B>` at every
world.  The checker independently enumerates every legal connected split and the
full Cartesian product of retained child indices.  Missing, duplicate, or
spurious coverage records are rejected.

A family `F_S` **uniformly covers** all legal plans `P_S` when

```
for every p in P_S, there exists one q in F_S
such that cost_q(w) <= cost_p(w) for every w in W.
```

The replacement may depend on `p`, but not on the later world.

### Theorem 6: compositional coverage

If all retained plans are legal and every required coverage inequality passes,
then every `F_S` uniformly covers `P_S`.

**Proof.**  Induct on state size.  The singleton case is immediate.  For an
arbitrary nonleaf plan `<p_A,p_B>`, the induction hypothesis supplies fixed
retained replacements `q_A,q_B` that dominate its children in every world.
Cost compositionality makes `<q_A,q_B>` dominate the original expansion.  The
complete coverage table then supplies one retained parent `q` that uniformly
dominates `<q_A,q_B>`.  Transitivity completes the induction.

The theorem relies on the state containing all properties relevant to parent
cost.  It does not extend unchanged to order-sensitive operators, physical
properties, or memory-dependent costs.

## 7. Root optimality packet

Let `F=F_V`, let `p*` be the selected retained plan, and let `r>=0` be the claimed
minimum regret.

For every retained rival `q`, the packet supplies a threshold proving

```
U(c_p* - c_q, lambda_q) <= r.
```

For every retained candidate `p`, it supplies a feasible world `w_p` and retained
rival `q_p` with

```
(c_p - c_qp) dot w_p >= r.
```

The rival need not itself be point-optimal at the witness; exhibiting one rival
already lower-bounds regret.

### Lemma 7: covered oracle equality

If `F` uniformly covers `P_V` and `F` is a subset of `P_V`, then for every world

```
min_{q in F} cost_q(w) = min_{q in P_V} cost_q(w).
```

Subset inclusion gives one direction.  A full-family minimizer has a retained
uniform replacement no more expensive at the same world, giving the other.

### Theorem 8: plan-certificate soundness

If template recomputation, tight containment, legal-plan checks, complete
coverage, all selected-plan upper thresholds, and all candidate lower witnesses
pass, then

```
R(p*) = r = min_{p in P_V} R(p).
```

Every certified connected interval is tight in the family, and a feasible
database realizes the selected plan's regret `r`.

**Proof.**  The upper thresholds and Lemma 7 bound every selected-plan pairwise
difference by `r`, hence `R(p*)<=r`.  Each retained candidate's lower witness
shows its regret is at least `r`.  Any discarded plan has a retained uniform
replacement whose regret is no larger; that retained replacement already has a
lower witness of `r`, so the discarded plan also has regret at least `r`.  Thus
all legal plans have regret at least `r`, including `p*`, and equality follows.
The selected plan's lower witness attains the value; Lemma 1 realizes its integer
world as a database.

## 8. End-to-end composition

### Corollary 9: checked snapshot and family guarantee

If `attest.py` and `checker.py` accept the same contract and `verify_chain.py`
accepts their composition, then:

- the snapshot corresponds to some feasible `w in W_Z`;
- the selected plan is globally minimax over every legal binary join plan for the
  entire declared family, with value `r`; and
- the selected plan's regret on the accepted snapshot is at most `r`.

The first item is Theorem 2.  The second is Theorem 8.  Applying Theorem 8's
all-world upper bound to the feasible world supplied by Theorem 2 proves the
third.  No probabilistic or asymptotic inference is involved.

After any snapshot update, membership must be checked again.  Rejection means the
old family guarantee is inapplicable to that snapshot.  A changed contract also
requires a new plan packet or a complete recheck of all old obligations; old
lower witnesses or exact endpoints may disappear even when the family shrinks.

## 9. Finite completeness and complexity boundary

Without prototype admission limits, the certificate format is finite-complete
for this finite model:

1. retain every legal plan at every connected state;
2. use each expansion itself as its coverage dominator with a zero difference;
3. include exact primal/threshold witnesses from Lemma 5;
4. enumerate the finite root plan and world sets to choose the minimax plan and
   one lower witness per retained candidate.

This proves existence of a finite packet, not a polynomial-size packet.  Join
plan families and retained frontiers can be exponential.  The executable imposes
explicit bounds on relations, template count, total mass, rows, tuple probes,
frontier width, coverage records, JSON bytes, and integer widths.

## 10. Falsification evidence

The retained evidence is finite validation, not a substitute for the proofs:

- 102 frozen plan instances agree with exhaustive plan/world oracles and both
  uniform- and componentwise-dominance variants;
- 12,816 SQLite connected template/subquery counts and 607 primary bag-result
  plan/world comparisons agree;
- 83,150 bounded support cases agree with direct integer maximization;
- 306 accepted snapshots contain 2,106 copies and 33,204 row occurrences;
- 7,812 SQLite snapshot connected-subquery counts equal `H_S dot w`;
- direct realized-plan evaluation checks `actual regret <= r` on all 306
  snapshots, with equality on 126;
- 2,754 semantic attestation corruptions across nine classes are all rejected;
- 68 regression methods pass: 59 rejection-oriented methods and nine
  valid/support/validation/crosscheck methods; the inventory maps every method to
  its source line and evidence area, and the independent crosscheck covers 36
  additional small contracts with separately enumerated plans, worlds, and SQLite
  counts;
- an auxiliary 20-case topology-interface route over five pinned public-query
  equality trees validates edge encoding, producer/checker/oracle agreement, and
  lossless tuple-keyed oracle serialization; it is excluded from the 102/306 core
  totals and is not a data or runtime benchmark;
- the retained and fresh attestation-overhead gates both read 306 snapshots and
  33,204 rows from the actual CSV fields and confirm every chain and realized
  regret bound;
- a separate two-copy drift packet leaves the one-copy plan certificate valid but
  is rejected by membership and composition; it is not counted in the 2,754
  mutation attempts;
- a realizable hedge shows pointwise envelope preservation can lose the minimax
  candidate, and a six-alias control shows one local minimax winner per state can
  increase global regret from 36 to 44.

## 11. Explicit non-claims

Acceptance does **not** establish any of the following:

- that ordinary database statistics reveal the literal templates or intervals;
- that an arbitrary database has a concise isolated-copy decomposition;
- that the supplied snapshot is authentic, transactionally consistent, or
  complete beyond its join-key projection;
- that later data still belong to the contract without another membership check;
- that the Python checker has been proved correct or hardened as a network
  service;
- that abstract intermediate-cardinality regret predicts elapsed runtime;
- that the frontier is minimal, certificates are polynomial-size, or the method
  covers cyclic queries, Cartesian intermediates, outer joins, or physical state.

Those boundaries are part of the result rather than omitted implementation work.
