import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tests.support import BASE,csv_bytes,contract_bytes

class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.s=self.root/'source.csv';self.p=self.root/'panel.csv';self.c=self.root/'contract.json'
        self.s.write_bytes(csv_bytes(BASE));self.p.write_bytes(csv_bytes(BASE));self.c.write_bytes(contract_bytes(self.s.read_bytes(),self.p.read_bytes()))
    def call(self,*args):
        env=dict(os.environ)
        env['PYTHONDONTWRITEBYTECODE']='1'
        return subprocess.run([sys.executable,'-m','panelframe',*map(str,args)],capture_output=True,text=True,env=env)
    def test_help_version(self):
        r=self.call('--help');self.assertEqual(r.returncode,0);self.assertIn('recover',r.stdout)
        r=self.call('--version');self.assertEqual(r.returncode,0);self.assertIn('0.1.0a1',r.stdout)
    def test_inspect_does_not_infer_profile_and_refuses_overwrite(self):
        out=self.root/'inventory.json';r=self.call('inspect',self.s,self.p,'--json',out)
        self.assertEqual(r.returncode,0,r.stderr);v=json.loads(out.read_text())
        self.assertEqual(v['source']['rows'],2);self.assertNotIn('profile',v)
        self.assertIn('does not infer',v['scope'])
        r=self.call('inspect',self.s,self.p,'--json',out);self.assertEqual(r.returncode,2)
        r=self.call('inspect',self.s,self.p,'--json',self.s);self.assertEqual(r.returncode,2)
    def test_recover_verify_complete_and_immutable(self):
        before=[p.read_bytes() for p in (self.s,self.p,self.c)];out=self.root/'report'
        r=self.call('recover',self.s,self.p,'--contract',self.c,'--out',out);self.assertEqual(r.returncode,0,r.stderr)
        r=self.call('verify',self.s,self.p,'--contract',self.c,'--report',out);self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual([p.read_bytes() for p in (self.s,self.p,self.c)],before)
    def test_incomplete_exit_one(self):
        self.p.write_bytes(csv_bytes(BASE[:1]));self.c.write_bytes(contract_bytes(self.s.read_bytes(),self.p.read_bytes()));out=self.root/'report'
        r=self.call('recover',self.s,self.p,'--contract',self.c,'--out',out)
        self.assertEqual(r.returncode,1,r.stderr);self.assertFalse((out/'offsets.csv').exists())
    def test_invalid_unsupported_and_missing_input_clean(self):
        original=self.c.read_bytes()
        for value,code in [({},2),({**json.loads(original),'profile':'bottom-x-negated'},3)]:
            self.c.write_text(json.dumps(value));r=self.call('recover',self.s,self.p,'--contract',self.c,'--out',self.root/'report')
            self.assertEqual(r.returncode,code,r.stderr);self.assertNotIn('Traceback',r.stderr);self.assertFalse((self.root/'report').exists())
        self.c.write_bytes(original);self.s.unlink();r=self.call('recover',self.s,self.p,'--contract',self.c,'--out',self.root/'report')
        self.assertEqual(r.returncode,2);self.assertNotIn('Traceback',r.stderr)
    def test_long_integer_and_deep_json_clean(self):
        for raw in [b'{"expected_instances":'+b'1'*5000+b'}',b'{"a":'+b'['*2000+b'0'+b']'*2000+b'}']:
            self.c.write_bytes(raw);r=self.call('recover',self.s,self.p,'--contract',self.c,'--out',self.root/'report')
            self.assertEqual(r.returncode,2,r.stderr);self.assertNotIn('Traceback',r.stderr)
    def test_failed_output_parent_clean(self):
        r=self.call('recover',self.s,self.p,'--contract',self.c,'--out',self.root/'missing'/'report')
        self.assertEqual(r.returncode,2,r.stderr);self.assertNotIn('Traceback',r.stderr)
