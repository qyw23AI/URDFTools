import { useEffect, useState } from 'react';
import { MediaEvidence } from './MediaEvidence';

export type ResultRun = { run_id: string; algorithm: string; protocol: string; origin: string;
  robot_hash: string; metrics: number; category: string };
export type ResultList = { runs: ResultRun[]; verified_reference_count: number };

export function ResultLibrary() {
  const desktopAvailable = typeof window !== 'undefined' && !!window.urdftools;
  const [listing, setListing] = useState<ResultList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (window.urdftools) void window.urdftools.resultRuns().then(setListing).catch(cause => setError(String(cause))); }, []);
  async function importBundle() {
    if (!window.urdftools || busy) return;
    setBusy(true); setError('');
    try {
      const result = await window.urdftools.resultImport();
      if (result) setListing(await window.urdftools.resultRuns());
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  return <div><section aria-label="外部训练结果库">
    <p>导入已在外部完成的四足或人形实验包；仅在本机处理，不启动训练。实验包需含 manifest.json、所列 URDF、experiment.json 与指标文件。</p>
    <button disabled={!desktopAvailable || busy} onClick={() => void importBundle()}>选择实验包文件夹</button>
    {busy && <p role="status">正在校验哈希并入库…</p>}
    {error && <p role="alert">{error}</p>}
    <p>已核验真实参考成绩：{listing?.verified_reference_count ?? 0}。合成夹具仅用于流程验收。</p>
    <ul>{listing?.runs.map(run => <li key={run.run_id}>{run.run_id} · {run.category} · {run.origin} ·
      {run.algorithm} / {run.protocol} · {run.metrics} 项指标 · SHA {run.robot_hash.slice(0, 12)}</li>)}</ul>
  </section><MediaEvidence /></div>;
}
