import { useEffect, useState } from 'react';

export type WebCodexTicket = {
  request_id: string;
  request_sha256: string;
  kind: 'diagnosis' | 'model_recipe';
  status: 'awaiting_chatgpt_web_reply' | 'awaiting_codex_cli_run' | 'reply_validated';
  request_path: string;
  result_path: string | null;
  source_current: boolean | null;
  prompt: string | null;
  result: {status: string; advice?: {
    summary: string; causes: {cause_id: string; status: string; interpretation: string;
      evidence_ids: string[]; missing_data: string[]}[];
    recommendations: {action: string; cause_id: string; evidence_ids: string[]}[];
    verification: {needs_human_review: boolean; changes_applied: boolean}};
    preview?: {proposal_id: string; expected_revision: number;
      diff: {added_parts: string[]; removed_parts: string[]; changed_parts: string[]};
      report: {parts: {name: string; mass_kg: number}[]}};
    suggestion?: {recipe: import('./ModelingWorkspace').ModelRecipe; rationale: string}} | null;
};

export function WebCodexAgentSidebar({desktopAvailable,importedOperationId}: {desktopAvailable: boolean; importedOperationId: string | null}) {
  const [mode,setMode]=useState<'webcodex'|'cli'>('webcodex');
  const [instruction,setInstruction]=useState('对照 D03 合成证据，解释四足控制器与机械设计的竞争性原因，列出复验步骤');
  const [ticket,setTicket]=useState<WebCodexTicket|null>(null);
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState('');
  useEffect(() => {
    if (!ticket || ticket.status !== 'awaiting_chatgpt_web_reply' || !window.urdftools) return;
    const requestId=ticket.request_id;
    const timer=window.setInterval(() => {
      void window.urdftools?.webcodexStatus(requestId).then(next => {
        if (next.status === 'reply_validated') setTicket(current =>
          current?.request_id === requestId ? next : current);
      }).catch(() => { /* explicit check button displays errors */ });
    }, 3000);
    return () => window.clearInterval(timer);
  }, [ticket?.request_id,ticket?.status]);
  async function start() {
    if (!window.urdftools) return;
    setBusy(true);setNotice('');
    try { const created=importedOperationId ?
      await window.urdftools.webcodexCreateImportedAnalysis(importedOperationId,instruction,mode) :
      await window.urdftools.webcodexCreateAnalysis(instruction,mode);
      setTicket(created);
      if (mode==='cli') setTicket(await window.urdftools.agentCliRun(created.request_id)); }
    catch(error) {setNotice(String(error));}
    finally {setBusy(false);}
  }
  async function refresh() {
    if (!ticket || !window.urdftools) return;
    setBusy(true);
    try {setTicket(await window.urdftools.webcodexStatus(ticket.request_id));}
    catch(error) {setNotice(String(error));}
    finally {setBusy(false);}
  }
  async function copy() {
    if (!ticket?.prompt || !window.urdftools) return;
    try {await window.urdftools.webcodexCopyPrompt(ticket.prompt);
      setNotice('已复制。请粘贴到已连接 WebCodex 的 ChatGPT 网页对话并发送。');}
    catch(error) {setNotice(String(error));}
  }
  async function openChat() {
    if (!ticket || !window.urdftools) return;
    try {await window.urdftools.webcodexOpen(ticket.request_id);
      setNotice('已打开 ChatGPT 并复制请求。请在网页对话粘贴并发送；回复会自动显示在这里。');}
    catch(error) {setNotice(String(error));}
  }
  return <section aria-label="WebCodex Agent 助手">
    <h2>URDFTools Agent</h2>
    <fieldset><legend>模型接入方式</legend>
      <label><input type="radio" name="analysis-agent-mode" value="webcodex" checked={mode==='webcodex'}
        onChange={()=>{setMode('webcodex');setTicket(null);setNotice('');}} />网页 ChatGPT + WebCodex</label>
      <label><input type="radio" name="analysis-agent-mode" value="cli" checked={mode==='cli'}
        onChange={()=>{setMode('cli');setTicket(null);setNotice('');}} />Codex CLI（当前账号）</label>
    </fieldset>
    <p>{mode==='webcodex' ? '桌面端创建请求并打开 ChatGPT；在网页会话粘贴发送后，建议自动回显。' :
      '点击运行后使用本机已登录的 Codex CLI 发送受限诊断摘要；不使用额外付费 API。'}</p>
    <p>{importedOperationId ? '当前导入的 URDF 将在本地执行静态检查，只向网页模型发送来源哈希、规则、Link/Joint 位置和数值摘要，不发送原始 URDF 或网格。静态告警不等于机器人真实性能。' : <>尚未选择导入机器人，当前入口仅使用项目自带 <strong>synthetic_fixture 合成案例</strong>；请先在“查看”导入模型以分析自己的 URDF。</>} 建模页面可针对当前 CAD 配方发起独立请求。</p>
    <label>分析任务<textarea aria-label="WebCodex 分析任务" rows={3} maxLength={2000}
      value={instruction} onChange={event=>setInstruction(event.target.value)} /></label>
    <button disabled={!desktopAvailable || busy || !instruction.trim()} onClick={()=>void start()}>
      {mode==='cli' ? '运行 Codex CLI 分析' : importedOperationId ? '分析当前导入 URDF（WebCodex）' : '创建网页 ChatGPT 分析请求'}
    </button>
    {ticket && <div data-webcodex-status={ticket.status}>
      <p>请求：<code>{ticket.request_id}</code></p>
      <p>{ticket.status === 'reply_validated' ? '建议已通过本地证据校验，仍需人工复核' :
        mode==='cli' ? 'CLI 未完成；可再次运行，失败不会生成假回复' : '等候网页 ChatGPT 会话提交回复'}</p>
      {ticket.source_current===false && <p role="alert">源 URDF 或 D02 报告自请求发起后已发生变化。此结果仅针对历史快照；请对当前模型创建新请求。</p>}
      {mode==='webcodex' && ticket.prompt && <>
        <button disabled={busy} onClick={()=>void openChat()}>打开 ChatGPT 并复制请求</button>
        <button disabled={busy} onClick={()=>void copy()}>复制 WebCodex 对话提示</button>
        <details><summary>查看需在 ChatGPT 网页发送的提示</summary>
          <textarea readOnly rows={6} value={ticket.prompt} aria-label="WebCodex handoff prompt" /></details>
      </>}
      {mode==='cli' && ticket.status!=='reply_validated' &&
        <button disabled={busy} onClick={()=>{setBusy(true);setNotice('');
          void window.urdftools?.agentCliRun(ticket.request_id).then(setTicket)
            .catch(error=>setNotice(String(error))).finally(()=>setBusy(false));}}>重试 Codex CLI</button>}
      <button disabled={busy} onClick={()=>void refresh()}>立即检查网页回复</button>
      {ticket.result?.advice && <div>
        <p>{ticket.result.advice.summary}</p>
        {ticket.result.advice.causes.map(c=><p key={c.cause_id}>
          <strong>{c.cause_id}</strong> · {c.status}：{c.interpretation}（证据：{c.evidence_ids.join(', ') || '缺失'}）</p>)}
        {ticket.result.advice.recommendations.map((r,i)=><p key={i}>
          待审建议：{r.action} · 引用 {r.evidence_ids.join(', ') || '无'}</p>)}
        <p>仅建议，不自动修改：{ticket.result.advice.verification.changes_applied ? '异常' : '确认'}</p>
      </div>}
    </div>}
    {notice && <p role="status">{notice}</p>}
    {!desktopAvailable && <p>请启动 URDFTools Electron 桌面版使用此功能。</p>}
  </section>;
}
