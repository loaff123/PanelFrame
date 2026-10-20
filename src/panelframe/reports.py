"""Deterministic handoff files and a saved-witness verifier without discovery."""
import csv
from decimal import Context, Decimal, localcontext
import html
import io
import json
from pathlib import Path
from . import __version__
from .model import (PanelFrameError, UnsupportedInput, MAX_CSV_BYTES, MAX_CONTRACT_BYTES,
                    parse_csv, parse_contract, inventory, json_object, exact_keys,
                    number, decimal_text)

SCOPE = ('Checks only the supplied exported component rows under the declared exact-pose '
         'contract. This is not electrical, physical, manufacturing, vendor-format, or '
         'assembly approval. Omitted export rows and falsely declared export settings '
         'cannot be checked. Hashes bind bytes, not authorship or authenticity.')
OFFSET_HEADER = ('instance_id','source_origin_x_mm','source_origin_y_mm','rotation_ccw_deg','matched_rows')
MAX_REPORT_BYTES = 256 * 1024 * 1024

def read_file(path, limit):
    path=Path(path)
    try:
        if not path.is_file():
            raise PanelFrameError(f'Expected an ordinary file: {path}')
        with path.open('rb') as stream:
            raw=stream.read(limit+1)
    except OSError as exc:
        raise PanelFrameError(f'Cannot read {path}: {exc}') from exc
    if len(raw)>limit:
        raise UnsupportedInput(f'File exceeds operational byte limit: {path}')
    return raw

def load_inputs(source_path,panel_path,contract_path):
    source=parse_csv(read_file(source_path,MAX_CSV_BYTES),'source')
    panel=parse_csv(read_file(panel_path,MAX_CSV_BYTES),'panel')
    contract=parse_contract(read_file(contract_path,MAX_CONTRACT_BYTES),source,panel)
    return source,panel,contract

def json_bytes(value):
    try:
        return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PanelFrameError('Evidence must be finite JSON with valid Unicode scalar values') from exc

def make_evidence(source,panel,contract,instances,outcome,diagnostics=None):
    return {'schema_version':1,'tool_version':__version__,'scope':SCOPE,
            'status':'complete' if outcome.complete else 'incomplete',
            'inputs':{'source':inventory(source),'panel':inventory(panel),'contract_sha256':contract.sha256},
            'assumptions':{'profile':contract.profile,'units':'mm','reference_mode':'same',
                           'source_origin':contract.source_origin,'panel_origin':contract.panel_origin,
                           'export_settings_are_operator_declarations':True},
            'expected_instances':contract.expected_instances,
            'instances':[{'instance_id':f'I{n:03d}','rotation_deg':i.rotation,
                          'tx_mm':decimal_text(i.tx),'ty_mm':decimal_text(i.ty),'matched_rows':len(i.mapping),
                          'mapping':[{'source_record':s,'panel_record':p} for s,p in i.mapping]}
                         for n,i in enumerate(instances,1)],
            'exclusions':[{'record':r,'reason':reason} for r,reason in contract.excluded_panel_records],
            'coverage':{'source_rows':len(source.rows),'panel_rows':len(panel.rows),'instances':len(instances),
                        'mapped_panel_rows':len(outcome.mapped_records),
                        'excluded_panel_rows':len(contract.excluded_panel_records),
                        'unexplained_panel_records':list(outcome.unexplained_records)},
            'issues':list(outcome.issues),'diagnostics':diagnostics or {}}

def offsets_bytes(evidence):
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n')
    writer.writerow(OFFSET_HEADER)
    for i in evidence['instances']:
        writer.writerow((i['instance_id'],i['tx_mm'],i['ty_mm'],i['rotation_deg'],i['matched_rows']))
    return stream.getvalue().encode('utf-8')

def html_bytes(evidence,source,panel):
    escape=lambda value:html.escape(str(value),quote=True)
    lines=['<!doctype html>','<html lang="en"><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           '<title>PanelFrame exported-row pose report</title>',
           '<style>body{font:16px system-ui;max-width:1000px;margin:2rem auto;padding:1rem;color:#17232c}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:.4rem;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}.notice{border:2px solid #987;padding:1rem}</style>',
           '<h1>PanelFrame: '+escape(evidence['status'])+'</h1>',
           '<p class="notice">'+escape(SCOPE)+'</p>',
           '<p>Origins are source-export (0, 0) in the panel-export Cartesian frame. '
           'Rotations are counterclockwise quarter-turns. Instance IDs belong only to this report.</p>']
    if evidence['status']!='complete':
        lines.append('<p class="notice">INCOMPLETE: no offsets handoff is emitted. Complete copies below are partial evidence. This does not label the board defective.</p>')
    lines.append('<h2>Recognized complete copies</h2><table><tr><th>Instance</th><th>X mm</th><th>Y mm</th><th>CCW degrees</th><th>Rows</th></tr>')
    for i in evidence['instances']:
        lines.append('<tr>'+''.join('<td>'+escape(i[k])+'</td>' for k in ('instance_id','tx_mm','ty_mm','rotation_deg','matched_rows'))+'</tr>')
    lines.append('</table><h2>Source export labels and poses</h2><table><tr><th>Record</th><th>Reference</th><th>Value</th><th>Package</th><th>Side</th><th>X</th><th>Y</th><th>Angle</th></tr>')
    for r in source.rows:
        lines.append('<tr>'+''.join('<td>'+escape(v)+'</td>' for v in (r.record,r.ref,r.value,r.package,r.side,decimal_text(r.x),decimal_text(r.y),decimal_text(r.angle)))+'</tr>')
    lines.append('</table><h2>Evidence and coverage</h2><pre>'+escape(json_bytes(evidence).decode('utf-8'))+'</pre></html>')
    return ('\n'.join(lines)+'\n').encode('utf-8')

def recover(source_path,panel_path,contract_path,output_path):
    from .matching import discover,assess
    source,panel,contract=load_inputs(source_path,panel_path,contract_path)
    output=Path(output_path)
    if output.exists() or output.is_symlink():
        raise PanelFrameError('Output must be a new directory; existing paths and aliases are not overwritten')
    discovery=discover(source,panel)
    outcome=assess(source,panel,contract,discovery)
    diagnostics={} if outcome.complete else {'seed_reference':discovery.seed_ref,
                 'candidate_count':discovery.candidate_count,'rejected_count':discovery.rejected_count,
                 'first_rejected_candidates':list(discovery.rejected),
                 'note':'Only exact missing expected poses are reported; no same-reference row is blamed by proximity. Diagnostics are limited to 100 candidates and 10 missing poses each.'}
    evidence=make_evidence(source,panel,contract,discovery.instances,outcome,diagnostics)
    members=[('evidence.json',json_bytes(evidence)),('report.html',html_bytes(evidence,source,panel))]
    if outcome.complete:
        members.append(('offsets.csv',offsets_bytes(evidence)))
    created=[]
    made_directory=False
    try:
        output.mkdir()
        made_directory=True
        for name,raw in members:
            path=output/name
            created.append(path)
            path.write_bytes(raw)
    except OSError as exc:
        # Best-effort cleanup of this invocation's files only. Not a concurrency sandbox.
        if made_directory:
            for path in reversed(created):
                try:path.unlink(missing_ok=True)
                except OSError:pass
            try:output.rmdir()
            except OSError:pass
        raise PanelFrameError(f'Cannot write new report directory: {exc}') from exc
    return outcome.complete

def verify(source_path,panel_path,contract_path,report_path):
    """Check a full saved witness directly. Never discover candidate transforms.

    Parser validation is shared. Geometric transformation, row uniqueness and full
    coverage are independently checked here, without matcher/rotate/assess calls.
    Canonical regeneration binds every reported input fact and both rendered files.
    """
    from .matching import Instance,Outcome
    source,panel,contract=load_inputs(source_path,panel_path,contract_path)
    report=Path(report_path)
    saved=json_object(read_file(report/'evidence.json',MAX_REPORT_BYTES),MAX_REPORT_BYTES)
    if saved.get('status')!='complete':
        raise PanelFrameError('Only a complete handoff can be verified; diagnostics are not a proof')
    instances=saved.get('instances')
    if not isinstance(instances,list) or len(instances)!=contract.expected_instances:
        raise PanelFrameError('Reported instance count does not match contract')
    checked=[]
    assigned=set()
    transforms=[]
    with localcontext(Context(prec=64)):
        for index,item in enumerate(instances,1):
            exact_keys(item,('instance_id','rotation_deg','tx_mm','ty_mm','matched_rows','mapping'),'Reported instance')
            r=item['rotation_deg']
            if type(r) is not int or r not in (0,90,180,270):
                raise PanelFrameError('Reported rotation is not an integer quarter-turn')
            tx,ty=number(item['tx_mm'],derived=True),number(item['ty_mm'],derived=True)
            mapping=item['mapping']
            if not isinstance(mapping,list) or len(mapping)!=len(source.rows):
                raise PanelFrameError('Reported mapping does not cover each source row')
            pairs=[]
            for source_row,pair in zip(source.rows,mapping):
                exact_keys(pair,('source_record','panel_record'),'Mapping')
                s,p=pair['source_record'],pair['panel_record']
                if type(s) is not int or s!=source_row.record or type(p) is not int or not 1<=p<=len(panel.rows):
                    raise PanelFrameError('Invalid or noncanonical row assignment')
                if p in assigned:
                    raise PanelFrameError('A panel record is assigned more than once')
                target=panel.rows[p-1]
                x,y=source_row.x,source_row.y
                # Independent explicit Cartesian quarter-turn equations.
                if r==0:expected_x,expected_y=x+tx,y+ty
                elif r==90:expected_x,expected_y=tx-y,ty+x
                elif r==180:expected_x,expected_y=tx-x,ty-y
                else:expected_x,expected_y=tx+y,ty-x
                expected_angle=(source_row.angle+Decimal(r))%Decimal(360)
                if (source_row.ref,source_row.value,source_row.package,source_row.side)!=(target.ref,target.value,target.package,target.side) or (expected_x,expected_y,expected_angle)!=(target.x,target.y,target.angle):
                    raise PanelFrameError(f'Reported pose does not match source record {s} and panel record {p}')
                assigned.add(p)
                pairs.append((s,p))
            transforms.append((r,tx,ty))
            checked.append(Instance(r,tx,ty,tuple(pairs)))
    if transforms!=sorted(set(transforms)):
        raise PanelFrameError('Transforms are duplicated or not in canonical order')
    excluded={r for r,reason in contract.excluded_panel_records}
    if assigned&excluded or assigned|excluded!=set(range(1,len(panel.rows)+1)):
        raise PanelFrameError('Saved mapping and exclusions do not account for every panel record exactly once')
    outcome=Outcome(True,(),tuple(sorted(assigned)),())
    expected=make_evidence(source,panel,contract,checked,outcome)
    if json_bytes(saved)!=json_bytes(expected):
        raise PanelFrameError('Saved evidence facts differ from the originals or contract')
    if read_file(report/'offsets.csv',MAX_REPORT_BYTES)!=offsets_bytes(expected):
        raise PanelFrameError('offsets.csv differs from the verified transformations')
    if read_file(report/'report.html',MAX_REPORT_BYTES)!=html_bytes(expected,source,panel):
        raise PanelFrameError('report.html differs from the verified evidence')
    return True
