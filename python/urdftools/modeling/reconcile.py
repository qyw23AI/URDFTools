"""Review a returned CAD assembly without mutating user link/joint edits."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer

from urdftools.cad.step2urdf_adapter import load_step
from urdftools.cad.step_reader import inspect_step


class ReconcileError(ValueError):
    pass


def _count(shape, kind):
    explorer=TopExp_Explorer(shape,kind)
    result=0
    while explorer.More():
        result+=1;explorer.Next()
    return result


def _parts(path):
    inspection=inspect_step(path)
    if inspection['units']['source_length_unit']!='mm' or inspection['adapter']['status']!='matched':
        raise ReconcileError('CAD source must have unambiguous mm units and matching part readers')
    parts={}
    for part in load_step(str(path)):
        if part.name in parts: raise ReconcileError(f'Duplicate part name: {part.name}')
        if part.approximate: raise ReconcileError(f'{part.name}: open geometry cannot be relinked')
        parts[part.name]={'name':part.name,'volume_mm3':float(part.volume),
          'center_mm':[float(v) for v in part.com],
          'bounds_mm':[float(b-a) for a,b in zip(part.bbox_min,part.bbox_max)],
          'faces':_count(part.shape,TopAbs_FACE),'solids':_count(part.shape,TopAbs_SOLID)}
    return inspection,parts


def compare_cad_versions(baseline: str | Path, returned: str | Path, *,
                         expected_baseline_sha256: str, link_mapping: dict[str,str] | None = None) -> dict:
    baseline,returned=Path(baseline),Path(returned)
    if baseline.resolve()==returned.resolve(): raise ReconcileError('Return source must differ from baseline')
    old_hash=hashlib.sha256(baseline.read_bytes()).hexdigest()
    if old_hash!=expected_baseline_sha256: raise ReconcileError('Baseline STEP changed since mapping was recorded')
    old_inspection,old=_parts(baseline)
    new_inspection,new=_parts(returned)
    mapping=link_mapping or {name:name for name in old}
    if set(mapping)!=set(old): raise ReconcileError('Link mapping does not cover exact baseline parts')
    if any(not isinstance(name,str) or not name for name in mapping.values()):
        raise ReconcileError('Link mapping contains an invalid link name')
    relinks=[];conflicts=[];used=set()
    for name,previous in old.items():
        candidate=name if name in new else None
        if candidate is None:
            signatures=[key for key,item in new.items() if key not in used and
              item['faces']==previous['faces'] and item['solids']==previous['solids'] and
              math.isclose(item['volume_mm3'],previous['volume_mm3'],rel_tol=1e-7,abs_tol=1e-6)]
            if len(signatures)==1: candidate=signatures[0]
            else:
                conflicts.append({'part':name,'kind':'missing_or_ambiguous',
                  'candidates':signatures,'preserved_link':mapping[name]});continue
        current=new[candidate]
        used.add(candidate)
        topology_changed=(previous['faces'],previous['solids'])!=(current['faces'],current['solids'])
        if topology_changed:
            conflicts.append({'part':name,'returned_part':candidate,'kind':'topology_changed',
              'before':previous,'after':current,'preserved_link':mapping[name]});continue
        relinks.append({'baseline_part':name,'returned_part':candidate,'link':mapping[name],
            'renamed':name!=candidate,
            'volume_delta_mm3':current['volume_mm3']-previous['volume_mm3'],
            'center_delta_mm':[b-a for a,b in zip(previous['center_mm'],current['center_mm'])],
            'bounds_delta_mm':[b-a for a,b in zip(previous['bounds_mm'],current['bounds_mm'])]})
    for name in sorted(set(new)-used):
        conflicts.append({'part':name,'kind':'new_unmapped_part','preserved_link':None})
    return {'status':'conflict' if conflicts else 'review_required',
      'baseline_sha256':old_hash,'returned_sha256':new_inspection['source']['sha256'],
      'baseline_part_count':len(old),'returned_part_count':len(new),
      'relinks':relinks,'conflicts':conflicts,'link_mapping_preserved':mapping,
      'requires_human_confirmation':True,
      'automatically_applied':False}
