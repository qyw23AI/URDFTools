import { useEffect, useState, type CSSProperties } from 'react';
import './style.css';
import { UrdfWorkbench, type LibraryEntry } from './UrdfWorkbench';
import { FloatingPanel } from './FloatingPanel';
import { CadWizard, type CadDraftSnapshot, type Configuration, type Discovery } from './CadWizard';
import type { ModelRecipe, ModelApplyResult } from './ModelingWorkspace';
import { ResultLibrary, type ResultComparison, type ResultList, type ResultSeries } from './ResultLibrary';
import type { ResultSceneAssets } from './ResultCompareScene';
import type { CompareEntry, RobotImport } from './RobotViewer';
import { WebCodexAgentSidebar, type WebCodexTicket } from './WebCodexAgent';

const workspaces = ['URDF 工作区', 'CAD转换URDF', '评估'] as const;
const textScaleKey = 'urdftools:fixed-text-scale:v1';
function readTextScale() {
  try {
    const value = Number(window.localStorage.getItem(textScaleKey));
    return Number.isFinite(value) && value >= 0.9 && value <= 1.6 ? value : 1;
  } catch { return 1; }
}
type Finding = {code: string; location: string; message: string};
type ImportReport = {operation_id: string; status: string; selected_model: string | null;
  package_map: Record<string, string[]>;
  assets?: {path: string; sha256: string; size: number}[];
  findings: Finding[]; models: {path: string; name: string | null; status: string;
  resources: {uri: string; path?: string}[]; findings: Finding[]}[]};
declare global {
  interface Window { urdftools?: {version: string;
    workbenchApply(xml: string, baseline: RobotImport | null): Promise<RobotImport>;
    workbenchExport(operation: string): Promise<{path:string}|null>;
    cadLibraryList(): Promise<LibraryEntry[]>; cadLibraryImport(unit: 'mm'|'m'): Promise<LibraryEntry|null>;
    cadLibraryGenerated(): Promise<LibraryEntry>; cadLibraryRemove(id:string): Promise<void>; importFile(file: File): Promise<ImportReport>;
    chooseImport(kind: string): Promise<ImportReport | null>;
    importExample(): Promise<ImportReport>;
    selectImport(operation: string, model: string): Promise<ImportReport>;
    viewerSettle(operation: string, model: string, joints: Record<string, number>, limits: Record<string, boolean>): Promise<{
      status: string; engine: string; position: number[]; quaternion_wxyz: number[];
      joints: Record<string, number>; contacts: number; ground_contacts: number; joint_count: number;
      max_speed: number; simulated_seconds: number; ground_clearance: number; frames: {
        time: number; position: number[]; quaternion_wxyz: number[]; joints: Record<string, number>; ground_clearance: number
      }[] }>;
    chooseCadStep(): Promise<Discovery | null>; importCadFile(file: File): Promise<Discovery | null>; cadPreview(config: Configuration): Promise<RobotImport>;
    cadDraftLoad(): Promise<{discovery: Discovery; ui: CadDraftSnapshot | null; updated_at: string} | null>;
    cadDraftSave(ui: CadDraftSnapshot): Promise<string>;
    cadDraftClear(): Promise<boolean>;
    modelCurrent(): Promise<{revision: number; recipe: ModelRecipe; built?: ModelApplyResult | null; returnWarning?: string | null}>;
    modelApply(recipe: ModelRecipe, expectedRevision: number): Promise<ModelApplyResult>;
    agentApply(proposalId: string): Promise<ModelApplyResult>;
    webcodexCreateModel(instruction: string, revision: number, mode?: 'webcodex'|'cli'): Promise<WebCodexTicket>;
    webcodexCreateAnalysis(instruction: string, mode?: 'webcodex'|'cli'): Promise<WebCodexTicket>;
    webcodexCreateImportedAnalysis(operationId: string, instruction: string, mode?: 'webcodex'|'cli'): Promise<WebCodexTicket>;
    webcodexCreateResultAnalysis(reference: string, candidate: string, instruction: string,
      mode?: 'webcodex'|'cli'): Promise<WebCodexTicket>;
    webcodexStatus(requestId: string): Promise<WebCodexTicket>;
    agentCliRun(requestId: string): Promise<WebCodexTicket>;
    webcodexCopyPrompt(prompt: string): Promise<boolean>;
    webcodexOpen(requestId: string): Promise<{request_id: string; copied: boolean; opened: boolean}>;
    modelReconcile(config: Configuration): Promise<{proposal: import('./ModelingWorkspace').CadReturnProposal;
      exchange: {source_sha256: string; output_sha256: string; losses: string[]}} | null>;
    modelAcceptReturn(config: Configuration): Promise<Discovery>;
    saveCadConfig(config: Configuration): Promise<boolean>; loadCadConfig(): Promise<Configuration | null>;
    exportCadPackage(config: Configuration, densities: Record<string, number>): Promise<{path: string; sha256: string; massProperties: {name: string; mass_kg: number; center_of_mass_local_m: number[]; inertia_com_kg_m2: number[][]}[]; validation: {mujoco_raw: {fixed_base_mass_excluded_kg: number}; mujoco_floating: {mass_kg: number}; training_ready: boolean}} | null>;
    resultRuns(): Promise<ResultList>; resultImport(): Promise<{run_id: string; rows: number} | null>;
    resultImportNative(algorithm: string, chooseVideos: boolean): Promise<{run_id: string; rows: number} | null>;
    resultProject(runId: string, name: string, isStandard: boolean): Promise<{run_id: string}>;
    resultSeries(runId: string): Promise<ResultSeries>; resultScene(runId: string): Promise<ResultSceneAssets>;
    resultPairs(candidate: string): Promise<{candidate_id: string; pairs: {reference_id: string; request_id: string | null; mode: 'webcodex' | 'cli' | null}[]}>;
    resultSavePair(candidate: string, reference: string, requestId: string | null,
      mode: 'webcodex' | 'cli' | null): Promise<{candidate_id: string}>;
    resultCompare(reference: string, candidate: string): Promise<ResultComparison>}; }
}
export function App() {
  const desktopAvailable = typeof window !== 'undefined' && typeof window.urdftools !== 'undefined';
  const [workspace, setWorkspace] = useState<typeof workspaces[number]>('URDF 工作区');
  const [report, setReport] = useState<RobotImport | null>(null);
  const [fileReport, setFileReport] = useState<ImportReport | null>(null);
  const [comparisons, setComparisons] = useState<CompareEntry[]>([]);
  const [textureEnabled, setTextureEnabled] = useState<Record<string, boolean>>({});
  const [activeCompareId, setActiveCompareId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [agentOpen, setAgentOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(true);
  const [fixedTextScale, setFixedTextScale] = useState(readTextScale);
  useEffect(() => {
    try { window.localStorage.setItem(textScaleKey, String(fixedTextScale)); }
    catch { /* App remains usable when local storage is unavailable. */ }
  }, [fixedTextScale]);
  function acceptImport(result: ImportReport) {
    setFileReport(result);
    if (result.status !== 'ready' || !result.selected_model) return;
    setReport(result);
    const id = `${result.operation_id}:${result.selected_model}`;
    setComparisons(old => old.some(entry => entry.id === id) ? old.map(entry => entry.id === id ? { id, report: result } : entry)
      : [...old, { id, report: result }]);
    setActiveCompareId(id);
  }
  async function run(action: () => Promise<ImportReport | null>) {
    if (busy) return;
    setBusy(true); setError('');
    try { const result = await action(); if (result) acceptImport(result); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function importDropped(files: FileList) {
    if (busy || !window.urdftools) return;
    setBusy(true); setError('');
    const failures: string[] = [];
    for (const file of Array.from(files)) {
      try { acceptImport(await window.urdftools.importFile(file)); }
      catch (cause) { failures.push(`${file.name}：${String(cause)}`); }
    }
    if (failures.length) setError(failures.join('；'));
    setBusy(false);
  }
  function selectComparison(id: string) {
    const entry = comparisons.find(item => item.id === id);
    if (!entry) return;
    setActiveCompareId(id);
    setReport(entry.report);
  }
  function removeComparison(id: string) {
    const remaining = comparisons.filter(entry => entry.id !== id);
    setComparisons(remaining);
    if (activeCompareId === id) {
      const next = remaining[0];
      setActiveCompareId(next?.id ?? null);
      setReport(next?.report ?? null);
    }
  }
  const viewing = workspace === 'URDF 工作区';
  return <div className={'shell' + (agentOpen ? ' agent-open' : '')}
    style={{ '--fixed-text-scale': fixedTextScale } as CSSProperties}>
    <header className="app-header"><div className="brand"><strong>URDFTools</strong><span>机器人设计工作台</span></div>
      <nav aria-label="工作区">{workspaces.map(name => <button key={name} aria-pressed={name === workspace} onClick={() => setWorkspace(name)}>{name}</button>)}</nav>
      <div className="header-actions"><span className="app-status">本地工作区 · SI 单位</span>
        <div className="text-size-control" role="group" aria-label="固定栏字体大小">
          <button type="button" aria-label="缩小固定栏字体" title="缩小固定栏字体" disabled={fixedTextScale <= 0.9}
            onClick={() => setFixedTextScale(value => Math.max(0.9, Math.round((value - 0.1) * 10) / 10))}>A−</button>
          <button type="button" className="text-size-value" aria-label="重置固定栏字体为百分之百" title="点击恢复 100% 字号"
            onClick={() => setFixedTextScale(1)}>{Math.round(fixedTextScale * 100)}%</button>
          <button type="button" aria-label="放大固定栏字体" title="放大固定栏字体" disabled={fixedTextScale >= 1.6}
            onClick={() => setFixedTextScale(value => Math.min(1.6, Math.round((value + 0.1) * 10) / 10))}>A+</button>
        </div>
        {viewing && <button type="button" onClick={() => setFilesOpen(open => !open)}>文件</button>}
        <button type="button" className="agent-toggle" aria-expanded={agentOpen} onClick={() => setAgentOpen(open => !open)}>{agentOpen ? '收起助手' : '打开助手'}</button></div></header>
    <main className={viewing ? 'workspace-main workspace-view' : 'workspace-main workspace-tools'}>
      {!desktopAvailable && <p className="desktop-notice" role="status">当前为浏览器界面预览。导入和转换请运行桌面应用。</p>}
      <section hidden={!viewing} className="viewer-workspace" aria-label="本地导入"
      onDragOver={event => event.preventDefault()} onDrop={event => {
        event.preventDefault(); const files = event.dataTransfer.files;
        if (event.dataTransfer.types.includes('application/x-urdf-cad')) return;
        if (!files.length) return;
        if (window.urdftools) void importDropped(files);
        else setError('请在桌面应用中导入本地文件');
      }}>
      {filesOpen && <FloatingPanel title="文件 · 导入模型" initial={{ x: 16, y: 70, width: 300, height: 370 }} onClose={() => setFilesOpen(false)} className="file-window" halfSide="left">
      <div className="import-panel"><div className="panel-heading"><div><small>01 / 文件</small><h1>打开机器人模型</h1></div></div>
      <p className="import-help">可一次拖入多个 URDF、ZIP 或模型文件夹，并排查看与检查。</p>
      <div className="import-actions"><button disabled={busy || !desktopAvailable} onClick={() => void run(() => window.urdftools!.chooseImport('folder'))}>选择文件夹</button>
      <button disabled={busy || !desktopAvailable} onClick={() => void run(() => window.urdftools!.chooseImport('file'))}>选择 URDF / ZIP</button>
      <button aria-label="打开内置示例" disabled={busy || !desktopAvailable} onClick={() => void run(() => window.urdftools!.importExample())}>打开内置示例</button></div>
      <p className="hint">选择 urdf/ 下的模型会自动带入相邻 meshes/ 和贴图；复杂 ROS 包也可选择整个机器人文件夹或 ZIP。</p>
      {busy && <p role="status">正在复制与检查资源…</p>}
      {error && <p role="alert">{error}</p>}
      <div className="imported-model-settings"><h2>已导入模型 · 贴图选项</h2>
        {!comparisons.length && <p className="hint">尚无已导入模型</p>}
        {comparisons.map(entry => <div key={entry.id} className="imported-model-row">
          <span title={entry.report.selected_model || ''}>{entry.report.models.find(model => model.path === entry.report.selected_model)?.name || entry.report.selected_model}</span>
          <label><input type="checkbox" aria-label={`加载贴图 ${entry.report.selected_model}`} checked={textureEnabled[entry.id] ?? Boolean(entry.report.assets?.some(asset => /\.(png|jpe?g|bmp|webp)$/i.test(asset.path)))}
            onChange={event => setTextureEnabled(old => ({...old, [entry.id]: event.target.checked}))} />加载贴图</label>
        </div>)}
        <p className="hint">含图片资源的模型默认加载贴图；其余模型默认显示灰色面片质感。每个模型可独立切换。</p>
      </div>
      {fileReport && <div className="import-report" data-import-status={fileReport.status}><h2>导入报告</h2>
        <p>{fileReport.status === 'selection_required' ? '发现多个模型，请选择' : fileReport.status === 'ready' ? '资源检查通过' : '导入失败，请查看定位信息'}</p>
        <p>已复制 {fileReport.assets?.filter(asset => /\.(stl|obj|dae)$/i.test(asset.path)).length || 0} 个网格文件、
          {fileReport.assets?.filter(asset => /\.(png|jpg|jpeg|bmp)$/i.test(asset.path)).length || 0} 张贴图。</p>
        {fileReport.models.map(model => <article key={model.path}>
          <button disabled={busy} aria-pressed={fileReport.selected_model === model.path}
            onClick={() => void run(() => window.urdftools!.selectImport(fileReport.operation_id, model.path))}>{model.name || model.path} · {model.path}</button>
          <p>{model.status === 'ready' ? '资源可用' : '存在错误'} · {model.resources.length} 项资源</p>
          {model.resources.some(r => !r.path) && <details><summary>未解析资源</summary>{model.resources.filter(r => !r.path).map((r, i) => <p key={i}>{r.uri}</p>)}</details>}
          {model.findings.map((f, i) => <p role="alert" key={i}>{f.code} · {f.location}：{f.message}</p>)}
        </article>)}
        {fileReport.findings.map((f, i) => <p role="alert" key={i}>{f.code} · {f.location}：{f.message}</p>)}
      </div>}</div></FloatingPanel>}
      <div className="stage-panel"><UrdfWorkbench initialReport={report?.status === 'ready' ? report : null}
        compareEntries={comparisons} activeCompareId={activeCompareId} textureEnabled={textureEnabled}
        onSelectCompare={selectComparison} onRemoveCompare={removeComparison}
        onReportChange={next => {
          if (activeCompareId) setComparisons(old => old.map(entry => entry.id === activeCompareId ? { ...entry, report: next } : entry));
          else if (next.status === 'ready' && next.selected_model) {
            const id = `${next.operation_id}:${next.selected_model}`;
            setComparisons(old => [...old, { id, report: next }]);
            setActiveCompareId(id);
          }
        }} /></div>
    </section>
      <section className="tool-workspace cad-tool-workspace" hidden={workspace !== 'CAD转换URDF'}
        aria-label="CAD转换URDF"><CadWizard /></section>
      <section className="tool-workspace" hidden={workspace !== '评估'}
        aria-label="评估"><div className="tool-heading"><small>工作区</small><h1>评估</h1></div><ResultLibrary /></section>
    </main>
    <aside className="agent-panel" aria-label="智能助手" hidden={!agentOpen}><WebCodexAgentSidebar desktopAvailable={desktopAvailable} importedOperationId={report?.status==='ready' ? report.operation_id : null} /></aside>
    <footer>本地运行 · 版本 0.1.0</footer></div>;
}
