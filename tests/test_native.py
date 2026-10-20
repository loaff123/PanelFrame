"""Native known-answer gates; normal tests never require KiCad or KiKit."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from panelframe.model import parse_csv, parse_contract, UnsupportedInput
from panelframe.reports import recover,verify
from tests.support import contract_bytes

FIXTURE=Path(__file__).parent/'fixtures'/'native'

class NativeAcceptanceTests(unittest.TestCase):
    def test_licensed_original_fixture_hashes(self):
        provenance=json.loads((FIXTURE/'provenance.json').read_text())
        for name,digest in provenance['files_sha256'].items():
            with self.subTest(name=name):self.assertEqual(hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest(),digest)
        self.assertIn('Mike Panetta',(FIXTURE/'LICENSE.board').read_text())
    def test_native_positive_cases_recover_and_independently_verify(self):
        expected=json.loads((FIXTURE/'expected.json').read_text())['cases']
        for name in ('default','mixed','varied'):
            case=expected[name]
            with self.subTest(case=name),tempfile.TemporaryDirectory() as temp:
                out=Path(temp)/'report'
                paths=(FIXTURE/case['source'],FIXTURE/case['panel'],FIXTURE/f'contract-{name}.json')
                before=[p.read_bytes() for p in paths]
                self.assertTrue(recover(*paths,out));self.assertTrue(verify(*paths,out))
                saved=json.loads((out/'evidence.json').read_text())
                fields=('rotation_deg','tx_mm','ty_mm')
                self.assertEqual([tuple(i[k] for k in fields) for i in saved['instances']],[tuple(i[k] for k in fields) for i in case['transforms']])
                self.assertEqual(saved['coverage']['mapped_panel_rows'],case['panel_rows'])
                self.assertEqual([p.read_bytes() for p in paths],before)
                contract=json.loads(paths[2].read_text());self.assertNotIn('transforms',contract);self.assertNotIn('offsets',contract)
    def test_native_post_panel_edit_refuses_offsets_preserves_other_five(self):
        case=json.loads((FIXTURE/'expected.json').read_text())['cases']['varied-edited']
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'report'
            self.assertFalse(recover(FIXTURE/case['source'],FIXTURE/case['panel'],FIXTURE/'contract-varied-edited.json',out))
            self.assertFalse((out/'offsets.csv').exists())
            saved=json.loads((out/'evidence.json').read_text());self.assertEqual(saved['status'],'incomplete')
            fields=('rotation_deg','tx_mm','ty_mm')
            self.assertEqual([tuple(i[k] for k in fields) for i in saved['instances']],[tuple(i[k] for k in fields) for i in case['complete_transforms']])
            self.assertEqual(saved['coverage']['mapped_panel_rows'],320)
            self.assertEqual(len(saved['coverage']['unexplained_panel_records']),64)
    def test_native_bottom_labels_and_arbitrary_angle_are_preserved(self):
        source=parse_csv((FIXTURE/'source-mixed.csv').read_bytes(),'source')
        panel=parse_csv((FIXTURE/'panel-mixed.csv').read_bytes(),'panel')
        self.assertEqual(sum(r.side=='bottom' for r in source.rows),3)
        self.assertEqual(sum(r.side=='bottom' for r in panel.rows),12)
        self.assertEqual(str(next(r.angle for r in source.rows if r.ref=='U2')),'17.125000')
        self.assertEqual(len({r.ref for r in panel.rows}),64)
    def test_bottom_negated_profile_is_explicitly_unsupported(self):
        s=(FIXTURE/'source-mixed-bottom-negated.csv').read_bytes();p=(FIXTURE/'panel-mixed-bottom-negated.csv').read_bytes()
        sd,pd=parse_csv(s,'source'),parse_csv(p,'panel')
        with self.assertRaises(UnsupportedInput):parse_contract(contract_bytes(s,p,4,profile='kicad-9-pos-csv-mm-bottom-negated'),sd,pd)
