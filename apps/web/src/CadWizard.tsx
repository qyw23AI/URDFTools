import { useEffect, useState } from 'react';
import { RobotViewer, type RobotImport } from './RobotViewer';

type Part = { name: string; center_m: number[]; bounds_min_m: number[]; bounds_max_m: number[];
  axis_hints: {axis: number[]; point_m: number[]; radius_m: number; evidence: string}[] };
type Draft = { source_name: string; source_sha256: string; source_length_unit: string; parts: Part[]; warning: string };
type Joint = { name: string; parent: string; child: string; type: 'fixed' | 'revolute' | 'prismatic' | 'continuous';
  axis: number[]; origin_m: number[]; limits: number[] | null; confirmed: boolean; candidate_evidence: string;
  effort?: number | null; velocity?: number | null };
export type Configuration = { schema_version: number; source_sha256: string; root: string;
  links: {name: string; parts: string[]}[]; joints: Joint[]; densities_kg_m3?: Record<string, string> };
export type Discovery = { draft: Draft; configuration: Configuration; exchangeReport?: { source?: string; losses: string[]; unit_handling?: string; objects?: {name: string; volume_mm3: number}[] } | null };

function parseVector(raw: string): number[] | null {
  const values = raw.trim().split(/[\s,]+/).map(Number);
  return values.length === 3 && values.every(Number.isFinite) ? values : null;
}
function join(values: number[]): string { return values.map(value => Number(value.toPrecision(8))).join(' '); }

export function CadWizard() {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [exchangeReport, setExchangeReport] = useState<Discovery['exchangeReport']>(null);
  const [config, setConfig] = useState<Configuration | null>(null);
  const [groupNames, setGroupNames] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<RobotImport | null>(null);
  const [densities, setDensities] = useState<Record<string, string>>({});
  const [exportReport, setExportReport] = useState<{path: string; sha256: string; validation: {mujoco_raw: {fixed_base_mass_excluded_kg: number}; mujoco_floating: {mass_kg: number}; training_ready: boolean}} | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);

  async function chooseStep() {
    if (!window.urdftools) { setError('请在桌面应用中选择 STEP 文件'); return; }
    setBusy(true); setError('');
    try {
      const result = await window.urdftools.chooseCadStep();
      if (!result) return;
      setDraft(result.draft); setConfig(result.configuration); setExchangeReport(result.exchangeReport); setPreview(null); setDensities({}); setExportReport(null);
      setGroupNames(Object.fromEntries(result.configuration.links.flatMap(link => link.parts.map(part => [part, link.name]))));
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  function updateJoint(index: number, patch: Partial<Joint>) {
    setConfig(previous => previous && ({...previous, joints: previous.joints.map((joint, i) => i === index ? {...joint, ...patch, confirmed: patch.confirmed ?? false} : joint)}));
  }
  function applyGrouping() {
    if (!draft || !config) return;
    const groups = new Map<string, string[]>();
    for (const part of draft.parts) {
      const name = (groupNames[part.name] || '').trim();
      if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) { setError('Link 名称只能含字母、数字、下划线，且不能以数字开头'); return; }
      groups.set(name, [...(groups.get(name) || []), part.name]);
    }
    const links = [...groups].map(([name, parts]) => ({name, parts}));
    const joints: Joint[] = links.slice(1).map((link, index) => {
      const part = draft.parts.find(item => item.name === link.parts[0])!;
      const hint = part.axis_hints[0];
      return {name: `${link.name}_joint`, parent: links[index].name, child: link.name,
        type: 'fixed', axis: hint?.axis || [0, 0, 1], origin_m: hint?.point_m || part.center_m,
        limits: null, confirmed: false, candidate_evidence: hint?.evidence || 'none'};
    });
    setConfig({...config, root: links[0].name, links, joints});
    setPreview(null); setError('分组已应用；请逐个检查并确认关节，再查看预览。');
  }
  useEffect(() => {
    if (!draft || !config) return;
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
  }, [draft, config]);
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
      setGroupNames(Object.fromEntries(loaded.links.flatMap(link => link.parts.map(part => [part, link.name]))));
      setError('');
    } catch (cause) { setError(String(cause)); }
  }
  async function exportPackage() {
    if (!config || !draft || !window.urdftools) return;
    try {
      if (config.joints.some(joint => !joint.confirmed)) throw new Error('请先人工确认所有关节');
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
  return <section aria-label="STEP 转换向导" className="cad-wizard">
    <p>选择 STEP、FreeCAD FCStd、IGES 或 BREP，人工分组并确认关节。三维预览使用包围盒，仅用于检查关节关系与运动，不包含可制造几何或真实物理属性。</p>
    <button disabled={busy} onClick={() => void chooseStep()}>选择 CAD 文件</button>
    {busy && <p role="status">正在读取 STEP 装配…</p>}
    {draft && config && <>
      <h2>{draft.source_name}</h2>{exchangeReport && <aside role="status">
        <strong>来源格式转换：{exchangeReport.source || '本地 CAD 文件'}</strong>
        <p>已重新载入 STEP；请核对转换损失并重新确认关节和材料。</p>
        <ul>{exchangeReport.losses.map(loss => <li key={loss}>{loss}</li>)}</ul>
      </aside>}<p>源单位：{draft.source_length_unit}；内部预览统一为 m。</p><p>来源 SHA-256：<code>{draft.source_sha256}</code></p>
      <h3>零件与 Link 分组</h3>
      {draft.parts.map(part => <label key={part.name} className="cad-row">
        <span>{part.name} · 几何轴线提示 {part.axis_hints.length} 个</span>
        <input aria-label={`${part.name} Link`} value={groupNames[part.name] || ''}
          onChange={event => setGroupNames(previous => ({...previous, [part.name]: event.target.value}))} />
      </label>)}
      <button onClick={applyGrouping}>应用分组</button>
      <h3>关节树</h3>
      {config.joints.length === 0 && <p>当前仅一个 Link，无需关节。</p>}
      {config.joints.map((joint, index) => <fieldset key={joint.child} className="cad-joint">
        <legend>{joint.name} · {joint.candidate_evidence === 'none' ? '无几何轴线证据' : '有圆柱面候选，仍需人工确认'}</legend>
        <label>父 Link <select aria-label={`${joint.name} parent`} value={joint.parent}
          onChange={event => updateJoint(index, {parent: event.target.value})}>
          {config.links.filter(link => link.name !== joint.child).map(link => <option key={link.name}>{link.name}</option>)}
        </select></label>
        <span> → {joint.child}　</span>
        <label>类型 <select aria-label={`${joint.name} type`} value={joint.type}
          onChange={event => updateJoint(index, {type: event.target.value as Joint['type'], limits: event.target.value === 'revolute' ? [-1, 1] : event.target.value === 'prismatic' ? [-0.1, 0.1] : null})}>
          <option value="fixed">固定</option><option value="revolute">旋转</option><option value="prismatic">直线</option><option value="continuous">连续旋转</option>
        </select></label>
        <label>轴 xyz <input aria-label={`${joint.name} axis`} defaultValue={join(joint.axis)} key={`${joint.name}-axis-${join(joint.axis)}`}
          onBlur={event => { const parsed = parseVector(event.target.value); if (parsed) updateJoint(index, {axis: parsed}); else setError('轴必须是三个有限数值'); }} /></label>
        <label>原点 m <input aria-label={`${joint.name} origin`} defaultValue={join(joint.origin_m)} key={`${joint.name}-origin-${join(joint.origin_m)}`}
          onBlur={event => { const parsed = parseVector(event.target.value); if (parsed) updateJoint(index, {origin_m: parsed}); else setError('原点必须是三个有限数值'); }} /></label>
        {(joint.type === 'revolute' || joint.type === 'prismatic') && <label>限位 <input aria-label={`${joint.name} limits`}
          defaultValue={joint.limits?.join(' ') || ''} key={`${joint.name}-limits-${joint.limits?.join(' ')}`}
          onBlur={event => { const values = event.target.value.trim().split(/[\s,]+/).map(Number);
            if (values.length === 2 && values.every(Number.isFinite)) updateJoint(index, {limits: values});
            else setError('限位必须是两个有限数值'); }} /></label>}
        {joint.type !== 'fixed' && <>
          <label>最大力/力矩 <input aria-label={`${joint.name} effort`} type="number" min="0" step="any" value={joint.effort ?? ''}
            onChange={event => updateJoint(index, {effort: event.target.value ? Number(event.target.value) : null})} /></label>
          <label>最大速度 <input aria-label={`${joint.name} velocity`} type="number" min="0" step="any" value={joint.velocity ?? ''}
            onChange={event => updateJoint(index, {velocity: event.target.value ? Number(event.target.value) : null})} /></label>
        </>}
        <label>人工确认 <input type="checkbox" aria-label={`${joint.name} confirmed`} checked={joint.confirmed}
          onChange={event => updateJoint(index, {confirmed: event.target.checked})} /></label>
      </fieldset>)}
      <p>未确认关节：{config.joints.filter(joint => !joint.confirmed).length}；只有全部确认后才自动刷新三维预览。</p>
      <button onClick={() => void saveConfig()}>保存配置 JSON</button>{' '}
      <button onClick={() => void loadConfig()}>载入配置 JSON</button>
      <h3>材料密度与导出</h3>
      <p>每个零件的密度必须由用户按实际材料确认；留空时拒绝物理导出。碰撞体采用包围盒代理，训练适用性仍需单独验证。</p>
      {draft.parts.map(part => <label key={part.name + '-density'} className="cad-row">
        {part.name} 密度 kg/m³ <input type="number" min="0" step="any" aria-label={`${part.name} density`}
          value={densities[part.name] || ''} onChange={event => setDensities(previous => ({...previous, [part.name]: event.target.value}))} />
      </label>)}
      <button disabled={busy} onClick={() => void exportPackage()}>导出并交叉校验 URDF / ROS ZIP</button>
      {exportReport && <p role="status">导出完成：{exportReport.path}；SHA-256 {exportReport.sha256}；
        MuJoCo 浮动基座质量 {exportReport.validation.mujoco_floating.mass_kg.toPrecision(8)} kg。
        原始固定基座编译排除质量 {exportReport.validation.mujoco_raw.fixed_base_mass_excluded_kg.toPrecision(8)} kg。
        训练就绪：{exportReport.validation.training_ready ? '是' : '尚未验证'}。</p>}
      {previewBusy && <p role="status">正在更新三维预览…</p>}
      {preview?.status === 'ready' && <RobotViewer report={preview} />}
    </>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
