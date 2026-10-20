# Exact-pose design

A source row is a unique-reference labeled pose `(ref, value, package, side,
x, y, angle)`. Input decimals are exact; rotations are normalized in a fresh
64-digit Decimal context, independent of caller precision, exponent limits
or traps. The maximum accepted input width plus translation/rotation arithmetic
fits comfortably within that precision. No floats enter matching.

Discovery chooses the unique source row with the fewest label-compatible
panel rows, breaking ties by reference. Each such panel row determines an
angle difference and a translation. Non-quarter-turn differences cannot seed
a supported instance. Every candidate is checked against all source poses in
an exact normalized tuple index. Only complete templates become instances.
Transform sorting is rotation, X, Y. Logical record ordinals are retained,
so source and panel permutation changes mappings but not recovered transforms.

No valid transform can be omitted by this seed rule: every complete copy must
contain that source reference with its exact value/package/side, and its
rotation/translation are uniquely determined by the seed's pose. Distinct
complete transforms cannot share a row because that row's unique source
reference and full pose determine the same transform. The code nevertheless
checks assignment disjointness and full accounting explicitly.

Duplicate identical normalized panel tuples are rejected before exclusions.
An exclusion can only name a reference absent from the source. Consequently,
a verifier can establish that the saved complete instances and explicit
exclusions account for all panel data without searching for alternative copies.

The independent saved-witness verifier reparses original bytes, validates the
contract, checks explicit Cartesian equations and every assignment, enforces
canonical distinct transforms, then regenerates all input facts and output
content. It does not call discovery, rotation or coverage helpers. It shares
strict input parsing and output serialization, but an independent test oracle
uses Fraction parsing and exhaustive compatible source/panel pair enumeration
with full multiset matching. Native known-answer tools separately derive
transforms from panel generator configuration and outline arithmetic.

CSV hashes refer to supplied bytes, so source or panel row reordering changes
the required contract hash. Numeric normalization does not change this binding.
Reports are deterministic for identical input bytes, including original line
ending/quoting effects in hash and normalization facts. Native regeneration
may reorder repeated-reference rows; compare pose multisets, not byte identity.

## Practical complexity

If S is the source row count, P the panel row count and C the label-compatible
seed row count, discovery is O(P + C×S), plus sorting transforms. Because source
references are unique and the least-common label is chosen, C×S cannot exceed
P when every label occurs; when a label is absent C is zero. Parsed labels,
exact Decimal values, mappings and rendered reports consume additional memory.
The operational byte/row limits are not an untrusted-input resource guarantee.

## Deliberate limitations

This is a single-design exact exported-row model: no mirrored instances,
non-quarter-turn board rotations, tolerance fitting, per-assembler angle
corrections, prefix normalization, raw PCB geometry, electrical inference,
network lookup, board writes or vendor submission. Incomplete discovery is
explanatory evidence only. Never interpret failed matching as a defective
board or successful matching as approval to manufacture.
