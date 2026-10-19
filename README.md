# PanelFrame

Recover board-copy origins and quarter-turn rotations from a source PCB's
placement CSV and its finished repeated-panel placement CSV. PanelFrame emits
an offsets file only when every source row appears at the exact transformed
pose in every recognized copy, the copy count matches your declaration, and
every panel row is mapped or explicitly excluded.

**Alpha, local-only tool.** The working package name has not been checked for
public-registry availability. Python 3.11+; standard library only at runtime.
KiCad and KiKit are needed only to regenerate development fixtures.

## When it helps

A finished panel export can differ from the layout you intended to generate.
PanelFrame recovers transforms from exported component poses and checks the
whole exported pattern before handing over origins. Repeated KiKit reference
names are supported directly: you do not label each copy or supply offsets.

If you only need intended offsets and already trust your generator settings,
reading them from KiKit configuration or its API is simpler. This is
conventional exact rigid-template matching, not a new registration algorithm.
A concrete motivating workflow is [KiKit issue #910](https://github.com/yaqwsx/KiKit/issues/910).

## What the result means

The output X/Y is the source-export point (0,0), expressed in the panel-export
Cartesian millimeter frame. Rotation is counterclockwise and is exactly 0,
90, 180 or 270 degrees. An origin is not necessarily a board-outline corner.
Instance IDs identify this report's sorted transforms, not physical serial
numbers. Labels mean exported strings, not manufacturer part identities.

This checks only supplied exported rows. It does **not** check copper,
connectivity, board outlines, electrical equivalence, DRC, actual pin one,
assembly safety or manufacturing readiness. It is not a vendor upload format.
Components omitted by export filters cannot be checked. Source/panel DNP or
filter differences may cause a legitimate refusal. A copper-only board change
is invisible to this model.

## Install and try the retained native example

Install the supplied wheel without fetching dependencies:

```sh
python -m pip install --no-deps --no-index /path/to/panelframe-0.1.0a1-py3-none-any.whl
panelframe --help
```

The source archive includes an MIT-licensed real-board native fixture:

```sh
panelframe inspect tests/fixtures/native/source.csv \
  tests/fixtures/native/panel-default.csv --json inventory.json
panelframe recover tests/fixtures/native/source.csv \
  tests/fixtures/native/panel-default.csv \
  --contract tests/fixtures/native/contract-default.json --out recovered
panelframe verify tests/fixtures/native/source.csv \
  tests/fixtures/native/panel-default.csv \
  --contract tests/fixtures/native/contract-default.json --report recovered
```

Both output paths must be new. `inspect` reports hashes and inventory facts;
it does not infer units, compatibility or exporter settings.

## Prepare your own inputs

The executed reference exporter is **KiCad 9.0.2**. Export both source and panel
position files as CSV, millimeters, both sides, with bottom-X negation disabled.
Use ordinary counterclockwise component angles and common Cartesian
coordinates on both sides. Example absolute-origin export:

```sh
kicad-cli pcb export pos --format csv --units mm --side both \
  --output source.csv source.kicad_pcb
```

Use `--use-drill-file-origin` if you want drill/place-origin coordinates, and
record that choice independently for each input. Do not add `--bottom-negate-x`.
Run `inspect`, then create a UTF-8 JSON contract with exactly these fields:

```json
{
  "schema_version": 1,
  "profile": "kicad-9-pos-csv-mm-cartesian",
  "source_sha256": "REPLACE_WITH_SOURCE_HASH_FROM_INSPECT",
  "panel_sha256": "REPLACE_WITH_PANEL_HASH_FROM_INSPECT",
  "source_origin": "absolute",
  "panel_origin": "absolute",
  "expected_instances": 4,
  "excluded_panel_records": []
}
```

The example hash placeholders must be replaced with actual lowercase SHA-256
hashes. Origins are `absolute` or `drill-place`; they may differ. These choices
and the profile are your declarations: CSV bytes cannot prove the export
options. Other KiCad versions require qualification before claiming support.
A falsely declared profile, especially for all-top-side data, cannot in
general be detected. The contracts never contain intended offsets or mappings.

To exclude an added rail fiducial, list its one-based logical CSV **data-record**
number (excluding the header) and a nonempty reason:

```json
"excluded_panel_records": [{"record": 257, "reason": "Added panel rail fiducial"}]
```

A quoted newline remains part of one logical record. An exclusion is bound to
the exact panel hash, cannot be duplicated, and cannot name any reference
present in the source, even if that panel row's other fields changed. Duplicate
identical normalized panel poses are always rejected, including exclusions.
Discovery considers the full panel before final exclusion accounting.

## Exact input contract and limits

- CSV header must be exactly `Ref,Val,Package,PosX,PosY,Rot,Side`, in that order,
  with exactly seven fields in every data record. UTF-8, optional leading BOM,
  CRLF and CSV-quoted commas/newlines are supported. NUL is rejected.
- Source references must be nonempty and unique; panel references may repeat.
  Reference renaming/prefixes, multiple source designs and board reflections
  are unsupported. `Side` is exactly `top` or `bottom`; value/package/side
  labels must match exactly. Arbitrary decimal component angles are allowed.
- Numbers use ASCII plain decimal notation: optional sign and decimal point,
  at least one digit, no whitespace or exponent. At most 12 fractional places
  and 256 characters. Angles normalize modulo 360; equivalent spellings match.
- Input coordinates have absolute value below 1,000,000 mm; input angles below
  1,000,000,000 degrees. Derived origins may approach 2,000,000 mm.
- At most 16 MiB per CSV, 2,000 source rows, 50,000 panel rows and 1–100 expected
  instances. Contract JSON is limited to 1 MiB; each saved report member to
  256 MiB on verification. These are operating limits, not hard memory/time
  or adversarial-resource guarantees.
- Contract keys are exact, unique and required. JSON integers cannot be booleans
  or floats. There is no tolerance field, rounding, fitting or correction.

Unmodified native six-place exports have passed exact checks. Files that need
tolerance or assembler-specific orientation corrections are outside this
version, and are never silently rounded into a match.

## Outputs and exit codes

A complete recovery creates a new directory containing:

- `offsets.csv`: instance ID, source-origin X/Y mm, CCW quarter-turn, row count
- `evidence.json`: byte hashes, declarations, exact transforms, per-instance
  source/panel record mappings, normalization facts, exclusions and coverage
- `report.html`: standalone escaped review with no scripts or external assets

Incomplete recognition creates only evidence and HTML, clearly marked
incomplete. Fully recognized copies remain visible, but no complete offsets
handoff is emitted. Missing poses are reported exactly without blaming a
nearby same-reference row. Rejection details are limited to the first 100
candidates and first 10 missing poses each; full coverage counts remain exact.
A failed recognition report is not a proof about models outside this contract
and does not mean a board is defective.

`verify` independently checks saved mappings, transform equations, every row,
hashes, declarations, normalized facts and exact CSV/HTML content. It does not
run candidate discovery. It verifies complete handoffs only. Changing HTML
annotations causes verification to fail; keep review comments separately.
Hashes establish byte identity, not authorship or authenticity.

| Exit | Meaning |
| --- | --- |
| 0 | Inventory written, complete recovery, or successful verification |
| 1 | Valid inputs, but recovery is incomplete |
| 2 | Invalid input/contract/evidence or ordinary I/O failure |
| 3 | Unsupported profile or operational limit |

No inputs are changed. Existing destinations, files and output aliases are
refused. Recover writes offsets last and cleans its new directory on ordinary
write failure where possible. This is normal filesystem handling, not a
concurrent malicious-writer or symlink-race defense. Use stable ordinary files
and do not modify inputs/output paths during a run. Failed cleanup can leave
partial files; a fresh `verify` is the completion check.

## Development and evidence

```sh
PYTHONPATH=src python -m unittest discover -v
python tools/native/check_fixtures.py
python -c 'from setuptools.build_meta import build_sdist, build_wheel; build_sdist("dist"); build_wheel("dist")'
bash tools/check_installed.sh dist/panelframe-0.1.0a1-py3-none-any.whl
```

Build tooling is setuptools and wheel, obtained from their official package
registry if not already installed. CI runs Linux tests against an installed
wheel from outside the checkout, with a read-only copy of tests/fixtures.
The hosted workflow has read-only repository permissions; local equivalent
runs are recorded separately and are not a claim that hosted CI ran.

Tests cover native 64→256 and 64→384 repeated-reference panels, common-frame
bottom rows, arbitrary source angles, auxiliary origins, a real native
post-panel one-unit edit, full-set comparisons to an independently written
Fraction/all-pairs oracle, report tampering, clean refusal paths and immutable
inputs. Native tool regeneration is separate from dependency-free runtime.
See [fixture provenance](tests/fixtures/native/PROVENANCE.md),
[native replay instructions](tools/native/README.md),
[verification](docs/VERIFICATION.md), and [design](docs/DESIGN.md).

Original code is MIT. Board data and derived fixtures retain Mike Panetta's
separate original MIT notice. No vendor endorsement or name availability is
claimed. No public package or repository publication is part of this build.
