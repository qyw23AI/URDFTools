import { useEffect, useRef, useState } from 'react';
import { MediaEvidence } from './MediaEvidence';

export type ResultRun = { run_id: string; algorithm: string; protocol: string; origin: string;
  robot_hash: string; metrics: number; category: string; has_evidence: boolean };
export type ResultList = { runs: ResultRun[]; verified_reference_count: number };
export type ResultMedia = { path: string; source_sha256: string; video: { episode_id: string; camera: string;
  frame_count: number; suspected_gap_frame_indices: number[] }; events: { metric: string; status: string;
  frame_index: number | null; frame_timestamp_s?: number; experiment_time_s: number }[] };
export type ResultComparison = { fixture_only: boolean; reference_origin: string; candidate_origin: string;
  comparison: { status: string; comparability: { status: string; reasons: { field: string; reason?: string }[] };
    reference_mean: number | null; candidate_mean: number | null; difference: number | null;
    confidence_interval_95: number[] | null; sampling_unit: string };
  reference_media: ResultMedia[]; candidate_media: ResultMedia[] };

function EvidenceVideo({ item, label }: { item: ResultMedia; label: string }) {
  const player = useRef<HTMLVideoElement>(null);
  return <article className="result-video"><h4>{label} · {item.video.episode_id} · {item.video.camera}</h4>
    <p>视频 SHA-256：<code>{item.source_sha256}</code> · {item.video.frame_count} 帧</p>
    <video ref={player} controls preload="metadata" src={`urdftools://result/${item.source_sha256}`} />
    {item.video.suspected_gap_frame_indices.length > 0 && <p role="alert">疑似缺帧：{item.video.suspected_gap_frame_indices.join(', ')}</p>}
    <ul>{item.events.map((event, index) => <li key={index}><button disabled={event.status !== 'located' || event.frame_index === null}
      onClick={() => { if (player.current && event.frame_timestamp_s !== undefined) player.current.currentTime = event.frame_timestamp_s; }}>
      {event.metric} · 实验 {event.experiment_time_s}s · 帧 {event.frame_index ?? '越界'}</button></li>)}</ul>
  </article>;
}

export function ResultLibrary() {
  const desktopAvailable = typeof window !== 'undefined' && !!window.urdftools;
  const [listing, setListing] = useState<ResultList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [reference, setReference] = useState('');
  const [candidate, setCandidate] = useState('');
  const [comparison, setComparison] = useState<ResultComparison | null>(null);
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
  async function compare() {
    if (!window.urdftools || !reference || !candidate || busy) return;
    setBusy(true); setError(''); setComparison(null);
    try { setComparison(await window.urdftools.resultCompare(reference, candidate)); }
    catch (cause) { setError(String(cause)); }
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
    <div className="result-compare-controls"><label>标准模型实验 <select value={reference} onChange={event => setReference(event.target.value)}>
      <option value="">选择 run</option>{listing?.runs.filter(run => run.has_evidence).map(run =>
        <option key={run.run_id} value={run.run_id}>{run.run_id}</option>)}</select></label>
      <label>自有模型实验 <select value={candidate} onChange={event => setCandidate(event.target.value)}>
        <option value="">选择 run</option>{listing?.runs.filter(run => run.has_evidence).map(run =>
          <option key={run.run_id} value={run.run_id}>{run.run_id}</option>)}</select></label>
      <button disabled={busy || !reference || !candidate || reference === candidate} onClick={() => void compare()}>核对协议与结果</button></div>
    {comparison && <section aria-label="实验结果对照"><h3>同协议对照</h3>
      <p>可比性：{comparison.comparison.comparability.status}；统计状态：{comparison.comparison.status}；独立单位：{comparison.comparison.sampling_unit}</p>
      {comparison.fixture_only && <p role="alert">包含 synthetic_fixture，仅供流程验证，不作为真实参考成绩。</p>}
      <p>标准成功均值：{comparison.comparison.reference_mean ?? '未知'}；自有成功均值：{comparison.comparison.candidate_mean ?? '未知'}；差值：{comparison.comparison.difference ?? '不可计算'}</p>
      <p>95% 区间：{comparison.comparison.confidence_interval_95?.join(' 至 ') ?? '样本不足或不可比'}</p>
      {comparison.comparison.comparability.reasons.map((reason, index) => <p role="alert" key={index}>{reason.field}：{reason.reason || '条件不同'}</p>)}
      <div className="result-videos">{comparison.reference_media.map(media => <EvidenceVideo key={`r-${media.source_sha256}`} item={media} label="标准" />)}
        {comparison.candidate_media.map(media => <EvidenceVideo key={`c-${media.source_sha256}`} item={media} label="自有" />)}</div>
    </section>}
  </section><MediaEvidence /></div>;
}
