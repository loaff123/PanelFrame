"""Independent whole-result discovery comparisons, including logical row mappings."""

import csv
from decimal import Decimal
from fractions import Fraction
import io
import random
import unittest


HEADER = ("Ref", "Val", "Package", "PosX", "PosY", "Rot", "Side")


def csv_bytes(rows, *, bom=False):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return ("\ufeff" if bom else "").encode("utf-8") + stream.getvalue().encode("utf-8")


def exact_text(number):
    """Serialize terminating fractions without Decimal context or binary floats."""
    number = Fraction(number)
    sign = "-" if number < 0 else ""
    numerator, denominator = abs(number.numerator), number.denominator
    whole, remainder = divmod(numerator, denominator)
    digits = []
    while remainder:
        digit, remainder = divmod(remainder * 10, denominator)
        digits.append(str(digit))
        if len(digits) > 12:
            raise ValueError("Generated value does not fit the decimal contract")
    return sign + str(whole) + (("." + "".join(digits)) if digits else "")


def generated_copy(rows, transform):
    """Fixture construction uses matrices, separate from the reference matcher."""
    rotation, tx, ty = transform
    a, b, c, d = {
        0: (1, 0, 0, 1), 90: (0, -1, 1, 0),
        180: (-1, 0, 0, -1), 270: (0, 1, -1, 0),
    }[rotation]
    output = []
    for reference, value, package, x, y, angle, side in rows:
        x, y, angle = Fraction(x), Fraction(y), Fraction(angle)
        output.append((reference, value, package,
                       exact_text(a * x + b * y + tx),
                       exact_text(c * x + d * y + ty),
                       exact_text(angle + rotation), side))
    return output


def generated_source(seed, count):
    rng = random.Random(seed)
    return [
        (f"P{i + 1}", f"Ω, value\n{seed % 5}", f"Pkg<{i % 2}>",
         exact_text(Fraction(rng.randrange(-64, 65), 8)),
         exact_text(Fraction(rng.randrange(-64, 65), 16)),
         exact_text(Fraction(rng.randrange(-11520, 11521), 16)),
         "bottom" if i % 2 == 0 else "top")
        for i in range(count)
    ]


def expected_records(source_rows, panel_entries, transforms, *, exclude=()):
    source_ordinals = {row[0]: ordinal for ordinal, row in enumerate(source_rows, 1)}
    return frozenset(
        (rotation, Fraction(tx), Fraction(ty), tuple(sorted(
            (source_ordinals[row[0]], panel_ordinal)
            for panel_ordinal, (copy_id, row) in enumerate(panel_entries, 1)
            if copy_id == instance_id
        )))
        for instance_id, (rotation, tx, ty) in enumerate(transforms)
        if instance_id not in exclude
    )


class ReferenceOracleTests(unittest.TestCase):
    def test_handwritten_full_transform_and_ordinals(self):
        from tests.oracle import brute_force_matches
        source = csv_bytes([
            ("R1", "10k", "R", "0", "0", "17.125", "top"),
            ("C1", "1u", "C", "2", "-1", "270", "bottom"),
        ])
        panel = csv_bytes([
            ("C1", "1u", "C", "12", "19", "270", "bottom"),
            ("R1", "10k", "R", "-8", "3", "107.125", "top"),
            ("R1", "10k", "R", "10", "20", "17.125", "top"),
            ("C1", "1u", "C", "-7", "5", "0", "bottom"),
        ])
        self.assertEqual(brute_force_matches(source, panel), frozenset({
            (0, Fraction(10), Fraction(20), ((1, 3), (2, 1))),
            (90, Fraction(-8), Fraction(3), ((1, 2), (2, 4))),
        }))

    def test_normalization_and_quoted_newlines_preserve_logical_ordinals(self):
        from tests.oracle import brute_force_matches
        source = csv_bytes([
            ("U1", "µ,\ncontroller", 'QFN"32', "+.50", "-0.000", "-342.875", "bottom"),
            ("R1", "<10Ω>", "R", "2.0", "1.", "720", "top"),
        ], bom=True)
        panel = csv_bytes([
            ("R1", "<10Ω>", "R", "12", "21.000", "-360", "top"),
            ("U1", "µ,\ncontroller", 'QFN"32', "10.500", "20", "377.125", "bottom"),
        ])
        self.assertEqual(brute_force_matches(source, panel), frozenset({
            (0, Fraction(10), Fraction(20), ((1, 2), (2, 1))),
        }))

    def test_incomplete_template_does_not_become_a_partial_match(self):
        from tests.oracle import brute_force_matches
        source_rows = generated_source(7, 3)
        incomplete = generated_copy(source_rows, (270, -10, 4))[:-1]
        self.assertEqual(brute_force_matches(csv_bytes(source_rows), csv_bytes(incomplete)),
                         frozenset())

    def test_normalized_duplicate_panel_tuple_is_ambiguous(self):
        from tests.oracle import brute_force_matches
        row = ("R1", "10k", "R", "0", "0", "17.125", "top")
        equivalent = ("R1", "10k", "R", "+0.0", "-0", "377.125", "top")
        with self.assertRaises(ValueError):
            brute_force_matches(csv_bytes([row]), csv_bytes([row, equivalent]))

    def test_invalid_numeric_spellings_do_not_enter_reference_arithmetic(self):
        from tests.oracle import brute_force_matches
        valid = ("R1", "10k", "R", "0", "0", "0", "top")
        for token in ("1e3", " NaN", "Infinity", "1 ", "١", ".", "1.0000000000001"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                malformed = list(valid)
                malformed[3] = token
                brute_force_matches(csv_bytes([malformed]), csv_bytes([valid]))


class DiscoveryOracleTests(unittest.TestCase):
    def assert_matches_oracle(self, source, panel, expected=None):
        from tests.oracle import brute_force_matches
        reference = brute_force_matches(source, panel)
        if expected is not None:
            self.assertEqual(reference, expected, "Independent reference failed the known answer")
        try:
            from panelframe.model import parse_csv
            from panelframe.matching import discover
        except ImportError as exc:
            self.fail(f"Required discovery API is not implemented: {exc}")
        result = discover(parse_csv(source, "source"), parse_csv(panel, "panel"))
        actual = set()
        for instance in result.instances:
            self.assertIsInstance(instance.tx, Decimal)
            self.assertIsInstance(instance.ty, Decimal)
            actual.add((instance.rotation, Fraction(instance.tx), Fraction(instance.ty),
                        tuple(sorted(instance.mapping))))
        self.assertEqual(len(actual), len(result.instances), "Duplicate transforms were returned")
        self.assertEqual(frozenset(actual), reference,
                         "Complete transform and row-assignment sets must agree")
        return reference

    def test_two_complete_instances_return_every_transform_and_mapping(self):
        """Dropping a complete copy or swapping its row assignments must fail."""
        try:
            from panelframe.model import parse_csv
            from panelframe.matching import discover
        except ImportError as exc:
            self.fail(f"Required discovery API is not implemented: {exc}")
        source = (b"Ref,Val,Package,PosX,PosY,Rot,Side\n"
                  b"R1,10k,R_0603,0,0,17.125,top\n"
                  b"C1,1u,C_0603,2,-1,270,bottom\n")
        panel = (b"Ref,Val,Package,PosX,PosY,Rot,Side\n"
                 b"C1,1u,C_0603,12,19,270,bottom\n"
                 b"R1,10k,R_0603,-8,3,107.125,top\n"
                 b"R1,10k,R_0603,10,20,17.125,top\n"
                 b"C1,1u,C_0603,-7,5,0,bottom\n")
        discovery = discover(parse_csv(source, "source"), parse_csv(panel, "panel"))
        actual = {(item.rotation, item.tx, item.ty, tuple(item.mapping))
                  for item in discovery.instances}
        self.assertEqual(actual, {
            (0, 10, 20, ((1, 3), (2, 1))),
            (90, -8, 3, ((1, 2), (2, 4))),
        })

    def test_all_quarter_turns_with_single_source_component(self):
        rows = [("U1", "MCU", "QFN", "-1.25", "2.5", "17.125", "bottom")]
        transforms = [(angle, 10 * i, -3 * i) for i, angle in enumerate((0, 90, 180, 270))]
        entries = [(i, row) for i, transform in enumerate(transforms)
                   for row in generated_copy(rows, transform)]
        entries.reverse()
        self.assert_matches_oracle(csv_bytes(rows), csv_bytes([row for _, row in entries]),
                                   expected_records(rows, entries, transforms))

    def test_exact_twelve_place_coordinates_and_large_derived_origin(self):
        rows = [("R1", "10k", "R", "-999999.999999999999", "-.000000000001", "-342.875", "bottom")]
        panel = [("R1", "10k", "R", "999999.999999999999", ".000000000001", "377.125", "bottom")]
        expected = frozenset({
            (0, Fraction("1999999.999999999998"), Fraction(".000000000002"), ((1, 1),)),
        })
        self.assert_matches_oracle(csv_bytes(rows), csv_bytes(panel), expected)

    def test_generated_complete_cases_include_all_transforms_and_mappings(self):
        """Incorrect quarter-turns, seed choice, signs, angle modulo or ordinals fail."""
        for seed in range(72):
            with self.subTest(seed=seed):
                rng = random.Random(seed + 1000)
                rows = generated_source(seed, 1 + seed % 5)
                transforms = [
                    (((seed + i) % 4) * 90, Fraction(100 * i - 150, 1) + Fraction(seed, 8),
                     Fraction(80 * i - 120, 1) - Fraction(seed, 16))
                    for i in range(1 + seed % 4)
                ]
                entries = [(i, row) for i, transform in enumerate(transforms)
                           for row in generated_copy(rows, transform)]
                rng.shuffle(rows)
                rng.shuffle(entries)
                self.assert_matches_oracle(csv_bytes(rows, bom=seed % 2 == 0),
                                           csv_bytes([row for _, row in entries]),
                                           expected_records(rows, entries, transforms))

    def test_generated_missing_and_altered_rows_preserve_only_complete_copies(self):
        """Ignoring any required label, side, position or angle would fail these cases."""
        mutations = ("missing", "reference", "value", "package", "x", "y", "angle", "side")
        for seed in range(24):
            source_rows = generated_source(seed + 200, 3 + seed % 3)
            transforms = [(0, -100, 50), (90, 10, -40), (270, 120, 80)]
            entries = [(i, row) for i, transform in enumerate(transforms)
                       for row in generated_copy(source_rows, transform)]
            for mutation in mutations:
                with self.subTest(seed=seed, mutation=mutation):
                    mutated = list(entries)
                    target = len(source_rows) + seed % len(source_rows)
                    if mutation == "missing":
                        del mutated[target]
                    else:
                        copy_id, old_row = mutated[target]
                        changed = list(old_row)
                        if mutation in ("reference", "value", "package"):
                            changed[{"reference": 0, "value": 1, "package": 2}[mutation]] += " changed"
                        elif mutation in ("x", "y", "angle"):
                            column = {"x": 3, "y": 4, "angle": 5}[mutation]
                            step = Fraction(1, 10**12 if mutation == "y" else 10**6)
                            changed[column] = exact_text(Fraction(changed[column]) + step)
                        else:
                            changed[6] = "top" if changed[6] == "bottom" else "bottom"
                        mutated[target] = (copy_id, tuple(changed))
                    random.Random(seed + 900).shuffle(mutated)
                    expected = expected_records(source_rows, mutated, transforms, exclude=(1,))
                    self.assert_matches_oracle(csv_bytes(source_rows),
                                               csv_bytes([row for _, row in mutated]), expected)

    def test_whole_board_added_removed_and_foreign_rows_do_not_hide_discovery(self):
        rows = generated_source(20, 4)
        transforms = [(0, -100, 0), (90, 0, 20), (180, 100, 40), (270, 200, 60)]
        for number in range(5):
            with self.subTest(number=number):
                entries = [(i, row) for i, transform in enumerate(transforms[:number])
                           for row in generated_copy(rows, transform)]
                panel_rows = [row for _, row in entries]
                panel_rows.insert(0, ("FID999", "fid", "Rail", "500", "600", "45", "top"))
                expected = frozenset(
                    (rotation, tx, ty, tuple((src, dst + 1) for src, dst in mapping))
                    for rotation, tx, ty, mapping in expected_records(rows, entries, transforms[:number])
                )
                self.assert_matches_oracle(csv_bytes(rows), csv_bytes(panel_rows), expected)

    def test_empty_panel_has_no_complete_copy(self):
        self.assert_matches_oracle(csv_bytes(generated_source(14, 3)), csv_bytes([]), frozenset())

    def test_reflection_and_unsupported_board_angle_do_not_match(self):
        rows = [
            ("A", "same", "Pkg", "0", "0", "17.125", "top"),
            ("B", "same", "Pkg", "2", "0", "33.25", "bottom"),
            ("C", "same", "Pkg", "0", "3", "-12.5", "top"),
        ]
        reflected = [(ref, value, package, exact_text(-Fraction(x) + 10),
                      exact_text(Fraction(y) + 20), exact_text(-Fraction(angle)), side)
                     for ref, value, package, x, y, angle, side in rows]
        self.assert_matches_oracle(csv_bytes(rows), csv_bytes(reflected), frozenset())
        # A single component at the origin allows an exact rational 45-degree
        # pose without approximating the irrational coordinates of other points.
        single = [rows[0]]
        unsupported = [tuple(list(rows[0][:5]) + ["62.125", rows[0][6]])]
        self.assert_matches_oracle(csv_bytes(single), csv_bytes(unsupported), frozenset())

    def test_source_export_revision_can_invalidate_every_instance(self):
        rows = generated_source(55, 3)
        panel_rows = generated_copy(rows, (90, -10, 25)) + generated_copy(rows, (270, 30, 40))
        changed_source = [list(row) for row in rows]
        changed_source[1][2] += " revised"
        self.assert_matches_oracle(csv_bytes(changed_source), csv_bytes(panel_rows), frozenset())

    def test_permutations_change_only_record_assignments(self):
        rows = generated_source(91, 5)
        transforms = [(angle, 100 * i, -50 * i) for i, angle in enumerate((0, 90, 180, 270))]
        entries = [(i, row) for i, transform in enumerate(transforms)
                   for row in generated_copy(rows, transform)]
        for seed in range(12):
            with self.subTest(seed=seed):
                shuffled_rows, shuffled_entries = list(rows), list(entries)
                rng = random.Random(seed)
                rng.shuffle(shuffled_rows)
                rng.shuffle(shuffled_entries)
                self.assert_matches_oracle(csv_bytes(shuffled_rows),
                                           csv_bytes([row for _, row in shuffled_entries]),
                                           expected_records(shuffled_rows, shuffled_entries, transforms))


if __name__ == "__main__":
    unittest.main()
