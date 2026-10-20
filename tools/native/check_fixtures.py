#!/usr/bin/env python3
"""Check exact fixture pose multisets against fixed generator settings.

Standard library only. This is not discovery or product verification. For the
edited negative it checks the expected one missing pose and one added pose,
and confirms the other five entire known-answer copies remain present.
"""

import argparse
from collections import Counter
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from known_answers import expected_document, rotate


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def key(row):
    return (row["Ref"], row["Val"], row["Package"], row["Side"],
            F(row["PosX"]), F(row["PosY"]), F(row["Rot"]) % 360)


def transformed(source, transform):
    angle = transform["rotation_deg"]
    tx, ty = F(transform["tx_mm"]), F(transform["ty_mm"])
    rows = Counter()
    for row in source:
        ref, val, package, side, x, y, a = key(row)
        x, y = rotate(x, y, angle)
        rows[(ref, val, package, side, x + tx, y + ty, (a + angle) % 360)] += 1
    return rows


def check(root):
    provenance = root / "provenance.json"
    if provenance.exists():
        for name, digest in json.loads(provenance.read_text())["files_sha256"].items():
            assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, (
                "Retained fixture hash mismatch", name)
    expected = expected_document()
    retained = root / "expected.json"
    if retained.exists():
        assert json.loads(retained.read_text()) == expected, "Known answers differ from configuration arithmetic"
    checks = {}
    for name, case in expected["cases"].items():
        source = read(root / case["source"])
        panel = read(root / case["panel"])
        assert len(source) == case["source_rows"]
        assert len(panel) == case["panel_rows"]
        all_expected = Counter()
        for transform in case["transforms"]:
            all_expected.update(transformed(source, transform))
        actual = Counter(map(key, panel))
        missing, extra = all_expected - actual, actual - all_expected
        assert sum(missing.values()) == case.get("missing_pose_rows", 0), (name, missing)
        assert sum(extra.values()) == case.get("extra_pose_rows", 0), (name, extra)
        if name == "varied-edited":
            before, after = next(iter(missing)), next(iter(extra))
            assert before[:4] == after[:4] and before[0] == "C1"
            assert after[4] - before[4] == F("0.000001")
            assert after[5:] == before[5:]
            for transform in case["complete_transforms"]:
                assert not (transformed(source, transform) - actual)
            assert sum((transformed(source, case["edited_transform"]) - actual).values()) == 1
        checks[name] = {
            "source_rows": len(source), "panel_rows": len(panel),
            "missing_pose_rows": sum(missing.values()), "extra_pose_rows": sum(extra.values()),
            "known_transforms_match": not missing and not extra,
            "expected_negative": name == "varied-edited",
            "source_bottom_rows": sum(r["Side"] == "bottom" for r in source),
            "panel_bottom_rows": sum(r["Side"] == "bottom" for r in panel),
        }
    for base in ("source-mixed", "panel-mixed"):
        ordinary = Counter(map(key, read(root / (base + ".csv"))))
        negated = Counter(map(key, read(root / (base + "-bottom-negated.csv"))))
        expected_negated = Counter()
        for pose, count in ordinary.items():
            ref, val, package, side, x, y, a = pose
            expected_negated[(ref, val, package, side, -x if side == "bottom" else x, y, a)] += count
        assert expected_negated == negated, base
        assert ordinary != negated, base
    checks["bottom_negated_control"] = {
        "qualifies_for_profile": False,
        "verified_only_bottom_x_changed": True,
        "note": "The CSV cannot establish export settings; a false declaration is not detectable in general.",
    }
    return {
        "oracle": expected["oracle"], "checks": checks,
        "csv_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted(root.glob("*.csv"))},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?",
                        default=Path(__file__).resolve().parents[2] / "tests/fixtures/native")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    result = json.dumps(check(args.directory), indent=2) + "\n"
    print(result, end="")
    if args.json:
        args.json.write_text(result, encoding="utf-8")
