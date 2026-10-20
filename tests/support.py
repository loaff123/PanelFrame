import csv
import hashlib
import io
import json

HEADER = ['Ref', 'Val', 'Package', 'PosX', 'PosY', 'Rot', 'Side']

def csv_bytes(rows, header=HEADER, newline='\n'):
    f = io.StringIO(newline='')
    w = csv.writer(f, lineterminator=newline)
    w.writerow(header)
    w.writerows(rows)
    return f.getvalue().encode('utf-8')

def contract_bytes(source, panel, count=1, exclusions=None, **changes):
    value = dict(schema_version=1, profile='kicad-9-pos-csv-mm-cartesian',
                 source_sha256=hashlib.sha256(source).hexdigest(),
                 panel_sha256=hashlib.sha256(panel).hexdigest(),
                 source_origin='absolute', panel_origin='absolute',
                 expected_instances=count, excluded_panel_records=exclusions or [])
    value.update(changes)
    return json.dumps(value, ensure_ascii=False).encode('utf-8')

BASE = [['R1', '10k', 'R_0603', '1', '2', '0', 'top'],
        ['U1', 'µC', 'QFN', '3', '-4', '17.125', 'bottom']]
