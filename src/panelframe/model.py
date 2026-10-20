"""Strict byte-bound inputs. Declarations do not prove exporter settings."""
from collections import Counter
import csv
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
import hashlib
import io
import json
import re

MAX_CSV_BYTES = 16 * 1024 * 1024
MAX_CONTRACT_BYTES = 1024 * 1024
HEADER = ('Ref', 'Val', 'Package', 'PosX', 'PosY', 'Rot', 'Side')
PROFILE = 'kicad-9-pos-csv-mm-cartesian'
NUMBER = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z', re.ASCII)
HASH = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)

class PanelFrameError(ValueError):
    """Invalid input, contract, or saved evidence."""

class UnsupportedInput(PanelFrameError):
    """Outside the explicit profile or operational limits."""

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def decimal_text(value):
    if value == 0:
        return '0'
    result = format(value, 'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result

def number(token, *, angle=False, derived=False):
    if not isinstance(token, str) or not NUMBER.fullmatch(token):
        raise PanelFrameError('Numeric fields require plain ASCII decimal tokens without whitespace')
    if len(token) > 256:
        raise UnsupportedInput('Numeric token exceeds 256 characters')
    if '.' in token and len(token.split('.')[1]) > 12:
        raise UnsupportedInput('More than 12 fractional decimal places')
    value = Decimal(token)
    bound = Decimal(1000000000 if angle else 2000000 if derived else 1000000)
    if value.copy_abs() >= bound:
        raise UnsupportedInput('Numeric value outside the declared operational range')
    return value

def angle_mod(value):
    with localcontext(Context(prec=64)):
        return (value % Decimal(360) + Decimal(360)) % Decimal(360)

@dataclass(frozen=True)
class Row:
    record: int
    line_start: int
    line_end: int
    ref: str
    value: str
    package: str
    x: Decimal
    y: Decimal
    angle: Decimal
    side: str

    @property
    def labels(self):
        return self.ref, self.value, self.package, self.side

    @property
    def pose(self):
        return self.labels + (self.x, self.y, self.angle)

@dataclass(frozen=True)
class Dataset:
    rows: tuple
    sha256: str
    role: str
    byte_count: int
    bom: bool
    normalized_numeric_fields: int

@dataclass(frozen=True)
class Contract:
    sha256: str
    profile: str
    source_origin: str
    panel_origin: str
    expected_instances: int
    excluded_panel_records: tuple

def parse_csv(raw, role):
    if role not in ('source', 'panel'):
        raise PanelFrameError('CSV role must be source or panel')
    if not isinstance(raw, bytes):
        raise PanelFrameError('CSV input must be bytes')
    if len(raw) > MAX_CSV_BYTES:
        raise UnsupportedInput('CSV exceeds 16 MiB')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise PanelFrameError('CSV must be UTF-8') from exc
    if '\x00' in text:
        raise PanelFrameError('NUL characters are unsupported in CSV text')
    # The CSV has a byte bound; permit individual quoted fields up to that bound.
    previous_limit = csv.field_size_limit()
    csv.field_size_limit(MAX_CSV_BYTES)
    result, references, poses = [], set(), set()
    normalized = 0
    try:
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        if tuple(next(reader, ())) != HEADER:
            raise PanelFrameError('Header must be exactly Ref,Val,Package,PosX,PosY,Rot,Side')
        previous_line = reader.line_num
        for record, fields in enumerate(reader, 1):
            if record > (2000 if role == 'source' else 50000):
                raise UnsupportedInput(f'{role} row count exceeds operational limit')
            if len(fields) != 7:
                raise PanelFrameError(f'{role} record {record}: expected exactly seven fields')
            ref, value, package, x_token, y_token, angle_token, side = fields
            if not ref:
                raise PanelFrameError(f'{role} record {record}: reference must be nonempty')
            if side not in ('top', 'bottom'):
                raise PanelFrameError(f'{role} record {record}: Side must be top or bottom')
            x, y = number(x_token), number(y_token)
            angle = angle_mod(number(angle_token, angle=True))
            normalized += sum(a != decimal_text(b) for a,b in [(x_token,x),(y_token,y),(angle_token,angle)])
            row = Row(record, previous_line+1, reader.line_num, ref, value, package, x, y, angle, side)
            previous_line = reader.line_num
            if role == 'source' and ref in references:
                raise PanelFrameError(f'Duplicate source reference: {ref!r}')
            if role == 'panel' and row.pose in poses:
                raise PanelFrameError(f'Duplicate normalized panel pose at record {record}')
            references.add(ref)
            poses.add(row.pose)
            result.append(row)
    except csv.Error as exc:
        raise PanelFrameError(f'Malformed CSV: {exc}') from exc
    finally:
        csv.field_size_limit(previous_limit)
    if role == 'source' and not result:
        raise PanelFrameError('Source CSV must contain at least one data record')
    return Dataset(tuple(result),digest(raw),role,len(raw),raw.startswith(b'\xef\xbb\xbf'),normalized)

def json_object(raw, max_bytes=MAX_CONTRACT_BYTES):
    if not isinstance(raw, bytes) or len(raw) > max_bytes:
        raise UnsupportedInput('JSON input exceeds operational byte limit')
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:
                raise PanelFrameError(f'Duplicate JSON key: {key}')
            value[key]=item
        return value
    def constant(value):
        raise PanelFrameError(f'Non-finite JSON value: {value}')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
    except PanelFrameError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PanelFrameError('Invalid UTF-8 JSON') from exc
    if not isinstance(value, dict):
        raise PanelFrameError('JSON root must be an object')
    return value

def exact_keys(obj, keys, what):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        raise PanelFrameError(f'{what} has missing or unknown fields')

def parse_contract(raw, source, panel):
    obj=json_object(raw)
    exact_keys(obj, ('schema_version','profile','source_sha256','panel_sha256','source_origin','panel_origin','expected_instances','excluded_panel_records'), 'Contract')
    if type(obj['schema_version']) is not int or obj['schema_version'] != 1:
        raise PanelFrameError('Contract schema_version must be integer 1')
    if obj['profile'] != PROFILE:
        raise UnsupportedInput('Unsupported export profile')
    for key,data in [('source_sha256',source),('panel_sha256',panel)]:
        if not isinstance(obj[key],str) or not HASH.fullmatch(obj[key]) or obj[key] != data.sha256:
            raise PanelFrameError(f'{key} does not bind the supplied bytes')
    for key in ('source_origin','panel_origin'):
        if obj[key] not in ('absolute','drill-place'):
            raise PanelFrameError(f'{key} must be absolute or drill-place')
    count=obj['expected_instances']
    if type(count) is not int or not 1 <= count <= 100:
        raise PanelFrameError('expected_instances must be an integer from 1 through 100')
    exclusions=obj['excluded_panel_records']
    if not isinstance(exclusions,list):
        raise PanelFrameError('excluded_panel_records must be an array')
    source_refs={r.ref for r in source.rows}
    seen=set()
    excluded=[]
    for item in exclusions:
        exact_keys(item,('record','reason'),'Exclusion')
        record,reason=item['record'],item['reason']
        if type(record) is not int or not 1 <= record <= len(panel.rows) or record in seen:
            raise PanelFrameError('Exclusion record is invalid or duplicated')
        if not isinstance(reason,str) or not reason.strip():
            raise PanelFrameError('Exclusion requires a nonempty reason')
        try:
            reason.encode('utf-8')
        except UnicodeError as exc:
            raise PanelFrameError('Exclusion reason must contain valid Unicode scalar values') from exc
        if panel.rows[record-1].ref in source_refs:
            raise PanelFrameError('Cannot exclude a reference occurring in the source')
        seen.add(record)
        excluded.append((record,reason))
    return Contract(digest(raw),PROFILE,obj['source_origin'],obj['panel_origin'],count,tuple(sorted(excluded)))

def inventory(data):
    refs=Counter(r.ref for r in data.rows)
    return {'sha256':data.sha256,'bytes':data.byte_count,'rows':len(data.rows),
            'unique_references':len(refs),'repeated_references':sum(n>1 for n in refs.values()),
            'sides':dict(sorted(Counter(r.side for r in data.rows).items())),
            'utf8_bom':data.bom,'normalized_numeric_fields':data.normalized_numeric_fields}
