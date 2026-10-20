#!/usr/bin/env python3
"""Local end-to-end timing; generated panel is performance data, not native proof."""
import argparse
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import platform
import resource
import tempfile
import time
from panelframe.reports import recover,verify

p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--instances',type=int,default=100)
a=p.parse_args()
if not 1<=a.instances<=100:p.error('--instances must be 1 through 100')
source=a.source.read_bytes()
rows=list(csv.DictReader(io.StringIO(source.decode('utf-8-sig'),newline='')))
buf=io.StringIO(newline='');writer=csv.DictWriter(buf,fieldnames=['Ref','Val','Package','PosX','PosY','Rot','Side'],lineterminator='\n');writer.writeheader()
for n in range(a.instances):
    rotation=(n%4)*90
    for row in rows:
        x,y=Decimal(row['PosX']),Decimal(row['PosY'])
        if rotation==90:x,y=-y,x
        elif rotation==180:x,y=-x,-y
        elif rotation==270:x,y=y,-x
        writer.writerow({**row,'PosX':str(x+1000*(n%10)),'PosY':str(y+1000*(n//10)),
                         'Rot':str((Decimal(row['Rot'])+rotation)%360)})
panel=buf.getvalue().encode('utf-8')
contract={'schema_version':1,'profile':'kicad-9-pos-csv-mm-cartesian',
          'source_sha256':hashlib.sha256(source).hexdigest(),'panel_sha256':hashlib.sha256(panel).hexdigest(),
          'source_origin':'absolute','panel_origin':'absolute','expected_instances':a.instances,'excluded_panel_records':[]}
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);s,p,c=root/'source.csv',root/'panel.csv',root/'contract.json';out=root/'report'
    s.write_bytes(source);p.write_bytes(panel);c.write_text(json.dumps(contract))
    t=time.perf_counter();complete=recover(s,p,c,out);recover_seconds=time.perf_counter()-t
    t=time.perf_counter();verified=verify(s,p,c,out);verify_seconds=time.perf_counter()-t
    result={'kind':'synthetic performance panel derived from native source rows; not a native acceptance fixture',
            'python':platform.python_version(),'platform':platform.platform(),
            'source_rows':len(rows),'panel_rows':len(rows)*a.instances,'instances':a.instances,
            'source_bytes':len(source),'panel_bytes':len(panel),'complete':complete,'verified':verified,
            'recover_seconds':recover_seconds,'verify_seconds':verify_seconds,
            'process_peak_rss_kib_linux':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'report_bytes':sum(f.stat().st_size for f in out.iterdir())}
    assert complete and verified
    print(json.dumps(result,indent=2))
