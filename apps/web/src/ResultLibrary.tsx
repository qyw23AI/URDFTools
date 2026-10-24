import { useEffect, useMemo, useRef, useState } from 'react';
import { MediaEvidence } from './MediaEvidence';
import { ResultCompareScene, type ResultSceneAssets } from './ResultCompareScene';
import type { WebCodexTicket } from './WebCodexAgent';

export type ResultRun = { run_id: string; algorithm: string; protocol: string; origin: string; robot_hash: string;
  metrics: number; category: string; has_evidence: boolean; model_name: string; display_name: string; is_standard: boolean };
export type ResultList = { runs: ResultRun[]; verified_reference_count: number };
export type ResultSeries = { run_id: string; series: { metric: string; unit: string; points: [number, number][] }[] };
export type ResultMedia = { path: string; source_sha256: string; video: { episode_id: string; camera: string;
  frame_count: number; suspected_gap_frame_indices: number[] }; events: { metric: string; status: string;
  frame_index: number | null; frame_timestamp_s?: number; experiment_time_s: number }[] };
export type ResultComparison = { reference_run_id: string; candidate_run_id: string; fixture_only: boolean;
  reference_origin: string; candidate_origin: string; comparison: { status: string;
    comparability: { status: string; reasons: { field: string; reason?: string }[] };
    reference_mean: number | null; candidate_mean: number | null; difference: number | null;
    confidence_interval_95: number[] | null; sampling_unit: string };
  reference_media: ResultMedia[]; candidate_media: ResultMedia[] };

function EvidenceVideo({ item, label }: { item: ResultMedia; label: string }) {
  const player = useRef<HTMLVideoElement>(null);
  return <article className="result-video"><h4>{label} · {item.video.episode_id} · {item.video.camera}</h4>
    <video ref={player} controls preload="metadata" src={`urdftools://result/${item.source_sha256}`} />
    {item.video.suspected_gap_frame_indices.length > 0 && <p role="alert">疑似缺帧：{item.video.suspected_gap_frame_indices.join(', ')}</p>}
    <div className="result-video-events">{item.events.map((event, index) => <button key={index}
      disabled={event.status !== 'located' || event.frame_index === null}
      onClick={() => { if (player.current && event.frame_timestamp_s !== undefined) player.current.currentTime = event.frame_timestamp_s; }}>
      {event.metric} · {event.experiment_time_s}s</button>)}</div>
  </article>;
}

function Curve({ metric, left, right }: { metric: string; left?: { points: [number, number][]; unit: string };
  right?: { points: [number, number][]; unit: string } }) {
  const points = [...(left?.points || []), ...(right?.points || [])];
  if (!points.length) return null;
  const xs = points.map(point => point[0]), ys = points.map(point => point[1]);
  const xmin = Math.min(...xs), xmax = Math.max(...xs), ymin = Math.min(...ys), ymax = Math.max(...ys);
  const plot = (values?: [number, number][]) => values?.map(([x, y]) =>
    `${18 + (x - xmin) / (xmax - xmin || 1) * 282},${103 - (y - ymin) / (ymax - ymin || 1) * 86}`).join(' ') || '';
  return <article className="result-curve"><h4>{metric} <small>{left?.unit || right?.unit}</small></h4>
    <svg viewBox="0 0 320 120" role="img" aria-label={`${metric} 的候选项目与标准项目曲线`}>
      <line x1="18" y1="103" x2="300" y2="103" /><line x1="18" y1="17" x2="18" y2="103" />
      {left && <polyline className="candidate-line" points={plot(left.points)} />}
      {right && <polyline className="standard-line" points={plot(right.points)} />}
    </svg><div className="result-curve-scale"><span>{ymin.toPrecision(3)}</span><span>{ymax.toPrecision(3)}</span></div>
    <div className="result-curve-values"><span>待分析末值：{left?.points.at(-1)?.[1] ?? '无'}</span>
      <span>标准末值：{right?.points.at(-1)?.[1] ?? '无'}</span></div>
  </article>;
}

function ProjectRow({ run, selected, onSelect, onSaved }: { run: ResultRun; selected: boolean;
  onSelect: () => void; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(run.display_name);
  const [standard, setStandard] = useState(run.is_standard);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setName(run.display_name); setStandard(run.is_standard); }, [run.display_name, run.is_standard]);
  async function save() {
    if (!window.urdftools || !name.trim()) return;
    setSaving(true); setError('');
    try { await window.urdftools.resultProject(run.run_id, name.trim(), standard); await onSaved(); setEditing(false); }
    catch (cause) { setError(String(cause)); }
    finally { setSaving(false); }
  }
  return <article className={`result-project ${selected ? 'selected' : ''}`}>
    <button className="result-project-select" onClick={onSelect} aria-pressed={selected}>
      <strong>{run.display_name}</strong><span>{run.model_name} · {run.protocol}</span>
      <small>{run.is_standard ? '标准项目' : '待对比项目'} · {run.metrics} 条指标 · {run.has_evidence ? '含训练证据' : '无视频证据'}</small>
    </button>
    <button className="result-project-edit" onClick={() => setEditing(value => !value)} aria-label={`设置 ${run.display_name}`}>设置</button>
    {editing && <div className="result-project-settings"><label>项目名称<input value={name} maxLength={120} onChange={event => setName(event.target.value)} /></label>
      <label className="result-standard-toggle"><input type="checkbox" checked={standard} onChange={event => setStandard(event.target.checked)} />设为标准项目</label>
      <button disabled={saving || !name.trim()} onClick={() => void save()}>保存项目</button>{error && <p role="alert">{error}</p>}</div>}
  </article>;
}

export function ResultLibrary() {
  const desktopAvailable = typeof window !== 'undefined' && !!window.urdftools;
  const [listing, setListing] = useState<ResultList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [nativeAlgorithm, setNativeAlgorithm] = useState('MyHIMLoco');
  const [chooseVideos, setChooseVideos] = useState(false);
  const [candidate, setCandidate] = useState('');
  const [pairs, setPairs] = useState<ResultComparison[]>([]);
  const [activePair, setActivePair] = useState<ResultComparison | null>(null);
  const [scenes, setScenes] = useState<[ResultSceneAssets, ResultSceneAssets] | null>(null);
  const [series, setSeries] = useState<[ResultSeries, ResultSeries] | null>(null);
  const [agentMode, setAgentMode] = useState<'webcodex' | 'cli'>('webcodex');
  const [agentInstruction, setAgentInstruction] = useState('逐项对比同算法标准项目与待分析项目的 URDF 结构、训练指标和步态视频元数据，引用证据，区分相关性与因果，给出下一步验证建议。');
  const [tickets, setTickets] = useState<Record<string, WebCodexTicket>>({});
  const [pairErrors, setPairErrors] = useState<Record<string, string>>({});
  const [agentNotice, setAgentNotice] = useState('');
  const runs = listing?.runs || [];
  const chosen = runs.find(run => run.run_id === candidate);
  const grouped = useMemo(() => Object.entries((listing?.runs || []).reduce<Record<string, ResultRun[]>>((groups, run) => {
    (groups[run.algorithm] ||= []).push(run); return groups;
  }, {})).sort(([a], [b]) => a.localeCompare(b)), [listing]);
  useEffect(() => { if (window.urdftools) void window.urdftools.resultRuns().then(setListing).catch(cause => setError(String(cause))); }, []);
  useEffect(() => {
    if (!candidate || !window.urdftools) return;
    let cancelled = false;
    setPairs([]); setTickets({}); setPairErrors({});
    void window.urdftools.resultPairs(candidate).then(async saved => {
      const recovered: ResultComparison[] = [];
      const recoveredTickets: Record<string, WebCodexTicket> = {};
      for (const item of saved.pairs) {
        try {
          recovered.push(await window.urdftools!.resultCompare(item.reference_id, candidate));
          if (item.request_id) recoveredTickets[item.reference_id] = await window.urdftools!.webcodexStatus(item.request_id);
        } catch (cause) {
          if (!cancelled) setPairErrors(current => ({ ...current, [item.reference_id]: String(cause) }));
        }
      }
      if (!cancelled) { setPairs(recovered); setTickets(recoveredTickets); }
    }).catch(cause => { if (!cancelled) setError(String(cause)); });
    return () => { cancelled = true; };
  }, [candidate]);
  useEffect(() => {
    if (!window.urdftools) return;
    const pending = Object.entries(tickets).filter(([, ticket]) => ticket.status === 'awaiting_chatgpt_web_reply');
    if (!pending.length) return;
    const timer = window.setInterval(() => {
      for (const [referenceId, ticket] of pending) void window.urdftools?.webcodexStatus(ticket.request_id)
        .then(next => setTickets(current => current[referenceId]?.request_id === next.request_id ?
          { ...current, [referenceId]: next } : current)).catch(() => {});
    }, 3000);
    return () => window.clearInterval(timer);
  }, [tickets]);
  async function refresh() { if (window.urdftools) setListing(await window.urdftools.resultRuns()); }
  async function importBundle() {
    if (!window.urdftools || busy) return;
    setBusy(true); setError('');
    try { const result = await window.urdftools.resultImport(); if (result) { await refresh(); setCandidate(result.run_id); } }
    catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function importNative() {
    if (!window.urdftools || busy || !nativeAlgorithm.trim()) return;
    setBusy(true); setError('');
    try {
      const result = await window.urdftools.resultImportNative(nativeAlgorithm.trim(), chooseVideos);
      if (result) { await refresh(); setCandidate(result.run_id); }
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function compareAll() {
    if (!window.urdftools || !chosen || busy) return;
    const standards = runs.filter(run => run.algorithm === chosen.algorithm && run.is_standard &&
      run.run_id !== chosen.run_id && run.has_evidence);
    setBusy(true); setError(''); setPairs([]); setActivePair(null); setTickets({}); setPairErrors({});
    try {
      const results: ResultComparison[] = [];
      for (const standard of standards) {
        try {
          const pair = await window.urdftools.resultCompare(standard.run_id, chosen.run_id);
          results.push(pair); setPairs([...results]);
          await window.urdftools.resultSavePair(chosen.run_id, standard.run_id, null, null);
          try {
            const created = await window.urdftools.webcodexCreateResultAnalysis(
              standard.run_id, chosen.run_id, agentInstruction, agentMode);
            await window.urdftools.resultSavePair(chosen.run_id, standard.run_id, created.request_id, agentMode);
            setTickets(current => ({ ...current, [standard.run_id]: created }));
            if (agentMode === 'cli') {
              const completed = await window.urdftools.agentCliRun(created.request_id);
              setTickets(current => ({ ...current, [standard.run_id]: completed }));
            }
          } catch (cause) {
            setPairErrors(current => ({ ...current, [standard.run_id]: String(cause) }));
          }
        } catch (cause) {
          setPairErrors(current => ({ ...current, [standard.run_id]: String(cause) }));
        }
      }
    } catch (cause) { setError(String(cause)); }
    finally { setBusy(false); }
  }
  async function openPair(pair: ResultComparison) {
    if (!window.urdftools) return;
    setActivePair(pair); setScenes(null); setSeries(null); setError('');
    try {
      const [candidateScene, standardScene, candidateSeries, standardSeries] = await Promise.all([
        window.urdftools.resultScene(pair.candidate_run_id), window.urdftools.resultScene(pair.reference_run_id),
        window.urdftools.resultSeries(pair.candidate_run_id), window.urdftools.resultSeries(pair.reference_run_id)
      ]);
      setScenes([candidateScene, standardScene]); setSeries([candidateSeries, standardSeries]);
    } catch (cause) { setError(String(cause)); }
  }
  const standardCount = chosen ? runs.filter(run => run.algorithm === chosen.algorithm && run.is_standard && run.run_id !== chosen.run_id).length : 0;
  const leftRun = activePair && runs.find(run => run.run_id === activePair.candidate_run_id);
  const rightRun = activePair && runs.find(run => run.run_id === activePair.reference_run_id);
  const metrics = series ? Array.from(new Set([...series[0].series, ...series[1].series].map(item => item.metric))) : [];
  const activeTicket = activePair ? tickets[activePair.reference_run_id] : null;
  async function openAgent() {
    if (!window.urdftools || !activeTicket) return;
    try { await window.urdftools.webcodexOpen(activeTicket.request_id);
      setAgentNotice('已打开 ChatGPT 并复制此组对比请求。请在已连接 WebCodex 的网页对话中粘贴发送。'); }
    catch (cause) { setAgentNotice(String(cause)); }
  }
  async function retryAgent() {
    if (!window.urdftools || !activeTicket || !activePair) return;
    try { const completed = await window.urdftools.agentCliRun(activeTicket.request_id);
      setTickets(current => ({ ...current, [activePair.reference_run_id]: completed })); setAgentNotice('模型回复已完成本地证据校验。'); }
    catch (cause) { setAgentNotice(String(cause)); }
  }
  return <div className="results-workspace">
    <header className="results-header"><div><small>训练结果工作台</small><h2>项目与标准对比</h2>
      <p>选择 MyHIMLoco / WMP 训练目录，自动读取配置、URDF、TensorBoard 与目录内步态视频。项目按自定义算法归类。</p></div>
      <button disabled={!desktopAvailable || busy} onClick={() => void importBundle()}>导入标准实验包</button></header>
    <section className="result-native-import" aria-label="导入原始训练目录">
      <label>算法名称<input value={nativeAlgorithm} maxLength={80} onChange={event => setNativeAlgorithm(event.target.value)}
        placeholder="例如 MyHIMLoco、WMP" /></label>
      <label className="result-native-video"><input type="checkbox" checked={chooseVideos}
        onChange={event => setChooseVideos(event.target.checked)} />另选视频目录</label>
      <button className="primary" disabled={!desktopAvailable || busy || !nativeAlgorithm.trim()}
        onClick={() => void importNative()}>导入原始训练目录</button>
      <small>需要 config.json 和 events.out.tfevents.*；URDF 从配置中的机器人路径定位。未提供独立评估结果时，仅展示曲线和视频，不推断成功率。</small>
    </section>
    {error && <p role="alert" className="result-error">{error}</p>}
    {busy && <p role="status">正在处理项目…</p>}
    {!activePair ? <div className="result-library-layout"><aside className="result-project-library" aria-label="训练项目列表">
      <h3>训练项目</h3><p>按用户定义的算法分组。项目名称和标准身份可随时修改。</p>
      {grouped.length === 0 && <p>暂无项目。请导入一个完整实验包开始。</p>}
      {grouped.map(([algorithm, projects]) => <section key={algorithm}><h4>{algorithm}<span>{projects.length}</span></h4>
        {projects.map(run => <ProjectRow key={run.run_id} run={run} selected={candidate === run.run_id}
          onSelect={() => { setCandidate(run.run_id); setPairs([]); }} onSaved={refresh} />)}</section>)}
    </aside><main className="result-project-main">
      {chosen ? <><div className="result-project-hero"><div><small>{chosen.algorithm} / {chosen.protocol}</small><h3>{chosen.display_name}</h3>
        <p>模型：{chosen.model_name}　·　{chosen.metrics} 条指标　·　{chosen.has_evidence ? '已关联训练证据' : '缺少训练证据'}</p></div>
        <button className="primary" disabled={busy || !chosen.has_evidence || standardCount === 0} onClick={() => void compareAll()}>
          与 {standardCount} 个标准项目逐项对比</button></div>
        <fieldset className="result-agent-mode"><legend>分析模型接入方式</legend>
          <label><input type="radio" name="result-agent-mode" checked={agentMode === 'webcodex'}
            onChange={() => setAgentMode('webcodex')} />网页 ChatGPT + WebCodex</label>
          <label><input type="radio" name="result-agent-mode" checked={agentMode === 'cli'}
            onChange={() => setAgentMode('cli')} />Codex CLI（当前账号，点击对比后逐项运行）</label>
          <label>分析要求<textarea rows={2} maxLength={2000} value={agentInstruction}
            onChange={event => setAgentInstruction(event.target.value)} /></label>
          <p>{agentMode === 'webcodex' ? '点击对比会逐项建立请求；须在 ChatGPT 网页主动发送后才能得到模型回复。' :
            '点击对比将通过本机已登录的 Codex CLI 逐项发送受限证据摘要。'}</p></fieldset>
        {standardCount === 0 && <p className="result-guidance">当前算法下没有其他标准项目。选择项目的“设置”，将适合的项目标记为标准。</p>}
        <section className="result-pair-list" aria-label="逐项对比结果"><h3>对比结果</h3>
          {pairs.length === 0 ? <p>点击上方按钮后，每个标准项目会生成一张独立的对比卡。</p> :
            pairs.map(pair => { const reference = runs.find(run => run.run_id === pair.reference_run_id);
              const comparable = pair.comparison.comparability.status === 'matched';
              return <button className="result-pair-card" key={pair.reference_run_id} onClick={() => void openPair(pair)}>
                <span><strong>{chosen.display_name}</strong> 与 <strong>{reference?.display_name || pair.reference_run_id}</strong></span>
                <span className={comparable ? 'result-ok' : 'result-blocked'}>{comparable ? '协议可比' : '证据不足或条件不一致'}</span>
                <small>{comparable ? `成功率差值 ${pair.comparison.difference ?? '样本不足'}` :
                  pair.comparison.comparability.reasons.map(reason => reason.field).join('、')}</small>
                <small>{tickets[pair.reference_run_id]?.status === 'reply_validated' ? 'Agent 已回复' :
                  tickets[pair.reference_run_id] ? 'Agent 请求待回复' :
                  pairErrors[pair.reference_run_id] ? 'Agent 请求失败：' + pairErrors[pair.reference_run_id] : '尚未生成 Agent 请求'}</small></button>; })}
          {Object.entries(pairErrors).filter(([id]) => !pairs.some(pair => pair.reference_run_id === id)).map(([id, message]) =>
            <p role="alert" key={id}>{runs.find(run => run.run_id === id)?.display_name || id}：{message}</p>)}</section></> :
        <div className="result-empty"><h3>先选择一个待对比项目</h3><p>左侧项目可设为标准；同一算法下的标准项目会分别生成对比结果。</p></div>}
    </main></div> : <div className="result-detail"><button className="result-back" onClick={() => setActivePair(null)}>返回 {leftRun?.display_name || '项目'} 的对比结果</button>
      <header><small>{leftRun?.algorithm} / {leftRun?.protocol}</small><h3>{leftRun?.display_name} 与 {rightRun?.display_name}</h3></header>
      <div className="result-detail-grid"><aside className="result-detail-videos"><h4>步态视频</h4>
        {activePair.candidate_media.map(media => <EvidenceVideo key={`c-${media.source_sha256}`} item={media} label={leftRun?.display_name || '待分析'} />)}
        {activePair.reference_media.map(media => <EvidenceVideo key={`r-${media.source_sha256}`} item={media} label={rightRun?.display_name || '标准'} />)}
        {!activePair.candidate_media.length && !activePair.reference_media.length && <p>两个项目都没有步态视频。</p>}</aside>
        <main className="result-detail-scene"><h4>同一网格中的 URDF 模型</h4>{scenes ? <ResultCompareScene left={scenes[0]} right={scenes[1]}
          leftName={leftRun?.display_name || '待分析'} rightName={rightRun?.display_name || '标准'} /> : <p>正在读取模型资源…</p>}</main>
        <aside className="result-detail-curves"><h4>训练指标曲线</h4><div className="result-legend"><span>待分析</span><span>标准</span></div>
          {series ? metrics.map(metric => <Curve key={metric} metric={metric}
            left={series[0].series.find(item => item.metric === metric)} right={series[1].series.find(item => item.metric === metric)} />) : <p>正在读取指标…</p>}</aside></div>
      <section className="result-agent-feedback"><h4>Agent 分析反馈</h4>
        <p>可比性：{activePair.comparison.comparability.status}；统计状态：{activePair.comparison.status}；独立单位：{activePair.comparison.sampling_unit}</p>
        {activePair.fixture_only && <p role="alert">包含合成夹具，仅供流程核验，不能作为真实训练标准。</p>}
        <p>待分析均值：{activePair.comparison.candidate_mean ?? '未知'}；标准均值：{activePair.comparison.reference_mean ?? '未知'}；差值：{activePair.comparison.difference ?? '无法计算'}</p>
        <p>95% 区间：{activePair.comparison.confidence_interval_95?.join(' 至 ') || '样本不足或不可比'}</p>
        {activePair.comparison.comparability.reasons.map((reason, index) => <p role="alert" key={index}>{reason.field}：{reason.reason || '条件不同'}</p>)}
        {activeTicket?.status === 'reply_validated' && activeTicket.result?.advice ? <div className="result-agent-advice">
          <h5>模型建议（证据引用已校验）</h5><p>{activeTicket.result.advice.summary}</p>
          {activeTicket.result.advice.causes.map(cause => <article key={cause.cause_id}><strong>{cause.cause_id}</strong>
            <p>{cause.interpretation}</p><small>证据：{cause.evidence_ids.join('、') || '无'}；待补：{cause.missing_data.join('、')}</small></article>)}
          <h5>后续操作建议</h5><ul>{activeTicket.result.advice.recommendations.map((item, index) =>
            <li key={index}>{item.action} <small>来源：{item.evidence_ids.join('、') || '尚无直接证据'}</small></li>)}</ul>
        </div> : activeTicket ? <div className="result-agent-request"><p>Agent 请求 {activeTicket.request_id}：{activeTicket.status}</p>
          {activeTicket.status === 'awaiting_chatgpt_web_reply' && <button onClick={() => void openAgent()}>打开 ChatGPT 并复制此组请求</button>}
          {activeTicket.status === 'awaiting_codex_cli_run' && <button onClick={() => void retryAgent()}>重试 Codex CLI</button>}
        </div> : <p className="result-guidance">此组尚无 Agent 回复；可先查看模型、曲线及视频，随后补充独立评估证据。</p>}
        {agentNotice && <p role="status">{agentNotice}</p>}
        <p className="result-guidance">Agent 仅接收 URDF 结构摘要、指标末值、统计结论和视频元数据，不会看到原始视频画面；涉及步态外观的判断须由用户在左侧视频中复核。</p>
      </section></div>}
    <MediaEvidence />
  </div>;
}
