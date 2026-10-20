# Verification and reproduction

Local verification date: 2026-10-19. Hosted verification date: 2026-10-20.
This is an alpha source distribution. Manufacturer qualification is not implied.

## Hosted checks

[GitHub Actions run 39350133348](https://github.com/loaff123/PanelFrame/actions/runs/39350133348)
passed for source commit `2b9803a3315c35b0a93b85e615fe9e481ed7c0c0`:

- Linux/Python 3.11, 3.12 and 3.13 each built the wheel and source distribution.
- Each interpreter passed all 93 installed-wheel tests, with no failures or
  skips, outside the checkout with read-only copies of tests and fixtures.
- Each interpreter passed the retained native known-answer checks without
  installing KiCad or KiKit. Hosted CI does not run native fixture regeneration
  or the separately recorded source-distribution rebuild check.

The source commit contains the reviewed snapshot. Later documentation updates
have separate workflow runs visible in the repository's Actions history.

## Local executed checks

- All 93 test methods pass on Linux/Python 3.12.14, with no failures or skips.
  The installed-wheel tests run outside the source checkout in a fresh virtual
  environment, with read-only copies of the tests and fixtures.
- A wheel rebuilt from the source distribution passes the same installed tests.
  Source archive hashes and wheel member contents are checked separately.
- Strict input tests cover CSV quoting and logical records, exact decimal
  arithmetic, input/resource boundaries, repeated references, duplicate poses,
  hash-bound contracts and exclusions that cannot hide source references.
- A separate Fraction/all-pairs oracle compares complete transformation and
  mapping sets across 72 generated complete cases, 192 corruptions and 12
  permutations, plus independent oracle controls.
- Saved-witness tests cover translation, rotation, count, mapping, exclusion,
  normalization and coverage tampering, changed original bytes, missing output
  members, CSV/HTML mismatch, strict JSON types, large derived origins, inert
  HTML labels, ordinary write failures and input immutability. Verification
  also passes with discovery, rotation and assessment helpers disabled.
- Native KiCad 9.0.2/KiKit 1.8.1 exports pass for 64-to-256 default and mixed-side
  panels and a genuinely different 64-to-384 panel. Mixed controls include 12
  bottom-side panel rows, an arbitrary source angle and changed auxiliary origins.
- A native post-panel C1 edit of 0.000001 mm prevents a complete handoff while
  preserving five complete copies. Native regeneration reproduces all nine CSV
  pose multisets, including explicitly unsupported bottom-X-negated controls.
  Repeated-reference row order and native UUIDs need not reproduce byte-for-byte.

## Reproduce the checks

From a source-archive checkout:

```sh
PYTHONPATH=src python -m unittest discover -v
python tools/native/check_fixtures.py
python -c 'from setuptools.build_meta import build_sdist, build_wheel; build_sdist("dist"); build_wheel("dist")'
bash tools/check_installed.sh dist/panelframe-0.1.0a1-py3-none-any.whl
```

Build requirements are setuptools 77+ and wheel. The recorded build environment
used setuptools 84.0.0 and wheel 0.48.0. There are no runtime dependencies.
Native regeneration is optional development work; see
[the replay instructions](../tools/native/README.md) and
[fixture provenance](../tests/fixtures/native/PROVENANCE.md). Normal consumer
recovery and the retained-fixture test suite do not require KiCad or KiKit.

## Performance observation

On the local Linux x86-64 environment with Python 3.12.14, a generated 100-copy
panel based on the 64 native source rows contained 6,400 panel rows (477,635
CSV bytes). One fresh process measured recovery/report writing at about 0.17
seconds, verification at about 0.15 seconds and peak resident memory at about
30 MiB. This is a single-machine observation, not a speed guarantee. The
performance panel is synthetic and is not native acceptance evidence.
The path-free measurements are in [benchmark-100.json](benchmark-100.json).
Reproduce them using `tools/benchmark.py` with an installed package or
`PYTHONPATH=src`.

## Qualification limits

The executed Linux CI matrix covers Python 3.11, 3.12 and 3.13. Other Python
versions and other KiCad exporter versions,
Windows/macOS filesystem behavior, mirrored panels, assembler-specific rotations
and tolerance fitting are not qualified. No physical board, vendor submission,
copper comparison, electrical test or manufacturing approval is implied.
Export settings are operator declarations; falsely declared profiles cannot
in general be detected from CSV bytes.
