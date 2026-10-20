"""Small, deliberately slow, independent exact-template reference matcher.

Only Python's standard library is imported. The oracle consumes original CSV
bytes and performs its own CSV parsing, decimal-to-Fraction conversion, angle
normalization, all-source/all-panel candidate enumeration, and full-tuple
multiset comparison. It never imports the product, shares a parsed Dataset,
uses the product's seed strategy, or calls production normalization helpers.

The result is a frozenset of
    (quarter_turn, Fraction(tx), Fraction(ty), ((source_ordinal, panel_ordinal), ...))
with mappings ordered by one-based logical source CSV record ordinal. Extra
panel rows do not suppress complete matches; final contract coverage is outside
this reference matcher's scope. Invalid or ambiguous input raises ValueError.
This is a correctness oracle for tiny test cases, not a production fallback.
"""

from collections import Counter
import csv
from fractions import Fraction
import io
import re


_HEADER = ["Ref", "Val", "Package", "PosX", "PosY", "Rot", "Side"]
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")


def _fraction(token, bound):
    """Parse decimal digits directly as an integer ratio, without Decimal."""
    if len(token) > 256 or _NUMBER.fullmatch(token) is None:
        raise ValueError("Invalid finite decimal spelling")
    negative = token.startswith("-")
    unsigned = token[1:] if token[:1] in ("+", "-") else token
    whole, point, fraction = unsigned.partition(".")
    if len(fraction) > 12:
        raise ValueError("Too many fractional places")
    digits = (whole or "0") + fraction
    numerator = int(digits) * (-1 if negative else 1)
    value = Fraction(numerator, 10 ** len(fraction))
    if abs(value) >= bound:
        raise ValueError("Numeric input is outside the declared bound")
    return value


def _read(blob, *, source):
    if len(blob) > 16 * 1024 * 1024:
        raise ValueError("CSV byte limit exceeded")
    try:
        reader = csv.reader(io.StringIO(blob.decode("utf-8-sig"), newline=""), strict=True)
        if next(reader, None) != _HEADER:
            raise ValueError("Unexpected CSV header")
        records = []
        references = set()
        normalized = set()
        for fields in reader:
            if len(fields) != 7:
                raise ValueError("CSV record must contain seven fields")
            reference, value, package, x, y, angle, side = fields
            if side not in ("top", "bottom"):
                raise ValueError("Invalid component side")
            if source and (not reference or reference in references):
                raise ValueError("Source references must be nonempty and unique")
            references.add(reference)
            pose = (reference, value, package, side,
                    _fraction(x, 1_000_000), _fraction(y, 1_000_000),
                    _fraction(angle, 1_000_000_000) % 360)
            if not source and pose in normalized:
                raise ValueError("Duplicate normalized panel tuple is ambiguous")
            normalized.add(pose)
            records.append(pose)
        if source and not records:
            raise ValueError("Source must contain at least one record")
        if len(records) > (2000 if source else 50000):
            raise ValueError("CSV record limit exceeded")
        return records
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ValueError("Malformed UTF-8 CSV") from exc


def _turn(x, y, quarter_turn):
    if quarter_turn == 0:
        return x, y
    if quarter_turn == 90:
        return -y, x
    if quarter_turn == 180:
        return -x, -y
    if quarter_turn == 270:
        return y, -x
    raise ValueError("Not a quarter-turn")


def brute_force_matches(source_csv, panel_csv):
    """Return all exact transforms and their complete logical-record mappings."""
    source = _read(source_csv, source=True)
    panel = _read(panel_csv, source=False)
    available = Counter(panel)
    panel_ordinal = {pose: ordinal for ordinal, pose in enumerate(panel, 1)}

    candidates = set()
    # Every label-compatible source/panel pair is tried. No source seed is
    # selected, no rare-reference heuristic is shared with the implementation.
    for source_pose in source:
        for panel_pose in panel:
            if source_pose[:4] != panel_pose[:4]:
                continue
            difference = (panel_pose[6] - source_pose[6]) % 360
            if difference not in (0, 90, 180, 270):
                continue
            rotation = int(difference)
            x, y = _turn(source_pose[4], source_pose[5], rotation)
            candidates.add((rotation, panel_pose[4] - x, panel_pose[5] - y))

    matches = set()
    for rotation, tx, ty in candidates:
        transformed = []
        for pose in source:
            x, y = _turn(pose[4], pose[5], rotation)
            transformed.append(pose[:4] + (x + tx, y + ty, (pose[6] + rotation) % 360))
        required = Counter(transformed)
        if required - available:
            continue
        assignment = tuple((ordinal, panel_ordinal[pose])
                           for ordinal, pose in enumerate(transformed, 1))
        matches.add((rotation, tx, ty, assignment))
    return frozenset(matches)
