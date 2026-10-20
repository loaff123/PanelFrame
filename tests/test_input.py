import json
import unittest
from decimal import Decimal
from panelframe.model import parse_csv, parse_contract, PanelFrameError, UnsupportedInput
from tests.support import BASE, HEADER, csv_bytes, contract_bytes

class InputTests(unittest.TestCase):
    def test_csv_bom_crlf_quotes_and_logical_records(self):
        rows = [['R1','a,"b\n<c>','µ','+01.00','-.5','-360.125','bottom']]
        d = parse_csv(b'\xef\xbb\xbf' + csv_bytes(rows, newline='\r\n'), 'source')
        self.assertEqual(d.rows[0].record, 1)
        self.assertEqual(d.rows[0].value, 'a,"b\n<c>')
        self.assertEqual((d.rows[0].x,d.rows[0].y,d.rows[0].angle), (Decimal(1),Decimal('-.5'),Decimal('359.875')))
        self.assertTrue(d.bom)
    def test_strict_headers(self):
        for h in [HEADER[:-1], HEADER+['Extra'], HEADER[::-1], ['Ref']*7]:
            with self.subTest(h=h), self.assertRaises(PanelFrameError): parse_csv(csv_bytes(BASE,h),'source')
    def test_record_width_blank_and_malformed_csv(self):
        for raw in [csv_bytes([BASE[0][:-1]]),csv_bytes([BASE[0]+['x']]),csv_bytes(BASE)+b'\n', b'Ref,Val,Package,PosX,PosY,Rot,Side\n"broken']:
            with self.subTest(raw=raw), self.assertRaises(PanelFrameError): parse_csv(raw,'source')
    def test_utf8_and_nul_rejected(self):
        for raw in [b'\xff', csv_bytes([['R\x001',*BASE[0][1:]]])]:
            with self.assertRaises(PanelFrameError): parse_csv(raw,'source')
    def test_source_unique_nonempty_references(self):
        for rows in [[], [BASE[0],BASE[0]], [['',*BASE[0][1:]]]]:
            with self.assertRaises(PanelFrameError): parse_csv(csv_bytes(rows),'source')
    def test_panel_repeated_references_legal(self):
        d = parse_csv(csv_bytes([BASE[0],['R1','10k','R_0603','5','2','90','top']]),'panel')
        self.assertEqual(len(d.rows),2)
    def test_panel_normalized_duplicates_rejected(self):
        with self.assertRaises(PanelFrameError): parse_csv(csv_bytes([BASE[0],['R1','10k','R_0603','1.00','+2','360','top']]),'panel')
    def test_empty_panel_valid(self): self.assertEqual(len(parse_csv(csv_bytes([]),'panel').rows),0)
    def test_side_exact(self):
        for side in ['Top','front','',' bottom']:
            with self.assertRaises(PanelFrameError): parse_csv(csv_bytes([[*BASE[0][:-1],side]]),'source')
    def test_numeric_grammar(self):
        for v in ['NaN','inf','1e2',' 1','1 ','１','.', '', '--1','0x1']:
            row=list(BASE[0]); row[3]=v
            with self.subTest(v=v), self.assertRaises(PanelFrameError): parse_csv(csv_bytes([row]),'source')
    def test_numeric_boundaries(self):
        for col,good,bad in [(3,'999999.999999999999','1000000'),(4,'-999999.999999999999','-1000000'),(5,'999999999.999999999999','1000000000'),(3,'0.000000000001','0.0000000000001')]:
            row=list(BASE[0]);row[col]=good;parse_csv(csv_bytes([row]),'source')
            row[col]=bad
            with self.assertRaises(UnsupportedInput):parse_csv(csv_bytes([row]),'source')
    def test_numeric_token_length(self):
        row=list(BASE[0]);row[3]='0'*255+'1';parse_csv(csv_bytes([row]),'source')
        row[3]='0'*256+'1'
        with self.assertRaises(UnsupportedInput):parse_csv(csv_bytes([row]),'source')
    def test_row_boundaries(self):
        rows=[[f'R{i}','v','p',str(i), '0','0','top'] for i in range(2001)]
        self.assertEqual(len(parse_csv(csv_bytes(rows[:2000]),'source').rows),2000)
        with self.assertRaises(UnsupportedInput):parse_csv(csv_bytes(rows),'source')
        rows=[[f'R{i}','v','p',str(i), '0','0','top'] for i in range(50001)]
        self.assertEqual(len(parse_csv(csv_bytes(rows[:50000]),'panel').rows),50000)
        with self.assertRaises(UnsupportedInput):parse_csv(csv_bytes(rows),'panel')
    def test_byte_boundary(self):
        raw=csv_bytes([BASE[0]]); n=16*1024*1024-len(raw)
        padded=raw.replace(b'10k', b'a'*n+b'10k')
        self.assertEqual(len(padded),16*1024*1024)
        parse_csv(padded,'source')
        with self.assertRaises(UnsupportedInput):parse_csv(padded+b'\n','source')
    def test_context_precision_cannot_round_input_angle(self):
        from decimal import localcontext
        row=list(BASE[0]);row[5]='999999999.123456789012'
        with localcontext() as c:
            c.prec=3
            self.assertEqual(parse_csv(csv_bytes([row]),'source').rows[0].angle,Decimal('279.123456789012'))

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.s=csv_bytes(BASE); self.p=csv_bytes(BASE+[['FID1','fid','dot','0','0','0','top']])
        self.sd=parse_csv(self.s,'source');self.pd=parse_csv(self.p,'panel')
    def parse(self, raw=None, **changes): return parse_contract(raw or contract_bytes(self.s,self.p,**changes),self.sd,self.pd)
    def test_valid_and_declared_origins(self):
        self.assertEqual(self.parse(panel_origin='drill-place').expected_instances,1)
        self.assertEqual(self.parse(count=100).expected_instances,100)
    def test_counts_strict(self):
        for n in [0,101,True,1.0,'1',None]:
            with self.subTest(n=n),self.assertRaises(PanelFrameError):self.parse(count=n)
    def test_schema_unknown_missing_duplicate(self):
        raw=contract_bytes(self.s,self.p)
        for value in [raw[:-1]+b',"schema_version":1}', raw[:-1]+b',"offsets":[]}', b'{}']:
            with self.assertRaises(PanelFrameError): self.parse(value)
        for version in [True,1.0,2]:
            with self.assertRaises(PanelFrameError): self.parse(schema_version=version)
    def test_profile_and_origin(self):
        with self.assertRaises(UnsupportedInput):self.parse(profile='bottom-x-negated')
        with self.assertRaises(PanelFrameError):self.parse(source_origin='unknown')
    def test_hash_exact_binding(self):
        for h in ['a'*64,'A'*64,'x','']:
            with self.assertRaises(PanelFrameError):self.parse(source_sha256=h)
    def test_exclusions_bound_and_only_foreign_refs(self):
        self.assertEqual(self.parse(exclusions=[{'record':3,'reason':'Added rail fiducial'}]).excluded_panel_records, ((3,'Added rail fiducial'),))
        for xs in [[{'record':1,'reason':'hide'}],[{'record':0,'reason':'x'}],[{'record':4,'reason':'x'}],[{'record':True,'reason':'x'}],[{'record':3,'reason':' '}],[{'record':3,'reason':'x','extra':1}],[{'record':3,'reason':'x'}]*2]:
            with self.subTest(xs=xs),self.assertRaises(PanelFrameError):self.parse(exclusions=xs)
    def test_exclusion_cannot_hide_altered_source_member(self):
        panel=csv_bytes(BASE+[['R1','different','other','5','6','10','bottom']]); pd=parse_csv(panel,'panel')
        with self.assertRaises(PanelFrameError):parse_contract(contract_bytes(self.s,panel,exclusions=[{'record':3,'reason':'hide'}]),self.sd,pd)

if __name__=='__main__':unittest.main()
