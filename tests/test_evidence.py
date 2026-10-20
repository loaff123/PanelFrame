import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from panelframe.model import PanelFrameError, parse_csv, parse_contract
from panelframe.matching import discover, assess
from panelframe.reports import recover, verify
from tests.support import BASE, csv_bytes, contract_bytes
from tests.test_matching import panel_rows

class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=csv_bytes(BASE);self.panel=csv_bytes(panel_rows(BASE,[(0,'10','20'),(90,'-30','5')]))
        self.contract=contract_bytes(self.source,self.panel,2)
        self.paths=[self.root/'source.csv',self.root/'panel.csv',self.root/'contract.json']
        for p,v in zip(self.paths,[self.source,self.panel,self.contract]):p.write_bytes(v)
        self.out=self.root/'result'
    def make(self):return recover(*self.paths,self.out)
    def check(self):return verify(*self.paths,self.out)
    def test_complete_artifact_verifies_without_discovery(self):
        self.assertTrue(self.make())
        self.assertEqual({p.name for p in self.out.iterdir()},{'offsets.csv','evidence.json','report.html'})
        with patch('panelframe.matching.discover',side_effect=AssertionError('Verifier must not discover')):
            self.assertTrue(self.check())
        for p,v in zip(self.paths,[self.source,self.panel,self.contract]):self.assertEqual(p.read_bytes(),v)
    def test_exact_transform_and_row_mapping(self):
        self.make();e=json.loads((self.out/'evidence.json').read_text())
        self.assertEqual([(x['rotation_deg'],x['tx_mm'],x['ty_mm']) for x in e['instances']],[(0,'10','20'),(90,'-30','5')])
        self.assertEqual(e['coverage']['mapped_panel_rows'],4)
        self.assertEqual(e['instances'][0]['mapping'],[{'source_record':1,'panel_record':1},{'source_record':2,'panel_record':2}])
    def test_evidence_tampering_fails(self):
        self.make();path=self.out/'evidence.json';original=path.read_bytes()
        def translation(e): e['instances'][0]['tx_mm']='11'
        def rotation(e): e['instances'][0]['rotation_deg']=90
        def count(e):e['expected_instances']=1
        def assignment(e):e['instances'][0]['mapping'][0]['panel_record']=2
        def exclusion(e):e['exclusions']=[{'record':1,'reason':'hide'}]
        def normalization(e):e['inputs']['source']['normalized_numeric_fields']=999
        def coverage(e):e['coverage']['mapped_panel_rows']=3
        def extra(e):e['invented']='x'
        def missing(e):del e['instances'][0]['mapping']
        for mutate in [translation,rotation,count,assignment,exclusion,normalization,coverage,extra,missing]:
            with self.subTest(mutate=mutate.__name__):
                e=json.loads(original);mutate(e);path.write_text(json.dumps(e))
                with self.assertRaises(PanelFrameError):self.check()
                path.write_bytes(original)
    def test_csv_html_missing_member_and_original_tampering_fail(self):
        self.make()
        for name in ['offsets.csv','report.html','evidence.json']:
            path=self.out/name;raw=path.read_bytes();path.unlink()
            with self.assertRaises(PanelFrameError):self.check()
            path.write_bytes(raw)
            path.write_bytes(raw+b'changed')
            with self.assertRaises(PanelFrameError):self.check()
            path.write_bytes(raw)
        self.paths[0].write_bytes(self.source.replace(b'10k',b'11k'))
        with self.assertRaises(PanelFrameError):self.check()
    def test_evidence_strict_types_and_duplicate_json_keys(self):
        self.make();p=self.out/'evidence.json';raw=p.read_bytes()
        for val in [True,0.0,'0',45]:
            e=json.loads(raw);e['instances'][0]['rotation_deg']=val;p.write_text(json.dumps(e))
            with self.assertRaises(PanelFrameError):self.check()
        p.write_bytes(raw[:-2]+b',"schema_version":1}\n')
        with self.assertRaises(PanelFrameError):self.check()
    def test_incomplete_has_diagnostics_and_no_offsets(self):
        self.paths[1].write_bytes(csv_bytes(panel_rows(BASE,[(0,'10','20')]) + [['R1','wrong','R_0603','-32','6','90','top']]))
        self.paths[2].write_bytes(contract_bytes(self.source,self.paths[1].read_bytes(),2))
        self.assertFalse(self.make())
        self.assertFalse((self.out/'offsets.csv').exists())
        e=json.loads((self.out/'evidence.json').read_text())
        self.assertEqual(e['status'],'incomplete');self.assertEqual(len(e['instances']),1)
        self.assertTrue(e['issues'])
        with self.assertRaises(PanelFrameError):self.check()
    def test_new_directory_and_alias_protection(self):
        self.out.mkdir()
        with self.assertRaises(PanelFrameError):self.make()
        for path in self.paths:
            with self.assertRaises(PanelFrameError):recover(*self.paths,path)
        alias=self.root/'alias';alias.symlink_to(self.paths[0])
        with self.assertRaises(PanelFrameError):recover(*self.paths,alias)
        for p,v in zip(self.paths,[self.source,self.panel,self.contract]):self.assertEqual(p.read_bytes(),v)
    def test_normal_write_failure_leaves_no_success_file(self):
        original=Path.write_bytes
        def failing(path,data):
            if path.name=='report.html':raise OSError('simulated full disk')
            return original(path,data)
        with patch.object(Path,'write_bytes',failing), self.assertRaises(PanelFrameError):self.make()
        self.assertFalse((self.out/'offsets.csv').exists())
        self.assertFalse(self.out.exists())
    def test_derived_origin_and_html_escaping(self):
        rows=[['A','<script>alert("x")</script>\nµ & Ω','P<>&','-999999.999999999999','0','17.125','bottom']]
        panel=[['A',rows[0][1],rows[0][2],'999999.999999999999','0','17.125','bottom']]
        self.paths[0].write_bytes(csv_bytes(rows));self.paths[1].write_bytes(csv_bytes(panel))
        self.paths[2].write_bytes(contract_bytes(self.paths[0].read_bytes(),self.paths[1].read_bytes()))
        self.assertTrue(self.make());self.assertTrue(self.check())
        e=json.loads((self.out/'evidence.json').read_text());self.assertEqual(e['instances'][0]['tx_mm'],'1999999.999999999998')
        html=(self.out/'report.html').read_text();self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html);self.assertIn('µ &amp; Ω',html)
    def test_deterministic_artifacts(self):
        self.make();other=self.root/'other';recover(*self.paths,other)
        for p in self.out.iterdir():self.assertEqual(p.read_bytes(),(other/p.name).read_bytes())

class EvidenceBoundaryTests(unittest.TestCase):
    setUp=EvidenceTests.setUp
    make=EvidenceTests.make
    check=EvidenceTests.check
    def test_invalid_surrogate_reason_is_clean_input_error(self):
        panel=self.panel+ b'FID,fid,dot,0,0,0,top\n'
        self.paths[1].write_bytes(panel)
        raw=contract_bytes(self.source,panel,2,exclusions=[{'record':5,'reason':'sentinel'}]).replace(b'sentinel',b'\\ud800')
        self.paths[2].write_bytes(raw)
        with self.assertRaises(PanelFrameError):self.make()
    def test_surrogate_report_tampering_is_clean_verification_error(self):
        self.make();p=self.out/'evidence.json';e=json.loads(p.read_bytes());e['scope']='\ud800';p.write_text(json.dumps(e))
        with self.assertRaises(PanelFrameError):self.check()
    def test_verifier_uses_its_own_arithmetic_context(self):
        from decimal import localcontext
        self.make()
        with localcontext() as ctx:
            ctx.prec=1;ctx.Emax=1
            self.assertTrue(self.check())
