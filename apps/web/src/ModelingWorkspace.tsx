import { useEffect, useMemo, useState } from 'react';
import { CadWizard, type Configuration, type Discovery } from './CadWizard';
import { ModelPuzzleCanvas } from './ModelPuzzleCanvas';
import type { WebCodexTicket } from './WebCodexAgent';

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

export function ModelingWorkspace({ libraryOnly = false, onLibraryChange }: {libraryOnly?: boolean; onLibraryChange?: () => void} = {}) {
  const [history, setHistory] = useState<ModelRecipe[]>([empty]);
  const [cursor, setCursor] = useState(0);
  const [revision, setRevision] = useState(0);
  const [built, setBuilt] = useState<ModelApplyResult | null>(null);
  const [modelConfig, setModelConfig] = useState<Configuration | null>(null);
  const [cadReturn, setCadReturn] = useState<CadReturnProposal | null>(null);
  const [agentInstruction, setAgentInstruction] = useState('');
  const [agentMode, setAgentMode] = useState<'webcodex'|'cli'>('webcodex');
  const [webTicket, setWebTicket] = useState<WebCodexTicket | null>(null);
  const [webNotice, setWebNotice] = useState('');
  const [libraryNotice, setLibraryNotice] = useState('');
  useEffect(() => {
    if (!webTicket || webTicket.status !== 'awaiting_chatgpt_web_reply' || !window.urdftools) return;
    const requestId=webTicket.request_id;
    const timer=window.setInterval(() => {
      void window.urdftools?.webcodexStatus(requestId).then(next => {
        if (next.status === 'reply_validated') {
          setWebTicket(current => current?.request_id === requestId ? next : current);
          if (next.result?.status === 'preview_only' && next.result.preview && next.result.suggestion) {
            setAgentProposal({status:'preview_only',proposal_id:next.result.preview.proposal_id,
              diff:next.result.preview.diff,report:next.result.preview.report,
              recipe:next.result.suggestion.recipe,rationale:next.result.suggestion.rationale});
          }
        }
      }).catch(() => { /* manual status button reports errors */ });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [webTicket?.request_id,webTicket?.status]);
  const [agentProposal, setAgentProposal] = useState<{proposal_id: string;
    diff: {added_parts: string[]; removed_parts: string[]; changed_parts: string[]};
    recipe: ModelRecipe; rationale: string;
    report: {parts: {name: string; mass_kg: number}[]}; status: 'preview_only'} | null>(null);
  const [name, setName] = useState('Base');
  const [selectedPart, setSelectedPart] = useState<string | null>(null);
  const [width, setWidth] = useState(20);
  const [height, setHeight] = useState(10);
  const [depth, setDepth] = useState(5);
  const [density, setDensity] = useState(2700);
  const [json, setJson] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const recipe = history[cursor];
  const puzzleParts = useMemo(() => recipe.parts.map(part => {
    const radius = part.profile.radius_mm || 10;
    return { name: part.name, width_mm: part.profile.width_mm || radius * 2,
      height_mm: part.profile.height_mm || radius * 2,
      depth_mm: part.operation.distance_mm || 5, placement_mm: part.placement_mm || [0, 0, 0] };
  }), [recipe]);
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
    setCursor(previous => previous + 1); setBuilt(null); setModelConfig(null); setCadReturn(null); setAgentProposal(null); setWebTicket(null); setJson(''); setError('');
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
    setSelectedPart(name);
  }
  function addPreset(prefix: string, widthMm: number, heightMm: number, depthMm: number) {
    let number = 1;
    while (recipe.parts.some(part => part.name === `${prefix}_${number}`)) number++;
    const nextName = `${prefix}_${number}`;
    edit({ ...recipe, parts: [...recipe.parts, { name: nextName, material: '用户指定材料', density_kg_m3: density,
      profile: { kind: 'rectangle', width_mm: widthMm, height_mm: heightMm },
      operation: { kind: 'extrude', distance_mm: depthMm }, placement_mm: [0, 0, 0] }] });
    setSelectedPart(nextName);
  }
  function movePart(partName: string, xMm: number, yMm: number) {
    const next = clone(recipe);
    const part = next.parts.find(item => item.name === partName);
    if (!part) return;
    part.placement_mm = [xMm, yMm, part.placement_mm?.[2] || 0];
    edit(next); setSelectedPart(partName);
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
    setBusy(true); setError(''); setAgentProposal(null); setWebTicket(null);
    try {const created=await window.urdftools.webcodexCreateModel(agentInstruction, revision, agentMode);
      setWebTicket(created);
      if (agentMode==='cli') {
        const completed=await window.urdftools.agentCliRun(created.request_id);
        setWebTicket(completed);
        if (completed.result?.preview && completed.result.suggestion)
          setAgentProposal({status:'preview_only',proposal_id:completed.result.preview.proposal_id,
            diff:completed.result.preview.diff,report:completed.result.preview.report,
            recipe:completed.result.suggestion.recipe,rationale:completed.result.suggestion.rationale});
      } else setWebNotice('已创建请求。请在网页 ChatGPT 主动发送，回复后自动构建预览。');}
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function checkWebCodex() {
    if (!window.urdftools || !webTicket) return;
    setBusy(true); setError('');
    try {
      const latest = await window.urdftools.webcodexStatus(webTicket.request_id);
      setWebTicket(latest);
      if (latest.status === 'reply_validated' && latest.result?.status === 'preview_only' &&
          latest.result.preview && latest.result.suggestion) {
        const preview=latest.result.preview;
        const suggestion=latest.result.suggestion;
        setAgentProposal({
          status: 'preview_only',
          proposal_id: preview.proposal_id,
          diff: preview.diff,
          report: preview.report,
          recipe: suggestion.recipe,
          rationale: suggestion.rationale
        });
      }
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function copyWebCodex() {
    if (!window.urdftools || !webTicket?.prompt) return;
    try {await window.urdftools.webcodexCopyPrompt(webTicket.prompt);
      setWebNotice('提示已复制，请在 ChatGPT 网页已连接 WebCodex 的对话中粘贴发送。');
    } catch (cause) {setError(String(cause));}
  }
  async function openWebCodex() {
    if (!window.urdftools || !webTicket) return;
    try {await window.urdftools.webcodexOpen(webTicket.request_id);
      setWebNotice('已打开 ChatGPT 并复制请求。请粘贴发送；建模预览会自动回显。');}
    catch (cause) {setError(String(cause));}
  }
  async function retryCli() {
    if (!window.urdftools || !webTicket) return;
    setBusy(true);setError('');
    try {const completed=await window.urdftools.agentCliRun(webTicket.request_id);
      setWebTicket(completed);
      if (completed.result?.preview && completed.result.suggestion)
        setAgentProposal({status:'preview_only',proposal_id:completed.result.preview.proposal_id,
          diff:completed.result.preview.diff,report:completed.result.preview.report,
          recipe:completed.result.suggestion.recipe,rationale:completed.result.suggestion.rationale});}
    catch(cause) {setError(String(cause));}
    finally {setBusy(false);}
  }

  async function acceptAgent() {
    if (!window.urdftools || !agentProposal) return;
    setBusy(true); setError('');
    try {
      const result = await window.urdftools.agentApply(agentProposal.proposal_id);
      setHistory(previous => [...previous.slice(0, cursor + 1), clone(agentProposal.recipe)]);
      setCursor(previous => previous + 1);
      setRevision(result.revision); setBuilt(result); setModelConfig(result.discovery.configuration);
      setCadReturn(null); setAgentProposal(null); setWebTicket(null);
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
  return <section aria-label="机器人建模工作台" className="cad-wizard modeling-workspace">
    {!libraryOnly && <><p>在本机编辑参数化 CAD 配方。尺寸用 mm，密度用 kg/m³；导出前需人工确认关节及材料。每次生成保存不可变版本。</p>
    <p>当前版本 {revision}；编辑历史 {cursor + 1}/{history.length}。</p>
    <button disabled={cursor === 0 || busy} onClick={() => { setCursor(cursor - 1); setBuilt(null); }}>撤销</button>{' '}
    <button disabled={cursor >= history.length - 1 || busy} onClick={() => { setCursor(cursor + 1); setBuilt(null); }}>重做</button>
    <div className="model-puzzle-workspace"><div className="model-puzzle-palette"><h2>零件素材</h2><p>点击添加，再在网格中拖动。每次移动吸附到 5 mm 网格。</p>
      <button onClick={() => addPreset('body', 80, 45, 20)}>添加机身</button>
      <button onClick={() => addPreset('link', 50, 12, 8)}>添加连杆</button>
      <button onClick={() => addPreset('joint', 18, 18, 18)}>添加关节块</button>
      <button onClick={() => addPreset('foot', 35, 16, 8)}>添加足端</button>
      {recipe.parts.map(part => <button key={part.name} aria-pressed={selectedPart === part.name}
        onClick={() => setSelectedPart(part.name)}>{part.name}</button>)}
    </div><div className="model-puzzle-stage"><header><strong>三维拼装</strong><span>拖动零件 · 左键空白旋转 · 右键平移 · 滚轮缩放</span></header>
      <ModelPuzzleCanvas parts={puzzleParts} selected={selectedPart} onSelect={setSelectedPart} onMove={movePart} />
      <p>当前选择：{selectedPart || '无'}。下方也可精确输入 XYZ；此画布用于构型草案，生成后以 CAD/URDF 预览复核。</p></div></div>
    <h2>新增 CAD 零件</h2>
    <label>名称 <input aria-label="零件名称" value={name} onChange={event => setName(event.target.value)} /></label>{' '}
    <label>宽 mm <input aria-label="宽度 mm" type="number" value={width} onChange={event => setWidth(Number(event.target.value))} /></label>{' '}
    <label>高 mm <input aria-label="高度 mm" type="number" value={height} onChange={event => setHeight(Number(event.target.value))} /></label>{' '}
    <label>厚 mm <input aria-label="厚度 mm" type="number" value={depth} onChange={event => setDepth(Number(event.target.value))} /></label>{' '}
    <label>密度 kg/m³ <input aria-label="建模密度" type="number" value={density} onChange={event => setDensity(Number(event.target.value))} /></label>{' '}
    <button disabled={busy} onClick={addPart}>添加零件</button>
    <h2>零件与位置</h2>
    {recipe.parts.map((part, index) => <div key={part.name} className="cad-row">
      <button type="button" aria-pressed={selectedPart === part.name} onClick={() => setSelectedPart(part.name)}>{part.name}</button> · {part.profile.kind} / {part.operation.kind}
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
    </>}
    {libraryOnly && !built && <><p>先建立起始 CAD，再让 Agent 按描述修改；起始配方为 20 × 10 × 5 mm 示例块，示例密度 2700 kg/m³。</p><button disabled={busy} onClick={async()=>{if(!window.urdftools)return;setBusy(true);setError('');try{const result=await window.urdftools.modelApply({schema_version:1,parts:[{name:'Module',material:'示例铝材（待确认）',density_kg_m3:2700,profile:{kind:'rectangle',width_mm:20,height_mm:10},operation:{kind:'extrude',distance_mm:5}}]},revision);setBuilt(result);setRevision(result.revision);setModelConfig(result.discovery.configuration);}catch(e){setError(String(e));}finally{setBusy(false);}}}>建立起始 CAD</button></>}
    {libraryOnly && built && <button disabled={busy} onClick={async()=>{setBusy(true);try{await window.urdftools!.cadLibraryGenerated();onLibraryChange?.();setLibraryNotice('已加入 CAD 模块库，可拖入 URDF 场景');}catch(e){setError(String(e));}finally{setBusy(false);}}}>将当前 CAD 加入模块库</button>}
    {libraryNotice && <p role="status">{libraryNotice}</p>}
    {busy && <p role="status">正在生成并重新载入 STEP 装配…</p>}
    {error && <p role="alert">{error}</p>}
    {built && <><p role="status">版本 {built.revision}：{built.assembly.parts.join('、')}；当前 STEP SHA-256 {built.assembly.sha256}</p>
      {!libraryOnly && <CadWizard key={`${built.revision}-${built.discovery.draft.source_sha256}`} initialDiscovery={built.discovery}
        modeling onConfigurationChange={setModelConfig} />}
      <h2>Agent 辅助建模</h2>
      <fieldset><legend>模型接入方式</legend>
        <label><input type="radio" name="model-agent-mode" value="webcodex" checked={agentMode==='webcodex'}
          onChange={()=>{setAgentMode('webcodex');setWebTicket(null);setAgentProposal(null);}} />网页 ChatGPT + WebCodex</label>
        <label><input type="radio" name="model-agent-mode" value="cli" checked={agentMode==='cli'}
          onChange={()=>{setAgentMode('cli');setWebTicket(null);setAgentProposal(null);}} />Codex CLI（当前账号）</label>
      </fieldset>
      <p>{agentMode==='webcodex' ? '创建请求后打开 ChatGPT，粘贴并发送；网页回复自动回显为独立 CAD 预览。' :
        '点击运行后通过已登录的 Codex CLI 发送当前 CAD 配方；建议仍需预览和人工确认。'} 不使用额外付费 API，接受前不会替换原模型。</p>
      <textarea aria-label="Agent 建模指令" rows={3} maxLength={2000} value={agentInstruction} onChange={event => setAgentInstruction(event.target.value)} />
      <button disabled={busy || !agentInstruction.trim()} onClick={() => void suggestModel()}>
        {agentMode==='cli' ? '运行 Codex CLI 建模建议' : '创建 WebCodex 建模请求'}</button>
      {webTicket && <div data-webcodex-model-status={webTicket.status}>
        <p>请求编号：<code>{webTicket.request_id}</code></p>
        <p>{webTicket.status === 'reply_validated' ? '建模建议已通过本地预览校验。' : agentMode==='cli' ?
          'CLI 未完成；失败时不会生成提案。' : '等待 ChatGPT 网页通过 WebCodex 提交回复。'}</p>
        {agentMode==='webcodex' && webTicket.prompt && <>
          <button disabled={busy} onClick={() => void openWebCodex()}>打开 ChatGPT 并复制建模请求</button>
          <button disabled={busy} onClick={() => void copyWebCodex()}>复制 ChatGPT/WebCodex 提示</button>
          <details><summary>查看提示和请求路径</summary><textarea aria-label="WebCodex 建模请求提示" readOnly rows={6} value={webTicket.prompt} /></details>
        </>}
        {agentMode==='cli' && webTicket.status!=='reply_validated' &&
          <button disabled={busy} onClick={() => void retryCli()}>重试 Codex CLI 建模建议</button>}
        <button disabled={busy} onClick={() => void checkWebCodex()}>检查 ChatGPT 建模回复</button>
        {webNotice && <p role="status">{webNotice}</p>}
      </div>}
      {agentProposal && <section aria-label="Agent 建模建议" data-agent-status={agentProposal.status}>
        <p>{agentProposal.rationale}</p>
        <p>新增：{agentProposal.diff.added_parts.join('、') || '无'}；移除：{agentProposal.diff.removed_parts.join('、') || '无'}；修改：{agentProposal.diff.changed_parts.join('、') || '无'}</p>
        {agentProposal.report.parts.map(part => <p key={part.name}>{part.name}：预览质量 {part.mass_kg.toPrecision(6)} kg</p>)}
        <details><summary>完整配方差异预览</summary><pre>{JSON.stringify(agentProposal.recipe, null, 2)}</pre></details>
        <button disabled={busy} onClick={() => void acceptAgent()}>接受建议并生成新版本</button>{' '}
        {!libraryOnly && <button disabled={busy} onClick={() => { const draft = clone(agentProposal.recipe); edit(draft); setJson(JSON.stringify(draft, null, 2)); }}>复制到编辑器微调</button>}{' '}
        <button disabled={busy} onClick={() => setAgentProposal(null)}>拒绝建议</button>
      </section>}
      {!libraryOnly && <><h2>FreeCAD 回流审阅</h2>
      <p>选择本机 FCStd，对照当前 STEP 的零件名称、体积、质心和拓扑。比较只生成提案；接受后所有关节需重新确认，原 CAD 版本保留。</p>
      <button disabled={busy || !modelConfig} onClick={() => void compareReturn()}>比较 FreeCAD 回流</button>
      {cadReturn && <section aria-label="FreeCAD 回流差异" data-return-status={cadReturn.status}>
        <p>{cadReturn.status === 'conflict' ? '发现冲突，禁止自动应用；请在 FreeCAD 中修正或重新分组。' : '零件可重关联；请审阅后明确接受。'}</p>
        {cadReturn.relinks.map(item => <p key={item.baseline_part}>{item.baseline_part} → {item.returned_part} / Link {item.link}；体积变化 {item.volume_delta_mm3.toPrecision(6)} mm³；质心位移 {item.center_delta_mm.map(x => x.toPrecision(4)).join(', ')} mm</p>)}
        {cadReturn.conflicts.map((item, index) => <p role="alert" key={index}>{item.part}：{item.kind}；原 Link {item.preserved_link || '未分配'} 保留</p>)}
        {cadReturn.status === 'review_required' && <button disabled={busy} onClick={() => void acceptReturn()}>接受回流并重新确认关节</button>}
      </section>}</>}
      </>}
  </section>;
}
