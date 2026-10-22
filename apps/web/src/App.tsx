import { useState } from 'react';
import './style.css';

const workspaces = ['查看', '转换', '建模', '评估'] as const;
export function App() {
  const [workspace, setWorkspace] = useState<typeof workspaces[number]>('查看');
  return <div className="shell"><header><strong>URDFTools</strong><span>本地机器人设计工作台</span></header>
    <nav aria-label="工作区">{workspaces.map(name => <button key={name} aria-pressed={name === workspace} onClick={() => setWorkspace(name)}>{name}</button>)}</nav>
    <main><h1>{workspace}</h1><p>尚未打开工程</p><p>当前为应用基础框架。机器人导入、三维查看、转换、建模与评估功能将在后续阶段提供。</p></main>
    <aside><h2>Agent</h2><p>尚未连接</p></aside><footer>本地运行 · SI 单位 · 版本 0.1.0</footer></div>;
}
