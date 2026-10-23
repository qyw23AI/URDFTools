import { useState } from 'react';
import './style.css';
import { RobotViewer } from './RobotViewer';
import { CadWizard, type Configuration, type Discovery } from './CadWizard';
import { ModelingWorkspace, type ModelRecipe, type ModelApplyResult } from './ModelingWorkspace';
import { ResultLibrary, type ResultList } from './ResultLibrary';
import type { RobotImport } from './RobotViewer';

const workspaces = ['查看', '转换', '建模', '评估'] as const;
type Finding = {code: string; location: string; message: string};
type ImportReport = {operation_id: string; status: string; selected_model: string | null;
  package_map: Record<string, string[]>;
  findings: Finding[]; models: {path: string; name: string | null; status: string;
  resources: {uri: string; path?: string}[]; findings: Finding[]}[]};
declare global {
  interface Window { urdftools?: {version: string; importFile(file: File): Promise<ImportReport>;
    chooseImport(kind: string): Promise<ImportReport | null>;
    selectImport(operation: string, model: string): Promise<ImportReport>;
    chooseCadStep(): Promise<Discovery | null>; cadPreview(config: Configuration): Promise<RobotImport>;
    modelCurrent(): Promise<{revision: number; recipe: ModelRecipe; built?: ModelApplyResult | null; returnWarning?: string | null}>;
    modelApply(recipe: ModelRecipe, expectedRevision: number): Promise<ModelApplyResult>;
    agentSuggest(instruction: string, expectedRevision: number): Promise<{proposal_id: string; diff: {added_parts: string[]; removed_parts: string[]; changed_parts: string[]}; recipe: ModelRecipe; rationale: string; report: {parts: {name: string; mass_kg: number}[]}; status: 'preview_only'}>;
    agentApply(proposalId: string): Promise<ModelApplyResult>;
    modelReconcile(config: Configuration): Promise<{proposal: import('./ModelingWorkspace').CadReturnProposal;
      exchange: {source_sha256: string; output_sha256: string; losses: string[]}} | null>;
    modelAcceptReturn(config: Configuration): Promise<Discovery>;
    saveCadConfig(config: Configuration): Promise<boolean>; loadCadConfig(): Promise<Configuration | null>;
    exportCadPackage(config: Configuration, densities: Record<string, number>): Promise<{path: string; sha256: string; validation: {mujoco_raw: {fixed_base_mass_excluded_kg: number}; mujoco_floating: {mass_kg: number}; training_ready: boolean}} | null>;
    resultRuns(): Promise<ResultList>; resultImport(): Promise<{run_id: string; rows: number} | null>}; }
}
export function App() {
  const desktopAvailable = typeof window !== 'undefined' && typeof window.urdftools !== 'undefined';
  const [workspace, setWorkspace] = useState<typeof workspaces[number]>('查看');
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function run(action: () => Promise<ImportReport | null>) {
    if (busy) return;
    setBusy(true); setError('');
    try { const result = await action(); if (result) setReport(result); }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  return <div className="shell"><header><strong>URDFTools</strong><span>本地机器人设计工作台</span></header>
    <nav aria-label="工作区">{workspaces.map(name => <button key={name} aria-pressed={name === workspace} onClick={() => setWorkspace(name)}>{name}</button>)}</nav>
    <main><h1>{workspace}</h1>{!desktopAvailable && <p role="status">当前是浏览器界面预览。URDF/ZIP 导入、CAD 转换与建模需要运行项目桌面应用：在终端执行 <code>./scripts/launch-dev-desktop.sh</code>。</p>}{workspace === '查看' ? <section aria-label="本地导入"
      onDragOver={event => event.preventDefault()} onDrop={event => {
        event.preventDefault(); const files = event.dataTransfer.files;
        if (files.length !== 1) { setError('每次请拖入一个文件夹、URDF 或 ZIP'); return; }
        if (window.urdftools) void run(() => window.urdftools!.importFile(files[0]));
        else setError('请在桌面应用中导入本地文件');
      }}>
      <p>拖入一个文件夹、URDF 或 ZIP；输入会复制到独立导入目录。</p>
      <button disabled={busy || !desktopAvailable} onClick={() => void run(() => window.urdftools!.chooseImport('folder'))}>选择文件夹</button>{' '}
      <button disabled={busy || !desktopAvailable} onClick={() => void run(() => window.urdftools!.chooseImport('file'))}>选择 URDF / ZIP</button>
      <p>单独导入 URDF 仅包含该文件；有关联网格时请选择所在文件夹。</p>
      {busy && <p role="status">正在复制与检查资源…</p>}
      {error && <p role="alert">{error}</p>}
      {report && <div data-import-status={report.status}><h2>导入报告</h2>
        <p>{report.status === 'selection_required' ? '发现多个模型，请选择' : report.status === 'ready' ? '资源检查通过' : '导入失败，请查看定位信息'}</p>
        <p>导入编号：{report.operation_id}</p>
        {report.models.map(model => <article key={model.path}>
          <button disabled={busy} aria-pressed={report.selected_model === model.path}
            onClick={() => void run(() => window.urdftools!.selectImport(report.operation_id, model.path))}>{model.name || model.path} · {model.path}</button>
          <p>{model.status === 'ready' ? '资源可用' : '存在错误'} · {model.resources.length} 项资源</p>
          {model.resources.map((r, i) => <p key={i}>{r.uri} → {r.path || '未解析'}</p>)}
          {model.findings.map((f, i) => <p role="alert" key={i}>{f.code} · {f.location}：{f.message}</p>)}
        </article>)}
        {report.findings.map((f, i) => <p role="alert" key={i}>{f.code} · {f.location}：{f.message}</p>)}
        {report.status === 'ready' && <RobotViewer report={report} />}
      </div>}
    </section> : workspace === '转换' ? <CadWizard /> : workspace === '建模' ? <ModelingWorkspace /> : <ResultLibrary />}</main>
    <aside><h2>Agent</h2><p>尚未连接</p></aside><footer>本地运行 · SI 单位 · 版本 0.1.0</footer></div>;
}
