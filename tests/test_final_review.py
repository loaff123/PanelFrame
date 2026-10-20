"""Independent final-release review regressions; no native tools required."""
from contextlib import ExitStack
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from panelframe.model import PanelFrameError
from panelframe.reports import recover, verify
from tests.support import BASE, contract_bytes, csv_bytes
from tests.test_matching import panel_rows


class FinalReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.csv'
        self.panel = self.root / 'panel.csv'
        self.contract = self.root / 'contract.json'
        self.out = self.root / 'report'
        self.prepare(BASE, panel_rows(BASE, [(0, '10', '20'), (90, '-30', '5')]), 2)

    def prepare(self, source_rows, panel_data, count=1, exclusions=None):
        self.source.write_bytes(csv_bytes(source_rows))
        self.panel.write_bytes(csv_bytes(panel_data))
        self.contract.write_bytes(contract_bytes(self.source.read_bytes(), self.panel.read_bytes(), count, exclusions))

    def make(self):
        self.assertTrue(recover(self.source, self.panel, self.contract, self.out))

    def check(self):
        return verify(self.source, self.panel, self.contract, self.out)

    def evidence(self):
        return json.loads((self.out / 'evidence.json').read_bytes())

    def replace_evidence(self, evidence):
        (self.out / 'evidence.json').write_text(json.dumps(evidence), encoding='utf-8')

    def test_verifier_uses_no_discovery_rotation_or_assessment(self):
        self.make()
        with ExitStack() as stack:
            for name in ('discover', 'rotate', 'assess'):
                stack.enter_context(patch('panelframe.matching.' + name, side_effect=AssertionError(name)))
            self.assertTrue(self.check())

    def test_strict_scalar_types_include_all_reported_facts(self):
        self.make()
        # Equal Python values must not make bool/int or float/int interchange valid.
        cases = [
            (('schema_version',), True),
            (('schema_version',), 1.0),
            (('expected_instances',), 2.0),
            (('inputs', 'source', 'rows'), 2.0),
            (('inputs', 'source', 'utf8_bom'), 0),
            (('assumptions', 'export_settings_are_operator_declarations'), 1),
            (('coverage', 'instances'), 2.0),
            (('coverage', 'mapped_panel_rows'), 4.0),
            (('coverage', 'excluded_panel_rows'), False),
            (('instances', 0, 'matched_rows'), 2.0),
            (('instances', 0, 'rotation_deg'), False),
            (('instances', 0, 'tx_mm'), 10),
            (('instances', 0, 'mapping', 0, 'source_record'), True),
            (('instances', 0, 'mapping', 0, 'panel_record'), True),
        ]
        original = (self.out / 'evidence.json').read_bytes()
        for path, value in cases:
            with self.subTest(path=path, value=value):
                item = json.loads(original)
                target = item
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.replace_evidence(item)
                with self.assertRaises(PanelFrameError):
                    self.check()
        (self.out / 'evidence.json').write_bytes(original)
        self.assertTrue(self.check())

    def test_structural_mapping_corruption_is_rejected(self):
        self.make()
        original = (self.out / 'evidence.json').read_bytes()
        def repeated_panel(e):
            e['instances'][1]['mapping'][0]['panel_record'] = e['instances'][0]['mapping'][0]['panel_record']
        def repeated_source(e):
            e['instances'][0]['mapping'][1]['source_record'] = 1
        def reversed_source(e):
            e['instances'][0]['mapping'].reverse()
        def outside_panel(e):
            e['instances'][0]['mapping'][0]['panel_record'] = 5
        def absent_source(e):
            e['instances'][0]['mapping'].pop()
        def duplicate_instance(e):
            e['instances'][1] = e['instances'][0]
        def reversed_instances(e):
            e['instances'].reverse()
        for mutate in (repeated_panel, repeated_source, reversed_source, outside_panel,
                       absent_source, duplicate_instance, reversed_instances):
            with self.subTest(mutate=mutate.__name__):
                item = json.loads(original)
                mutate(item)
                self.replace_evidence(item)
                with self.assertRaises(PanelFrameError):
                    self.check()

    def test_exclusions_are_verified_with_full_accounting(self):
        rows = panel_rows(BASE, [(90, '-30', '5')])
        rows.append(['FID', 'rail', 'dot', '4', '9', '0', 'top'])
        self.prepare(BASE, rows, exclusions=[{'record': 3, 'reason': 'Added rail fiducial'}])
        self.make()
        self.assertTrue(self.check())
        self.assertEqual(self.evidence()['coverage'], {
            'source_rows': 2, 'panel_rows': 3, 'instances': 1,
            'mapped_panel_rows': 2, 'excluded_panel_rows': 1,
            'unexplained_panel_records': []})
        original = (self.out / 'evidence.json').read_bytes()
        for exclusions in ([], [{'record': 2, 'reason': 'Added rail fiducial'}],
                           [{'record': 3, 'reason': 'Changed annotation'}]):
            with self.subTest(exclusions=exclusions):
                item = json.loads(original)
                item['exclusions'] = exclusions
                self.replace_evidence(item)
                with self.assertRaises(PanelFrameError):
                    self.check()

    def test_each_original_remains_byte_bound_after_equivalent_change(self):
        self.make()
        for path in (self.source, self.panel, self.contract):
            original = path.read_bytes()
            with self.subTest(path=path.name):
                # CSV CRLF is semantically equivalent; extra JSON whitespace is too.
                changed = original.replace(b'\n', b'\r\n') if path != self.contract else original + b'\n'
                self.assertNotEqual(changed, original)
                path.write_bytes(changed)
                with self.assertRaises(PanelFrameError):
                    self.check()
                path.write_bytes(original)
        self.assertTrue(self.check())

    def test_all_quarters_support_full_derived_origin_range(self):
        a = '999999.999999999999'
        source = [['A', 'value', 'package', '-' + a, a, '80.000000000001', 'bottom']]
        panel = [['A', 'value', 'package', a, '-' + a, angle, 'bottom']
                 for angle in ('80.000000000001', '170.000000000001', '260.000000000001', '350.000000000001')]
        self.prepare(source, panel, 4)
        self.make()
        self.assertTrue(self.check())
        large = '1999999.999999999998'
        self.assertEqual([(i['rotation_deg'], i['tx_mm'], i['ty_mm']) for i in self.evidence()['instances']],
                         [(0, large, '-' + large), (90, large, '0'), (180, '0', '0'), (270, '0', '-' + large)])

    def test_html_all_untrusted_labels_and_exclusion_reason_are_inert(self):
        ref = '<img src=x onerror="alert(1)">\nΩ'
        value = '</pre><script>alert("value")</script>&µ'
        package = '<svg/onload=alert(2)>"\''
        reason = '</pre><iframe src="https://invalid.example/"></iframe>'
        source = [[ref, value, package, '0', '0', '0', 'top']]
        self.prepare(source, source + [['FID', 'rail', 'dot', '2', '2', '0', 'top']],
                     exclusions=[{'record': 2, 'reason': reason}])
        self.make()
        self.assertTrue(self.check())
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(convert_charrefs=True)
                self.tags = []
                self.attributes = []
                self.parts = []
            def handle_starttag(self, tag, attrs):
                self.tags.append(tag)
                self.attributes.extend(attrs)
            def handle_data(self, data):
                self.parts.append(data)
        parser = Parser()
        parser.feed((self.out / 'report.html').read_text(encoding='utf-8'))
        self.assertFalse({'script', 'img', 'svg', 'iframe'} & set(parser.tags))
        self.assertFalse(any(k in ('src', 'href') or k.startswith('on') for k, _ in parser.attributes))
        text = ''.join(parser.parts)
        for label in (ref, value, package):
            self.assertIn(label, text)
        self.assertIn(json.dumps(reason, ensure_ascii=False)[1:-1], text)

    def test_partial_offsets_write_failure_cleans_new_report(self):
        before = [p.read_bytes() for p in (self.source, self.panel, self.contract)]
        original = Path.write_bytes
        def fail(path, data):
            if path.name == 'offsets.csv':
                original(path, data[:5])
                raise OSError('simulated disk full during final handoff write')
            return original(path, data)
        with patch.object(Path, 'write_bytes', fail), self.assertRaises(PanelFrameError):
            recover(self.source, self.panel, self.contract, self.out)
        self.assertFalse(self.out.exists())
        self.assertEqual([p.read_bytes() for p in (self.source, self.panel, self.contract)], before)

    def test_output_aliases_and_dangling_symlink_are_not_replaced(self):
        before = [p.read_bytes() for p in (self.source, self.panel, self.contract)]
        aliases = [self.root / 'hard-link', self.root / 'dangling-link', self.root / 'directory-link']
        aliases[0].hardlink_to(self.source)
        aliases[1].symlink_to(self.root / 'absent-target')
        aliases[2].symlink_to(self.root, target_is_directory=True)
        for path in aliases:
            with self.subTest(path=path.name), self.assertRaises(PanelFrameError):
                recover(self.source, self.panel, self.contract, path)
        self.assertTrue(aliases[1].is_symlink())
        self.assertFalse((self.root / 'absent-target').exists())
        self.assertEqual([p.read_bytes() for p in (self.source, self.panel, self.contract)], before)

    def test_original_report_facts_cannot_be_hidden_by_unknown_fields(self):
        self.make()
        original = (self.out / 'evidence.json').read_bytes()
        cases = [('inputs',), ('inputs', 'source'), ('assumptions',), ('coverage',), ('instances', 0)]
        for path in cases:
            with self.subTest(path=path):
                item = json.loads(original)
                target = item
                for key in path:
                    target = target[key]
                target['review_annotation'] = 'This extra field must not silently change the schema.'
                self.replace_evidence(item)
                with self.assertRaises(PanelFrameError):
                    self.check()
