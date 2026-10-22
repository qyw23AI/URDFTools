import { useEffect, useState } from 'react';
import { CadWizard, type Configuration, type Discovery } from './CadWizard';

type Part = { name: string; material: string; density_kg_m3: number;
  profile: { kind: string; width_mm?: number; height_mm?: number; radius_mm?: number; holes?: unknown[] };
  operation: { kind: string; distance_mm?: number; angle_deg?: number };
  modifiers?: unknown[]; placement_mm?: number[] };
export type ModelRecipe = { schema_version: number; parts: Part[] };
export type ModelApplyResult = { revision: number; package: string; report: { parts: {name: string; step_sha256: string}[] };
  assembly: {path: string; sha256: string; parts: string[]}; discovery: Discovery };
export type CadReturnProposal = { status: 'review_required' | 'conflict'; baseline_sha256: string;
  returned_sha256: string; relinks: {baseline_part: string; returned_part: string; link: string;
    renamed: boolean; volume_delta_mm3: number; center_delta_mm: number[]}[];
  conflicts: {part: string; kind: string; preserved_link: string | null}[];
  automatically_applied: boolean; requires_human_confirmation: boolean };
const empty: ModelRecipe = { schema_version: 1, parts: [] };
const clone = (value: ModelRecipe): ModelRecipe => JSON.parse(JSON.stringify(value));

export function ModelingWorkspace() {
  const [history, setHistory] = useState<ModelRecipe[]>([empty]);
  const [cursor, setCursor] = useState(0);
  const [revision, setRevision] = useState(0);
  const [built, setBuilt] = useState<ModelApplyResult | null>(null);
  const [modelConfig, setModelConfig] = useState<Configuration | null>(null);
  const [cadReturn, setCadReturn] = useState<CadReturnProposal | null>(null);
  const [agentInstruction, setAgentInstruction] = useState('');
  const [agentProposal, setAgentProposal] = useState<Awaited<ReturnType<NonNullable<Window['urdftools']>['agentSuggest']>> | null>(null);
  const [name, setName] = useState('Base');
  const [width, setWidth] = useState(20);
  const [height, setHeight] = useState(10);
  const [depth, setDepth] = useState(5);
  const [density, setDensity] = useState(2700);
  const [json, setJson] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const recipe = history[cursor];
  useEffect(() => {
    let cancelled = false;
    window.urdftools?.modelCurrent().then(current => {
      if (cancelled) return;
      setRevision(current.revision); setHistory([current.recipe]); setCursor(0);
      if (current.built) { setBuilt(current.built); setModelConfig(current.built.discovery.configuration); }
      if (current.returnWarning) setError(`回流记录未恢复：${current.returnWarning}`);
    }).catch(cause => { if (!cancelled) setError(String(cause)); });
    return () => { cancelled = true; };
  }, []);
  function edit(next: ModelRecipe) {
    setHistory(previous => [...previous.slice(0, cursor + 1), clone(next)]);
    setCursor(previous => previous + 1); setBuilt(null); setModelConfig(null); setCadReturn(null); setAgentProposal(null); setJson(''); setError('');
  }
  function addPart() {
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) || recipe.parts.some(part => part.name === name)) {
      setError('零件名须唯一，且只含字母、数字、下划线'); return;
    }
    if (![width, height, depth, density].every(value => Number.isFinite(value) && value > 0)) {
      setError('尺寸与密度必须为正数'); return;
    }
    edit({ ...recipe, parts: [...recipe.parts, { name, material: '用户指定材料', density_kg_m3: density,
      profile: { kind: 'rectangle', width_mm: width, height_mm: height },
      operation: { kind: 'extrude', distance_mm: depth }, placement_mm: [0, 0, 0] }] });
  }
  function mirrorPart(part: Part) {
    const nextName = `${part.name}_mirror`;
    if (recipe.parts.some(item => item.name === nextName)) { setError('镜像零件已存在'); return; }
    const copy = clone({ schema_version: 1, parts: [part] }).parts[0];
    copy.name = nextName;
    copy.placement_mm = [-(part.placement_mm?.[0] || 0), part.placement_mm?.[1] || 0, part.placement_mm?.[2] || 0];
    edit({ ...recipe, parts: [...recipe.parts, copy] });
  }
  function applyJson() {
    try {
      const parsed = JSON.parse(json);
      if (parsed.schema_version !== 1 || !Array.isArray(parsed.parts)) throw new Error('配方需要 schema_version=1 和 parts 数组');
      edit(parsed);
    } catch (cause) { setError(String(cause)); }
  }
  async function build() {
    if (!window.urdftools) { setError('需要桌面应用中的本地建模 worker'); return; }
    if (!recipe.parts.length) { setError('至少添加一个零件'); return; }
    setBusy(true); setError('');
    try {
      const result = await window.urdftools.modelApply(recipe, revision);
      setRevision(result.revision); setBuilt(result); setModelConfig(result.discovery.configuration); setCadReturn(null);
    } catch (cause) {
      setError(String(cause));
      try { const current = await window.urdftools.modelCurrent(); setRevision(current.revision); } catch { /* retain the visible error */ }
    } finally { setBusy(false); }
  }
  async function suggestModel() {
    if (!window.urdftools || !built || built.revision !== revision) return;
    setBusy(true); setError(''); setAgentProposal(null);
    try { setAgentProposal(await window.urdftools.agentSuggest(agentInstruction, revision)); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function acceptAgent() {
    if (!window.urdftools || !agentProposal) return;
    setBusy(true); setError('');
    try {
      const result = await window.urdftools.agentApply(agentProposal.proposal_id);
      setHistory(previous => [...previous.slice(0, cursor + 1), clone(agentProposal.recipe)]);
      setCursor(previous => previous + 1);
      setRevision(result.revision); setBuilt(result); setModelConfig(result.discovery.configuration);
      setCadReturn(null); setAgentProposal(null);
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function compareReturn() {
    if (!modelConfig || !window.urdftools) return;
    setBusy(true); setError(''); setCadReturn(null);
    try { const result=await window.urdftools.modelReconcile(modelConfig);
      if (result) setCadReturn(result.proposal);
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function acceptReturn() {
    if (!built || !modelConfig || !cadReturn || !window.urdftools) return;
    setBusy(true); setError('');
    try {
      const discovery=await window.urdftools.modelAcceptReturn(modelConfig);
      setBuilt({ ...built, discovery,
        assembly: { ...built.assembly, path: discovery.draft.source_name, sha256: discovery.draft.source_sha256,
          parts: discovery.draft.parts.map(part => part.name) } });
      setModelConfig(discovery.configuration); setCadReturn(null);
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  return <section aria-label="机器人建模工作台" className="cad-wizard">
    <p>在本机编辑参数化 CAD 配方。尺寸用 mm，密度用 kg/m³；导出前需人工确认关节及材料。每次生成保存不可变版本。</p>
    <p>当前版本 {revision}；编辑历史 {cursor + 1}/{history.length}。</p>
    <button disabled={cursor === 0 || busy} onClick={() => { setCursor(cursor - 1); setBuilt(null); }}>撤销</button>{' '}
    <button disabled={cursor >= history.length - 1 || busy} onClick={() => { setCursor(cursor + 1); setBuilt(null); }}>重做</button>
    <h2>新增 CAD 零件</h2>
    <label>名称 <input aria-label="零件名称" value={name} onChange={event => setName(event.target.value)} /></label>{' '}
    <label>宽 mm <input aria-label="宽度 mm" type="number" value={width} onChange={event => setWidth(Number(event.target.value))} /></label>{' '}
    <label>高 mm <input aria-label="高度 mm" type="number" value={height} onChange={event => setHeight(Number(event.target.value))} /></label>{' '}
    <label>厚 mm <input aria-label="厚度 mm" type="number" value={depth} onChange={event => setDepth(Number(event.target.value))} /></label>{' '}
    <label>密度 kg/m³ <input aria-label="建模密度" type="number" value={density} onChange={event => setDensity(Number(event.target.value))} /></label>{' '}
    <button disabled={busy} onClick={addPart}>添加零件</button>
    <h2>零件与位置</h2>
    {recipe.parts.map((part, index) => <div key={part.name} className="cad-row">
      <strong>{part.name}</strong> · {part.profile.kind} / {part.operation.kind}
      {([0, 1, 2] as const).map(axis => <label key={axis}>{'xyz'[axis]} mm <input type="number" aria-label={`${part.name} ${'xyz'[axis]} mm`}
        value={part.placement_mm?.[axis] || 0} onChange={event => {
          const next = clone(recipe); next.parts[index].placement_mm ||= [0, 0, 0];
          next.parts[index].placement_mm![axis] = Number(event.target.value); edit(next);
        }} /></label>)}
      <button onClick={() => mirrorPart(part)}>镜像 X 位置</button>{' '}
      <button onClick={() => edit({ ...recipe, parts: recipe.parts.filter((_, i) => i !== index) })}>删除</button>
    </div>)}
    <details><summary>高级 CAD 配方编辑（允许列表：草图、拉伸、旋转、布尔、圆角）</summary>
      <button onClick={() => setJson(JSON.stringify(recipe, null, 2))}>载入当前配方</button>
      <textarea aria-label="CAD 配方 JSON" rows={14} value={json} onChange={event => setJson(event.target.value)} />
      <button onClick={applyJson}>应用配方编辑</button>
    </details>
    <p><button disabled={busy} onClick={() => void build()}>生成 CAD 与 URDF 预览来源</button></p>
    {busy && <p role="status">正在生成并重新载入 STEP 装配…</p>}
    {error && <p role="alert">{error}</p>}
    {built && <><p role="status">版本 {built.revision}：{built.assembly.parts.join('、')}；当前 STEP SHA-256 {built.assembly.sha256}</p>
      <h2>Agent 辅助建模</h2>
      <p>仅发送当前 CAD 配方和下方指令给已登录的 ChatGPT/Codex。建议先在独立副本构建，审阅后才能接受；接受后可撤销或继续编辑参数。</p>
      <textarea aria-label="Agent 建模指令" rows={3} maxLength={2000} value={agentInstruction} onChange={event => setAgentInstruction(event.target.value)} />
      <button disabled={busy || !agentInstruction.trim()} onClick={() => void suggestModel()}>生成建模建议</button>
      {agentProposal && <section aria-label="Agent 建模建议" data-agent-status={agentProposal.status}>
        <p>{agentProposal.rationale}</p>
        <p>新增：{agentProposal.diff.added_parts.join('、') || '无'}；移除：{agentProposal.diff.removed_parts.join('、') || '无'}；修改：{agentProposal.diff.changed_parts.join('、') || '无'}</p>
        {agentProposal.report.parts.map(part => <p key={part.name}>{part.name}：预览质量 {part.mass_kg.toPrecision(6)} kg</p>)}
        <details><summary>完整配方差异预览</summary><pre>{JSON.stringify(agentProposal.recipe, null, 2)}</pre></details>
        <button disabled={busy} onClick={() => void acceptAgent()}>接受建议并生成新版本</button>{' '}
        <button disabled={busy} onClick={() => { const draft = clone(agentProposal.recipe); edit(draft); setJson(JSON.stringify(draft, null, 2)); }}>复制到编辑器微调</button>{' '}
        <button disabled={busy} onClick={() => setAgentProposal(null)}>拒绝建议</button>
      </section>}
      <h2>FreeCAD 回流审阅</h2>
      <p>选择本机 FCStd，对照当前 STEP 的零件名称、体积、质心和拓扑。比较只生成提案；接受后所有关节需重新确认，原 CAD 版本保留。</p>
      <button disabled={busy || !modelConfig} onClick={() => void compareReturn()}>比较 FreeCAD 回流</button>
      {cadReturn && <section aria-label="FreeCAD 回流差异" data-return-status={cadReturn.status}>
        <p>{cadReturn.status === 'conflict' ? '发现冲突，禁止自动应用；请在 FreeCAD 中修正或重新分组。' : '零件可重关联；请审阅后明确接受。'}</p>
        {cadReturn.relinks.map(item => <p key={item.baseline_part}>{item.baseline_part} → {item.returned_part} / Link {item.link}；体积变化 {item.volume_delta_mm3.toPrecision(6)} mm³；质心位移 {item.center_delta_mm.map(x => x.toPrecision(4)).join(', ')} mm</p>)}
        {cadReturn.conflicts.map((item, index) => <p role="alert" key={index}>{item.part}：{item.kind}；原 Link {item.preserved_link || '未分配'} 保留</p>)}
        {cadReturn.status === 'review_required' && <button disabled={busy} onClick={() => void acceptReturn()}>接受回流并重新确认关节</button>}
      </section>}
      <CadWizard key={`${built.revision}-${built.discovery.draft.source_sha256}`} initialDiscovery={built.discovery}
        modeling onConfigurationChange={setModelConfig} /></>}
  </section>;
}
