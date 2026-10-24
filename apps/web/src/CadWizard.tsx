import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { RobotViewer, type RobotImport } from './RobotViewer';
import { CadPartCanvas } from './CadPartCanvas';
import { FloatingPanel } from './FloatingPanel';
import { findJointCandidates, inferJoint, type JointAxisCandidate } from './cadJointInference';

type Part = { name: string; center_m: number[]; bounds_min_m: number[]; bounds_max_m: number[];
  axis_hints: {axis: number[]; point_m: number[]; radius_m: number; evidence: string}[] };
type Draft = { source_name: string; source_sha256: string; source_length_unit: string; parts: Part[]; warning: string };
type Joint = { name: string; parent: string; child: string; type: 'fixed' | 'revolute' | 'prismatic' | 'continuous';
  axis: number[]; origin_m: number[]; limits: number[] | null; confirmed: boolean; candidate_evidence: string;
  effort?: number | null; velocity?: number | null };
export type Configuration = { schema_version: number; source_sha256: string; root: string;
  links: {name: string; parts: string[]}[]; joints: Joint[]; densities_kg_m3?: Record<string, string> };
export type Discovery = { draft: Draft; configuration: Configuration;
  meshParts?: {name: string; url: string; color: number[] | null}[];
  exchangeReport?: { source?: string; losses: string[]; unit_handling?: string; objects?: {name: string; volume_mm3: number}[] } | null };
export type CadDraftSnapshot = { schema_version: 1; source_sha256: string; config: Configuration;
  groupNames: Record<string, string>; parentNames: Record<string, string>;
  selectedParts: string[]; hiddenParts: string[]; newLinkName: string; newLinkParent: string;
  step: 'import' | 'links' | 'joints' | 'export'; panels: {link: boolean; joint: boolean; motion: boolean};
  groupingApplied: boolean; activeJointIndex: number; densities: Record<string, string> };

function parseVector(raw: string): number[] | null {
  const values = raw.trim().split(/[\s,]+/).map(Number);
  return values.length === 3 && values.every(Number.isFinite) ? values : null;
}
function join(values: number[]): string { return values.map(value => Number(value.toPrecision(8))).join(' '); }

export function CadWizard({ initialDiscovery, modeling = false, onConfigurationChange }: {
  initialDiscovery?: Discovery; modeling?: boolean; onConfigurationChange?: (config: Configuration | null) => void
} = {}) {
  const [draft, setDraft] = useState<Draft | null>(initialDiscovery?.draft || null);
  const [meshParts, setMeshParts] = useState<Discovery['meshParts']>(initialDiscovery?.meshParts);
  const [exchangeReport, setExchangeReport] = useState<Discovery['exchangeReport']>(null);
  const [config, setConfig] = useState<Configuration | null>(initialDiscovery?.configuration || null);
  const [groupNames, setGroupNames] = useState<Record<string, string>>(
    Object.fromEntries((initialDiscovery?.configuration.links || []).flatMap(link => link.parts.map(part =>
      [part, link.name === initialDiscovery?.configuration.root ? 'base_link' : link.name]))));
  const [preview, setPreview] = useState<RobotImport | null>(null);
  const [selectedPart, setSelectedPart] = useState<string | null>(null);
  const [selectedParts, setSelectedParts] = useState<string[]>([]);
  const [hiddenParts, setHiddenParts] = useState<string[]>([]);
  const [newLinkName, setNewLinkName] = useState(initialDiscovery ? '' : 'base_link');
  const [newLinkParent, setNewLinkParent] = useState('base_link');
  const [parentNames, setParentNames] = useState<Record<string, string>>(
    Object.fromEntries((initialDiscovery?.configuration.joints || []).map(joint =>
      [joint.child, joint.parent === initialDiscovery?.configuration.root ? 'base_link' : joint.parent])));
  const [step, setStep] = useState<'import' | 'links' | 'joints' | 'export'>(initialDiscovery ? 'links' : 'import');
  const [panels, setPanels] = useState({link: true, joint: false, motion: false});
  const [jointValues, setJointValues] = useState<Record<string, number>>({});
  const [groupingApplied, setGroupingApplied] = useState(Boolean(initialDiscovery));
  const [activeJointIndex, setActiveJointIndex] = useState(0);
  const [axisPickPoints, setAxisPickPoints] = useState<number[][] | null>(null);
  const [showAxisCandidates, setShowAxisCandidates] = useState(false);
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  const [renaming, setRenaming] = useState<{kind: 'link' | 'joint'; name: string} | null>(null);
  const [renameDraft, setRenameDraft] = useState('');
  const [densities, setDensities] = useState<Record<string, string>>({});
  const [exportReport, setExportReport] = useState<{path: string; sha256: string; validation: {mujoco_raw: {fixed_base_mass_excluded_kg: number}; mujoco_floating: {mass_kg: number}; training_ready: boolean}; massProperties: {name: string; mass_kg: number; center_of_mass_local_m: number[]; inertia_com_kg_m2: number[][]}[]} | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [draggingCad, setDraggingCad] = useState(false);
  const [draftHydrated, setDraftHydrated] = useState(Boolean(initialDiscovery || modeling));
  const [draftSaveState, setDraftSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [draftSavedAt, setDraftSavedAt] = useState('');
  const canvasParts = useMemo(() => draft?.parts.map(part => {
    const mesh = meshParts?.find(item => item.name === part.name);
    return {...part, mesh_url: mesh?.url, color_rgb: mesh?.color};
  }) || [], [draft, meshParts]);
  useEffect(() => { onConfigurationChange?.(config); }, [config, onConfigurationChange]);

  useEffect(() => {
    if (modeling || initialDiscovery || !window.urdftools) return;
    let active = true;
    setBusy(true);
    void window.urdftools.cadDraftLoad().then(saved => {
      if (!active || !saved) return;
      applyDiscovery(saved.discovery);
      const ui = saved.ui;
      if (ui?.schema_version === 1 && ui.source_sha256 === saved.discovery.draft.source_sha256) {
        const validParts = new Set(saved.discovery.draft.parts.map(part => part.name));
        const validLinks = new Set(ui.config.links.map(link => link.name));
        if (ui.config.links.every(link => link.parts.every(part => validParts.has(part))) &&
            ui.config.joints.every(joint => validLinks.has(joint.parent) && validLinks.has(joint.child))) {
          setConfig(ui.config); setGroupNames(ui.groupNames); setParentNames(ui.parentNames);
          setSelectedParts(ui.selectedParts.filter(part => validParts.has(part)));
          setHiddenParts(ui.hiddenParts.filter(part => validParts.has(part)));
          setNewLinkName(ui.newLinkName); setNewLinkParent(ui.newLinkParent);
          setStep(ui.step); setPanels(ui.panels); setGroupingApplied(ui.groupingApplied);
          setActiveJointIndex(Math.max(0, Math.min(ui.activeJointIndex, ui.config.joints.length - 1)));
          setDensities(ui.densities);
        } else setError('暂存配置与 CAD 零件不匹配，已恢复源模型，请重新配置 Link');
      }
      setDraftSavedAt(saved.updated_at);
      setDraftSaveState('saved');
    }).catch(cause => { if (active) setError(`恢复 CAD 暂存失败：${String(cause)}`); })
      .finally(() => { if (active) { setBusy(false); setDraftHydrated(true); } });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!draftHydrated || modeling || !draft || !config || !window.urdftools) return;
    const ui: CadDraftSnapshot = { schema_version: 1, source_sha256: draft.source_sha256, config,
      groupNames, parentNames, selectedParts, hiddenParts, newLinkName, newLinkParent,
      step, panels, groupingApplied, activeJointIndex, densities };
    setDraftSaveState('saving');
    let active = true;
    void window.urdftools.cadDraftSave(ui).then(at => {
      if (active) { setDraftSavedAt(at); setDraftSaveState('saved'); }
    }).catch(() => { if (active) setDraftSaveState('error'); });
    return () => { active = false; };
  }, [draftHydrated, modeling, draft, config, groupNames, parentNames, selectedParts, hiddenParts,
    newLinkName, newLinkParent, step, panels, groupingApplied, activeJointIndex, densities]);

  function applyDiscovery(result: Discovery) {
    setDraft(result.draft); setMeshParts(result.meshParts); setConfig(result.configuration); setExchangeReport(result.exchangeReport); setPreview(null); setDensities({}); setExportReport(null);
    setSelectedPart(null); setStep('links'); setActiveJointIndex(0);
    setSelectedParts([]); setHiddenParts([]); setNewLinkName('base_link'); setNewLinkParent('base_link'); setParentNames({}); setGroupNames({});
    setPanels({link: true, joint: false, motion: false}); setJointValues({}); setGroupingApplied(false);
    setLinkDialogOpen(false); setShowAxisCandidates(false); setRenaming(null);
  }
  function togglePart(name: string) {
    setSelectedPart(name);
    setSelectedParts(previous => previous.includes(name) ? previous.filter(item => item !== name) : [...previous, name]);
  }
  function createLink() {
    const name = newLinkName.trim();
    if (!selectedParts.length) { setError('请先在三维视图中选择零件'); return; }
    const alreadyAssigned = selectedParts.find(part => groupNames[part]);
    if (alreadyAssigned) { setError(`${alreadyAssigned} 已属于 ${groupNames[alreadyAssigned]}，请先移除该 Link 后重新分组`); return; }
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) { setError('Link 名称只能含字母、数字、下划线，且不能以数字开头'); return; }
    const existing = new Set(Object.values(groupNames));
    if (!existing.has('base_link') && name !== 'base_link') { setError('请先选择基座零件并创建 base_link'); return; }
    if (existing.has('base_link') && name === 'base_link') { setError('base_link 已建立，请为其它 Link 输入新名称'); return; }
    if (existing.has(name)) { setError('Link 名称已存在，请输入新名称'); return; }
    const parent = existing.has(newLinkParent) ? newLinkParent : 'base_link';
    const link = {name, parts: [...selectedParts]};
    const nextJoint = name === 'base_link' ? null : (() => {
      const parentParts = (config?.links.find(item => item.name === parent)?.parts || []).map(partName => draft?.parts.find(item => item.name === partName)).filter((part): part is Part => !!part);
      const childParts = selectedParts.map(partName => draft?.parts.find(item => item.name === partName)).filter((part): part is Part => !!part);
      const inferred = inferJoint(parentParts, childParts);
      return {name: `${name}_joint`, parent, child: name, type: 'fixed' as const, axis: inferred.axis,
        origin_m: inferred.origin_m, limits: null, confirmed: false, candidate_evidence: inferred.evidence};
    })();
    setConfig(previous => previous && ({...previous, root: 'base_link',
      links: name === 'base_link' ? [link] : [...previous.links.filter(item => Object.values(groupNames).includes(item.name)), link],
      joints: name === 'base_link' ? [] : [...previous.joints, nextJoint!]}));
    setGroupNames(previous => ({...previous, ...Object.fromEntries(selectedParts.map(part => [part, name]))}));
    setGroupingApplied(true); setPreview(null); setJointValues({});
    if (name !== 'base_link') { setParentNames(previous => ({...previous, [name]: parent})); setActiveJointIndex(config?.joints.length || 0); }
    setHiddenParts(previous => [...new Set([...previous, ...selectedParts])]);
    setSelectedParts([]); setSelectedPart(null); setNewLinkName(''); setNewLinkParent(name); setError(''); setLinkDialogOpen(false);
  }
  async function loadCad(request: () => Promise<Discovery | null>) {
    if (!window.urdftools) { setError('请在桌面应用中导入 CAD 文件'); return; }
    setBusy(true); setError('');
    try {
      const result = await request();
      if (result) applyDiscovery(result);
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function chooseStep() { await loadCad(() => window.urdftools!.chooseCadStep()); }
  async function clearDraft() {
    if (!window.urdftools) return;
    setDraftHydrated(false);
    try {
      await window.urdftools.cadDraftClear();
      setDraft(null); setMeshParts(undefined); setConfig(null); setExchangeReport(null); setPreview(null);
      setGroupNames({}); setParentNames({}); setSelectedParts([]); setHiddenParts([]);
      setDensities({}); setExportReport(null); setStep('import'); setPanels({link: true, joint: false, motion: false});
      setGroupingApplied(false); setDraftSaveState('idle'); setDraftSavedAt(''); setError('');
    } catch (cause) { setError(`清除 CAD 暂存失败：${String(cause)}`); }
    finally { setDraftHydrated(true); }
  }
  async function importDropped(file: File) {
    if (!/\.(step|stp|fcstd|igs|iges|brep|brp)$/i.test(file.name)) { setError('请拖入 STEP、STP、FCStd、IGES 或 BREP 文件'); return; }
    await loadCad(() => window.urdftools!.importCadFile(file));
  }
  function updateJoint(index: number, patch: Partial<Joint>) {
    setConfig(previous => previous && ({...previous, joints: previous.joints.map((joint, i) => i === index ? {...joint, ...patch, confirmed: patch.confirmed ?? false} : joint)}));
  }
  useEffect(() => {
    if (!draft || !config || Object.keys(groupNames).length !== draft.parts.length || !groupingApplied) return;
    if (config.joints.some(joint => !joint.confirmed)) { setPreview(null); return; }
    let cancelled = false;
    const handle = window.setTimeout(async () => {
      if (!window.urdftools) return;
      setPreviewBusy(true); setError('');
      try {
        const result = await window.urdftools.cadPreview(config);
        if (!cancelled) { setPreview(result); setError(''); }
      } catch (cause) { if (!cancelled) { setPreview(null); setError(String(cause)); } }
      finally { if (!cancelled) setPreviewBusy(false); }
    }, 700);
    return () => { cancelled = true; window.clearTimeout(handle); };
  }, [draft, config, groupNames, groupingApplied]);
  async function saveConfig() {
    if (!config || !window.urdftools) return;
    try { await window.urdftools.saveCadConfig({...config, densities_kg_m3: densities}); setError(''); }
    catch (cause) { setError(String(cause)); }
  }
  async function loadConfig() {
    if (!window.urdftools) return;
    try {
      const loaded = await window.urdftools.loadCadConfig();
      if (!loaded) return;
      if (loaded.source_sha256 !== draft?.source_sha256) throw new Error('配置来源与当前 STEP 不匹配');
      setConfig(loaded); setPreview(null); setDensities(loaded.densities_kg_m3 || {}); setExportReport(null);
      setGroupingApplied(true); setJointValues({});
      setSelectedPart(null);
      setGroupNames(Object.fromEntries(loaded.links.flatMap(link => link.parts.map(part => [part, link.name]))));
      setParentNames(Object.fromEntries(loaded.joints.map(joint => [joint.child, joint.parent])));
      setError('');
    } catch (cause) { setError(String(cause)); }
  }
  async function exportPackage() {
    if (!config || !draft || !window.urdftools) return;
    try {
      if (Object.keys(groupNames).length !== draft.parts.length) throw new Error('请先为全部零件创建 Link');
      if (config.joints.some(joint => !joint.confirmed)) throw new Error('请先人工确认所有关节');
      for (const joint of config.joints) if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(joint.name))
        throw new Error(`${joint.child} 的 Joint 名称无效`);
      const assigned: Record<string, number> = {};
      for (const part of draft.parts) {
        const raw = densities[part.name];
        if (!raw?.trim()) throw new Error(`${part.name} 缺少明确的材料密度`);
        const value = Number(raw);
        if (!Number.isFinite(value) || value <= 0) throw new Error(`${part.name} 的密度必须是正数 kg/m³`);
        assigned[part.name] = value;
      }
      for (const joint of config.joints.filter(item => item.type !== 'fixed')) {
        if (!Number.isFinite(joint.effort) || !(joint.effort! > 0) ||
            !Number.isFinite(joint.velocity) || !(joint.velocity! > 0)) {
          throw new Error(`${joint.name} 需要明确填写正的最大力/力矩与最大速度`);
        }
      }
      setBusy(true); setError(''); setExportReport(null);
      const report = await window.urdftools.exportCadPackage(config, assigned);
      if (report) setExportReport(report);
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  const selectedJoint = config?.joints[Math.min(activeJointIndex, Math.max(0, config.joints.length - 1))];
  const childLink = config?.links.find(link => link.name === selectedJoint?.child);
  const parentLink = config?.links.find(link => link.name === selectedJoint?.parent);
  const allAxisCandidates = useMemo(() => draft && childLink && parentLink ? findJointCandidates(
    parentLink.parts.map(name => draft.parts.find(part => part.name === name)).filter((part): part is Part => !!part),
    childLink.parts.map(name => draft.parts.find(part => part.name === name)).filter((part): part is Part => !!part)) : [],
  [draft, parentLink, childLink]);
  function selectJoint(index: number) {
    setActiveJointIndex(index); setAxisPickPoints(null); setShowAxisCandidates(false); setStep('joints');
    const joint = config?.joints[index];
    if (joint) {
      const visible = config?.links.filter(link => link.name === joint.parent || link.name === joint.child).flatMap(link => link.parts) || [];
      setHiddenParts(previous => previous.filter(part => !visible.includes(part)));
    }
    setPanels(previous => ({...previous, joint: true}));
  }
  function renameItem() {
    if (!renaming || !config) return;
    const name = renameDraft.trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) { setError('名称只能含字母、数字、下划线，且不能以数字开头'); return; }
    if (renaming.kind === 'joint') {
      if (config.joints.some(joint => joint.name === name && joint.name !== renaming.name)) { setError('Joint 名称已存在'); return; }
      setConfig(previous => previous && ({...previous, joints: previous.joints.map(joint => joint.name === renaming.name ? {...joint, name, confirmed: false} : joint)}));
    } else {
      if (renaming.name === 'base_link') { setRenaming(null); return; }
      if (config.links.some(link => link.name === name && link.name !== renaming.name)) { setError('Link 名称已存在'); return; }
      setGroupNames(previous => Object.fromEntries(Object.entries(previous).map(([part, link]) => [part, link === renaming.name ? name : link])));
      setParentNames(previous => Object.fromEntries(Object.entries(previous).map(([child, parent]) => [child === renaming.name ? name : child, parent === renaming.name ? name : parent])));
      setNewLinkParent(previous => previous === renaming.name ? name : previous);
      setConfig(previous => previous && ({...previous,
        links: previous.links.map(link => link.name === renaming.name ? {...link, name} : link),
        joints: previous.joints.map(joint => ({...joint,
          name: joint.name === `${renaming.name}_joint` ? `${name}_joint` : joint.name,
          parent: joint.parent === renaming.name ? name : joint.parent,
          child: joint.child === renaming.name ? name : joint.child, confirmed: false}))}));
    }
    setRenaming(null); setError('');
  }
  function detectJointAxis() {
    if (!draft || !parentLink || !childLink) return;
    const byName = (name: string) => draft.parts.find(part => part.name === name);
    const candidates = findJointCandidates(parentLink.parts.map(byName).filter((part): part is Part => !!part),
      childLink.parts.map(byName).filter((part): part is Part => !!part));
    setAxisPickPoints(null); setShowAxisCandidates(candidates.length > 0);
    if (candidates.length === 1) selectAxisCandidate(candidates[0]);
    setError(candidates.length ? `识别到 ${candidates.length} 个父子零件配对轴。悬停预览，点击圆环选定。` :
      '没有找到父子零件共享的圆柱轴。请用两点设轴或精确参数设置。');
  }
  function selectAxisCandidate(candidate: JointAxisCandidate) {
    updateJoint(activeJointIndex, {axis: candidate.axis, origin_m: candidate.origin_m,
      candidate_evidence: `matched_cylinders:${candidate.parentPart}:${candidate.childPart}`});
    setShowAxisCandidates(false); setError(`已选择 ${candidate.parentPart} 与 ${candidate.childPart} 的共同轴，请试转并确认。`);
  }
  function pickJointPoint(part: string, point: [number, number, number]) {
    if (step !== 'joints' || !groupingApplied || !panels.joint || panels.motion || !selectedJoint || !config) return;
    if (![...(childLink?.parts || []), ...(parentLink?.parts || [])].includes(part)) {
      setError(`请在 ${selectedJoint.parent} 或 ${selectedJoint.child} 的零件上选择连接点`); return;
    }
    if (axisPickPoints) {
      if (!axisPickPoints.length) { setAxisPickPoints([point]); setError('已选择轴线起点，请点击第二个点确定方向。'); return; }
      const delta = point.map((value, i) => value - axisPickPoints[0][i]);
      const length = Math.hypot(...delta);
      if (length < 1e-6) { setError('两点距离太近，请重新选择终点。'); return; }
      updateJoint(activeJointIndex, {origin_m: axisPickPoints[0], axis: delta.map(value => value / length), candidate_evidence: 'two_point_manual'});
      setAxisPickPoints(null); setError('两点轴线已设置，请试转并确认。'); return;
    }
    updateJoint(activeJointIndex, {origin_m: point, candidate_evidence: 'picked_point'});
    setError(`已从 ${part} 选取连接点，请确认关节后继续。`);
  }
  const confirmedCount = config?.joints.filter(joint => joint.confirmed).length || 0;
  const allConfirmed = !!config && confirmedCount === config.joints.length;
  const assignedLinks = [...new Set(Object.values(groupNames))];
  const assignedCount = Object.keys(groupNames).length;
  const allPartsAssigned = !!draft && assignedCount === draft.parts.length;
  const assembling = step === 'links' || step === 'joints';
  function toggleLinkVisibility(name: string) {
    const parts = config?.links.find(link => link.name === name)?.parts || [];
    setHiddenParts(previous => parts.every(part => previous.includes(part)) ? previous.filter(part => !parts.includes(part)) :
      [...new Set([...previous, ...parts])]);
  }
  function removeLink(name: string) {
    if (config?.joints.some(joint => joint.parent === name)) return;
    const parts = Object.keys(groupNames).filter(part => groupNames[part] === name);
    setGroupNames(previous => Object.fromEntries(Object.entries(previous).filter(([, value]) => value !== name)));
    setConfig(previous => previous && ({...previous, links: previous.links.filter(link => link.name !== name),
      joints: previous.joints.filter(joint => joint.child !== name)}));
    setHiddenParts(previous => previous.filter(part => !parts.includes(part)));
    setParentNames(previous => Object.fromEntries(Object.entries(previous).filter(([child]) => child !== name)));
    setPreview(null); setJointValues({});
    if (name === 'base_link') setNewLinkName('base_link');
  }
  function renameField(kind: 'link' | 'joint', name: string) {
    setRenaming({kind, name}); setRenameDraft(name);
  }
  function renderLinkTree(name: string, depth = 0): ReactNode {
    const link = config?.links.find(item => item.name === name);
    if (!link) return null;
    const hidden = link.parts.every(part => hiddenParts.includes(part));
    const children = config?.joints.filter(joint => joint.parent === name) || [];
    return <div className="cad-tree-branch" key={name} style={{marginLeft: Math.min(depth * 14, 56)}}>
      <div className="cad-tree-line">
        {renaming?.kind === 'link' && renaming.name === name ?
          <input aria-label={`重命名 Link ${name}`} autoFocus value={renameDraft} onChange={event => setRenameDraft(event.target.value)}
            onBlur={renameItem} onKeyDown={event => { if (event.key === 'Enter') renameItem(); if (event.key === 'Escape') setRenaming(null); }} /> :
          <button type="button" className="cad-tree-label" onDoubleClick={() => renameField('link', name)} title="双击重命名 Link">
            ▣ {name} <small>{link.parts.length} 件</small></button>}
        <button type="button" aria-label={`${hidden ? '显示' : '隐藏'} Link ${name}`} title={hidden ? '显示' : '隐藏'} onClick={() => toggleLinkVisibility(name)}>{hidden ? '◌' : '◉'}</button>
        <button type="button" aria-label={`移除 Link ${name}`} title="移除 Link" disabled={children.length > 0} onClick={() => removeLink(name)}>×</button>
      </div>
      {children.map(joint => { const index = config!.joints.indexOf(joint);
        return <div className="cad-tree-child" key={joint.name}>
          <div className="cad-tree-line cad-tree-joint-line">
            {renaming?.kind === 'joint' && renaming.name === joint.name ?
              <input aria-label={`重命名 Joint ${joint.name}`} autoFocus value={renameDraft} onChange={event => setRenameDraft(event.target.value)}
                onBlur={renameItem} onKeyDown={event => { if (event.key === 'Enter') renameItem(); if (event.key === 'Escape') setRenaming(null); }} /> :
              <button type="button" className="cad-tree-label" aria-label={`编辑关节 ${joint.name}`}
                aria-pressed={panels.joint && activeJointIndex === index} onClick={() => selectJoint(index)}
                onDoubleClick={event => { event.preventDefault(); renameField('joint', joint.name); }} title="点击设置 Joint；双击重命名">
                ◌ {joint.name} <small>{joint.confirmed ? '已确认' : '待确认'}</small></button>}
            <button type="button" aria-label={`反转关节 ${joint.name}`} title="反转轴向"
              onClick={() => updateJoint(index, {axis: joint.axis.map(value => -value),
                limits: joint.limits ? [-joint.limits[1], -joint.limits[0]] : null})}>⇄</button>
          </div>
          {renderLinkTree(joint.child, depth + 1)}
        </div>;
      })}
    </div>;
  }
  return <section aria-label="CAD 转 URDF 工作区" className={`cad-wizard cad-conversion-workflow cad-full-workspace${draggingCad ? ' cad-dragging' : ''}`}
    onDragEnter={event => { event.preventDefault(); setDraggingCad(true); }}
    onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; }}
    onDragLeave={event => { const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX <= rect.left || event.clientX >= rect.right || event.clientY <= rect.top || event.clientY >= rect.bottom)
        setDraggingCad(false); }}
    onDrop={event => { event.preventDefault(); setDraggingCad(false); const file = event.dataTransfer.files[0];
      if (file) void importDropped(file); }}>
    {draggingCad && <div className="cad-drop-overlay">松开鼠标，导入 CAD 文件</div>}
    <nav className="cad-flow" aria-label="CAD 转 URDF 步骤">
      <button type="button" className={step === 'import' ? 'active' : ''} aria-current={step === 'import' ? 'step' : undefined}
        onClick={() => setStep('import')}><span>1</span>导入 CAD</button>
      <button type="button" className={assembling ? 'active' : ''} aria-current={assembling ? 'step' : undefined}
        disabled={!draft} onClick={() => { setStep('links'); setPanels(previous => ({...previous, link: true})); }}><span>2</span>配置 Link / Joint</button>
      <button type="button" className={step === 'export' ? 'active' : ''} aria-current={step === 'export' ? 'step' : undefined}
        disabled={!draft} onClick={() => setStep('export')}><span>3</span>验证导出</button>
      {assembling && <div className="cad-panel-switches">
        <button type="button" aria-pressed={panels.link} onClick={() => {
          setPanels(previous => ({...previous, link: !previous.link})); setStep('links'); }}>Link 设置</button>
        <button type="button" aria-pressed={panels.motion} onClick={() => {
          setPanels(previous => ({...previous, motion: !previous.motion})); setStep('joints');
        }}>关节试转</button>
      </div>}
      <small>{draft ? `${draft.parts.length} 个零件 · ${groupingApplied ? `${confirmedCount}/${config?.joints.length || 0} 个关节已确认` : '等待 Link 分组'} · ${draftSaveState === 'saving' ? '正在暂存' : draftSaveState === 'saved' ? '已自动暂存' : draftSaveState === 'error' ? '暂存失败' : '等待暂存'}` : '从本地 CAD 文件开始'}</small>
    </nav>
    {linkDialogOpen && <div className="cad-dialog-backdrop" onPointerDown={event => event.stopPropagation()}>
      <section className="cad-create-dialog" role="dialog" aria-modal="true" aria-label="创建 Link"
        onKeyDown={event => { if (event.key === 'Escape') setLinkDialogOpen(false); }}>
        <header><div><h2>创建 Link</h2><p>请输入名称，并指定父 Link。</p></div>
          <button type="button" onClick={() => setLinkDialogOpen(false)}>关闭</button></header>
        <label>LINK 名称<input aria-label="新 Link 名称" autoFocus value={newLinkName}
          readOnly={!assignedLinks.includes('base_link')} onChange={event => setNewLinkName(event.target.value)} /></label>
        {assignedLinks.includes('base_link') && <label>父 LINK
          <select aria-label="新 Link 父 Link" value={assignedLinks.includes(newLinkParent) ? newLinkParent : 'base_link'}
            onChange={event => setNewLinkParent(event.target.value)}>
            {assignedLinks.map(name => <option key={name}>{name}</option>)}</select></label>}
        <p>当前已选 {selectedParts.length} 个零件；确认后会创建连接 Joint。</p>
        {error && <p role="alert">{error}</p>}
        <footer><button type="button" onClick={() => setLinkDialogOpen(false)}>取消</button>
          <button type="button" className="cad-primary" onClick={createLink}>确认创建</button></footer>
      </section>
    </div>}
    <div className={`cad-controls${assembling ? ' cad-floating-controls' : ''}`}>
      {step === 'import' && <section className="cad-flow-panel">
        <small className="cad-eyebrow">CAD / URDF</small><h2>从 CAD 装配到机器人结构</h2>
        <p>选择或拖入 STEP、STP、FCStd、IGES 或 BREP。零件留在本机；识别结果可在右侧逐个核对。</p>
        {!modeling && <button className="cad-primary" disabled={busy} onClick={() => void chooseStep()}>选择 CAD 文件</button>}
        {modeling && <p>当前使用建模工作台生成的 CAD 装配。</p>}
        {busy && <p role="status">正在读取 CAD 装配与几何轴线…</p>}
        {draft && <div className="cad-source-card"><strong>{draft.source_name}</strong>
          <span>{draft.parts.length} 个零件 · 源单位 {draft.source_length_unit}</span>
          {!modeling && <span role="status">{draftSaveState === 'saved' ? `已自动暂存 · ${new Date(draftSavedAt).toLocaleString('zh-CN')}` :
            draftSaveState === 'error' ? '自动暂存失败，请检查磁盘空间' : '编辑内容将自动暂存，重开应用可继续'}</span>}
          <button onClick={() => { setStep('links'); setPanels(previous => ({...previous, link: true})); }}>继续配置 Link / Joint →</button></div>}
        {!modeling && (draft || error.startsWith('恢复 CAD 暂存失败')) &&
          <button type="button" disabled={busy} onClick={() => void clearDraft()}>清除暂存并重新开始</button>}
        {exchangeReport && <aside role="status"><strong>格式转换说明</strong>
          <ul>{exchangeReport.losses.map(loss => <li key={loss}>{loss}</li>)}</ul></aside>}
        {draft?.warning && <p role="status">{draft.warning}</p>}
      </section>}
      {assembling && panels.link && draft && config && <FloatingPanel title="Link / Joint 工作台"
        initial={{x: Math.max(16, window.innerWidth - 370), y: 16, width: 350, height: Math.min(570, window.innerHeight - 175)}}
        className="cad-work-window" onClose={() => setPanels(previous => ({...previous, link: false}))}>
        <section className="cad-flow-panel" onPointerDown={() => setStep('links')}>
        <small className="cad-eyebrow">步骤 2 · Link / Joint 工作台</small>
        <div className="cad-tree-toolbar"><button type="button" className="cad-primary" onClick={() => {
          setError('');
          setNewLinkName(assignedLinks.includes('base_link') ? `link_${String(assignedLinks.length).padStart(3, '0')}` : 'base_link');
          setLinkDialogOpen(true); }}>创建 Link</button>
          <button type="button" onClick={() => setSelectedParts([])}>清除选中</button>
          <button type="button" onClick={() => setHiddenParts([])}>显示全部</button></div>
        <p>单击零件多选，左键拖动旋转，右键拖动平移。双击树中名称可重命名；点眼睛隐藏或显示 Link。</p>
        <small>{draft.source_name} · {draft.source_length_unit}</small>
        <div className="cad-selection-card"><strong>已选 {selectedParts.length} 件 · 已分组 {assignedCount}/{draft.parts.length}</strong>
          <span>{selectedParts.length ? selectedParts.join('、') : '请在三维模型或下方列表中选择零件'}</span></div>
        <div className="cad-link-list cad-structure-tree"><strong>Link → Joint → 子 Link</strong>
          {assignedLinks.includes('base_link') ? renderLinkTree('base_link') : <p>先选择基座零件，再创建 base_link。</p>}
        </div>
        <details className="cad-unassigned-list"><summary>未分组零件（{draft.parts.length - assignedCount}）</summary>
          <div>{draft.parts.filter(part => !groupNames[part.name]).map(part =>
            <button key={part.name} type="button" aria-label={`选择零件 ${part.name}`}
              aria-pressed={selectedParts.includes(part.name)} onClick={() => togglePart(part.name)}>{part.name}</button>)}</div>
        </details>
        {exchangeReport && <details><summary>CAD 格式转换说明</summary><ul>{exchangeReport.losses.map(loss => <li key={loss}>{loss}</li>)}</ul></details>}
        </section></FloatingPanel>}
      {assembling && panels.joint && selectedJoint && draft && config && <FloatingPanel title={`Joint 设置 · ${selectedJoint.name}`}
        initial={{x: 16, y: Math.max(16, window.innerHeight - 475), width: Math.min(820, window.innerWidth - 32), height: 275}}
        className="cad-work-window cad-joint-work-window" halfSide="left"
        onClose={() => { setPanels(previous => ({...previous, joint: false})); setShowAxisCandidates(false); setStep('links'); }}>
        <section className="cad-flow-panel" onPointerDown={() => setStep('joints')}>
        {!groupingApplied && <p role="status">请先创建 base_link 和子 Link；每个子 Link 会立即生成连接 Joint。</p>}
        {groupingApplied && <>
        {!config.joints.length && <p>当前只有一个 Link，无需设置关节。</p>}
        {selectedJoint && <div className="cad-joint-editor" key={selectedJoint.child}>
          <label>Joint 名称 <input aria-label="Joint 名称" value={selectedJoint.name}
            onChange={event => updateJoint(activeJointIndex, {name: event.target.value})} /></label>
          <label>父 Link <select aria-label={`${selectedJoint.name} parent`} value={selectedJoint.parent}
            onChange={event => { const parent = event.target.value;
              setParentNames(previous => ({...previous, [selectedJoint.child]: parent}));
              const byName = (name: string) => draft.parts.find(part => part.name === name);
              const parentParts = (config.links.find(link => link.name === parent)?.parts || []).map(byName).filter((part): part is Part => !!part);
              const childParts = (childLink?.parts || []).map(byName).filter((part): part is Part => !!part);
              const inferred = inferJoint(parentParts, childParts);
              updateJoint(activeJointIndex, {parent, axis: inferred.axis, origin_m: inferred.origin_m,
                candidate_evidence: inferred.evidence}); }}>
            {config.links.slice(0, config.links.findIndex(link => link.name === selectedJoint.child)).map(link => <option key={link.name}>{link.name}</option>)}
          </select></label>
          <label>子 Link <input aria-label={`${selectedJoint.name} child`} value={selectedJoint.child} readOnly /></label>
          <label>关节类型 <select aria-label={`${selectedJoint.name} type`} value={selectedJoint.type}
            onChange={event => updateJoint(activeJointIndex, {type: event.target.value as Joint['type'],
              limits: event.target.value === 'revolute' ? [-1, 1] : event.target.value === 'prismatic' ? [-0.1, 0.1] : null})}>
            <option value="fixed">固定</option><option value="revolute">旋转</option>
            <option value="prismatic">直线</option><option value="continuous">连续旋转</option>
          </select></label>
          <div className="cad-point-card"><strong>关节运动轴 [{join(selectedJoint.axis)}]</strong>
            <span>{selectedJoint.candidate_evidence.startsWith('matched_cylinders') ? '已选择父子圆柱共同轴' : '未确认真实运动轴'} · 原点 {join(selectedJoint.origin_m)} m</span>
            <div className="cad-joint-actions"><button type="button" onClick={detectJointAxis}>自动识别</button>
              <button type="button" aria-pressed={showAxisCandidates} onClick={() => {
                setShowAxisCandidates(previous => !previous); setAxisPickPoints(null);
                if (!allAxisCandidates.length) setError('没有可显示的父子零件共同轴。请使用两点设轴或精确参数。');
              }}>显示全部轴 ({allAxisCandidates.length})</button>
              <button type="button" aria-pressed={axisPickPoints !== null} onClick={() => {
                setShowAxisCandidates(false); setAxisPickPoints(axisPickPoints ? null : []);
              }}>两点设轴</button>
              <button type="button" onClick={() => updateJoint(activeJointIndex, {axis: selectedJoint.axis.map(value => -value),
                limits: selectedJoint.limits ? [-selectedJoint.limits[1], -selectedJoint.limits[0]] : null})}>反转轴向</button></div>
            {axisPickPoints && <small>在父子 Link 上依次点击轴线起点和终点（{axisPickPoints.length}/2）</small>}</div>
          {showAxisCandidates && <div className="cad-axis-candidates"><strong>父子零件配对候选</strong>
            {allAxisCandidates.map((candidate, index) => <button key={`${candidate.parentPart}-${candidate.childPart}`}
              onClick={() => selectAxisCandidate(candidate)}>
              {index + 1}. {candidate.parentPart} → {candidate.childPart} · 轴 {join(candidate.axis)}</button>)}
          </div>}
          {(selectedJoint.type === 'revolute' || selectedJoint.type === 'prismatic') &&
            <div className="cad-joint-limits"><strong>{selectedJoint.type === 'revolute' ? '角度限位 (°)' : '位移限位 (m)'}</strong>
              {(['下限', '上限'] as const).map((label, index) => <label key={label}>{label}
                <input type="number" step="any" aria-label={`${selectedJoint.name} ${label}`}
                  value={selectedJoint.type === 'revolute' ? Number(((selectedJoint.limits?.[index] || 0) * 180 / Math.PI).toFixed(4)) : selectedJoint.limits?.[index] ?? 0}
                  onChange={event => { const value = Number(event.target.value) * (selectedJoint.type === 'revolute' ? Math.PI / 180 : 1);
                    const limits = [...(selectedJoint.limits || [-1, 1])]; limits[index] = value;
                    updateJoint(activeJointIndex, {limits}); }} /></label>)}</div>}
          {selectedJoint.type !== 'fixed' && <label className="cad-motion-row">测试{selectedJoint.type === 'prismatic' ? '移动' : '旋转'}
            <input type="range" aria-label={`测试 ${selectedJoint.name}`}
              min={selectedJoint.type === 'continuous' ? -Math.PI : selectedJoint.limits?.[0] ?? -1}
              max={selectedJoint.type === 'continuous' ? Math.PI : selectedJoint.limits?.[1] ?? 1}
              step={selectedJoint.type === 'prismatic' ? 0.001 : 0.01} value={jointValues[selectedJoint.child] || 0}
              onChange={event => setJointValues(previous => ({...previous, [selectedJoint.child]: Number(event.target.value)}))} />
            <output>{selectedJoint.type === 'prismatic' ? `${(jointValues[selectedJoint.child] || 0).toFixed(3)} m` : `${((jointValues[selectedJoint.child] || 0) * 180 / Math.PI).toFixed(1)}°`}</output>
          </label>}
          <details><summary>精确参数与运动约束</summary>
            <label>轴 xyz <input aria-label={`${selectedJoint.name} axis`} defaultValue={join(selectedJoint.axis)}
              key={`${selectedJoint.name}-axis-${join(selectedJoint.axis)}`}
              onBlur={event => { const parsed = parseVector(event.target.value);
                const length = parsed && Math.hypot(...parsed);
                if (parsed && length && length > 1e-9) updateJoint(activeJointIndex, {axis: parsed.map(value => value / length)});
                else setError('轴必须是三个有限数值，且长度不能为零'); }} /></label>
            <label>原点 m <input aria-label={`${selectedJoint.name} origin`} defaultValue={join(selectedJoint.origin_m)}
              key={`${selectedJoint.name}-origin-${join(selectedJoint.origin_m)}`}
              onBlur={event => { const parsed = parseVector(event.target.value);
                if (parsed) updateJoint(activeJointIndex, {origin_m: parsed}); else setError('原点必须是三个有限数值'); }} /></label>
            {selectedJoint.type !== 'fixed' && <>
              <label>最大力/力矩 <input aria-label={`${selectedJoint.name} effort`} type="number" min="0" step="any"
                value={selectedJoint.effort ?? ''} onChange={event => updateJoint(activeJointIndex,
                  {effort: event.target.value ? Number(event.target.value) : null})} /></label>
              <label>最大速度 <input aria-label={`${selectedJoint.name} velocity`} type="number" min="0" step="any"
                value={selectedJoint.velocity ?? ''} onChange={event => updateJoint(activeJointIndex,
                  {velocity: event.target.value ? Number(event.target.value) : null})} /></label>
            </>}
          </details>
          <button className="cad-primary" onClick={() => {
            if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(selectedJoint.name)) { setError('Joint 名称只能含字母、数字、下划线，且不能以数字开头'); return; }
            if (config.joints.some((joint, index) => index !== activeJointIndex && joint.name === selectedJoint.name)) { setError('Joint 名称不能重复'); return; }
            if (selectedJoint.limits && selectedJoint.limits[0] >= selectedJoint.limits[1]) { setError('关节下限必须小于上限'); return; }
            updateJoint(activeJointIndex, {confirmed: true});
            setPanels(previous => ({...previous, joint: false})); setShowAxisCandidates(false); setStep('links');
          }}>确认完成</button>
          {selectedJoint.confirmed && <button onClick={() => updateJoint(activeJointIndex, {confirmed: false})}>撤销确认</button>}
        </div>}
        <div className="cad-progress-line"><span>{confirmedCount}/{config.joints.length} 已确认</span>
          <button onClick={() => setStep('export')}>查看导出准备 →</button></div>
        </>}
        </section></FloatingPanel>}
      {assembling && panels.motion && config && <FloatingPanel title="关节试转" initial={{x: 730, y: 16, width: 310, height: 420}}
        className="cad-work-window" onClose={() => setPanels(previous => ({...previous, motion: false}))}>
        <section className="cad-flow-panel cad-motion-panel">
          <h2>检查可动关节</h2><p>确认关节后拖动滑块，在主模型中检查连接和转轴。</p>
          {(!groupingApplied || !config.joints.some(joint => joint.confirmed && joint.type !== 'fixed')) &&
            <p role="status">尚无已确认的可动关节。请先在 Joint 设置中选择旋转或直线类型并确认。</p>}
          {groupingApplied && config.joints.filter(joint => joint.confirmed && joint.type !== 'fixed').map(joint => {
            const bounds = joint.type === 'continuous' ? [-Math.PI, Math.PI] :
              joint.limits && joint.limits.length === 2 ? joint.limits :
              joint.type === 'prismatic' ? [-0.1, 0.1] : [-1, 1];
            const current = jointValues[joint.child] || 0;
            return <label key={joint.name} className="cad-motion-row">{joint.name}
              <input type="range" aria-label={`试转 ${joint.name}`} min={bounds[0]} max={bounds[1]}
                step={joint.type === 'prismatic' ? 0.001 : 0.01} value={current}
                onChange={event => setJointValues(previous => ({...previous, [joint.child]: Number(event.target.value)}))} />
              <output>{current.toFixed(3)} {joint.type === 'prismatic' ? 'm' : 'rad'}</output>
            </label>;
          })}
          <button onClick={() => setJointValues({})}>全部复位</button>
        </section></FloatingPanel>}
      {step === 'export' && draft && config && <section className="cad-flow-panel">
        <small className="cad-eyebrow">步骤 4 · 物理属性与导出</small><h2>验证并导出 URDF</h2>
        <p>质量、质心和惯量由原始 CAD 实体与材料密度计算。请按实际材料填写密度；未知值不自动猜测。</p>
        <div className="cad-progress-line"><span>关节确认</span><strong>{confirmedCount}/{config.joints.length}</strong></div>
        {!allPartsAssigned && <p role="status">请先完成全部零件的 Link 分组。</p>}
        {allPartsAssigned && !allConfirmed && <button onClick={() => { setStep('links'); setPanels(previous => ({...previous, link: true})); }}>返回 Link 树选择待确认 Joint</button>}
        {config.joints.some(joint => joint.type !== 'fixed' && (!joint.effort || !joint.velocity)) &&
          <p role="status">活动关节还需确认最大力/力矩与最大速度。预览值不能代替真实驱动参数。</p>}
        <div className="cad-density-list">{draft.parts.map(part => <label key={part.name}>
          <span>{part.name}</span><span>密度 kg/m³</span>
          <input type="number" min="0" step="any" aria-label={`${part.name} density`}
            value={densities[part.name] || ''} onChange={event => setDensities(previous => ({...previous, [part.name]: event.target.value}))} />
        </label>)}</div>
        <details><summary>转换配置</summary><p>可保存当前 Link、关节和材料设置，之后继续编辑同一 CAD 文件。</p>
          <button onClick={() => void saveConfig()}>保存配置 JSON</button>
          <button onClick={() => void loadConfig()}>载入配置 JSON</button></details>
        <button className="cad-primary" disabled={busy || !allPartsAssigned || !allConfirmed} onClick={() => void exportPackage()}>
          导出 URDF / ROS ZIP 并检查</button>
        {previewBusy && <p role="status">正在计算模型预览…</p>}
        {exportReport && <div className="cad-export-result" role="status"><strong>导出完成</strong>
          <p>{exportReport.path}</p><p>MuJoCo 浮动基座质量：{exportReport.validation.mujoco_floating.mass_kg.toPrecision(8)} kg</p>
          <p>原始固定基座编译排除质量：{exportReport.validation.mujoco_raw.fixed_base_mass_excluded_kg.toPrecision(8)} kg</p>
          <p>训练就绪：{exportReport.validation.training_ready ? '已验证' : '尚未验证'}。ROS 包与 MuJoCo 编译结果已交叉检查；其他软件需分别验证。</p>
          <details><summary>查看自动计算的质量、质心和惯量</summary>
            {exportReport.massProperties.map(link => <div key={link.name} className="cad-mass-row">
              <strong>{link.name}</strong><span>质量 {link.mass_kg.toPrecision(6)} kg</span>
              <span>质心 {join(link.center_of_mass_local_m)} m</span>
              <span>惯量对角线 {join([link.inertia_com_kg_m2[0][0], link.inertia_com_kg_m2[1][1], link.inertia_com_kg_m2[2][2]])} kg·m²</span>
            </div>)}
          </details>
        </div>}
      </section>}
      {error && <p role={error.startsWith('已') || error.startsWith('分组') ? 'status' : 'alert'}>{error}</p>}
    </div>
    <div className="cad-preview">{step === 'export' && preview?.status === 'ready' ?
      <RobotViewer report={preview} showJointGizmos={modeling} /> : draft ?
      <div className="cad-part-stage"><header><strong>{step === 'joints' && panels.joint && !panels.motion ? 'Joint 轴线工作区' : 'CAD 零件工作区'}</strong>
        <span>单击选择 · 左键旋转 · 右键平移 · 滚轮缩放</span></header>
        <CadPartCanvas parts={canvasParts}
          selected={step === 'links' ? selectedParts : selectedPart ? [selectedPart] : []}
          hidden={hiddenParts}
          fallbackBoxes={modeling}
          links={groupingApplied ? config?.links : undefined} joints={groupingApplied ? config?.joints : undefined} jointValues={jointValues}
          onSelect={step === 'links' ? togglePart : setSelectedPart}
          onLoadError={message => setError(message)}
          onPick={pickJointPoint} pickingJoint={step === 'joints' && groupingApplied && panels.joint && !panels.motion}
          jointOrigin={step === 'joints' && panels.joint ? selectedJoint?.origin_m : undefined}
          jointAxis={selectedJoint?.axis} parentParts={parentLink?.parts} childParts={childLink?.parts}
          axisCandidates={step === 'joints' && panels.joint && showAxisCandidates ? allAxisCandidates : []}
          onAxisSelect={selectAxisCandidate} />
        <p>{step === 'joints' ? `橙色：父 Link · 青色：子 Link · 当前关节 ${selectedJoint?.name || '无'}` :
          '点击零件选中或取消；黑色为已选中。创建 Link 后零件自动隐藏，可随时显示全部。'}</p></div> :
      <div className="empty-stage"><div className="empty-stage-mark">⌖</div><h2>CAD → URDF</h2>
        <p>导入装配后，这里显示零件位置与可视化关节编辑。</p></div>}</div>
  </section>;
}
