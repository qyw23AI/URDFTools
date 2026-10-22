"""Versioned, data-only CAD suggestion preview with explicit human application."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import uuid

from urdftools.modeling.core import apply_project, build_project, ModelingError


class AgentToolError(ValueError):
    pass


_PREVIEW_SCHEMA={
  'name':'preview_recipe',
  'description':'Create an isolated, uncommitted CAD preview from a complete allowlisted recipe.',
  'input_schema':{'type':'object','additionalProperties':False,
    'required':['schema_version','action','expected_revision','recipe','rationale'],
    'properties':{'schema_version':{'const':1},'action':{'const':'replace_recipe'},
      'expected_revision':{'type':'integer','minimum':0},
      'recipe':{'type':'object'},'rationale':{'type':'string','maxLength':2000}}}}


def tool_catalog():
    """Only model-callable tools. apply_preview is reserved for the human UI."""
    return [_PREVIEW_SCHEMA]


def _digest(data: bytes):
    return hashlib.sha256(data).hexdigest()


def _current(project: Path):
    pointer=project/'current.json'
    if not pointer.is_file(): return 0,None,None
    current=json.loads(pointer.read_text())
    revision=current['revision']
    if not isinstance(revision,int) or revision<1: raise AgentToolError('Current revision pointer invalid')
    folder=project/'revisions'/f'{revision:06d}'
    report=folder/'report.json'
    if _digest(report.read_bytes())!=current['report_sha256']:
        raise AgentToolError('Current revision report changed')
    recipe=json.loads((folder/'recipe.json').read_text())
    return revision,current['report_sha256'],recipe


def _validate_suggestion(value):
    if not isinstance(value,dict) or set(value)!={'schema_version','action','expected_revision','recipe','rationale'}:
        raise AgentToolError('Suggestion must contain only the declared schema fields')
    if value['schema_version']!=1 or value['action']!='replace_recipe':
        raise AgentToolError('Unsupported agent action')
    if isinstance(value['expected_revision'],bool) or not isinstance(value['expected_revision'],int) or value['expected_revision']<0:
        raise AgentToolError('Invalid expected revision')
    if not isinstance(value['rationale'],str) or not value['rationale'].strip() or len(value['rationale'])>2000:
        raise AgentToolError('Rationale is required and must be under 2000 characters')
    if not isinstance(value['recipe'],dict): raise AgentToolError('Recipe must be a JSON object')
    _validate_recipe_keys(value['recipe'])
    try: encoded=json.dumps(value,ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError) as exc: raise AgentToolError('Suggestion must be finite JSON data') from exc
    if len(encoded.encode())>4*1024*1024: raise AgentToolError('Suggestion exceeds 4 MiB')


def _keys(value, allowed, label):
    if not isinstance(value,dict) or not set(value)<=set(allowed):
        raise AgentToolError(f'{label} contains undeclared fields')


def _validate_recipe_keys(recipe):
    _keys(recipe,('schema_version','parts'),'recipe')
    if not isinstance(recipe.get('parts'),list): raise AgentToolError('parts must be an array')
    for index,part in enumerate(recipe['parts']):
        _keys(part,('name','material','density_kg_m3','profile','operation','modifiers','placement_mm'),f'part {index}')
        profile=part.get('profile')
        _keys(profile,('kind','width_mm','height_mm','radius_mm','points_mm','holes'),f'part {index} profile')
        if not isinstance(profile.get('holes',[]),list): raise AgentToolError('holes must be an array')
        for hole in profile.get('holes',[]):
            _keys(hole,('center_mm','radius_mm'),f'part {index} hole')
        _keys(part.get('operation'),('kind','distance_mm','axis','angle_deg'),f'part {index} operation')
        if not isinstance(part.get('modifiers',[]),list): raise AgentToolError('modifiers must be an array')
        for modifier in part.get('modifiers',[]):
            _keys(modifier,('kind','size_mm','center_mm','radius_mm','height_mm','parallel_axis'),f'part {index} modifier')
        if 'placement_mm' in part:
            values=part['placement_mm']
            if not isinstance(values,list) or len(values)!=3 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>=1e6 for v in values):
                raise AgentToolError('placement_mm must contain three finite coordinates under 1000 m')


def _diff(before,after):
    old={part['name']:part for part in before.get('parts',[])} if before else {}
    new={part['name']:part for part in after['parts']}
    return {'added_parts':sorted(set(new)-set(old)),'removed_parts':sorted(set(old)-set(new)),
      'changed_parts':sorted(name for name in set(old)&set(new) if old[name]!=new[name])}


def preview_recipe(project: str | Path, suggestion: dict) -> dict:
    """Build actual STEP/STL assets in a separate proposal; never move current.json."""
    project=Path(project).resolve()
    _validate_suggestion(suggestion)
    revision,report_hash,before=_current(project)
    if suggestion['expected_revision']!=revision: raise AgentToolError('Stale suggestion revision')
    proposal_id=uuid.uuid4().hex
    proposals=project/'proposals';proposals.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.preview-',dir=project) as temporary:
        staging=Path(temporary)
        package=staging/'package'
        try: report=build_project(suggestion['recipe'],package)
        except (ModelingError,OSError,ValueError) as exc: raise AgentToolError(f'CAD preview rejected: {exc}') from exc
        metadata={'schema_version':1,'proposal_id':proposal_id,'expected_revision':revision,
          'baseline_report_sha256':report_hash,'rationale':suggestion['rationale'],
          'recipe_sha256':_digest((package/'recipe.json').read_bytes()),
          'diff':_diff(before,suggestion['recipe']),'status':'preview_only'}
        (package/'proposal.json').write_text(json.dumps(metadata,sort_keys=True,ensure_ascii=False)+'\n')
        package.rename(proposals/proposal_id)
    return {'status':'preview_only','proposal_id':proposal_id,'expected_revision':revision,
      'diff':metadata['diff'],'report':report,
      'proposal_path':str(proposals/proposal_id)}


def apply_preview(project: str | Path, proposal_id: str, *, human_confirmed: bool) -> dict:
    """Only call after an explicit UI/user action; revalidate stale and tampered data."""
    if human_confirmed is not True: raise AgentToolError('Explicit human confirmation is required')
    if not isinstance(proposal_id,str) or not re.fullmatch(r'[0-9a-f]{32}',proposal_id):
        raise AgentToolError('Invalid proposal ID')
    project=Path(project).resolve()
    folder=project/'proposals'/proposal_id
    if folder.is_symlink() or not folder.is_dir(): raise AgentToolError('Proposal not found')
    metadata=json.loads((folder/'proposal.json').read_text())
    if metadata.get('proposal_id')!=proposal_id or metadata.get('status')!='preview_only':
        raise AgentToolError('Proposal metadata invalid')
    recipe_path=folder/'recipe.json'
    if recipe_path.is_symlink() or _digest(recipe_path.read_bytes())!=metadata['recipe_sha256']:
        raise AgentToolError('Proposal recipe changed after preview')
    revision,report_hash,_=_current(project)
    if revision!=metadata['expected_revision'] or report_hash!=metadata['baseline_report_sha256']:
        raise AgentToolError('Project advanced since preview; re-preview required')
    recipe=json.loads(recipe_path.read_text())
    result=apply_project(project,recipe,expected_revision=revision)
    return {'status':'applied','proposal_id':proposal_id,'revision':result['revision'],
      'package':result['package'],'report':result['report']}
