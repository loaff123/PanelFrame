"""Independent core-review regressions for the frozen exact-pose contract."""
from decimal import Decimal, localcontext
import unittest

from panelframe.model import (
    PanelFrameError, UnsupportedInput, number, parse_contract, parse_csv,
)
from panelframe.matching import assess, discover
from tests.support import contract_bytes, csv_bytes


class CoreReviewTests(unittest.TestCase):
    def datasets(self, source, panel):
        source_raw, panel_raw = csv_bytes(source), csv_bytes(panel)
        return (source_raw, panel_raw, parse_csv(source_raw, 'source'),
                parse_csv(panel_raw, 'panel'))

    def test_long_json_integer_is_a_clean_contract_error(self):
        raw = csv_bytes([['A', 'v', 'p', '0', '0', '0', 'top']])
        source, panel = parse_csv(raw, 'source'), parse_csv(raw, 'panel')
        contract = contract_bytes(raw, raw).replace(
            b'"expected_instances": 1', b'"expected_instances": ' + b'9' * 5000)
        with self.assertRaises(PanelFrameError):
            parse_contract(contract, source, panel)

    def test_angle_normalization_is_independent_of_caller_exponent_range(self):
        raw = csv_bytes([['A', 'v', 'p', '0', '0', '0', 'top']])
        with localcontext() as context:
            context.Emax = 1
            for signal in context.traps:
                context.traps[signal] = False
            source = parse_csv(raw, 'source')
        self.assertTrue(source.rows[0].angle.is_finite())
        self.assertEqual(source.rows[0].angle, Decimal(0))

    def test_discovery_is_independent_of_caller_exponent_range_and_traps(self):
        raw = csv_bytes([['A', 'v', 'p', '1000', '0', '0', 'top']])
        source, panel = parse_csv(raw, 'source'), parse_csv(raw, 'panel')
        for traps in (True, False):
            with self.subTest(traps=traps), localcontext() as context:
                context.Emax = 2
                for signal in context.traps:
                    context.traps[signal] = traps
                result = discover(source, panel)
                self.assertEqual([(i.rotation, i.tx, i.ty, i.mapping) for i in result.instances],
                                 [(0, Decimal(0), Decimal(0), ((1, 1),))])

    def test_multiline_source_spans_are_physical_lines_but_records_are_logical(self):
        raw = csv_bytes([
            ['A', 'one\r\ntwo\r\nthree', 'p', '0', '0', '0', 'top'],
            ['B', 'four', 'p', '1', '2', '3', 'bottom'],
        ], newline='\r\n')
        rows = parse_csv(raw, 'source').rows
        self.assertEqual([(r.record, r.line_start, r.line_end) for r in rows],
                         [(1, 2, 4), (2, 5, 5)])

    def test_duplicate_foreign_pose_cannot_be_hidden_by_proposed_exclusions(self):
        rows = [
            ['A', 'v', 'p', '0', '0', '0', 'top'],
            ['FID', 'fid', 'p', '5', '6', '17.125', 'top'],
            ['FID', 'fid', 'p', '+5.000', '6.0', '-342.875', 'top'],
        ]
        with self.assertRaisesRegex(PanelFrameError, 'Duplicate normalized panel pose'):
            parse_csv(csv_bytes(rows), 'panel')

    def test_repeated_reference_same_position_different_angle_is_not_duplicate(self):
        source_rows = [['A', 'v', 'p', '0', '0', '17.125', 'bottom']]
        panel_rows = [
            ['A', 'v', 'p', '3', '4', '17.125', 'bottom'],
            ['A', 'v', 'p', '3', '4', '107.125', 'bottom'],
        ]
        sr, pr, source, panel = self.datasets(source_rows, panel_rows)
        contract = parse_contract(contract_bytes(sr, pr, count=2), source, panel)
        discovery = discover(source, panel)
        self.assertEqual([(i.rotation, i.tx, i.ty) for i in discovery.instances],
                         [(0, Decimal(3), Decimal(4)), (90, Decimal(3), Decimal(4))])
        self.assertTrue(assess(source, panel, contract, discovery).complete)

    def test_seed_uses_exact_labels_then_lexical_reference(self):
        source_rows = [
            ['B', 'v', 'p', '2', '0', '0', 'top'],
            ['A', 'v', 'p', '0', '0', '0', 'top'],
        ]
        panel_rows = source_rows + [
            ['A', 'wrong', 'p', '4', '0', '0', 'top'],
            ['A', 'wrong', 'p', '5', '0', '0', 'top'],
        ]
        _, _, source, panel = self.datasets(source_rows, panel_rows)
        discovery = discover(source, panel)
        self.assertEqual(discovery.seed_ref, 'A')
        self.assertEqual(len(discovery.instances), 1)

    def test_missing_pose_diagnostic_is_exact_and_does_not_accuse_nearby_row(self):
        source_rows = [
            ['A', 'v', 'p', '0', '0', '0', 'top'],
            ['B', 'Ω<value>', 'pkg', '2', '-3', '17.125', 'bottom'],
        ]
        panel_rows = [
            ['A', 'v', 'p', '10', '20', '90', 'top'],
            ['B', 'Ω<value>', 'pkg', '13.000001', '22', '107.125', 'bottom'],
        ]
        _, _, source, panel = self.datasets(source_rows, panel_rows)
        discovery = discover(source, panel)
        self.assertEqual(discovery.instances, ())
        self.assertEqual(discovery.rejected_count, 1)
        detail = discovery.rejected[0]
        self.assertEqual(detail['missing_pose_count'], 1)
        self.assertEqual(detail['first_missing_poses'], [{
            'source_record': 2, 'reference': 'B', 'value': 'Ω<value>', 'package': 'pkg',
            'side': 'bottom', 'x_mm': '13', 'y_mm': '22', 'angle_deg': '107.125',
        }])
        self.assertNotIn('panel_record', detail['first_missing_poses'][0])

    def test_missing_diagnostics_are_bounded_without_losing_rejection_total(self):
        source_rows = [
            ['A', 'v', 'p', '0', '0', '0', 'top'],
            ['B', 'v', 'p', '2', '0', '0', 'top'],
        ]
        panel_rows = [
            [ref, 'v', 'p', str(10 * i + delta), '0', '0', 'top']
            for i in range(101) for ref, delta in [('A', 0), ('B', 3)]
        ]
        _, _, source, panel = self.datasets(source_rows, panel_rows)
        discovery = discover(source, panel)
        self.assertEqual(discovery.candidate_count, 101)
        self.assertEqual(discovery.rejected_count, 101)
        self.assertEqual(len(discovery.rejected), 100)
        self.assertEqual(discovery.instances, ())

    def test_derived_origin_parser_accepts_full_reachable_range(self):
        self.assertEqual(number('1999999.999999999998', derived=True),
                         Decimal('1999999.999999999998'))
        self.assertEqual(number('-1999999.999999999998', derived=True),
                         Decimal('-1999999.999999999998'))
        for value in ('2000000', '-2000000', '0.0000000000001'):
            with self.subTest(value=value), self.assertRaises(UnsupportedInput):
                number(value, derived=True)

    def test_duplicate_keys_inside_exclusions_are_rejected(self):
        source_rows = [['A', 'v', 'p', '0', '0', '0', 'top']]
        sr, pr, source, panel = self.datasets(
            source_rows, source_rows + [['FID', 'v', 'p', '1', '0', '0', 'top']])
        raw = contract_bytes(sr, pr, exclusions=[{'record': 2, 'reason': 'Rail'}])
        raw = raw.replace(b'"reason": "Rail"', b'"reason": "Rail", "reason": "Again"')
        with self.assertRaisesRegex(PanelFrameError, 'Duplicate JSON key'):
            parse_contract(raw, source, panel)

    def test_input_numeric_spelling_does_not_change_byte_hash_binding(self):
        source_rows = [['A', 'v', 'p', '0', '0', '0', 'top']]
        sr, pr, source, panel = self.datasets(source_rows, source_rows)
        equivalent = parse_csv(pr.replace(b',0,0,0,', b',+0.0,-0,360,'), 'panel')
        self.assertEqual(equivalent.rows[0].pose, panel.rows[0].pose)
        self.assertNotEqual(equivalent.sha256, panel.sha256)
        with self.assertRaisesRegex(PanelFrameError, 'panel_sha256'):
            parse_contract(contract_bytes(sr, pr), source, equivalent)


if __name__ == '__main__':
    unittest.main()
