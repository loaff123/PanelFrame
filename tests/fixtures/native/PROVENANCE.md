# Native fixture provenance

## Source and rights

The unchanged original board in `boards/USB-C-FUSB302-PI.kicad_pcb` is from
[bentwire/USB-C-FUSB302-PI](https://github.com/bentwire/USB-C-FUSB302-PI), commit
`7d95292262b42767bbeefebadb6bafe055923d50`:

- [Pinned board](https://github.com/bentwire/USB-C-FUSB302-PI/blob/7d95292262b42767bbeefebadb6bafe055923d50/USB-C-FUSB302-PI.kicad_pcb)
- [Pinned MIT license](https://github.com/bentwire/USB-C-FUSB302-PI/blob/7d95292262b42767bbeefebadb6bafe055923d50/LICENSE)
- Copyright (c) 2023 Mike Panetta
- Original board SHA-256: `2f3b4a62d4034342854fe1ac1c47c62f289756875668acf0320e72ff7868241d`
- Unmodified `LICENSE.board` SHA-256: `e3bd2123ddfedf44c2b4078b86e3d6c5be483f3675612bfc6076bbacc03077c8`

The root MIT license is the rights evidence for the board and derived CSV
fixtures. No conflicting board notice was observed during the source review.
This is a real 64-footprint RP2040/FUSB302 development board, not geometry
invented for PanelFrame. Embedded standard KiCad and project-specific
footprints are part of that board; no standalone footprint library, font,
3D model or source photograph is redistributed. KiCad's [library design
exception](https://www.kicad.org/libraries/license/) permits independent
licensing of designs and generated files.

## Native execution and fixture inventory

Native tools: **KiCad 9.0.2** (`pcbnew` also 9.0.2) and **KiKit 1.8.1**.
Native replay and independent checks were executed on **2026-10-19**.

All CSVs were emitted by `kicad-cli pcb export pos --format csv --units mm
--side both`. No CSV pose data was synthesized or hand-edited. The original
board and default/mixed exports were copied from the retained feasibility
evidence after verifying their recorded SHA-256 values. All three cases were
then regenerated in the new replay, proving the known-answer calculations on
new native exports. Default/mixed retained bytes preserve the original
research hashes; regenerated row order can differ.

- `source.csv` / `panel-default.csv`: unchanged source, absolute origins;
  2 rows × 2 columns, 3 mm spacing, initial 90° rotation, alternating rows;
  64 source rows and 256 panel rows.
- `source-mixed.csv` / `panel-mixed.csv`: controlled native source mutation
  flips C1, R1 and U1 to the bottom and sets U2 orientation to 17.125°;
  source drill/place origin (120, 80) mm and panel origin (10, 20) mm in
  KiCad board coordinates. The panel is 2 × 2, 3 mm spacing, initial 90°,
  alternating columns. There are 3 source and 12 panel bottom-side rows.
- `source-varied.csv` / `panel-varied.csv`: unchanged component poses, source
  drill/place origin (111.25, 77.5) mm; a genuinely different **3 × 2** native
  panel with **7.5 mm horizontal / 4.25 mm vertical** spacing, initial
  **180°** rotation, alternating **columns**; top-left page anchor **(35,45)**
  mm, and panel drill/place origin **(-5.5,12.25)** mm. All 384 panel rows
  match exactly six independently predicted transforms.
- `panel-varied-edited.csv`: reload the native six-copy panel and move only
  C1 in grid row 0 / column 0 by one native internal unit in X
  (**0.000001 mm**), save the PCB, and export again. The target is selected
  by configuration-derived coordinates before editing. Its expected transform
  is 180° at (96,-51.25) mm. The other five complete known-answer copies
  remain present. The edited copy has exactly one missing and one extra pose.
- `source-mixed-bottom-negated.csv` / `panel-mixed-bottom-negated.csv`:
  genuine native exports made with the extra `--bottom-negate-x` option.
  The independent checker confirms that only bottom X signs change. These
  are **unqualified controls**, outside the common Cartesian input profile;
  they must never be described as supported data. CSV bytes do not prove
  export settings, so a false operator profile declaration is not detectable
  in general.

All reference names are retained; every instance repeats the same 64 names.
No per-instance references, offset answers or mappings are supplied to the
product. `expected.json` exists only as test-oracle data, not as a recovery
contract. Optional `contract-*.json` files contain only the frozen input
declarations and hashes, never per-instance coordinates.

## Independent known-answer derivation

No PanelFrame code is imported by `tools/native/known_answers.py`,
`check_fixtures.py` or `replay.py`.

The source Edge.Cuts centreline bounding rectangle in native board coordinates
is x=100, y=74, width=66.75, height=22 mm. Its centre is (133.375,85) mm.
The native replay checks these source edge endpoints against the fixed values.
For each case, rotate width/height for the initial quarter-turn, calculate
grid centre positions from spacing and page anchor, and add 180° on odd
alternating rows/columns.

Let C be the source rectangle centre, S the source auxiliary origin, P the
panel auxiliary origin, D the configured grid-instance centre in native
coordinates, and R the configured rotation in Cartesian coordinates.
The exported source-centre coordinate is (C.x−S.x, S.y−C.y), while the
exported panel-centre coordinate is (D.x−P.x, P.y−D.y). Therefore the
export-frame translation is:

    t = (D.x−P.x, P.y−D.y) − R(C.x−S.x, S.y−C.y)

For default/mixed layouts, the default page anchor is middle-top at
(148.5,20) mm on the inherited A4 sheet. For the varied layout it is the
explicit top-left anchor at (35,45) mm. The six varied expected results are:

| Rotation | X mm | Y mm |
| --- | --- | --- |
| 0 | 126 | -88.75 |
| 0 | 126 | -62.5 |
| 0 | 126 | -36.25 |
| 180 | 96 | -103.75 |
| 180 | 96 | -77.5 |
| 180 | 96 | -51.25 |

The checker applies those known transforms to every source pose and compares
complete exact-rational multisets. It also checks the edited delta and all
five remaining known complete copies. It does not find or fit transforms.
This qualifies native fixtures independently of the product's discovery and
saved-report verification algorithms.

## Reproducibility and scope

`provenance.json` lists retained fixture hashes. `known-answer-check.json`
records checks of these retained CSVs. `replay-evidence/` contains normalized
command records, generated-board hashes and path-free known-answer/reproduction
summaries. The public command record uses tool names and relative board paths
and omits machine-specific KiCad configuration hashes. It is a normalized
record, not verbatim raw execution output. Raw execution logs are not
distributed. Regenerated default/mixed CSV byte hashes can differ because
repeated-reference row order is not stable. UUIDs in generated boards can
likewise change. Exact pose multisets, configurations and expected transforms
are the reproduction criterion.

Only the unchanged licensed source board is bundled; large generated panel
boards can be reconstructed with the replay script. KiCad and KiKit are
development/reference dependencies only. Normal PanelFrame runtime remains
dependency-free. These fixtures demonstrate exported pose behavior, not
electrical correctness, manufacturing approval, copper equivalence or a
production-qualified alteration of the board.
