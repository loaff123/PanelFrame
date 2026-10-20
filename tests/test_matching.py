import unittest
from decimal import Decimal, localcontext
from panelframe.model import parse_csv, parse_contract
from panelframe.matching import discover, assess
from tests.support import BASE, csv_bytes, contract_bytes

def panel_rows(source, transforms):
    result=[]
    for r,tx,ty in transforms:
        for row in source:
            ref,val,pkg,x,y,a,side=row
            x,y,a=Decimal(x),Decimal(y),Decimal(a)
            rx,ry={0:(x,y),90:(-y,x),180:(-x,-y),270:(y,-x)}[r]
            result.append([ref,val,pkg,str(rx+Decimal(tx)),str(ry+Decimal(ty)),str((a+r)%360),side])
    return result

class MatchingTests(unittest.TestCase):
    def run_case(self, source, panel, count, exclusions=None):
        s,p=csv_bytes(source),csv_bytes(panel)
        sd,pd=parse_csv(s,'source'),parse_csv(p,'panel')
        contract=parse_contract(contract_bytes(s,p,count,exclusions),sd,pd)
        discovery=discover(sd,pd)
        return discovery,assess(sd,pd,contract,discovery)
    def test_all_quarter_turns_repeated_references(self):
        ts=[(0,'10','20'),(90,'-30','5'),(180,'9','-100'),(270,'70','-80')]
        d,o=self.run_case(BASE,panel_rows(BASE,ts),4)
        self.assertEqual([(i.rotation,str(i.tx),str(i.ty)) for i in d.instances],ts)
        self.assertTrue(o.complete)
        self.assertEqual(len({p for i in d.instances for s,p in i.mapping}),8)
    def test_each_pose_field_change_prevents_complete_handoff(self):
        good=panel_rows(BASE,[(0,'10','20'),(90,'-30','5')])
        for col,new in [(0,'R9'),(1,'different'),(2,'other'),(3,'11.000001'),(4,'22.000001'),(5,'0.000001'),(6,'bottom')]:
            rows=[r[:] for r in good];rows[0][col]=new
            with self.subTest(col=col):
                d,o=self.run_case(BASE,rows,2)
                self.assertFalse(o.complete)
                self.assertEqual(len(d.instances),1)
    def test_removed_row_missing_board_extra_board(self):
        for ts,remove in [([(0,'10','20'),(90,'-30','5')],True), ([(0,'10','20')],False), ([(0,'10','20'),(90,'-30','5'),(270,'70','-80')],False)]:
            rows=panel_rows(BASE,ts)
            if remove: rows.pop()
            self.assertFalse(self.run_case(BASE,rows,2)[1].complete)
    def test_foreign_row_requires_exclusion(self):
        rows=panel_rows(BASE,[(0,'10','20')])+[['FID','fid','dot','7','8','0','top']]
        self.assertFalse(self.run_case(BASE,rows,1)[1].complete)
        self.assertTrue(self.run_case(BASE,rows,1,[{'record':3,'reason':'Rail fiducial'}])[1].complete)
    def test_non_quarter_turn_and_reflection_fail(self):
        source=[['A','v','p','0','0','0','top'],['B','v','p','2','3','17','bottom']]
        for rows in [[['A','v','p','0','0','45','top'],['B','v','p','2','3','62','bottom']], [['A','v','p','0','0','0','top'],['B','v','p','-2','3','17','bottom']]]:
            self.assertFalse(self.run_case(source,rows,1)[1].complete)
    def test_derived_origin_exceeds_input_bound_exactly(self):
        source=[['A','v','p','-999999.999999999999','0','0','top']]
        panel=[['A','v','p','999999.999999999999','0','0','top']]
        with localcontext() as ctx:
            ctx.prec=3
            d,o=self.run_case(source,panel,1)
        self.assertTrue(o.complete)
        self.assertEqual(d.instances[0].tx,Decimal('1999999.999999999998'))
    def test_permutation_stable_transforms(self):
        rows=panel_rows(BASE,[(270,'70','-80'),(0,'10','20')])
        a,_=self.run_case(BASE,rows,2);b,_=self.run_case(BASE[::-1],rows[::-1],2)
        self.assertEqual([(i.rotation,i.tx,i.ty) for i in a.instances],[(i.rotation,i.tx,i.ty) for i in b.instances])
    def test_source_revision_changing_exported_field_is_not_explained(self):
        rows=panel_rows(BASE,[(0,'10','20'),(90,'-30','5')])
        changed=[r[:] for r in BASE];changed[1][1]='new revision value'
        self.assertFalse(self.run_case(changed,rows,2)[1].complete)

    def test_disjointness_is_checked_even_if_discovery_invariant_breaks(self):
        from dataclasses import replace
        s,p=csv_bytes(BASE),csv_bytes(BASE)
        sd,pd=parse_csv(s,'source'),parse_csv(p,'panel');c=parse_contract(contract_bytes(s,p,2),sd,pd)
        d=discover(sd,pd);d=replace(d,instances=d.instances*2)
        self.assertFalse(assess(sd,pd,c,d).complete)
        self.assertIn('overlapping_assignments',assess(sd,pd,c,d).issues)
