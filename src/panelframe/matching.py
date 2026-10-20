"""Exact label-and-pose template recognition, with no tolerance fitting."""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Context, localcontext
from .model import angle_mod, decimal_text

@dataclass(frozen=True)
class Instance:
    rotation: int
    tx: object
    ty: object
    mapping: tuple

@dataclass(frozen=True)
class Discovery:
    instances: tuple
    seed_ref: str
    candidate_count: int
    rejected_count: int
    rejected: tuple

@dataclass(frozen=True)
class Outcome:
    complete: bool
    issues: tuple
    mapped_records: tuple
    unexplained_records: tuple

def rotate(x,y,rotation):
    if rotation == 0:
        return x,y
    if rotation == 90:
        return y.copy_negate(),x
    if rotation == 180:
        return x.copy_negate(),y.copy_negate()
    if rotation == 270:
        return y,x.copy_negate()
    raise ValueError('Expected a quarter-turn')

def discover(source, panel):
    by_labels=defaultdict(list)
    by_pose={}
    for row in panel.rows:
        by_labels[row.labels].append(row)
        by_pose[row.pose]=row
    seed=min(source.rows,key=lambda r:(len(by_labels[r.labels]),r.ref))
    candidates={}
    rejected=[]
    rejected_count=0
    with localcontext(Context(prec=64)):
        for target in by_labels[seed.labels]:
            rotation=angle_mod(target.angle-seed.angle)
            if rotation not in (0,90,180,270):
                rejected_count+=1
                if len(rejected)<100:
                    rejected.append({'seed_panel_record':target.record,'reason':'angle_difference_is_not_quarter_turn'})
                continue
            rotation=int(rotation)
            sx,sy=rotate(seed.x,seed.y,rotation)
            key=(rotation,target.x-sx,target.y-sy)
            candidates[key]=None
        instances=[]
        for (rotation,tx,ty) in sorted(candidates):
            mapping=[]
            missing=[]
            for row in source.rows:
                x,y=rotate(row.x,row.y,rotation)
                pose=row.labels+(x+tx,y+ty,angle_mod(row.angle+rotation))
                match=by_pose.get(pose)
                if match is None:
                    if len(missing)<10:
                        missing.append({'source_record':row.record,'reference':row.ref,
                                        'value':row.value,'package':row.package,'side':row.side,
                                        'x_mm':decimal_text(pose[-3]),'y_mm':decimal_text(pose[-2]),
                                        'angle_deg':decimal_text(pose[-1])})
                else:
                    mapping.append((row.record,match.record))
            if len(mapping)==len(source.rows):
                instances.append(Instance(rotation,tx,ty,tuple(mapping)))
            else:
                rejected_count+=1
                if len(rejected)<100:
                    rejected.append({'rotation_deg':rotation,'tx_mm':decimal_text(tx),'ty_mm':decimal_text(ty),
                                     'missing_pose_count':len(source.rows)-len(mapping),'first_missing_poses':missing})
    return Discovery(tuple(instances),seed.ref,len(candidates),rejected_count,tuple(rejected))

def assess(source, panel, contract, discovery):
    issues=[]
    if len(discovery.instances)!=contract.expected_instances:
        issues.append('instance_count_mismatch')
    mapped=[p for i in discovery.instances for s,p in i.mapping]
    if len(mapped)!=len(set(mapped)):
        issues.append('overlapping_assignments')
    exclusions={r for r,reason in contract.excluded_panel_records}
    if set(mapped)&exclusions:
        issues.append('excluded_record_is_mapped')
    unexplained=set(range(1,len(panel.rows)+1))-set(mapped)-exclusions
    if unexplained:
        issues.append('unexplained_panel_records')
    return Outcome(not issues,tuple(issues),tuple(sorted(set(mapped))),tuple(sorted(unexplained)))
